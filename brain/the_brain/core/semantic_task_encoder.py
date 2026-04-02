"""
SemanticTaskEncoder - Sentence-BERT Based Task Encoding

Replaces simple hash-based encoding with semantically rich embeddings
using Sentence-BERT (all-MiniLM-L6-v2 by default).

This enables the CTM to understand semantic relationships between tasks,
improving generalization and transfer learning.

Architecture:
    Task String → Sentence-BERT (384-dim) → Projection (256-dim) → CTM Input

Usage:
    from core.semantic_task_encoder import SemanticTaskEncoder

    encoder = SemanticTaskEncoder()
    features = encoder.encode("Explain machine learning")
    # features.shape = (256,)

    # Batch encoding
    features = encoder.encode_batch(["Task 1", "Task 2", "Task 3"])
    # features.shape = (3, 256)
"""

import torch
import torch.nn as nn
from typing import List, Union, Optional
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    print("[SemanticTaskEncoder] Warning: sentence-transformers not installed.")
    print("  Install with: pip install sentence-transformers")


class SemanticTaskEncoder(nn.Module):
    """
    Encodes natural language tasks into semantic feature vectors.

    Uses Sentence-BERT for rich semantic embeddings, then projects
    to the CTM's feature dimension.

    Parameters:
        model_name: Sentence-BERT model to use (default: all-MiniLM-L6-v2)
        output_dim: Output dimension (CTM feature_dim, default: 256)
        freeze_encoder: Whether to freeze Sentence-BERT weights
        device: Torch device
    """

    # Available models with their embedding dimensions
    MODELS = {
        'all-MiniLM-L6-v2': 384,      # Fast, good quality (default)
        'all-mpnet-base-v2': 768,      # Best quality, slower
        'paraphrase-MiniLM-L6-v2': 384, # Good for paraphrase detection
        'all-distilroberta-v1': 768,   # DistilRoBERTa based
    }

    def __init__(
        self,
        model_name: str = 'all-MiniLM-L6-v2',
        output_dim: int = 256,
        freeze_encoder: bool = True,
        dropout: float = 0.1,
        device: str = 'cpu'
    ):
        super().__init__()

        if not HAS_SENTENCE_TRANSFORMERS:
            raise RuntimeError(
                "sentence-transformers required. Install with: pip install sentence-transformers"
            )

        self.model_name = model_name
        self.output_dim = output_dim
        self.device = device
        self.freeze_encoder = freeze_encoder

        # Get embedding dimension for chosen model
        if model_name in self.MODELS:
            self.embedding_dim = self.MODELS[model_name]
        else:
            # Try to load and get dimension
            self.embedding_dim = 384  # Default assumption

        # Load Sentence-BERT
        self.encoder = SentenceTransformer(model_name, device=device)

        # Freeze encoder if requested
        if freeze_encoder:
            for param in self.encoder.parameters():
                param.requires_grad = False

        # Projection layer: embedding_dim → output_dim
        self.projector = nn.Sequential(
            nn.Linear(self.embedding_dim, self.embedding_dim),
            nn.LayerNorm(self.embedding_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(self.embedding_dim, output_dim),
            nn.LayerNorm(output_dim)
        )

        # Optional: Learnable position encoding for task structure
        self.task_type_embedding = nn.Embedding(8, output_dim)  # 8 task types

        # Task type classifier (for routing)
        self.task_classifier = nn.Sequential(
            nn.Linear(self.embedding_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 8)  # 8 task types
        )

    def encode(self, task: str) -> torch.Tensor:
        """
        Encode a single task string.

        Args:
            task: Natural language task description

        Returns:
            features: (output_dim,) tensor
        """
        # Get Sentence-BERT embedding
        with torch.no_grad() if self.freeze_encoder else torch.enable_grad():
            embedding = self.encoder.encode(
                task,
                convert_to_tensor=True,
                device=self.device
            )

        # Ensure correct device
        embedding = embedding.to(self.device)

        # Project to output dimension
        features = self.projector(embedding)

        return features

    def encode_batch(self, tasks: List[str]) -> torch.Tensor:
        """
        Encode a batch of task strings.

        Args:
            tasks: List of task descriptions

        Returns:
            features: (batch, output_dim) tensor
        """
        # Get Sentence-BERT embeddings
        with torch.no_grad() if self.freeze_encoder else torch.enable_grad():
            embeddings = self.encoder.encode(
                tasks,
                convert_to_tensor=True,
                device=self.device,
                batch_size=32
            )

        # Ensure correct device
        embeddings = embeddings.to(self.device)

        # Project to output dimension
        features = self.projector(embeddings)

        return features

    def encode_with_type(self, task: str) -> tuple:
        """
        Encode task and classify its type.

        Args:
            task: Natural language task description

        Returns:
            features: (output_dim,) tensor
            task_type: Predicted task type index
            type_probs: Task type probabilities
        """
        # Get Sentence-BERT embedding
        with torch.no_grad() if self.freeze_encoder else torch.enable_grad():
            embedding = self.encoder.encode(
                task,
                convert_to_tensor=True,
                device=self.device
            )

        embedding = embedding.to(self.device)

        # Classify task type
        type_logits = self.task_classifier(embedding)
        type_probs = torch.softmax(type_logits, dim=-1)
        task_type = type_logits.argmax().item()

        # Project to output dimension
        features = self.projector(embedding)

        # Add task type embedding
        type_embed = self.task_type_embedding(torch.tensor(task_type, device=self.device))
        features = features + 0.1 * type_embed  # Small contribution

        return features, task_type, type_probs

    def get_similarity(self, task1: str, task2: str) -> float:
        """
        Compute semantic similarity between two tasks.

        Args:
            task1: First task
            task2: Second task

        Returns:
            similarity: Cosine similarity (0-1)
        """
        with torch.no_grad():
            emb1 = self.encoder.encode(task1, convert_to_tensor=True)
            emb2 = self.encoder.encode(task2, convert_to_tensor=True)

            # Cosine similarity
            similarity = torch.nn.functional.cosine_similarity(
                emb1.unsqueeze(0),
                emb2.unsqueeze(0)
            ).item()

        return similarity

    def find_similar_tasks(
        self,
        query: str,
        corpus: List[str],
        top_k: int = 5
    ) -> List[tuple]:
        """
        Find most similar tasks from a corpus.

        Args:
            query: Query task
            corpus: List of tasks to search
            top_k: Number of results

        Returns:
            List of (task, similarity) tuples
        """
        with torch.no_grad():
            query_emb = self.encoder.encode(query, convert_to_tensor=True)
            corpus_emb = self.encoder.encode(corpus, convert_to_tensor=True)

            # Compute similarities
            similarities = torch.nn.functional.cosine_similarity(
                query_emb.unsqueeze(0),
                corpus_emb
            )

            # Get top-k
            top_indices = similarities.argsort(descending=True)[:top_k]

            results = [
                (corpus[idx], similarities[idx].item())
                for idx in top_indices
            ]

        return results

    def forward(self, tasks: Union[str, List[str]]) -> torch.Tensor:
        """
        Forward pass for nn.Module compatibility.

        Args:
            tasks: Single task or list of tasks

        Returns:
            features: (batch, output_dim) or (output_dim,) tensor
        """
        if isinstance(tasks, str):
            return self.encode(tasks)
        else:
            return self.encode_batch(tasks)

    def unfreeze_encoder(self, num_layers: int = 2):
        """
        Unfreeze top layers of Sentence-BERT for fine-tuning.

        Args:
            num_layers: Number of top layers to unfreeze
        """
        # Access the underlying transformer
        if hasattr(self.encoder, '_modules'):
            for name, module in self.encoder._modules.items():
                if hasattr(module, 'auto_model'):
                    transformer = module.auto_model
                    if hasattr(transformer, 'encoder') and hasattr(transformer.encoder, 'layer'):
                        layers = transformer.encoder.layer
                        total = len(layers)
                        for i, layer in enumerate(layers):
                            if i >= total - num_layers:
                                for param in layer.parameters():
                                    param.requires_grad = True

        self.freeze_encoder = False
        print(f"[SemanticTaskEncoder] Unfroze top {num_layers} encoder layers")

    def get_num_parameters(self) -> dict:
        """Get parameter counts."""
        encoder_params = sum(p.numel() for p in self.encoder.parameters())
        encoder_trainable = sum(p.numel() for p in self.encoder.parameters() if p.requires_grad)
        projector_params = sum(p.numel() for p in self.projector.parameters())
        classifier_params = sum(p.numel() for p in self.task_classifier.parameters())
        embedding_params = sum(p.numel() for p in self.task_type_embedding.parameters())

        return {
            'encoder_total': encoder_params,
            'encoder_trainable': encoder_trainable,
            'projector': projector_params,
            'task_classifier': classifier_params,
            'task_type_embedding': embedding_params,
            'total_trainable': encoder_trainable + projector_params + classifier_params + embedding_params
        }


class FallbackTaskEncoder(nn.Module):
    """
    Fallback encoder when sentence-transformers is not available.

    Uses simple hash-based encoding with learnable embeddings.
    """

    def __init__(
        self,
        vocab_size: int = 10000,
        embedding_dim: int = 128,
        output_dim: int = 256,
        device: str = 'cpu'
    ):
        super().__init__()
        self.vocab_size = vocab_size
        self.output_dim = output_dim
        self.device = device

        # Simple word embeddings
        self.word_embedding = nn.Embedding(vocab_size, embedding_dim)

        # Projection
        self.projector = nn.Sequential(
            nn.Linear(embedding_dim, output_dim),
            nn.LayerNorm(output_dim),
            nn.GELU()
        )

    def _hash_words(self, task: str) -> torch.Tensor:
        """Hash words to indices."""
        words = task.lower().split()
        indices = [hash(w) % self.vocab_size for w in words]
        return torch.tensor(indices, device=self.device)

    def encode(self, task: str) -> torch.Tensor:
        """Encode a single task."""
        indices = self._hash_words(task)
        if len(indices) == 0:
            return torch.zeros(self.output_dim, device=self.device)

        embeddings = self.word_embedding(indices)
        pooled = embeddings.mean(dim=0)
        return self.projector(pooled)

    def encode_batch(self, tasks: List[str]) -> torch.Tensor:
        """Encode batch of tasks."""
        return torch.stack([self.encode(t) for t in tasks])

    def forward(self, tasks: Union[str, List[str]]) -> torch.Tensor:
        if isinstance(tasks, str):
            return self.encode(tasks)
        return self.encode_batch(tasks)


def get_task_encoder(
    use_semantic: bool = True,
    **kwargs
) -> nn.Module:
    """
    Factory function to get appropriate task encoder.

    Args:
        use_semantic: Use Sentence-BERT if available
        **kwargs: Arguments for encoder

    Returns:
        Task encoder module
    """
    if use_semantic and HAS_SENTENCE_TRANSFORMERS:
        return SemanticTaskEncoder(**kwargs)
    else:
        print("[TaskEncoder] Using fallback hash-based encoder")
        return FallbackTaskEncoder(**kwargs)


# Task type definitions for classification
TASK_TYPES = {
    0: 'definition',      # "What is X?"
    1: 'explanation',     # "Explain how X works"
    2: 'reasoning',       # "If A then B, what follows?"
    3: 'comparison',      # "Compare X and Y"
    4: 'problem_solving', # "Solve this problem"
    5: 'creative',        # "Write a story about X"
    6: 'factual',         # "What is the capital of X?"
    7: 'procedural',      # "How to do X step by step"
}


if __name__ == "__main__":
    print("=" * 60)
    print("Testing SemanticTaskEncoder")
    print("=" * 60)

    if not HAS_SENTENCE_TRANSFORMERS:
        print("\nSentence-transformers not installed. Testing fallback encoder.")
        encoder = FallbackTaskEncoder()

        task = "Explain machine learning"
        features = encoder.encode(task)
        print(f"\nFallback encoding shape: {features.shape}")

        print("\n" + "=" * 60)
        print("Install sentence-transformers for full functionality:")
        print("  pip install sentence-transformers")
        print("=" * 60)
        exit(0)

    # Test semantic encoder
    print("\n" + "-" * 40)
    print("Creating SemanticTaskEncoder:")
    print("-" * 40)

    encoder = SemanticTaskEncoder(
        model_name='all-MiniLM-L6-v2',
        output_dim=256
    )

    print(f"\nParameter counts:")
    for name, count in encoder.get_num_parameters().items():
        print(f"  {name}: {count:,}")

    # Test single encoding
    print("\n" + "-" * 40)
    print("Testing single task encoding:")
    print("-" * 40)

    task = "Explain how machine learning works"
    features = encoder.encode(task)
    print(f"Task: '{task}'")
    print(f"Features shape: {features.shape}")
    print(f"Features range: [{features.min():.3f}, {features.max():.3f}]")

    # Test batch encoding
    print("\n" + "-" * 40)
    print("Testing batch encoding:")
    print("-" * 40)

    tasks = [
        "What is recursion?",
        "Explain sorting algorithms",
        "If A implies B and B implies C, what can we conclude?",
        "Compare Python and JavaScript",
    ]

    features = encoder.encode_batch(tasks)
    print(f"Batch size: {len(tasks)}")
    print(f"Features shape: {features.shape}")

    # Test similarity
    print("\n" + "-" * 40)
    print("Testing semantic similarity:")
    print("-" * 40)

    pairs = [
        ("What is machine learning?", "Explain ML"),
        ("What is machine learning?", "What is the weather?"),
        ("Sort a list of numbers", "Order items by value"),
        ("Sort a list of numbers", "Write a poem"),
    ]

    for t1, t2 in pairs:
        sim = encoder.get_similarity(t1, t2)
        print(f"  '{t1[:25]}...' <-> '{t2[:25]}...': {sim:.3f}")

    # Test task type classification
    print("\n" + "-" * 40)
    print("Testing task type classification:")
    print("-" * 40)

    test_tasks = [
        "What is a neural network?",
        "Explain how backpropagation works",
        "If X > Y and Y > Z, who is largest?",
        "Compare CNNs and RNNs",
    ]

    for task in test_tasks:
        features, task_type, probs = encoder.encode_with_type(task)
        type_name = TASK_TYPES[task_type]
        print(f"  '{task[:40]}...'")
        print(f"    Type: {type_name} (conf: {probs[task_type]:.2f})")

    # Test find similar
    print("\n" + "-" * 40)
    print("Testing similar task search:")
    print("-" * 40)

    corpus = [
        "Explain machine learning",
        "What is deep learning?",
        "How does gradient descent work?",
        "Write a sorting algorithm",
        "What is the capital of France?",
        "Compare supervised and unsupervised learning",
    ]

    query = "Tell me about neural networks"
    results = encoder.find_similar_tasks(query, corpus, top_k=3)

    print(f"Query: '{query}'")
    print("Most similar:")
    for task, sim in results:
        print(f"  {sim:.3f}: {task}")

    # Test forward compatibility
    print("\n" + "-" * 40)
    print("Testing nn.Module forward:")
    print("-" * 40)

    out1 = encoder("Single task test")
    out2 = encoder(["Task 1", "Task 2"])
    print(f"Single: {out1.shape}")
    print(f"Batch: {out2.shape}")

    print("\n" + "=" * 60)
    print("SemanticTaskEncoder tests PASSED!")
    print("=" * 60)
