"""
MemoryAugmentedCTM - CTM with Episodic and Semantic Memory Systems

Augments the CTM with external memory systems for improved reasoning:
- Working Memory: Extended state beyond trace window
- Episodic Memory: Stores past reasoning episodes for retrieval
- Semantic Memory: Key-value store for learned facts

Architecture:
    Task → Retrieve(Episodic, Semantic) → CTM + Working Memory → Store Episode → Output

Memory Types:
1. Working Memory: Transformer-based extended context
2. Episodic Memory: FAISS-backed episode store with similarity retrieval
3. Semantic Memory: Learnable key-value memory bank

Usage:
    from core.memory_augmented_ctm import MemoryAugmentedCTM

    ctm = MemoryAugmentedCTM(
        feature_dim=256,
        episodic_capacity=10000,
        semantic_slots=1000
    )

    output = ctm(task_encoding)
    # Memory automatically updated
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, List, Dict, Any, Tuple, Union
from dataclasses import dataclass
import numpy as np
from collections import deque

try:
    from core.hybrid_ctm import HybridNeuroSymbolicCTM, HybridCTMOutput
except ImportError:
    from hybrid_ctm import HybridNeuroSymbolicCTM, HybridCTMOutput


@dataclass
class MemoryAugmentedOutput:
    """Output from MemoryAugmentedCTM."""
    predictions: torch.Tensor
    certainties: torch.Tensor
    thought_vector: Optional[torch.Tensor]
    consciousness_trajectory: List[float]
    converged: bool
    reasoning_steps: int
    episodic_memories_used: int
    semantic_memories_used: int
    memory_attention_weights: Optional[torch.Tensor]


class WorkingMemory(nn.Module):
    """
    Transformer-based working memory for extended context.

    Maintains a buffer of recent states that the CTM can attend to,
    extending its effective memory beyond the trace window.

    Parameters:
        feature_dim: Feature dimension
        capacity: Number of states to store
        num_heads: Attention heads
        num_layers: Transformer layers
    """

    def __init__(
        self,
        feature_dim: int = 256,
        capacity: int = 32,
        num_heads: int = 4,
        num_layers: int = 2,
        dropout: float = 0.1
    ):
        super().__init__()
        self.feature_dim = feature_dim
        self.capacity = capacity

        # Memory buffer (not a parameter, updated dynamically)
        self.register_buffer('memory', torch.zeros(1, capacity, feature_dim))
        self.register_buffer('write_ptr', torch.zeros(1, dtype=torch.long))

        # Transformer for memory processing
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=feature_dim,
            nhead=num_heads,
            dim_feedforward=feature_dim * 4,
            dropout=dropout,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Query projection for reading
        self.query_proj = nn.Linear(feature_dim, feature_dim)

        # Output projection
        self.output_proj = nn.Sequential(
            nn.Linear(feature_dim, feature_dim),
            nn.LayerNorm(feature_dim)
        )

    def write(self, state: torch.Tensor):
        """
        Write state to working memory.

        Args:
            state: (batch, feature_dim) state to write
        """
        batch_size = state.size(0)

        # Expand memory if batch size changed
        if self.memory.size(0) != batch_size:
            self.memory = self.memory.expand(batch_size, -1, -1).clone()
            self.write_ptr = self.write_ptr.expand(batch_size).clone()

        # Write at current position (circular buffer)
        ptr = self.write_ptr[0].item() % self.capacity
        self.memory[:, ptr] = state.detach()
        self.write_ptr[0] = (self.write_ptr[0] + 1) % self.capacity

    def read(self, query: torch.Tensor) -> torch.Tensor:
        """
        Read from working memory using attention.

        Args:
            query: (batch, feature_dim) query vector

        Returns:
            output: (batch, feature_dim) retrieved context
        """
        batch_size = query.size(0)

        # Ensure memory matches batch
        if self.memory.size(0) != batch_size:
            memory = self.memory.expand(batch_size, -1, -1)
        else:
            memory = self.memory

        # Process memory with transformer
        processed = self.transformer(memory)

        # Compute attention
        q = self.query_proj(query).unsqueeze(1)  # (B, 1, D)
        attn_scores = torch.bmm(q, processed.transpose(1, 2))  # (B, 1, C)
        attn_weights = F.softmax(attn_scores, dim=-1)

        # Weighted sum
        context = torch.bmm(attn_weights, processed).squeeze(1)  # (B, D)

        return self.output_proj(context)

    def reset(self, batch_size: int = 1):
        """Reset memory buffer."""
        device = self.memory.device
        self.memory = torch.zeros(batch_size, self.capacity, self.feature_dim, device=device)
        self.write_ptr = torch.zeros(batch_size, dtype=torch.long, device=device)


class EpisodicMemory(nn.Module):
    """
    Episodic memory for storing and retrieving past reasoning episodes.

    Each episode contains:
    - Task embedding
    - Thought vector
    - Outcome (certainty, success)

    Uses cosine similarity for retrieval.

    Parameters:
        capacity: Maximum number of episodes
        embedding_dim: Embedding dimension for episodes
        thought_dim: Thought vector dimension
    """

    def __init__(
        self,
        capacity: int = 10000,
        embedding_dim: int = 256,
        thought_dim: int = 2048
    ):
        super().__init__()
        self.capacity = capacity
        self.embedding_dim = embedding_dim
        self.thought_dim = thought_dim

        # Episode storage (CPU for large capacity)
        self.task_embeddings = deque(maxlen=capacity)
        self.thought_vectors = deque(maxlen=capacity)
        self.outcomes = deque(maxlen=capacity)

        # Projection for queries
        self.query_proj = nn.Linear(embedding_dim, embedding_dim)
        self.thought_proj = nn.Linear(thought_dim, embedding_dim)

        # Output fusion
        self.fusion = nn.Sequential(
            nn.Linear(embedding_dim + thought_dim, embedding_dim),
            nn.ReLU(),
            nn.Linear(embedding_dim, embedding_dim)
        )

    def store(
        self,
        task_embedding: torch.Tensor,
        thought_vector: torch.Tensor,
        certainty: float,
        success: bool = True
    ):
        """
        Store a new episode.

        Args:
            task_embedding: (embedding_dim,) task representation
            thought_vector: (thought_dim,) final thought
            certainty: Final certainty score
            success: Whether reasoning was successful
        """
        self.task_embeddings.append(task_embedding.detach().cpu())
        self.thought_vectors.append(thought_vector.detach().cpu())
        self.outcomes.append({'certainty': certainty, 'success': success})

    def retrieve(
        self,
        query: torch.Tensor,
        top_k: int = 5
    ) -> Tuple[torch.Tensor, List[Dict], torch.Tensor]:
        """
        Retrieve similar episodes.

        Args:
            query: (batch, embedding_dim) query embedding
            top_k: Number of episodes to retrieve

        Returns:
            thoughts: (batch, top_k, thought_dim) retrieved thoughts
            outcomes: List of outcome dicts
            similarities: (batch, top_k) similarity scores
        """
        if len(self.task_embeddings) == 0:
            # No episodes stored yet
            batch_size = query.size(0)
            device = query.device
            return (
                torch.zeros(batch_size, top_k, self.thought_dim, device=device),
                [{'certainty': 0.0, 'success': False}] * top_k,
                torch.zeros(batch_size, top_k, device=device)
            )

        device = query.device
        batch_size = query.size(0)

        # Stack stored embeddings
        stored = torch.stack(list(self.task_embeddings)).to(device)  # (N, D)
        thoughts = torch.stack(list(self.thought_vectors)).to(device)  # (N, T)

        # Compute similarities
        query_proj = self.query_proj(query)  # (B, D)
        similarities = F.cosine_similarity(
            query_proj.unsqueeze(1),  # (B, 1, D)
            stored.unsqueeze(0),      # (1, N, D)
            dim=-1
        )  # (B, N)

        # Get top-k
        k = min(top_k, len(self.task_embeddings))
        top_sims, top_indices = similarities.topk(k, dim=-1)

        # Gather thoughts
        top_thoughts = thoughts[top_indices]  # (B, k, T)

        # Pad if needed
        if k < top_k:
            pad_thoughts = torch.zeros(batch_size, top_k - k, self.thought_dim, device=device)
            top_thoughts = torch.cat([top_thoughts, pad_thoughts], dim=1)
            pad_sims = torch.zeros(batch_size, top_k - k, device=device)
            top_sims = torch.cat([top_sims, pad_sims], dim=1)

        # Get outcomes
        outcomes = [list(self.outcomes)[i] for i in top_indices[0].tolist()]
        while len(outcomes) < top_k:
            outcomes.append({'certainty': 0.0, 'success': False})

        return top_thoughts, outcomes, top_sims

    def get_context(
        self,
        query: torch.Tensor,
        top_k: int = 3
    ) -> torch.Tensor:
        """
        Get aggregated context from similar episodes.

        Args:
            query: (batch, embedding_dim) query
            top_k: Episodes to aggregate

        Returns:
            context: (batch, embedding_dim) aggregated context
        """
        thoughts, outcomes, similarities = self.retrieve(query, top_k)

        # Weight by similarity
        weights = F.softmax(similarities, dim=-1).unsqueeze(-1)  # (B, k, 1)

        # Project and aggregate thoughts
        thought_proj = self.thought_proj(thoughts)  # (B, k, D)
        aggregated = (thought_proj * weights).sum(dim=1)  # (B, D)

        return aggregated

    def __len__(self):
        return len(self.task_embeddings)


class SemanticMemory(nn.Module):
    """
    Learnable key-value memory for storing semantic knowledge.

    Unlike episodic memory, semantic memory is trainable and
    learns to store generalizable knowledge.

    Parameters:
        num_slots: Number of memory slots
        key_dim: Key dimension
        value_dim: Value dimension
    """

    def __init__(
        self,
        num_slots: int = 1000,
        key_dim: int = 256,
        value_dim: int = 512
    ):
        super().__init__()
        self.num_slots = num_slots
        self.key_dim = key_dim
        self.value_dim = value_dim

        # Learnable keys and values
        self.keys = nn.Parameter(torch.randn(num_slots, key_dim) * 0.02)
        self.values = nn.Parameter(torch.randn(num_slots, value_dim) * 0.02)

        # Query projection
        self.query_proj = nn.Linear(key_dim, key_dim)

        # Output projection
        self.output_proj = nn.Linear(value_dim, key_dim)

        # Temperature for softmax
        self.temperature = nn.Parameter(torch.ones(1))

    def lookup(
        self,
        query: torch.Tensor,
        top_k: Optional[int] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Look up values from semantic memory.

        Args:
            query: (batch, key_dim) query vector
            top_k: If set, use sparse top-k attention

        Returns:
            output: (batch, key_dim) retrieved values
            attention: (batch, num_slots) attention weights
        """
        # Project query
        q = self.query_proj(query)  # (B, D)

        # Compute attention scores
        scores = torch.mm(q, self.keys.t()) / self.temperature  # (B, N)

        if top_k is not None and top_k < self.num_slots:
            # Sparse attention: only attend to top-k
            top_scores, top_indices = scores.topk(top_k, dim=-1)
            attention = F.softmax(top_scores, dim=-1)  # (B, k)

            # Gather values
            top_values = self.values[top_indices]  # (B, k, V)
            output = torch.bmm(attention.unsqueeze(1), top_values).squeeze(1)
        else:
            # Dense attention
            attention = F.softmax(scores, dim=-1)  # (B, N)
            output = torch.mm(attention, self.values)  # (B, V)

        return self.output_proj(output), attention

    def update(
        self,
        query: torch.Tensor,
        value: torch.Tensor,
        learning_rate: float = 0.01
    ):
        """
        Update memory based on new information (for inference-time learning).

        Args:
            query: (batch, key_dim) query that triggered this update
            value: (batch, value_dim) new value information
            learning_rate: Update strength
        """
        with torch.no_grad():
            # Find most similar key
            q = self.query_proj(query)
            scores = torch.mm(q, self.keys.t())
            top_indices = scores.argmax(dim=-1)

            # Soft update of corresponding value
            for i, idx in enumerate(top_indices):
                self.values.data[idx] = (
                    (1 - learning_rate) * self.values.data[idx] +
                    learning_rate * value[i]
                )


