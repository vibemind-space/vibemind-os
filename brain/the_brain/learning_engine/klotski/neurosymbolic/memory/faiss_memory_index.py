"""
FAISS Memory Index for Fast k-NN Search

Provides fast approximate nearest neighbor search for game experiences.
Uses FAISS (Facebook AI Similarity Search) for efficient vector search.
"""

import numpy as np
import torch
import torch.nn as nn
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import pickle
from pathlib import Path


@dataclass
class MemoryEntry:
    """Single memory entry with embedding"""
    state: np.ndarray  # Board state
    action: int  # Action taken
    reward: float  # Reward received
    next_state: np.ndarray  # Next state
    done: bool  # Episode done
    embedding: np.ndarray  # 256D embedding
    metadata: Dict  # Additional info


class StateEmbedder(nn.Module):
    """
    Neural network to embed board states into 256D vectors

    Learns to encode board states into dense representations
    that capture semantic similarity (similar states → similar vectors).
    """

    def __init__(self, input_dim: int = 20, embedding_dim: int = 256):
        super().__init__()
        self.input_dim = input_dim
        self.embedding_dim = embedding_dim

        # Encoder network
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, embedding_dim),
            nn.Tanh()  # Bounded output
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """
        Embed state into 256D vector

        Args:
            state: (batch, 4, 5) or (batch, 20) board state

        Returns:
            embedding: (batch, 256) vector
        """
        # Flatten if needed
        if len(state.shape) == 3:
            state = state.view(state.size(0), -1)

        # Normalize to [0, 1]
        state = state.float() / 11.0  # Max piece ID is 10

        # Encode
        embedding = self.encoder(state)

        # L2 normalize for cosine similarity
        embedding = nn.functional.normalize(embedding, p=2, dim=-1)

        return embedding


