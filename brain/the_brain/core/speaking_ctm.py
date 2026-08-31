"""
SpeakingCTM - Complete CTM + Text Decoder System

Combines the HybridCTM (brain) with the ThoughtDecoder (mouth) to create
a complete system that can think AND speak without external LLM calls.

Architecture:
    Task → Encoder → HybridCTM (thinking) → ThoughtProjector → ThoughtDecoder → Text

The SpeakingCTM performs:
1. Task encoding into board representation
2. CTM reasoning with temporal traces and synchronisation
3. Thought vector projection from CTM states
4. Text decoding from thought vector

Usage:
    from core.speaking_ctm import SpeakingCTM

    ctm = SpeakingCTM(
        ctm_checkpoint="data/hybrid_ctm_checkpoints/best_model.pth",
        decoder_checkpoint="data/thought_decoder_checkpoints/"
    )

    result = ctm.think_and_speak("Explain how recursion works")
    print(result['response'])
    print(f"Certainty: {result['certainty']:.2f}")
"""

import torch
import torch.nn as nn
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from dataclasses import dataclass
import hashlib

try:
    from core.hybrid_ctm import HybridNeuroSymbolicCTM, HybridCTMOutput
    from core.thought_decoder import ThoughtDecoder, HAS_TRANSFORMERS
    from core.thought_logger import ThoughtLogger
    from core.semantic_task_encoder import SemanticTaskEncoder, get_task_encoder, HAS_SENTENCE_TRANSFORMERS
except ImportError:
    from hybrid_ctm import HybridNeuroSymbolicCTM, HybridCTMOutput
    from thought_decoder import ThoughtDecoder, HAS_TRANSFORMERS
    from thought_logger import ThoughtLogger
    try:
        from semantic_task_encoder import SemanticTaskEncoder, get_task_encoder, HAS_SENTENCE_TRANSFORMERS
    except ImportError:
        HAS_SENTENCE_TRANSFORMERS = False


@dataclass
class SpeakingCTMOutput:
    """
    Output from SpeakingCTM think_and_speak.

    Attributes:
        response: Generated natural language response
        thought_vector: The intermediate thought representation
        certainty: CTM certainty at end of reasoning
        reasoning_steps: Number of CTM iterations
        consciousness_trajectory: Consciousness values during reasoning
        converged: Whether CTM converged early
        task_encoding: How the task was encoded
    """
    response: str
    thought_vector: torch.Tensor
    certainty: float
    reasoning_steps: int
    consciousness_trajectory: List[float]
    converged: bool
    task_encoding: Optional[Dict[str, Any]] = None


class TaskEncoder(nn.Module):
    """
    Encodes text tasks into CTM-compatible format.

    Since HybridCTM expects (batch, 5, 4) board input,
    this encoder maps text to a pseudo-board representation.

    Uses a simple hash-based encoding for now. In production,
    could use a sentence encoder (BERT, etc.) for richer encoding.
    """

    def __init__(
        self,
        vocab_size: int = 10000,
        embed_dim: int = 64,
        board_size: tuple = (5, 4)
    ):
        super().__init__()
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        self.board_size = board_size

        # Simple character-level embedding + projection to board
        self.char_embed = nn.Embedding(256, embed_dim)  # ASCII range
        self.projection = nn.Linear(embed_dim * 20, board_size[0] * board_size[1])

    def forward(self, text: str) -> torch.Tensor:
        """
        Encode text task to board representation.

        Args:
            text: Task text string

        Returns:
            board: (1, 5, 4) tensor
        """
        # Convert text to character indices (truncate/pad to 20 chars)
        chars = [ord(c) % 256 for c in text[:20]]
        while len(chars) < 20:
            chars.append(0)

        char_tensor = torch.tensor([chars])  # (1, 20)

        # Embed and project
        embedded = self.char_embed(char_tensor)  # (1, 20, embed_dim)
        flat = embedded.view(1, -1)  # (1, 20 * embed_dim)
        projected = self.projection(flat)  # (1, 20)

        # Reshape to board and quantize to 0-10 range
        board = projected.view(1, *self.board_size)  # (1, 5, 4)
        board = torch.sigmoid(board) * 10
        board = board.long()

        return board

    def encode_hash(self, text: str) -> torch.Tensor:
        """
        Deterministic hash-based encoding (no learning required).

        Useful for inference when we want consistent encoding.
        """
        # Hash text to get deterministic values
        hash_bytes = hashlib.sha256(text.encode()).digest()
        values = [b % 11 for b in hash_bytes[:20]]  # 0-10 range

        board = torch.tensor(values).view(1, 5, 4)
        return board