class MemoryAugmentedCTM(nn.Module):
    """
    CTM augmented with working, episodic, and semantic memory systems.

    The memory systems provide:
    - Extended context beyond trace window (working memory)
    - Experience replay from similar past episodes (episodic)
    - Generalizable knowledge retrieval (semantic)

    Parameters:
        feature_dim: CTM feature dimension
        iterations: Maximum reasoning iterations
        working_memory_capacity: Working memory slots
        episodic_capacity: Maximum episodes to store
        semantic_slots: Number of semantic memory slots
        enable_thought_projection: Project to thought vectors
        thought_dim: Thought vector dimension
        device: Torch device
    """

    def __init__(
        self,
        feature_dim: int = 256,
        iterations: int = 30,
        working_memory_capacity: int = 32,
        episodic_capacity: int = 10000,
        semantic_slots: int = 1000,
        consciousness_threshold: float = 0.85,
        enable_thought_projection: bool = True,
        thought_dim: int = 2048,
        device: str = 'cpu'
    ):
        super().__init__()

        self.feature_dim = feature_dim
        self.iterations = iterations
        self.thought_dim = thought_dim
        self.device = device
        self.enable_thought_projection = enable_thought_projection

        # Core CTM
        self.ctm = HybridNeuroSymbolicCTM(
            feature_dim=feature_dim,
            iterations=iterations,
            consciousness_threshold=consciousness_threshold,
            enable_thought_projection=enable_thought_projection,
            thought_dim=thought_dim,
            device=device
        )

        # Memory systems
        self.working_memory = WorkingMemory(
            feature_dim=feature_dim,
            capacity=working_memory_capacity
        )

        self.episodic_memory = EpisodicMemory(
            capacity=episodic_capacity,
            embedding_dim=feature_dim,
            thought_dim=thought_dim
        )

        self.semantic_memory = SemanticMemory(
            num_slots=semantic_slots,
            key_dim=feature_dim,
            value_dim=feature_dim * 2
        )

        # Context integration
        self.context_integration = nn.Sequential(
            nn.Linear(feature_dim * 4, feature_dim * 2),  # input + working + episodic + semantic
            nn.LayerNorm(feature_dim * 2),
            nn.ReLU(),
            nn.Linear(feature_dim * 2, feature_dim),
            nn.LayerNorm(feature_dim)
        )

        # Input encoder
        self.input_encoder = nn.Sequential(
            nn.LazyLinear(feature_dim),
            nn.LayerNorm(feature_dim)
        )

    def _create_board(self, features: torch.Tensor) -> torch.Tensor:
        """Create board-like input for CTM."""
        B = features.size(0)
        # Use first 20 features or pad
        if features.size(1) >= 20:
            board_flat = features[:, :20]
        else:
            padding = torch.zeros(B, 20 - features.size(1), device=features.device)
            board_flat = torch.cat([features, padding], dim=1)

        board_flat = torch.sigmoid(board_flat) * 10
        return board_flat.view(B, 5, 4).long()

    def forward(
        self,
        x: torch.Tensor,
        max_iterations: Optional[int] = None,
        store_episode: bool = True,
        use_memories: bool = True
    ) -> MemoryAugmentedOutput:
        """
        Forward pass with memory augmentation.

        Args:
            x: Input tensor (batch, ...) will be flattened
            max_iterations: Override max iterations
            store_episode: Whether to store this as an episode
            use_memories: Whether to use memory systems

        Returns:
            MemoryAugmentedOutput
        """
        # Flatten if needed
        if x.dim() > 2:
            x = x.view(x.size(0), -1).float()

        B = x.size(0)
        device = x.device

        # Encode input
        input_features = self.input_encoder(x)

        if use_memories:
            # Retrieve from working memory
            working_context = self.working_memory.read(input_features)

            # Retrieve from episodic memory
            episodic_context = self.episodic_memory.get_context(input_features)
            episodic_count = min(3, len(self.episodic_memory))

            # Retrieve from semantic memory
            semantic_context, semantic_attn = self.semantic_memory.lookup(input_features, top_k=10)
            semantic_count = (semantic_attn > 0.01).sum().item()

            # Integrate all contexts
            combined = torch.cat([
                input_features,
                working_context,
                episodic_context,
                semantic_context
            ], dim=-1)
            integrated = self.context_integration(combined)
        else:
            integrated = input_features
            episodic_count = 0
            semantic_count = 0

        # Create board for CTM
        board = self._create_board(integrated)

        # Run CTM with optional semantic features
        ctm_output = self.ctm(
            board,
            max_iterations=max_iterations,
            semantic_features=integrated
        )

        # Update working memory with final state
        if ctm_output.final_sync is not None:
            self.working_memory.write(ctm_output.final_sync[:, :self.feature_dim])

        # Store episode
        if store_episode and ctm_output.thought_vector is not None:
            certainty = ctm_output.certainties[:, -1].mean().item()
            self.episodic_memory.store(
                task_embedding=input_features[0],
                thought_vector=ctm_output.thought_vector[0],
                certainty=certainty,
                success=ctm_output.converged
            )

        return MemoryAugmentedOutput(
            predictions=ctm_output.final_prediction,
            certainties=ctm_output.certainties,
            thought_vector=ctm_output.thought_vector,
            consciousness_trajectory=ctm_output.consciousness_trajectory,
            converged=ctm_output.converged,
            reasoning_steps=ctm_output.reasoning_steps,
            episodic_memories_used=episodic_count,
            semantic_memories_used=int(semantic_count),
            memory_attention_weights=semantic_attn if use_memories else None
        )

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about memory systems."""
        return {
            'working_memory': {
                'capacity': self.working_memory.capacity,
                'feature_dim': self.working_memory.feature_dim
            },
            'episodic_memory': {
                'capacity': self.episodic_memory.capacity,
                'current_size': len(self.episodic_memory)
            },
            'semantic_memory': {
                'num_slots': self.semantic_memory.num_slots,
                'key_dim': self.semantic_memory.key_dim
            }
        }

    def reset_memories(self, which: List[str] = None):
        """
        Reset specified memory systems.

        Args:
            which: List of ['working', 'episodic', 'semantic'] or None for all
        """
        if which is None:
            which = ['working', 'episodic', 'semantic']

        if 'working' in which:
            self.working_memory.reset()

        if 'episodic' in which:
            self.episodic_memory.task_embeddings.clear()
            self.episodic_memory.thought_vectors.clear()
            self.episodic_memory.outcomes.clear()

        # Note: semantic memory is learnable, so "reset" would mean reinitializing parameters

    def get_num_parameters(self) -> int:
        """Get total parameter count."""
        return sum(p.numel() for p in self.parameters())


if __name__ == "__main__":
    print("=" * 60)
    print("Testing MemoryAugmentedCTM")
    print("=" * 60)

    # Create MemoryAugmentedCTM
    print("\n" + "-" * 40)
    print("Creating MemoryAugmentedCTM:")
    print("-" * 40)

    ctm = MemoryAugmentedCTM(
        feature_dim=256,
        iterations=20,
        working_memory_capacity=16,
        episodic_capacity=100,
        semantic_slots=100,
        enable_thought_projection=True,
        thought_dim=2048
    )

    # Initialize with dummy input
    dummy = torch.randn(1, 20)
    with torch.no_grad():
        _ = ctm(dummy, max_iterations=1, store_episode=False, use_memories=False)

    print(f"\nTotal parameters: {ctm.get_num_parameters():,}")
    print("\nMemory statistics:")
    for mem_type, stats in ctm.get_memory_stats().items():
        print(f"  {mem_type}: {stats}")

    # Test memory accumulation
    print("\n" + "-" * 40)
    print("Testing memory accumulation:")
    print("-" * 40)

    test_input = torch.randn(2, 20)

    for i in range(10):
        output = ctm(test_input, max_iterations=10)
        print(f"\nIteration {i + 1}:")
        print(f"  Episodic memories: {len(ctm.episodic_memory)}")
        print(f"  Episodes used: {output.episodic_memories_used}")
        print(f"  Semantic memories used: {output.semantic_memories_used}")
        print(f"  Steps: {output.reasoning_steps}")
        print(f"  Converged: {output.converged}")

    # Test without memories
    print("\n" + "-" * 40)
    print("Testing without memory augmentation:")
    print("-" * 40)

    output_no_mem = ctm(test_input, max_iterations=10, use_memories=False)
    print(f"Without memories - Steps: {output_no_mem.reasoning_steps}")

    output_with_mem = ctm(test_input, max_iterations=10, use_memories=True)
    print(f"With memories - Steps: {output_with_mem.reasoning_steps}")

    # Test memory reset
    print("\n" + "-" * 40)
    print("Testing memory reset:")
    print("-" * 40)

    print(f"Before reset - Episodic size: {len(ctm.episodic_memory)}")
    ctm.reset_memories(['episodic'])
    print(f"After reset - Episodic size: {len(ctm.episodic_memory)}")

    print("\n" + "=" * 60)
    print("MemoryAugmentedCTM tests PASSED!")
    print("=" * 60)
