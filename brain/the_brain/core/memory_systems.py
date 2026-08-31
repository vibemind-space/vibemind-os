"""
Memory Systems for Tahlamus - Brain-Inspired Memory Architecture

Implements two types of memory inspired by neuroscience:

1. WorkingMemory: Short-term buffer (capacity ~10 items)
   - Stores recent task-decision pairs
   - Fast similarity-based retrieval
   - Used for immediate context

2. EpisodicMemory: Long-term experience storage
   - Rich contextual details
   - Importance weighting
   - Emotional valence
   - Used for learning patterns over time

These memory systems enhance decision making by providing:
- Context from recent tasks
- Similar past experiences
- Learned patterns and outcomes
"""

import numpy as np
from collections import deque
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from pathlib import Path


@dataclass
class WorkingMemoryEntry:
    """
    Single entry in working memory

    Stores minimal information for fast retrieval
    """
    task: str
    task_type: str
    decision: str
    confidence: float
    outcome: Optional[str]  # 'success', 'failure', None (unknown)
    brain_gates: np.ndarray  # Gate activations at decision time
    timestamp: str

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        d = asdict(self)
        d['brain_gates'] = d['brain_gates'].tolist() if hasattr(d['brain_gates'], 'tolist') else list(d['brain_gates'])
        return d


@dataclass
class EpisodicMemoryEntry:
    """
    Rich episodic memory with full context

    Like human episodic memory - remembers specific experiences
    with rich detail and emotional context
    """
    # Core information
    task: str
    task_type: str
    decision: str
    confidence: float
    outcome: str

    # Rich context
    brain_gates: np.ndarray
    layer1_features: Dict[str, float]
    layer2_sequence: List[str]
    reasoning_chain: List[str]

    # Memory metadata
    timestamp: str
    importance: float  # 0-1, how important is this memory?
    emotional_valence: str  # 'positive', 'negative', 'neutral'
    retrieval_count: int  # How many times retrieved

    # Learning signals
    prediction_error: float  # How surprising was the outcome?
    execution_time_ms: Optional[float]
    user_rating: Optional[float]

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        d = asdict(self)
        d['brain_gates'] = d['brain_gates'].tolist() if hasattr(d['brain_gates'], 'tolist') else list(d['brain_gates'])
        return d


class WorkingMemory:
    """
    Short-term working memory buffer

    Like human working memory:
    - Limited capacity (~7-10 items)
    - Fast access
    - Provides immediate context
    - Similarity-based retrieval
    """

    def __init__(self, capacity: int = 10):
        """
        Initialize working memory

        Args:
            capacity: Maximum number of items to store
        """
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)

    def add(self, entry: WorkingMemoryEntry):
        """
        Add entry to working memory

        Automatically evicts oldest if at capacity
        """
        self.buffer.append(entry)

    def get_recent(self, n: int = 5) -> List[WorkingMemoryEntry]:
        """
        Get N most recent entries

        Args:
            n: Number of entries to retrieve

        Returns:
            List of recent entries (most recent first)
        """
        return list(reversed(list(self.buffer)))[:n]

    def retrieve_similar(
        self,
        current_task: str,
        current_brain_gates: np.ndarray,
        top_k: int = 3,
        gate_weight: float = 0.7
    ) -> List[Tuple[WorkingMemoryEntry, float]]:
        """
        Retrieve similar past tasks based on:
        1. Brain gate similarity (cosine similarity)
        2. Task string similarity (simple heuristic)

        Args:
            current_task: Current task description
            current_brain_gates: Current brain gate activations
            top_k: Number of similar entries to return
            gate_weight: Weight for gate similarity (vs text similarity)

        Returns:
            List of (entry, similarity_score) tuples, sorted by similarity
        """
        if len(self.buffer) == 0:
            return []

        similarities = []

        for entry in self.buffer:
            # 1. Brain gate similarity (cosine similarity)
            gate_sim = self._cosine_similarity(
                current_brain_gates,
                entry.brain_gates
            )

            # 2. Task text similarity (simple word overlap)
            text_sim = self._text_similarity(current_task, entry.task)

            # Combined similarity
            combined_sim = gate_weight * gate_sim + (1 - gate_weight) * text_sim

            similarities.append((entry, combined_sim))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]

    def get_decision_patterns(self) -> Dict[str, float]:
        """
        Analyze recent decision patterns

        Returns:
            Dictionary of decision -> frequency
        """
        if len(self.buffer) == 0:
            return {}

        decisions = [entry.decision for entry in self.buffer]
        unique_decisions = set(decisions)

        patterns = {}
        for decision in unique_decisions:
            count = decisions.count(decision)
            patterns[decision] = count / len(decisions)

        return patterns

    def get_success_rate(self, last_n: Optional[int] = None) -> float:
        """
        Calculate success rate for recent tasks

        Args:
            last_n: Number of recent tasks to consider (None = all)

        Returns:
            Success rate (0-1)
        """
        entries = list(self.buffer) if last_n is None else list(self.buffer)[-last_n:]

        if not entries:
            return 0.5  # Default

        # Count successes
        outcomes = [e.outcome for e in entries if e.outcome is not None]
        if not outcomes:
            return 0.5

        successes = outcomes.count('success')
        return successes / len(outcomes)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors"""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def _text_similarity(text1: str, text2: str) -> float:
        """Simple word overlap similarity"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        total = len(words1 | words2)

        return overlap / total if total > 0 else 0.0

    def clear(self):
        """Clear working memory"""
        self.buffer.clear()

    def __len__(self):
        return len(self.buffer)

    def __repr__(self):
        return f"WorkingMemory(capacity={self.capacity}, current={len(self.buffer)})"