class SpeakingCTM(nn.Module):
    """
    Complete CTM + Decoder system for autonomous text generation.

    Brain (HybridCTM) + Mouth (ThoughtDecoder) = Speaking System

    This system can:
    1. Accept natural language tasks
    2. Perform multi-step reasoning via CTM
    3. Generate natural language responses
    4. Optionally log thought-response pairs for training

    Parameters:
        ctm_checkpoint: Path to HybridCTM checkpoint (optional)
        decoder_checkpoint: Path to ThoughtDecoder checkpoint (optional)
        feature_dim: CTM feature dimension
        thought_dim: Thought vector dimension
        max_iterations: Maximum CTM iterations
        consciousness_threshold: Early stopping threshold
        enable_logging: Whether to log thought-response pairs
        log_dir: Directory for logging
        device: Torch device
    """

    def __init__(
        self,
        ctm_checkpoint: Optional[str] = None,
        decoder_checkpoint: Optional[str] = None,
        feature_dim: int = 256,
        thought_dim: int = 2048,
        max_iterations: int = 30,
        consciousness_threshold: float = 0.85,
        enable_logging: bool = False,
        log_dir: str = "data/thought_corpus",
        use_semantic_encoding: bool = False,
        semantic_model: str = 'all-MiniLM-L6-v2',
        device: str = "cpu"
    ):
        super().__init__()

        if not HAS_TRANSFORMERS:
            raise RuntimeError("transformers required for SpeakingCTM. Install with: pip install transformers")

        self.device = device
        self.feature_dim = feature_dim
        self.thought_dim = thought_dim
        self.max_iterations = max_iterations
        self.enable_logging = enable_logging
        self.use_semantic_encoding = use_semantic_encoding

        # Task encoder - semantic (Sentence-BERT) or simple hash-based
        if use_semantic_encoding and HAS_SENTENCE_TRANSFORMERS:
            self.semantic_encoder = SemanticTaskEncoder(
                model_name=semantic_model,
                output_dim=feature_dim,
                device=device
            )
            self.task_encoder = TaskEncoder()  # Fallback for board encoding
            print(f"[SpeakingCTM] Using SemanticTaskEncoder ({semantic_model})")
        else:
            self.semantic_encoder = None
            self.task_encoder = TaskEncoder()
            if use_semantic_encoding and not HAS_SENTENCE_TRANSFORMERS:
                print("[SpeakingCTM] Warning: sentence-transformers not installed, using hash encoder")

        # Brain: HybridCTM with thought projection
        self.ctm = HybridNeuroSymbolicCTM(
            feature_dim=feature_dim,
            iterations=max_iterations,
            consciousness_threshold=consciousness_threshold,
            enable_thought_projection=True,
            thought_dim=thought_dim,
            device=device
        )

        # Load CTM checkpoint if provided
        if ctm_checkpoint:
            self._load_ctm_checkpoint(ctm_checkpoint)

        # Initialize lazy modules
        self._initialize_lazy_modules()

        # Mouth: ThoughtDecoder
        self.decoder = ThoughtDecoder(
            thought_dim=thought_dim,
            model_name="gpt2",
            num_prefix_tokens=8,
            device=device,
            freeze_gpt2=True
        )

        # Load decoder checkpoint if provided
        if decoder_checkpoint:
            self.decoder = ThoughtDecoder.load(decoder_checkpoint, device)

        # Optional logging
        self.logger = None
        if enable_logging:
            self.logger = ThoughtLogger(log_dir=log_dir)
            self.logger.start_session("speaking_ctm")

        # Move to device
        self.to(device)

    def _initialize_lazy_modules(self):
        """Initialize lazy modules in CTM with dummy forward pass."""
        dummy_board = torch.randint(0, 11, (1, 5, 4)).to(self.device)
        with torch.no_grad():
            _ = self.ctm(dummy_board, max_iterations=1)

    def _load_ctm_checkpoint(self, path: str):
        """Load CTM from checkpoint."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        if 'model_state_dict' in checkpoint:
            self.ctm.load_state_dict(checkpoint['model_state_dict'])
        else:
            self.ctm.load_state_dict(checkpoint)
        print(f"[SpeakingCTM] Loaded CTM from {path}")

    def think(
        self,
        task: str,
        max_iterations: Optional[int] = None
    ) -> HybridCTMOutput:
        """
        Perform CTM reasoning on a task without generating text.

        Args:
            task: Natural language task
            max_iterations: Override default max iterations

        Returns:
            HybridCTMOutput with thought_vector
        """
        # Encode task - use semantic encoding if available
        if self.semantic_encoder is not None:
            # Get semantic features
            semantic_features = self.semantic_encoder.encode(task).to(self.device)
            # Also get board encoding for CTM compatibility
            board = self.task_encoder.encode_hash(task).to(self.device)
            # Run CTM with semantic features
            with torch.no_grad():
                output = self.ctm(
                    board,
                    max_iterations=max_iterations,
                    semantic_features=semantic_features.unsqueeze(0)  # Add batch dim
                )
        else:
            # Traditional hash-based encoding
            board = self.task_encoder.encode_hash(task).to(self.device)
            with torch.no_grad():
                output = self.ctm(board, max_iterations=max_iterations)

        return output

    def speak(
        self,
        thought_vector: torch.Tensor,
        max_new_tokens: int = 128,
        temperature: float = 0.7
    ) -> str:
        """
        Generate text from thought vector.

        Args:
            thought_vector: (thought_dim,) or (1, thought_dim) tensor
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Generated text string
        """
        return self.decoder.generate(
            thought_vector,
            max_new_tokens=max_new_tokens,
            temperature=temperature
        )

    def think_and_speak(
        self,
        task: str,
        max_iterations: Optional[int] = None,
        max_new_tokens: int = 128,
        temperature: float = 0.7,
        log: bool = True
    ) -> SpeakingCTMOutput:
        """
        Complete thinking and speaking pipeline.

        Args:
            task: Natural language task/query
            max_iterations: Override default CTM iterations
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            log: Whether to log this interaction

        Returns:
            SpeakingCTMOutput with response and reasoning info
        """
        # Think
        ctm_output = self.think(task, max_iterations)

        # Speak
        response = self.speak(
            ctm_output.thought_vector,
            max_new_tokens=max_new_tokens,
            temperature=temperature
        )

        # Create output
        encoding_method = 'semantic' if self.semantic_encoder is not None else 'hash'
        output = SpeakingCTMOutput(
            response=response,
            thought_vector=ctm_output.thought_vector.squeeze(0),
            certainty=ctm_output.certainties[:, -1].mean().item(),
            reasoning_steps=ctm_output.reasoning_steps,
            consciousness_trajectory=ctm_output.consciousness_trajectory,
            converged=ctm_output.converged,
            task_encoding={'method': encoding_method}
        )

        # Optional logging
        if log and self.logger is not None:
            self.logger.log(
                thought_vector=ctm_output.thought_vector,
                llm_response=response,
                task=task,
                certainty=output.certainty,
                reasoning_steps=output.reasoning_steps
            )

        return output

    def train_decoder(
        self,
        corpus_path: str,
        epochs: int = 5,
        batch_size: int = 8,
        learning_rate: float = 1e-4,
        unfreeze_layers: int = 0
    ) -> Dict[str, List[float]]:
        """
        Train the decoder on collected thought-response pairs.

        Args:
            corpus_path: Path to thought corpus
            epochs: Number of training epochs
            batch_size: Training batch size
            learning_rate: Learning rate
            unfreeze_layers: Number of GPT-2 layers to unfreeze (0=none)

        Returns:
            Training history dict
        """
        from torch.utils.data import DataLoader
        from core.thought_logger import ThoughtCorpusDataset

        # Load corpus
        corpus = ThoughtLogger.load_corpus(corpus_path)
        if not corpus:
            raise ValueError(f"No data found in {corpus_path}")

        print(f"[SpeakingCTM] Loaded {len(corpus)} training pairs")

        # Create dataset and loader
        dataset = ThoughtCorpusDataset(corpus, self.decoder.tokenizer)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        # Optionally unfreeze GPT-2 layers
        if unfreeze_layers > 0:
            self.decoder.unfreeze_top_layers(unfreeze_layers)

        # Optimizer
        optimizer = torch.optim.AdamW(
            [p for p in self.decoder.parameters() if p.requires_grad],
            lr=learning_rate
        )

        # Training loop
        self.decoder.train()
        history = {'loss': []}

        for epoch in range(epochs):
            epoch_loss = 0
            for batch in loader:
                thoughts = batch['thought_vector'].to(self.device)
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)

                optimizer.zero_grad()
                outputs = self.decoder(thoughts, input_ids, attention_mask)
                loss = outputs['loss']
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(loader)
            history['loss'].append(avg_loss)
            print(f"[SpeakingCTM] Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}")

        return history

    def save(self, path: str):
        """Save complete SpeakingCTM."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save CTM
        torch.save(self.ctm.state_dict(), path / "ctm.pt")

        # Save decoder
        self.decoder.save(str(path / "decoder"))

        # Save task encoder
        torch.save(self.task_encoder.state_dict(), path / "task_encoder.pt")

        # Save semantic encoder if present
        if self.semantic_encoder is not None:
            torch.save(self.semantic_encoder.projector.state_dict(), path / "semantic_projector.pt")
            torch.save(self.semantic_encoder.task_classifier.state_dict(), path / "semantic_classifier.pt")
            torch.save(self.semantic_encoder.task_type_embedding.state_dict(), path / "semantic_type_embed.pt")

        # Save config
        config = {
            'feature_dim': self.feature_dim,
            'thought_dim': self.thought_dim,
            'max_iterations': self.max_iterations,
            'device': self.device,
            'use_semantic_encoding': self.use_semantic_encoding,
            'semantic_model': self.semantic_encoder.model_name if self.semantic_encoder else None
        }
        torch.save(config, path / "config.pt")

        print(f"[SpeakingCTM] Saved to {path}")

    @classmethod
    def load(cls, path: str, device: str = "cpu") -> 'SpeakingCTM':
        """Load SpeakingCTM from saved checkpoint."""
        path = Path(path)

        # Load config
        config = torch.load(path / "config.pt", map_location=device, weights_only=False)

        # Create instance
        ctm = cls(
            feature_dim=config['feature_dim'],
            thought_dim=config['thought_dim'],
            max_iterations=config['max_iterations'],
            device=device,
            enable_logging=False,
            use_semantic_encoding=config.get('use_semantic_encoding', False),
            semantic_model=config.get('semantic_model', 'all-MiniLM-L6-v2')
        )

        # Load CTM
        ctm.ctm.load_state_dict(
            torch.load(path / "ctm.pt", map_location=device, weights_only=False)
        )

        # Load decoder
        ctm.decoder = ThoughtDecoder.load(str(path / "decoder"), device)

        # Load task encoder
        ctm.task_encoder.load_state_dict(
            torch.load(path / "task_encoder.pt", map_location=device, weights_only=False)
        )

        # Load semantic encoder weights if present
        semantic_projector_path = path / "semantic_projector.pt"
        if semantic_projector_path.exists() and ctm.semantic_encoder is not None:
            ctm.semantic_encoder.projector.load_state_dict(
                torch.load(semantic_projector_path, map_location=device, weights_only=False)
            )
            ctm.semantic_encoder.task_classifier.load_state_dict(
                torch.load(path / "semantic_classifier.pt", map_location=device, weights_only=False)
            )
            ctm.semantic_encoder.task_type_embedding.load_state_dict(
                torch.load(path / "semantic_type_embed.pt", map_location=device, weights_only=False)
            )

        ctm.to(device)
        print(f"[SpeakingCTM] Loaded from {path}")

        return ctm

    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics."""
        ctm_params = self.ctm.get_num_parameters()
        decoder_params = self.decoder.get_num_parameters()
        encoder_params = sum(p.numel() for p in self.task_encoder.parameters())

        # Semantic encoder params if present
        semantic_params = 0
        if self.semantic_encoder is not None:
            semantic_info = self.semantic_encoder.get_num_parameters()
            semantic_params = semantic_info.get('total_trainable', 0)

        return {
            'ctm_parameters': ctm_params,
            'decoder_parameters': decoder_params,
            'task_encoder_parameters': encoder_params,
            'semantic_encoder_parameters': semantic_params,
            'use_semantic_encoding': self.use_semantic_encoding,
            'total_parameters': ctm_params + decoder_params['total_trainable'] + encoder_params + semantic_params,
            'feature_dim': self.feature_dim,
            'thought_dim': self.thought_dim,
            'max_iterations': self.max_iterations
        }

    def __del__(self):
        """Cleanup logging session."""
        if self.logger is not None:
            self.logger.end_session()


if __name__ == "__main__":
    if not HAS_TRANSFORMERS:
        print("Skipping tests - transformers not installed")
        exit(0)

    print("=" * 60)
    print("Testing SpeakingCTM")
    print("=" * 60)

    # Create SpeakingCTM
    print("\n" + "-" * 40)
    print("Creating SpeakingCTM:")
    print("-" * 40)

    ctm = SpeakingCTM(
        feature_dim=256,
        thought_dim=2048,
        max_iterations=20,
        consciousness_threshold=0.85,
        enable_logging=False,
        device="cpu"
    )

    print("\nSystem statistics:")
    for key, value in ctm.get_stats().items():
        print(f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}")

    # Test think
    print("\n" + "-" * 40)
    print("Testing think():")
    print("-" * 40)

    task = "Explain how recursion works in programming"
    ctm_output = ctm.think(task)

    print(f"Task: {task}")
    print(f"Thought vector shape: {ctm_output.thought_vector.shape}")
    print(f"Reasoning steps: {ctm_output.reasoning_steps}")
    print(f"Final certainty: {ctm_output.certainties[:, -1].mean().item():.4f}")
    print(f"Converged: {ctm_output.converged}")

    # Test speak
    print("\n" + "-" * 40)
    print("Testing speak():")
    print("-" * 40)

    response = ctm.speak(ctm_output.thought_vector, max_new_tokens=50)
    print(f"Generated response:\n  {response[:200]}...")

    # Test think_and_speak
    print("\n" + "-" * 40)
    print("Testing think_and_speak():")
    print("-" * 40)

    tasks = [
        "What is the capital of France?",
        "Explain machine learning briefly",
        "How do computers work?"
    ]

    for task in tasks:
        result = ctm.think_and_speak(task, max_new_tokens=30, temperature=0.8)
        print(f"\nTask: {task}")
        print(f"  Certainty: {result.certainty:.4f}")
        print(f"  Steps: {result.reasoning_steps}")
        print(f"  Response: {result.response[:100]}...")

    # Test save/load
    print("\n" + "-" * 40)
    print("Testing save/load:")
    print("-" * 40)

    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    try:
        save_path = Path(temp_dir) / "test_speaking_ctm"
        ctm.save(str(save_path))

        loaded = SpeakingCTM.load(str(save_path))
        print("Load successful!")

        # Verify it works
        result = loaded.think_and_speak("Test task", max_new_tokens=20)
        print(f"Loaded CTM response: {result.response[:80]}...")

    finally:
        shutil.rmtree(temp_dir)

    print("\n" + "=" * 60)
    print("SpeakingCTM tests PASSED!")
    print("=" * 60)
