"""
ConnectionEvaluator - Scores connections using embedding similarity + LLM reasoning.

Combines VibeMind's EmbeddingService with LLM-based reasoning to
evaluate the quality of discovered idea connections.
"""

from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

from .idea_node import IdeaNode, ConnectionType
from llm_config import get_model

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of evaluating a potential connection."""
    embedding_similarity: float
    llm_confidence: float
    combined_score: float
    connection_type: ConnectionType
    reasoning: str
    edge_label: str
    is_valid: bool
    metadata: Dict[str, Any]


class ConnectionEvaluator:
    """
    Evaluates potential connections between ideas using multiple signals:
    1. Embedding similarity (fast, from EmbeddingService)
    2. LLM confidence (deep reasoning about why they connect)
    """

    # Weights for combining scores
    DEFAULT_EMBEDDING_WEIGHT = 0.4
    DEFAULT_LLM_WEIGHT = 0.6

    # Thresholds
    MIN_EMBEDDING_SIMILARITY = 0.3  # Below this, skip LLM evaluation
    MIN_COMBINED_SCORE = 0.4        # Below this, connection is invalid

    def __init__(
        self,
        embedding_service=None,
        llm_client=None,
        embedding_weight: float = DEFAULT_EMBEDDING_WEIGHT,
        llm_weight: float = DEFAULT_LLM_WEIGHT,
    ):
        """
        Initialize the evaluator.

        Args:
            embedding_service: VibeMind's EmbeddingService instance
            llm_client: LLM client for reasoning (OpenAI/Anthropic compatible)
            embedding_weight: Weight for embedding similarity (default 0.4)
            llm_weight: Weight for LLM confidence (default 0.6)
        """
        self.embedding_service = embedding_service
        self.llm_client = llm_client
        self.embedding_weight = embedding_weight
        self.llm_weight = llm_weight

    def set_embedding_service(self, service):
        """Set the embedding service (for lazy initialization)."""
        self.embedding_service = service

    def set_llm_client(self, client):
        """Set the LLM client (for lazy initialization)."""
        self.llm_client = client

    async def evaluate_connection(
        self,
        source_bubble: Dict[str, Any],
        target_bubble: Dict[str, Any],
        context: Optional[str] = None,
        use_llm: bool = True,
    ) -> EvaluationResult:
        """
        Evaluate a potential connection between two bubbles.

        Args:
            source_bubble: Source bubble dict with 'id', 'title', 'description', 'embedding_vector'
            target_bubble: Target bubble dict with same fields
            context: Optional context about what kind of connections to find
            use_llm: Whether to use LLM for deep evaluation (slower but better)

        Returns:
            EvaluationResult with scores and reasoning
        """
        logger.debug("evaluate_connection: source=%s, target=%s, use_llm=%s",
                     source_bubble.get("title"), target_bubble.get("title"), use_llm)
        # Step 1: Calculate embedding similarity
        embedding_similarity = self._calculate_embedding_similarity(
            source_bubble, target_bubble
        )

        # Early exit if similarity too low
        if embedding_similarity < self.MIN_EMBEDDING_SIMILARITY and not use_llm:
            return EvaluationResult(
                embedding_similarity=embedding_similarity,
                llm_confidence=0.0,
                combined_score=embedding_similarity * self.embedding_weight,
                connection_type=ConnectionType.SEMANTIC,
                reasoning="",
                edge_label="",
                is_valid=False,
                metadata={"skipped_llm": True, "reason": "low_similarity"},
            )

        # Step 2: LLM evaluation (if enabled)
        llm_confidence = 0.0
        connection_type = ConnectionType.SEMANTIC
        reasoning = ""
        edge_label = ""

        if use_llm and self.llm_client:
            llm_result = await self._evaluate_with_llm(
                source_bubble, target_bubble, context
            )
            llm_confidence = llm_result.get("confidence", 0.0)
            connection_type = ConnectionType(llm_result.get("connection_type", "semantic"))
            reasoning = llm_result.get("reasoning", "")
            edge_label = llm_result.get("edge_label", "")
        else:
            # Generate basic edge label from embedding similarity
            edge_label = self._generate_basic_label(source_bubble, target_bubble)

        # Step 3: Calculate combined score
        # When LLM is not used, use embedding similarity directly
        # (otherwise max score would be 0.4, which barely meets threshold)
        if not use_llm or not self.llm_client:
            combined_score = embedding_similarity  # Full weight to embedding
        else:
            combined_score = (
                self.embedding_weight * embedding_similarity +
                self.llm_weight * llm_confidence
            )

        # Determine validity
        is_valid = combined_score >= self.MIN_COMBINED_SCORE

        return EvaluationResult(
            embedding_similarity=embedding_similarity,
            llm_confidence=llm_confidence,
            combined_score=combined_score,
            connection_type=connection_type,
            reasoning=reasoning,
            edge_label=edge_label,
            is_valid=is_valid,
            metadata={
                "source_id": source_bubble.get("id"),
                "target_id": target_bubble.get("id"),
                "used_llm": use_llm and self.llm_client is not None,
            },
        )

    def _calculate_embedding_similarity(
        self,
        source_bubble: Dict[str, Any],
        target_bubble: Dict[str, Any],
    ) -> float:
        """Calculate cosine similarity between bubble embeddings."""
        if not self.embedding_service:
            logger.warning("No embedding service available")
            return 0.0

        source_vec = source_bubble.get("embedding_vector")
        target_vec = target_bubble.get("embedding_vector")

        # Generate embeddings if not present
        if source_vec is None:
            text = f"{source_bubble.get('title', '')} {source_bubble.get('description', '')}"
            source_vec = self.embedding_service.embed(text)

        if target_vec is None:
            text = f"{target_bubble.get('title', '')} {target_bubble.get('description', '')}"
            target_vec = self.embedding_service.embed(text)

        if source_vec is None or target_vec is None:
            return 0.0

        return self.embedding_service.similarity(source_vec, target_vec)

    async def _evaluate_with_llm(
        self,
        source_bubble: Dict[str, Any],
        target_bubble: Dict[str, Any],
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Use LLM to evaluate connection quality and generate reasoning.

        Returns dict with:
        - confidence: 0.0-1.0
        - connection_type: one of ConnectionType values
        - reasoning: explanation of the connection
        - edge_label: short label for visualization
        """
        prompt = self._build_evaluation_prompt(source_bubble, target_bubble, context)

        try:
            # Call LLM (assuming OpenAI-compatible client)
            response = await self._call_llm(prompt)
            return self._parse_llm_response(response)
        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            return {
                "confidence": 0.0,
                "connection_type": "semantic",
                "reasoning": "",
                "edge_label": "",
            }

    def _build_evaluation_prompt(
        self,
        source_bubble: Dict[str, Any],
        target_bubble: Dict[str, Any],
        context: Optional[str] = None,
    ) -> str:
        """Build the prompt for LLM evaluation."""
        context_text = f"\nKontext: {context}" if context else ""

        return f"""Analysiere die Verbindung zwischen diesen zwei Ideen:

IDEE 1: {source_bubble.get('title', 'Unbekannt')}
Beschreibung: {source_bubble.get('description', 'Keine Beschreibung')}

IDEE 2: {target_bubble.get('title', 'Unbekannt')}
Beschreibung: {target_bubble.get('description', 'Keine Beschreibung')}
{context_text}

Bewerte die Verbindung zwischen diesen Ideen:

1. CONFIDENCE (0.0-1.0): Wie stark ist die Verbindung?
2. CONNECTION_TYPE: Welche Art von Verbindung?
   - semantic: Ähnlicher Inhalt/Bedeutung
   - causal: Eine führt zur anderen
   - temporal: Zeitliche Beziehung
   - hierarchical: Teil-Ganzes Beziehung
   - contrast: Gegensätze/Kontrast
   - creative: Neuartige/unerwartete Verbindung
   - dependency: Eine hängt von der anderen ab
   - elaboration: Eine erweitert die andere

3. EDGE_LABEL: Kurzes Label (2-4 Wörter) für die Visualisierung
4. REASONING: Kurze Erklärung (1-2 Sätze) warum sie verbunden sind

Antworte im Format:
CONFIDENCE: [Zahl]
CONNECTION_TYPE: [Typ]
EDGE_LABEL: [Label]
REASONING: [Erklärung]"""

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the given prompt."""
        if not self.llm_client:
            return ""

        # Support different LLM client interfaces
        try:
            # OpenAI-style client
            if hasattr(self.llm_client, 'chat'):
                response = await self.llm_client.chat.completions.create(
                    model=get_model("connection_eval"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=300,
                )
                return response.choices[0].message.content

            # Direct completion style
            elif hasattr(self.llm_client, 'complete'):
                response = await self.llm_client.complete(prompt)
                return response

            # Fallback: assume it's callable
            else:
                response = await self.llm_client(prompt)
                return str(response)

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse structured response from LLM."""
        result = {
            "confidence": 0.5,
            "connection_type": "semantic",
            "reasoning": "",
            "edge_label": "",
        }

        if not response:
            return result

        lines = response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('CONFIDENCE:'):
                try:
                    val = line.split(':', 1)[1].strip()
                    result["confidence"] = float(val)
                except (ValueError, IndexError):
                    pass
            elif line.startswith('CONNECTION_TYPE:'):
                try:
                    val = line.split(':', 1)[1].strip().lower()
                    if val in [t.value for t in ConnectionType]:
                        result["connection_type"] = val
                except IndexError:
                    pass
            elif line.startswith('EDGE_LABEL:'):
                try:
                    result["edge_label"] = line.split(':', 1)[1].strip()
                except IndexError:
                    pass
            elif line.startswith('REASONING:'):
                try:
                    result["reasoning"] = line.split(':', 1)[1].strip()
                except IndexError:
                    pass

        return result

    def _generate_basic_label(
        self,
        source_bubble: Dict[str, Any],
        target_bubble: Dict[str, Any],
    ) -> str:
        """Generate a basic edge label without LLM."""
        # Find common words between titles
        source_words = set(source_bubble.get('title', '').lower().split())
        target_words = set(target_bubble.get('title', '').lower().split())
        common = source_words & target_words

        # Remove stop words
        stop_words = {'der', 'die', 'das', 'und', 'in', 'von', 'mit', 'für',
                     'the', 'a', 'an', 'and', 'in', 'of', 'with', 'for'}
        common = common - stop_words

        if common:
            return ' '.join(list(common)[:2])
        return "verbunden"

    # ---- Batch Evaluation ----

    async def evaluate_candidates(
        self,
        source_bubble: Dict[str, Any],
        candidate_bubbles: List[Dict[str, Any]],
        top_k: int = 5,
        context: Optional[str] = None,
        use_llm_for_top: int = 3,
    ) -> List[Tuple[Dict[str, Any], EvaluationResult]]:
        """
        Evaluate multiple candidate connections efficiently.

        Uses embedding similarity for initial ranking, then LLM
        evaluation only for the top candidates.

        Args:
            source_bubble: The source bubble
            candidate_bubbles: List of candidate target bubbles
            top_k: Number of results to return
            context: Optional context
            use_llm_for_top: Number of top candidates to evaluate with LLM

        Returns:
            List of (bubble, evaluation_result) tuples sorted by score
        """
        logger.debug("evaluate_candidates: source=%s, candidates=%s, top_k=%s",
                     source_bubble.get("title"), len(candidate_bubbles), top_k)
        # Step 1: Calculate embedding similarities for all candidates
        similarities = []
        for candidate in candidate_bubbles:
            sim = self._calculate_embedding_similarity(source_bubble, candidate)
            similarities.append((candidate, sim))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Step 2: Evaluate top candidates with LLM
        results = []
        for i, (candidate, sim) in enumerate(similarities[:top_k]):
            use_llm = i < use_llm_for_top
            eval_result = await self.evaluate_connection(
                source_bubble, candidate, context, use_llm=use_llm
            )
            results.append((candidate, eval_result))

        # Sort by combined score
        results.sort(key=lambda x: x[1].combined_score, reverse=True)
        return results