class EpisodicMemory:
    """
    Long-term episodic memory storage

    Like human episodic memory:
    - Stores specific experiences with rich detail
    - Importance-based retention
    - Emotional context
    - Retrieved based on relevance
    """

    def __init__(self, max_size: int = 1000, save_dir: Optional[str] = None):
        """
        Initialize episodic memory

        Args:
            max_size: Maximum number of episodes to store
            save_dir: Directory to save memories (None = no persistence)
        """
        self.max_size = max_size
        self.save_dir = Path(save_dir) if save_dir else None
        self.memories: List[EpisodicMemoryEntry] = []

        if self.save_dir:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            self._load_memories()

    def add(self, entry: EpisodicMemoryEntry):
        """
        Add episodic memory

        If at capacity, evicts least important memory
        """
        self.memories.append(entry)

        # If over capacity, remove least important
        if len(self.memories) > self.max_size:
            self._evict_least_important()

        # Save if persistence enabled
        if self.save_dir:
            self._save_memory(entry)

    def retrieve_similar(
        self,
        current_task: str,
        current_brain_gates: np.ndarray,
        current_task_type: str,
        top_k: int = 5,
        min_importance: float = 0.3
    ) -> List[Tuple[EpisodicMemoryEntry, float]]:
        """
        Retrieve similar episodic memories

        Combines multiple similarity signals:
        1. Brain gate similarity
        2. Task type match
        3. Importance weighting
        4. Recency

        Args:
            current_task: Current task description
            current_brain_gates: Current brain gates
            current_task_type: Current task type
            top_k: Number of memories to retrieve
            min_importance: Minimum importance threshold

        Returns:
            List of (memory, relevance_score) tuples
        """
        if not self.memories:
            return []

        # Filter by minimum importance
        candidates = [m for m in self.memories if m.importance >= min_importance]

        if not candidates:
            return []

        scores = []

        for memory in candidates:
            # 1. Brain gate similarity
            gate_sim = self._cosine_similarity(current_brain_gates, memory.brain_gates)

            # 2. Task type match
            type_match = 1.0 if memory.task_type == current_task_type else 0.3

            # 3. Importance
            importance = memory.importance

            # 4. Recency (exponential decay)
            time_delta = self._time_since(memory.timestamp)
            recency = np.exp(-time_delta / 7.0)  # 7-day half-life

            # Combined relevance score
            relevance = (
                0.4 * gate_sim +
                0.3 * type_match +
                0.2 * importance +
                0.1 * recency
            )

            scores.append((memory, relevance))

            # Increment retrieval count
            memory.retrieval_count += 1

        # Sort by relevance
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:top_k]

    def get_important_memories(self, top_k: int = 10) -> List[EpisodicMemoryEntry]:
        """
        Get most important memories

        Args:
            top_k: Number of memories to return

        Returns:
            List of important memories
        """
        sorted_memories = sorted(
            self.memories,
            key=lambda m: m.importance,
            reverse=True
        )
        return sorted_memories[:top_k]

    def get_by_outcome(self, outcome: str) -> List[EpisodicMemoryEntry]:
        """
        Get all memories with specific outcome

        Args:
            outcome: 'success', 'failure', etc.

        Returns:
            List of matching memories
        """
        return [m for m in self.memories if m.outcome == outcome]

    def get_by_decision(self, decision: str) -> List[EpisodicMemoryEntry]:
        """
        Get all memories where specific decision was made

        Args:
            decision: Decision type (suggest, execute, etc.)

        Returns:
            List of matching memories
        """
        return [m for m in self.memories if m.decision == decision]

    def compute_decision_success_rate(self, decision: str) -> float:
        """
        Compute success rate for a specific decision type

        Args:
            decision: Decision type

        Returns:
            Success rate (0-1)
        """
        relevant_memories = self.get_by_decision(decision)

        if not relevant_memories:
            return 0.5  # Unknown

        successes = len([m for m in relevant_memories if m.outcome == 'success'])
        return successes / len(relevant_memories)

    def _evict_least_important(self):
        """Remove least important memory"""
        if not self.memories:
            return

        # Sort by importance (ascending)
        self.memories.sort(key=lambda m: m.importance)

        # Remove least important
        evicted = self.memories.pop(0)

        print(f"[EpisodicMemory] Evicted: {evicted.task[:50]}... (importance={evicted.importance:.2f})")

    def _save_memory(self, entry: EpisodicMemoryEntry):
        """Save memory to disk"""
        if not self.save_dir:
            return

        filename = f"memory_{entry.timestamp.replace(':', '-').replace(' ', '_')}.json"
        filepath = self.save_dir / filename

        with open(filepath, 'w') as f:
            json.dump(entry.to_dict(), f, indent=2)

    def _load_memories(self):
        """Load memories from disk"""
        if not self.save_dir or not self.save_dir.exists():
            return

        memory_files = list(self.save_dir.glob("memory_*.json"))

        for filepath in memory_files:
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)

                # Reconstruct entry
                data['brain_gates'] = np.array(data['brain_gates'])
                entry = EpisodicMemoryEntry(**data)
                self.memories.append(entry)

            except Exception as e:
                print(f"[EpisodicMemory] Failed to load {filepath}: {e}")

        print(f"[EpisodicMemory] Loaded {len(self.memories)} memories from disk")

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity"""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def _time_since(timestamp_str: str) -> float:
        """Days since timestamp"""
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            delta = datetime.now() - timestamp
            return delta.total_seconds() / (24 * 3600)  # Days
        except (ValueError, TypeError, AttributeError):
            return 999.0  # Very old

    def clear(self):
        """Clear all memories"""
        self.memories.clear()

    def __len__(self):
        return len(self.memories)

    def __repr__(self):
        return f"EpisodicMemory(size={len(self.memories)}, max={self.max_size})"


class MemoryManager:
    """
    Manager for both working and episodic memory

    Coordinates:
    - Working memory for immediate context
    - Episodic memory for long-term learning
    - Memory consolidation from working -> episodic
    """

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'MemoryManager':
        """Create MemoryManager from YAML config dict (P5.68)."""
        mem = yaml_config.get('memory', {})
        return cls(
            working_capacity=mem.get('working_memory_capacity', 10),
            episodic_max=mem.get('episodic_max_size', 1000),
            episodic_save_dir=mem.get('persistence_dir', None),
        )

    def __init__(
        self,
        working_capacity: int = 10,
        episodic_max: int = 1000,
        episodic_save_dir: Optional[str] = None
    ):
        """
        Initialize memory manager

        Args:
            working_capacity: Working memory capacity
            episodic_max: Max episodic memories
            episodic_save_dir: Directory for episodic persistence
        """
        self.working = WorkingMemory(capacity=working_capacity)
        self.episodic = EpisodicMemory(
            max_size=episodic_max,
            save_dir=episodic_save_dir
        )
        # Context cache for repeated queries within short time window (P4.57)
        self._context_cache: Dict[str, Any] = {}
        self._context_cache_time: Dict[str, float] = {}
        self._context_cache_ttl: float = 5.0  # seconds

    def remember_task(
        self,
        task: str,
        task_type: str,
        decision: str,
        confidence: float,
        brain_gates: np.ndarray,
        outcome: Optional[str] = None
    ):
        """
        Remember a task in working memory

        Args:
            task: Task description
            task_type: Type of task
            decision: Decision made
            confidence: Confidence score
            brain_gates: Brain gate activations
            outcome: Outcome (success/failure/None)
        """
        entry = WorkingMemoryEntry(
            task=task,
            task_type=task_type,
            decision=decision,
            confidence=confidence,
            outcome=outcome,
            brain_gates=brain_gates,
            timestamp=datetime.now().isoformat()
        )

        self.working.add(entry)

    def consolidate_to_episodic(
        self,
        task: str,
        task_type: str,
        decision: str,
        confidence: float,
        outcome: str,
        brain_gates: np.ndarray,
        layer1_features: Dict[str, float],
        layer2_sequence: List[str],
        reasoning_chain: List[str],
        importance: float,
        emotional_valence: str,
        prediction_error: float = 0.0,
        execution_time_ms: Optional[float] = None,
        user_rating: Optional[float] = None
    ):
        """
        Consolidate experience into episodic memory

        This creates a rich episodic memory with full context
        """
        entry = EpisodicMemoryEntry(
            task=task,
            task_type=task_type,
            decision=decision,
            confidence=confidence,
            outcome=outcome,
            brain_gates=brain_gates,
            layer1_features=layer1_features,
            layer2_sequence=layer2_sequence,
            reasoning_chain=reasoning_chain,
            timestamp=datetime.now().isoformat(),
            importance=importance,
            emotional_valence=emotional_valence,
            retrieval_count=0,
            prediction_error=prediction_error,
            execution_time_ms=execution_time_ms,
            user_rating=user_rating
        )

        self.episodic.add(entry)

    def get_context(
        self,
        current_task: str,
        current_brain_gates: np.ndarray,
        current_task_type: str
    ) -> Dict[str, Any]:
        """
        Get memory context for current task

        Returns:
            Dictionary with working and episodic context
        """
        import time as _time

        # Check cache (P4.57): same task within TTL returns cached result
        cache_key = f"{current_task}:{current_task_type}"
        now = _time.time()
        if cache_key in self._context_cache:
            cached_time = self._context_cache_time.get(cache_key, 0)
            if (now - cached_time) < self._context_cache_ttl:
                return self._context_cache[cache_key]

        # Working memory context
        recent_tasks = self.working.get_recent(n=5)
        similar_recent = self.working.retrieve_similar(
            current_task,
            current_brain_gates,
            top_k=3
        )
        decision_patterns = self.working.get_decision_patterns()
        recent_success_rate = self.working.get_success_rate(last_n=5)

        # Episodic memory context
        similar_episodes = self.episodic.retrieve_similar(
            current_task,
            current_brain_gates,
            current_task_type,
            top_k=5
        )

        result = {
            'working_memory': {
                'recent_tasks': [e.to_dict() for e in recent_tasks],
                'similar_tasks': [(e.to_dict(), score) for e, score in similar_recent],
                'decision_patterns': decision_patterns,
                'recent_success_rate': recent_success_rate
            },
            'episodic_memory': {
                'similar_episodes': [(e.to_dict(), score) for e, score in similar_episodes],
                'num_memories': len(self.episodic)
            }
        }

        # Store in cache (P4.57)
        self._context_cache[cache_key] = result
        self._context_cache_time[cache_key] = now
        # Evict stale entries (keep cache bounded)
        if len(self._context_cache) > 50:
            oldest_key = min(self._context_cache_time, key=self._context_cache_time.get)
            self._context_cache.pop(oldest_key, None)
            self._context_cache_time.pop(oldest_key, None)

        return result

    def __repr__(self):
        return (
            f"MemoryManager(\n"
            f"  {self.working},\n"
            f"  {self.episodic}\n"
            f")"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("MEMORY SYSTEMS DEMO")
    print("=" * 70)
    print()

    # Create memory manager
    manager = MemoryManager(
        working_capacity=5,
        episodic_max=100,
        episodic_save_dir="data/episodic_memory"
    )

    print(manager)
    print()

    # Simulate some tasks
    tasks = [
        ("Deploy Docker container", "docker", "execute", 0.85, "success"),
        ("Fix authentication bug", "bug", "suggest", 0.60, "success"),
        ("Deploy Docker urgently", "docker", "execute", 0.90, "success"),
        ("Update database schema", "database", "wait", 0.40, "failure"),
        ("Deploy API endpoint", "api", "suggest", 0.70, "success"),
    ]

    for task, task_type, decision, conf, outcome in tasks:
        # Random brain gates
        gates = np.random.dirichlet(np.ones(10))

        # Add to working memory
        manager.remember_task(task, task_type, decision, conf, gates, outcome)

        print(f"Remembered: {task[:40]}... -> {decision} ({outcome})")

    print()
    print("=" * 70)
    print("MEMORY RETRIEVAL")
    print("=" * 70)
    print()

    # Test retrieval
    current_task = "Deploy Docker container with high priority"
    current_gates = np.random.dirichlet(np.ones(10))
    current_type = "docker"

    context = manager.get_context(current_task, current_gates, current_type)

    print(f"Current task: {current_task}")
    print()
    print("Similar recent tasks:")
    for task_dict, score in context['working_memory']['similar_tasks']:
        print(f"  {task_dict['task'][:40]}... (similarity={score:.2f})")

    print()
    print("Decision patterns:")
    for decision, freq in context['working_memory']['decision_patterns'].items():
        print(f"  {decision}: {freq:.1%}")

    print()
    print(f"Recent success rate: {context['working_memory']['recent_success_rate']:.1%}")
    print()

    print("=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