class FAISSMemoryIndex:
    """
    Fast k-NN memory search using FAISS

    Stores game experiences as 256D vectors and enables fast retrieval
    of similar states (<10ms p95 for 100K memories).
    """

    def __init__(
        self,
        embedding_dim: int = 256,
        use_gpu: bool = False,
        index_type: str = "IVF"  # "Flat", "IVF", "HNSW"
    ):
        """
        Initialize FAISS index

        Args:
            embedding_dim: Dimension of embeddings (256)
            use_gpu: Use GPU for FAISS (faster but more memory)
            index_type: Type of index
                - "Flat": Exact search (slow for large data)
                - "IVF": Inverted file index (fast, approximate)
                - "HNSW": Hierarchical NSW (faster, more memory)
        """
        self.embedding_dim = embedding_dim
        self.use_gpu = use_gpu
        self.index_type = index_type

        # Try to import FAISS
        try:
            import faiss
            self.faiss = faiss
        except ImportError:
            raise ImportError(
                "FAISS not installed. Install with: pip install faiss-cpu (or faiss-gpu)"
            )

        # Create index
        self.index = self._create_index()

        # Storage for metadata
        self.memories: List[MemoryEntry] = []

        # Embedder network
        self.embedder = StateEmbedder(input_dim=20, embedding_dim=embedding_dim)

    def _create_index(self):
        """Create FAISS index based on type"""
        if self.index_type == "Flat":
            # Exact search (L2 distance)
            index = self.faiss.IndexFlatL2(self.embedding_dim)

        elif self.index_type == "IVF":
            # Inverted file index (approximate)
            # Good for 10K-1M vectors
            nlist = 100  # Number of clusters
            quantizer = self.faiss.IndexFlatL2(self.embedding_dim)
            index = self.faiss.IndexIVFFlat(quantizer, self.embedding_dim, nlist)

        elif self.index_type == "HNSW":
            # Hierarchical Navigable Small World (fast, accurate)
            # Good for 100K-10M vectors
            M = 32  # Number of connections per layer
            index = self.faiss.IndexHNSWFlat(self.embedding_dim, M)

        else:
            raise ValueError(f"Unknown index type: {self.index_type}")

        # Move to GPU if requested
        if self.use_gpu and self.faiss.get_num_gpus() > 0:
            index = self.faiss.index_cpu_to_gpu(
                self.faiss.StandardGpuResources(), 0, index
            )

        return index

    def add(self, entry: MemoryEntry):
        """Add single memory to index"""
        self.add_batch([entry])

    def add_batch(self, entries: List[MemoryEntry]):
        """
        Add batch of memories to index

        Args:
            entries: List of MemoryEntry objects
        """
        if not entries:
            return

        # Extract embeddings
        embeddings = np.array([e.embedding for e in entries], dtype=np.float32)

        # Train index if needed (for IVF)
        if self.index_type == "IVF" and not self.index.is_trained:
            if embeddings.shape[0] >= 100:  # Need enough data
                self.index.train(embeddings)

        # Add to index
        if self.index_type == "IVF" and self.index.is_trained:
            self.index.add(embeddings)
        elif self.index_type != "IVF":
            self.index.add(embeddings)

        # Store metadata
        self.memories.extend(entries)

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 10,
        return_distances: bool = False
    ) -> List[MemoryEntry]:
        """
        Search for k nearest neighbors

        Args:
            query_embedding: (256,) query vector
            k: Number of neighbors to return
            return_distances: Also return distances

        Returns:
            List of k nearest MemoryEntry objects
            (or Tuple[List[MemoryEntry], np.ndarray] if return_distances=True)
        """
        if len(self.memories) == 0:
            return [] if not return_distances else ([], np.array([]))

        # Reshape query
        query = query_embedding.reshape(1, -1).astype(np.float32)

        # Search
        k_actual = min(k, len(self.memories))
        distances, indices = self.index.search(query, k_actual)

        # Get memories
        results = [self.memories[i] for i in indices[0] if i < len(self.memories)]

        if return_distances:
            return results, distances[0]
        return results

    def search_by_state(
        self,
        state: np.ndarray,
        k: int = 10,
        return_distances: bool = False
    ) -> List[MemoryEntry]:
        """
        Search for similar states

        Args:
            state: (4, 5) or (20,) board state
            k: Number of neighbors
            return_distances: Also return distances

        Returns:
            List of k nearest MemoryEntry objects
        """
        # Embed state
        with torch.no_grad():
            state_tensor = torch.from_numpy(state).float().unsqueeze(0)
            embedding = self.embedder(state_tensor).numpy()[0]

        # Search
        return self.search(embedding, k, return_distances)

    def embed_state(self, state: np.ndarray) -> np.ndarray:
        """
        Embed single state into 256D vector

        Args:
            state: (4, 5) or (20,) board state

        Returns:
            embedding: (256,) vector
        """
        with torch.no_grad():
            state_tensor = torch.from_numpy(state).float().unsqueeze(0)
            embedding = self.embedder(state_tensor).numpy()[0]
        return embedding

    def embed_batch(self, states: np.ndarray) -> np.ndarray:
        """
        Embed batch of states

        Args:
            states: (batch, 4, 5) or (batch, 20) states

        Returns:
            embeddings: (batch, 256) vectors
        """
        with torch.no_grad():
            states_tensor = torch.from_numpy(states).float()
            embeddings = self.embedder(states_tensor).numpy()
        return embeddings

    def save(self, path: str):
        """Save index and metadata to disk"""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        index_path = path / "faiss_index.bin"
        if self.use_gpu:
            # Move to CPU before saving
            cpu_index = self.faiss.index_gpu_to_cpu(self.index)
            self.faiss.write_index(cpu_index, str(index_path))
        else:
            self.faiss.write_index(self.index, str(index_path))

        # Save memories
        memories_path = path / "memories.pkl"
        with open(memories_path, 'wb') as f:
            pickle.dump(self.memories, f)

        # Save embedder
        embedder_path = path / "embedder.pt"
        torch.save(self.embedder.state_dict(), embedder_path)

        print(f"Saved FAISS index: {index_path}")
        print(f"Saved {len(self.memories)} memories: {memories_path}")

    def load(self, path: str):
        """Load index and metadata from disk"""
        path = Path(path)

        # Load FAISS index
        index_path = path / "faiss_index.bin"
        if index_path.exists():
            cpu_index = self.faiss.read_index(str(index_path))

            if self.use_gpu and self.faiss.get_num_gpus() > 0:
                self.index = self.faiss.index_cpu_to_gpu(
                    self.faiss.StandardGpuResources(), 0, cpu_index
                )
            else:
                self.index = cpu_index

        # Load memories
        memories_path = path / "memories.pkl"
        if memories_path.exists():
            with open(memories_path, 'rb') as f:
                self.memories = pickle.load(f)

        # Load embedder
        embedder_path = path / "embedder.pt"
        if embedder_path.exists():
            self.embedder.load_state_dict(torch.load(embedder_path, weights_only=True))

        print(f"Loaded FAISS index from {index_path}")
        print(f"Loaded {len(self.memories)} memories")

    def get_statistics(self) -> Dict:
        """Get index statistics"""
        return {
            "num_memories": len(self.memories),
            "index_type": self.index_type,
            "embedding_dim": self.embedding_dim,
            "is_trained": self.index.is_trained if self.index_type == "IVF" else True,
            "ntotal": self.index.ntotal,
            "use_gpu": self.use_gpu
        }


if __name__ == "__main__":
    # Test FAISS memory index
    print("Testing FAISS Memory Index...")
    print("="*60)

    # Create index
    index = FAISSMemoryIndex(embedding_dim=256, index_type="Flat")

    # Create sample memories
    print("\nCreating sample memories...")
    memories = []
    for i in range(100):
        state = np.random.randint(0, 11, size=(4, 5))
        action = np.random.randint(0, 40)
        reward = np.random.randn()
        next_state = np.random.randint(0, 11, size=(4, 5))

        # Embed state
        embedding = index.embed_state(state)

        entry = MemoryEntry(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=False,
            embedding=embedding,
            metadata={"episode": i // 10, "step": i}
        )
        memories.append(entry)

    # Add to index
    print(f"Adding {len(memories)} memories...")
    index.add_batch(memories)

    # Search
    print("\nSearching for similar states...")
    query_state = np.random.randint(0, 11, size=(4, 5))
    results, distances = index.search_by_state(query_state, k=5, return_distances=True)

    print(f"Found {len(results)} similar states:")
    for i, (result, dist) in enumerate(zip(results, distances)):
        print(f"  {i+1}. Distance: {dist:.4f}, Reward: {result.reward:.2f}, "
              f"Episode: {result.metadata['episode']}")

    # Statistics
    print("\nIndex statistics:")
    stats = index.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Save/load test
    print("\nTesting save/load...")
    index.save("test_faiss_index")

    index2 = FAISSMemoryIndex(embedding_dim=256)
    index2.load("test_faiss_index")

    print(f"Loaded index with {len(index2.memories)} memories")

    print("\n" + "="*60)
    print("FAISS Memory Index test complete!")
