"""
Hippocampal Memory Module for Episodic Memory and Context-Dependent Routing

Implements biologically-inspired episodic memory system with:
1. Pattern separation (Dentate Gyrus)
2. Autoassociative memory (CA3)
3. Pattern completion and memory retrieval
4. Novelty-based encoding
5. Memory-biased routing

Biological inspiration:
- DG: Sparse encoding for pattern separation
- CA3: Recurrent network for pattern completion
- CA1: Comparator and output
- EC: Interface with cortex/thalamus
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import deque


class EpisodicMemory:
    """
    Single episodic memory entry.

    Stores a snapshot of the system state at a particular moment.
    """

    def __init__(
        self,
        state: np.ndarray,
        context: Optional[np.ndarray],
        gates: np.ndarray,
        prediction_error: float,
        timestamp: int
    ):
        """
        Initialize episodic memory.

        Args:
            state: Concatenated thalamic state vector
            context: Context vector
            gates: Gate distribution at this moment
            prediction_error: Novelty signal
            timestamp: Time index
        """
        self.state = state.copy()
        self.context = context.copy() if context is not None else None
        self.gates = gates.copy()
        self.prediction_error = prediction_error
        self.timestamp = timestamp
        self.retrieval_count = 0  # Track how often retrieved
        self.strength = 1.0  # Memory strength


class DentateGyrus:
    """
    Dentate Gyrus: Pattern separation via sparse coding.

    Projects high-dimensional inputs to sparse representations.
    """

    def __init__(
        self,
        input_dim: int,
        dg_dim: int = 512,
        sparsity: float = 0.05,
        seed: int = 42
    ):
        """
        Initialize DG.

        Args:
            input_dim: Input dimension
            dg_dim: DG representation dimension (typically large)
            sparsity: Fraction of active units (5% is biological)
            seed: Random seed
        """
        self.input_dim = input_dim
        self.dg_dim = dg_dim
        self.sparsity = sparsity

        self.rng = np.random.RandomState(seed)

        # Random projection for pattern separation
        self.W_dg = self.rng.normal(
            0, 1/np.sqrt(input_dim), (dg_dim, input_dim)
        )

    def encode(self, x: np.ndarray) -> np.ndarray:
        """
        Encode input to sparse DG representation.

        Args:
            x: Input vector

        Returns:
            Sparse DG code (binary)
        """
        # Project to DG space
        activation = self.W_dg @ x

        # k-winners-take-all for sparsity
        k = int(self.dg_dim * self.sparsity)
        threshold = np.partition(activation, -k)[-k]

        sparse_code = (activation >= threshold).astype(np.float32)
        return sparse_code


class CA3AutoAssociative:
    """
    CA3: Autoassociative memory for pattern completion.

    Stores patterns and retrieves from partial cues.
    """

    def __init__(
        self,
        dg_dim: int,
        learning_rate: float = 0.01,
        decay_rate: float = 0.001
    ):
        """
        Initialize CA3.

        Args:
            dg_dim: DG code dimension
            learning_rate: Hebbian learning rate
            decay_rate: Synaptic decay rate
        """
        self.dg_dim = dg_dim
        self.lr = learning_rate
        self.decay = decay_rate

        # Recurrent weight matrix (autoassociative)
        self.W_ca3 = np.zeros((dg_dim, dg_dim))

    def store_pattern(self, pattern: np.ndarray):
        """
        Store pattern via Hebbian learning.

        Args:
            pattern: DG sparse code to store
        """
        # Hebbian: ΔW = η * outer(pattern, pattern)
        # Symmetric for autoassociation
        dW = self.lr * np.outer(pattern, pattern)

        # No self-connections
        np.fill_diagonal(dW, 0)

        self.W_ca3 += dW

        # Apply decay to prevent saturation
        self.W_ca3 *= (1 - self.decay)

    def retrieve_pattern(
        self,
        cue: np.ndarray,
        num_iterations: int = 5
    ) -> np.ndarray:
        """
        Retrieve pattern from partial cue via recurrent dynamics.

        Args:
            cue: Partial pattern (DG code)
            num_iterations: Number of recurrent iterations

        Returns:
            Completed pattern
        """
        # Initialize with cue
        state = cue.copy()

        # Recurrent dynamics for pattern completion
        for _ in range(num_iterations):
            # Recurrent update
            activation = self.W_ca3 @ state

            # Threshold (binary)
            state = (activation > 0.5).astype(np.float32)

            # Mix with original cue to prevent drift
            state = 0.7 * state + 0.3 * cue
            state = (state > 0.5).astype(np.float32)

        return state


class Hippocampus:
    """
    Full hippocampal system for episodic memory and routing.

    Integrates DG (pattern separation), CA3 (pattern completion),
    and episodic memory buffer.
    """

    def __init__(
        self,
        state_dim: int,
        context_dim: int = 6,
        num_modalities: int = 6,
        dg_dim: int = 512,
        sparsity: float = 0.05,
        memory_capacity: int = 1000,
        novelty_threshold: float = 0.5,
        retrieval_threshold: float = 0.7,
        learning_rate_ca3: float = 0.01,
        memory_influence: float = 0.3,
        seed: int = 42
    ):
        """
        Initialize hippocampus.

        Args:
            state_dim: Dimension of thalamic state vector
            context_dim: Context vector dimension
            num_modalities: Number of modalities
            dg_dim: Dentate gyrus dimension
            sparsity: DG sparsity level
            memory_capacity: Maximum number of memories
            novelty_threshold: PE threshold for encoding
            retrieval_threshold: Similarity threshold for retrieval
            learning_rate_ca3: CA3 learning rate
            memory_influence: Strength of memory bias on routing
            seed: Random seed
        """
        self.state_dim = state_dim
        self.context_dim = context_dim
        self.M = num_modalities
        self.novelty_threshold = novelty_threshold
        self.retrieval_threshold = retrieval_threshold
        self.memory_influence = memory_influence

        self.rng = np.random.RandomState(seed)

        # Dentate gyrus for pattern separation
        self.dg = DentateGyrus(
            input_dim=state_dim + (context_dim if context_dim else 0),
            dg_dim=dg_dim,
            sparsity=sparsity,
            seed=seed
        )

        # CA3 autoassociative memory
        self.ca3 = CA3AutoAssociative(
            dg_dim=dg_dim,
            learning_rate=learning_rate_ca3
        )

        # Episodic memory buffer (FIFO with capacity limit)
        self.memories: deque = deque(maxlen=memory_capacity)
        self.timestep = 0

        # CA1 output projection (DG code → gate bias)
        self.W_ca1 = self.rng.normal(
            0, 1/np.sqrt(dg_dim), (num_modalities, dg_dim)
        )

    def _pack_input(
        self,
        state: np.ndarray,
        context: Optional[np.ndarray]
    ) -> np.ndarray:
        """Pack state and context for DG encoding."""
        if context is not None:
            return np.concatenate([state, context])
        # If no context, use zeros to maintain dimension
        return np.concatenate([state, np.zeros(self.context_dim if self.context_dim else 0)])

    def should_encode(self, prediction_error: float) -> bool:
        """
        Determine if current experience should be encoded.

        Args:
            prediction_error: Current prediction error (novelty)

        Returns:
            True if PE exceeds threshold (novel enough to remember)
        """
        return prediction_error > self.novelty_threshold

    def encode_memory(
        self,
        state: np.ndarray,
        context: Optional[np.ndarray],
        gates: np.ndarray,
        prediction_error: float
    ):
        """
        Encode current experience to episodic memory.

        Args:
            state: Current thalamic state
            context: Context vector
            gates: Current gate distribution
            prediction_error: Novelty signal
        """
        # Create episodic memory entry
        memory = EpisodicMemory(
            state=state,
            context=context,
            gates=gates,
            prediction_error=prediction_error,
            timestamp=self.timestep
        )

        # Add to buffer (automatically removes oldest if full)
        self.memories.append(memory)

        # Encode to CA3 for pattern completion
        x_in = self._pack_input(state, context)
        dg_code = self.dg.encode(x_in)
        self.ca3.store_pattern(dg_code)

    def retrieve_memory(
        self,
        state: np.ndarray,
        context: Optional[np.ndarray],
        k: int = 5
    ) -> List[EpisodicMemory]:
        """
        Retrieve k most similar memories.

        Args:
            state: Current state (query)
            context: Current context
            k: Number of memories to retrieve

        Returns:
            List of retrieved memories (sorted by similarity)
        """
        if len(self.memories) == 0:
            return []

        # Compute similarity to all memories
        similarities = []
        for mem in self.memories:
            # State similarity (cosine)
            state_sim = self._cosine_similarity(state, mem.state)

            # Context similarity
            if context is not None and mem.context is not None:
                ctx_sim = self._cosine_similarity(context, mem.context)
                sim = 0.7 * state_sim + 0.3 * ctx_sim
            else:
                sim = state_sim

            similarities.append(sim)

        # Sort by similarity
        similarities = np.array(similarities)
        top_k_idx = np.argsort(similarities)[-k:][::-1]

        # Filter by threshold
        retrieved = []
        for idx in top_k_idx:
            if similarities[idx] >= self.retrieval_threshold:
                mem = self.memories[idx]
                mem.retrieval_count += 1
                retrieved.append(mem)

        return retrieved

    def pattern_completion(
        self,
        state: np.ndarray,
        context: Optional[np.ndarray]
    ) -> np.ndarray:
        """
        Complete pattern from partial cue using CA3.

        Args:
            state: Partial state
            context: Partial context

        Returns:
            Gate bias from completed pattern
        """
        # Encode current state to DG
        x_in = self._pack_input(state, context)
        dg_cue = self.dg.encode(x_in)

        # CA3 pattern completion
        completed = self.ca3.retrieve_pattern(dg_cue)

        # Project to gate space via CA1
        gate_bias = self.W_ca1 @ completed

        return gate_bias

    def compute_memory_bias(
        self,
        state: np.ndarray,
        context: Optional[np.ndarray],
        current_gates: np.ndarray
    ) -> np.ndarray:
        """
        Compute memory-based bias for routing gates.

        Args:
            state: Current state
            context: Current context
            current_gates: Current gate distribution

        Returns:
            Biased gates (blend of current + memory)
        """
        # Retrieve similar memories
        retrieved = self.retrieve_memory(state, context, k=5)

        if len(retrieved) == 0:
            # No memories: return current gates
            return current_gates

        # Compute weighted average of retrieved gate patterns
        memory_gates = np.zeros(self.M)
        total_weight = 0.0

        for mem in retrieved:
            # Weight by recency and strength
            recency_weight = np.exp(-0.01 * (self.timestep - mem.timestamp))
            strength_weight = mem.strength
            weight = recency_weight * strength_weight

            memory_gates += weight * mem.gates
            total_weight += weight

        if total_weight > 0:
            memory_gates /= total_weight

        # Blend with current gates
        biased_gates = (1 - self.memory_influence) * current_gates + \
                       self.memory_influence * memory_gates

        # Renormalize
        biased_gates = biased_gates / (np.sum(biased_gates) + 1e-10)

        return biased_gates

    def step(
        self,
        state: np.ndarray,
        context: Optional[np.ndarray],
        gates: np.ndarray,
        prediction_error: float,
        encode: bool = True
    ) -> Dict:
        """
        Single hippocampal timestep.

        Args:
            state: Current thalamic state
            context: Context vector
            gates: Current gate distribution
            prediction_error: Prediction error (novelty)
            encode: Whether to encode if novel

        Returns:
            Dict with memory-biased gates and retrieval info
        """
        # Encode to memory if novel enough
        encoded = False
        if encode and self.should_encode(prediction_error):
            self.encode_memory(state, context, gates, prediction_error)
            encoded = True

        # Retrieve similar memories and compute bias
        memory_biased_gates = self.compute_memory_bias(state, context, gates)

        # Pattern completion from CA3
        ca3_bias = self.pattern_completion(state, context)

        self.timestep += 1

        return {
            'memory_biased_gates': memory_biased_gates,
            'ca3_bias': ca3_bias,
            'num_memories': len(self.memories),
            'encoded': encoded,
            'timestep': self.timestep
        }

    def reset(self):
        """Reset timestep (keep memories)."""
        self.timestep = 0

    def clear_memories(self):
        """Clear all episodic memories."""
        self.memories.clear()
        self.ca3.W_ca3.fill(0)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return np.dot(a, b) / (norm_a * norm_b)

    def get_state(self) -> Dict:
        """Get hippocampal state."""
        return {
            'num_memories': len(self.memories),
            'timestep': self.timestep,
            'ca3_weights_norm': np.linalg.norm(self.ca3.W_ca3),
            'memory_ages': [self.timestep - m.timestamp for m in self.memories],
            'memory_strengths': [m.strength for m in self.memories]
        }
