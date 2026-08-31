"""
Semantic Coherence Layer (PHASE 13 - Truth Dynamics)

Implements "Wahrheit als stabile Kohärenz" - truth as semantic stability
across brain responses.

Key concepts:
1. Semantic Embeddings: Convert brain answers to vector space
2. Coherence Measure K: Average pairwise similarity (0-1)
3. Disagreement U: Variance of similarities
4. Truth Stability: K × voting_score
5. Meta-level validation: Pattern analysis over time

Mathematical foundation:
    K = (2 / n(n-1)) × Σ sim(E_i, E_j)  for i < j
    U = Var({sim_ij})
    final_score = α × voting_score + (1-α) × K

Thresholds:
    K ≥ 0.82: GREEN (high truth stability, deploy)
    0.72 ≤ K < 0.82: YELLOW (review needed)
    K < 0.72: RED (clarification required)

Based on philosophical framework:
- Coherence Theory of Truth (Rescher, 1973)
- Gödel's incompleteness → meta-level validation
- Semantic convergence as truth indicator
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib


@dataclass
class BrainAnswer:
    """
    Answer from a single brain with semantic embedding
    """
    brain_id: str
    text: str
    confidence: float
    domain: str

    # Semantic representation
    embedding: Optional[np.ndarray] = None

    # Context
    decision_type: Optional[str] = None  # suggest, retry, wait, terminate
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'brain_id': self.brain_id,
            'text': self.text,
            'confidence': self.confidence,
            'domain': self.domain,
            'decision_type': self.decision_type,
            'has_embedding': self.embedding is not None
        }


@dataclass
class SemanticConsensus:
    """
    Consensus with semantic coherence metrics
    """
    decision_id: str
    task_description: str

    # Traditional voting
    decision: str
    voting_score: float
    mechanism: str  # majority, weighted, expert, fallback

    # Semantic coherence (NEW)
    coherence_K: float = 0.5  # Average pairwise similarity
    disagreement_U: float = 0.5  # Variance of similarities
    truth_stability: float = 0.5  # Final score: K × voting_score

    # Flags
    low_coherence_flag: bool = False
    needs_clarification: bool = False
    hysteresis_count: int = 0  # Consecutive times K ≥ K_min

    # Participating brains
    brain_answers: List[BrainAnswer] = field(default_factory=list)
    participating_brains: List[str] = field(default_factory=list)

    # Similarity matrix
    similarity_matrix: Optional[np.ndarray] = None

    def get_status_color(self, green_threshold: float = 0.82, yellow_threshold: float = 0.72) -> str:
        """Get traffic light status"""
        if self.truth_stability >= green_threshold:
            return "GREEN"
        elif self.truth_stability >= yellow_threshold:
            return "YELLOW"
        else:
            return "RED"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'decision_id': self.decision_id,
            'task_description': self.task_description,
            'decision': self.decision,
            'voting_score': self.voting_score,
            'mechanism': self.mechanism,
            'coherence_K': self.coherence_K,
            'disagreement_U': self.disagreement_U,
            'truth_stability': self.truth_stability,
            'status': self.get_status_color(),
            'low_coherence_flag': self.low_coherence_flag,
            'needs_clarification': self.needs_clarification,
            'participating_brains': len(self.participating_brains)
        }


class SemanticEncoder:
    """
    Semantic encoder for brain answers

    Uses simple TF-IDF + cosine similarity for baseline.
    Can be replaced with neural embeddings (sentence-transformers, etc.)
    """

    def __init__(self, use_simple: bool = True):
        """
        Initialize encoder

        Args:
            use_simple: Use simple TF-IDF (True) or neural embeddings (False)
        """
        self.use_simple = use_simple
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.corpus_size = 0

        # For neural embeddings (optional)
        self.neural_model = None

        if not use_simple:
            try:
                from sentence_transformers import SentenceTransformer
                self.neural_model = SentenceTransformer('all-MiniLM-L6-v2')
                print("[+] Neural embeddings loaded (sentence-transformers)")
            except ImportError:
                print("[!] sentence-transformers not available, falling back to TF-IDF")
                self.use_simple = True

    def encode(self, text: str) -> np.ndarray:
        """
        Encode text to embedding vector

        Args:
            text: Input text

        Returns:
            Embedding vector (normalized)
        """
        if not self.use_simple and self.neural_model is not None:
            # Neural embeddings
            embedding = self.neural_model.encode(text, normalize_embeddings=True)
            return embedding
        else:
            # Simple TF-IDF
            return self._tfidf_encode(text)

    def _tfidf_encode(self, text: str) -> np.ndarray:
        """
        Simple TF-IDF encoding

        Note: Returns fixed-size vector using hash-based dimensionality
        to avoid shape mismatches when vocabulary grows
        """
        # Use fixed vocabulary size with hashing
        vocab_size = 128  # Fixed size

        # Tokenize
        tokens = text.lower().split()

        # Create vector using hash-based indexing
        vector = np.zeros(vocab_size)

        # Term frequency with hash function
        for token in tokens:
            # Simple hash to fixed range
            token_hash = abs(hash(token)) % vocab_size
            vector[token_hash] += 1.0

        # Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def update_idf(self, corpus: List[str]):
        """Update IDF weights from corpus"""
        self.corpus_size = len(corpus)

        # Count document frequencies
        df = defaultdict(int)
        for doc in corpus:
            tokens = set(doc.lower().split())
            for token in tokens:
                df[token] += 1

        # Compute IDF
        for token, freq in df.items():
            self.idf[token] = np.log((self.corpus_size + 1) / (freq + 1)) + 1.0


class SemanticCoherenceLayer:
    """
    Semantic Coherence Layer for Multi-Brain Swarm

    Measures semantic convergence across brain answers and computes
    truth stability as coherent consensus.
    """

    def __init__(
        self,
        encoder: Optional[SemanticEncoder] = None,
        k_min: float = 0.55,  # Adjusted for neural embeddings (was 0.72)
        green_threshold: float = 0.75,  # Adjusted for neural embeddings (was 0.82)
        alpha: float = 0.5,
        hysteresis_rounds: int = 2
    ):
        """
        Initialize semantic coherence layer

        Args:
            encoder: Semantic encoder (creates default if None)
            k_min: Minimum coherence threshold (RED below this)
            green_threshold: GREEN status threshold
            alpha: Weight for voting_score vs K (0=pure K, 1=pure voting)
            hysteresis_rounds: Consecutive rounds above k_min for stability
        """
        self.encoder = encoder or SemanticEncoder(use_simple=True)
        self.k_min = k_min
        self.green_threshold = green_threshold
        self.alpha = alpha
        self.hysteresis_rounds = hysteresis_rounds

        # History for meta-level analysis
        self.consensus_history: List[SemanticConsensus] = []

        # Statistics
        self.total_decisions = 0
        self.green_count = 0
        self.yellow_count = 0
        self.red_count = 0

    def compute_coherence(
        self,
        brain_answers: List[BrainAnswer]
    ) -> Tuple[float, float, np.ndarray]:
        """
        Compute semantic coherence across brain answers

        Args:
            brain_answers: List of brain answers with embeddings

        Returns:
            (K, U, similarity_matrix)
            K: Average pairwise similarity (0-1)
            U: Variance of similarities
            similarity_matrix: n×n matrix of pairwise similarities
        """
        n = len(brain_answers)

        if n < 2:
            # Single answer → perfect coherence
            return 1.0, 0.0, np.ones((1, 1))

        # Ensure embeddings exist
        for answer in brain_answers:
            if answer.embedding is None:
                answer.embedding = self.encoder.encode(answer.text)

        # Compute pairwise similarities
        similarities = []
        sim_matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(i + 1, n):
                # Cosine similarity
                sim = self._cosine_similarity(
                    brain_answers[i].embedding,
                    brain_answers[j].embedding
                )
                similarities.append(sim)
                sim_matrix[i, j] = sim
                sim_matrix[j, i] = sim

        # Diagonal is 1.0 (self-similarity)
        np.fill_diagonal(sim_matrix, 1.0)

        # Compute K (average pairwise similarity)
        K = np.mean(similarities) if similarities else 0.0

        # Compute U (variance)
        U = np.var(similarities) if len(similarities) >= 2 else 0.0

        return K, U, sim_matrix

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors"""
        # Handle zero vectors
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # Cosine similarity
        sim = np.dot(vec1, vec2) / (norm1 * norm2)

        # Clip to [0, 1] (should already be in [-1, 1])
        sim = np.clip(sim, -1.0, 1.0)

        # Map to [0, 1] for convenience
        sim = (sim + 1.0) / 2.0

        return sim

    def compute_truth_stability(
        self,
        voting_score: float,
        coherence_K: float
    ) -> float:
        """
        Compute final truth stability score

        Args:
            voting_score: Score from voting mechanism (0-1)
            coherence_K: Semantic coherence (0-1)

        Returns:
            Truth stability: α × voting_score + (1-α) × K
        """
        return self.alpha * voting_score + (1 - self.alpha) * coherence_K

    def create_semantic_consensus(
        self,
        task_description: str,
        brain_answers: List[BrainAnswer],
        decision: str,
        voting_score: float,
        mechanism: str,
        previous_consensus: Optional[SemanticConsensus] = None
    ) -> SemanticConsensus:
        """
        Create semantic consensus from brain answers

        Args:
            task_description: Task description
            brain_answers: List of brain answers
            decision: Chosen decision (suggest, retry, etc.)
            voting_score: Score from voting mechanism
            mechanism: Consensus mechanism used
            previous_consensus: Previous consensus for hysteresis

        Returns:
            Semantic consensus with coherence metrics
        """
        # Generate decision ID
        decision_id = hashlib.md5(task_description.encode()).hexdigest()[:8]

        # Compute semantic coherence
        K, U, sim_matrix = self.compute_coherence(brain_answers)

        # Compute truth stability
        truth_stability = self.compute_truth_stability(voting_score, K)

        # Check hysteresis
        hysteresis_count = 0
        if previous_consensus is not None:
            if K >= self.k_min:
                hysteresis_count = previous_consensus.hysteresis_count + 1
        else:
            hysteresis_count = 1 if K >= self.k_min else 0

        # Flags
        low_coherence_flag = K < self.k_min
        needs_clarification = (
            low_coherence_flag and
            hysteresis_count < self.hysteresis_rounds
        )

        # Create consensus
        consensus = SemanticConsensus(
            decision_id=decision_id,
            task_description=task_description,
            decision=decision,
            voting_score=voting_score,
            mechanism=mechanism,
            coherence_K=K,
            disagreement_U=U,
            truth_stability=truth_stability,
            low_coherence_flag=low_coherence_flag,
            needs_clarification=needs_clarification,
            hysteresis_count=hysteresis_count,
            brain_answers=brain_answers,
            participating_brains=[a.brain_id for a in brain_answers],
            similarity_matrix=sim_matrix
        )

        # Update statistics
        self.consensus_history.append(consensus)
        self.total_decisions += 1

        status = consensus.get_status_color(self.green_threshold, self.k_min)
        if status == "GREEN":
            self.green_count += 1
        elif status == "YELLOW":
            self.yellow_count += 1
        else:
            self.red_count += 1

        return consensus

    def get_statistics(self) -> Dict:
        """Get semantic coherence statistics"""
        if not self.consensus_history:
            return {
                'total_decisions': 0,
                'avg_coherence_K': 0.0,
                'avg_disagreement_U': 0.0,
                'avg_truth_stability': 0.0,
                'green_rate': 0.0,
                'yellow_rate': 0.0,
                'red_rate': 0.0
            }

        avg_K = np.mean([c.coherence_K for c in self.consensus_history])
        avg_U = np.mean([c.disagreement_U for c in self.consensus_history])
        avg_truth = np.mean([c.truth_stability for c in self.consensus_history])

        return {
            'total_decisions': self.total_decisions,
            'avg_coherence_K': avg_K,
            'avg_disagreement_U': avg_U,
            'avg_truth_stability': avg_truth,
            'green_rate': self.green_count / self.total_decisions,
            'yellow_rate': self.yellow_count / self.total_decisions,
            'red_rate': self.red_count / self.total_decisions,
            'k_min': self.k_min,
            'green_threshold': self.green_threshold,
            'alpha': self.alpha
        }

    def __repr__(self):
        return (
            f"SemanticCoherenceLayer("
            f"decisions={self.total_decisions}, "
            f"K_min={self.k_min}, "
            f"GREEN={self.green_threshold})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("SEMANTIC COHERENCE LAYER (PHASE 13 - Truth Dynamics)")
    print("=" * 70)
    print()
    print("Implements 'Wahrheit als stabile Kohärenz' framework:")
    print("  1. Semantic embeddings for brain answers")
    print("  2. Coherence measure K (average pairwise similarity)")
    print("  3. Disagreement U (variance of similarities)")
    print("  4. Truth stability = α × voting_score + (1-α) × K")
    print("  5. Traffic light system (GREEN/YELLOW/RED)")
    print()
    print("Mathematical foundation:")
    print("  K = (2 / n(n-1)) × Σ sim(E_i, E_j)  for i < j")
    print("  U = Var({sim_ij})")
    print()
    print("Thresholds:")
    print("  K ≥ 0.82: GREEN (deploy)")
    print("  0.72 ≤ K < 0.82: YELLOW (review)")
    print("  K < 0.72: RED (clarification)")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_semantic_coherence.py")
    print()
    print("=" * 70)
