"""
ThoughtDecoder - Text Generation from Thought Vectors

Converts CTM thought vectors into natural language using a fine-tuned
GPT-2 decoder. This is the "mouth" of the system - the CTM "thinks"
and the decoder "speaks".

Architecture:
    Thought Vector (2048) → thought_to_embedding → GPT-2 Prefix (768)
                                                        ↓
                                                  GPT-2 Small (124M)
                                                        ↓
                                                  Generated Text

Training Strategy:
1. Phase A: Freeze GPT-2, only train thought_to_embedding
2. Phase B: Unfreeze top 2 GPT-2 layers
3. Phase C: Optional full fine-tuning or LoRA

Usage:
    from core.thought_decoder import ThoughtDecoder

    decoder = ThoughtDecoder(thought_dim=2048)
    text = decoder.generate(thought_vector)
    print(text)

    # Or for training
    loss = decoder.compute_loss(thought_vectors, target_texts)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

try:
    from transformers import GPT2LMHeadModel, GPT2Tokenizer, GPT2Config
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    print("[ThoughtDecoder] Warning: transformers not installed. Install with: pip install transformers")


class ThoughtToEmbedding(nn.Module):
    """
    Projects thought vector into GPT-2 embedding space.

    The thought vector captures the CTM's reasoning state.
    This module transforms it into a format GPT-2 can use
    as a "prefix" to condition text generation.

    Architecture:
        thought (2048) → Linear → LayerNorm → GELU → Linear → LayerNorm
        Output: (batch, num_prefix_tokens, gpt2_hidden_size)
    """

    def __init__(
        self,
        thought_dim: int = 2048,
        gpt2_hidden_size: int = 768,
        num_prefix_tokens: int = 8,
        dropout: float = 0.1
    ):
        super().__init__()
        self.thought_dim = thought_dim
        self.gpt2_hidden_size = gpt2_hidden_size
        self.num_prefix_tokens = num_prefix_tokens

        # Project thought to prefix embeddings
        self.projection = nn.Sequential(
            nn.Linear(thought_dim, gpt2_hidden_size * 2),
            nn.LayerNorm(gpt2_hidden_size * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(gpt2_hidden_size * 2, gpt2_hidden_size * num_prefix_tokens),
            nn.LayerNorm(gpt2_hidden_size * num_prefix_tokens)
        )

    def forward(self, thought_vector: torch.Tensor) -> torch.Tensor:
        """
        Convert thought vector to GPT-2 prefix embeddings.

        Args:
            thought_vector: (batch, thought_dim)

        Returns:
            prefix_embeddings: (batch, num_prefix_tokens, gpt2_hidden_size)
        """
        batch_size = thought_vector.size(0)

        # Project and reshape
        prefix_flat = self.projection(thought_vector)
        prefix_embeddings = prefix_flat.view(
            batch_size, self.num_prefix_tokens, self.gpt2_hidden_size
        )

        return prefix_embeddings


class ThoughtDecoder(nn.Module):
    """
    Decodes thought vectors into natural language using GPT-2.

    The thought vector from the CTM is converted to a sequence of
    "prefix embeddings" that condition GPT-2's generation.

    Parameters:
        thought_dim: Dimension of input thought vector (default: 2048)
        model_name: GPT-2 model to use (default: "gpt2")
        num_prefix_tokens: Number of prefix tokens for conditioning
        max_length: Maximum generation length
        device: Torch device
        freeze_gpt2: Whether to freeze GPT-2 weights initially
    """

    def __init__(
        self,
        thought_dim: int = 2048,
        model_name: str = "gpt2",
        num_prefix_tokens: int = 8,
        max_length: int = 256,
        device: str = "cpu",
        freeze_gpt2: bool = True
    ):
        super().__init__()

        if not HAS_TRANSFORMERS:
            raise RuntimeError("transformers package required. Install with: pip install transformers")

        self.thought_dim = thought_dim
        self.model_name = model_name
        self.num_prefix_tokens = num_prefix_tokens
        self.max_length = max_length
        self.device = device
        self.freeze_gpt2 = freeze_gpt2

        # Load GPT-2
        self.tokenizer = GPT2Tokenizer.from_pretrained(model_name)
        self.gpt2 = GPT2LMHeadModel.from_pretrained(model_name)

        # Set pad token
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
            self.gpt2.config.pad_token_id = self.tokenizer.eos_token_id

        # Get GPT-2 config
        self.gpt2_hidden_size = self.gpt2.config.n_embd

        # Thought to embedding projection
        self.thought_to_embedding = ThoughtToEmbedding(
            thought_dim=thought_dim,
            gpt2_hidden_size=self.gpt2_hidden_size,
            num_prefix_tokens=num_prefix_tokens
        )

        # Freeze GPT-2 if requested
        if freeze_gpt2:
            self._freeze_gpt2()

    def _freeze_gpt2(self):
        """Freeze all GPT-2 parameters."""
        for param in self.gpt2.parameters():
            param.requires_grad = False

    def unfreeze_top_layers(self, num_layers: int = 2):
        """
        Unfreeze top N transformer layers for fine-tuning.

        Args:
            num_layers: Number of top layers to unfreeze
        """
        # First freeze everything
        self._freeze_gpt2()

        # Unfreeze top layers
        total_layers = len(self.gpt2.transformer.h)
        for i in range(total_layers - num_layers, total_layers):
            for param in self.gpt2.transformer.h[i].parameters():
                param.requires_grad = True

        # Unfreeze output projection
        for param in self.gpt2.lm_head.parameters():
            param.requires_grad = True

        print(f"[ThoughtDecoder] Unfroze top {num_layers} GPT-2 layers")

    def unfreeze_all(self):
        """Unfreeze all GPT-2 parameters for full fine-tuning."""
        for param in self.gpt2.parameters():
            param.requires_grad = True
        print("[ThoughtDecoder] Unfroze all GPT-2 parameters")

    def forward(
        self,
        thought_vector: torch.Tensor,
        target_ids: Optional[torch.Tensor] = None,
        attention_mask: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass for training.

        Args:
            thought_vector: (batch, thought_dim) thought vectors
            target_ids: (batch, seq_len) target token IDs
            attention_mask: (batch, seq_len) attention mask

        Returns:
            dict with 'loss', 'logits'
        """
        batch_size = thought_vector.size(0)

        # Get prefix embeddings from thought
        prefix_embeds = self.thought_to_embedding(thought_vector)  # (B, P, H)

        # Get GPT-2 word embeddings for targets
        if target_ids is not None:
            target_embeds = self.gpt2.transformer.wte(target_ids)  # (B, T, H)

            # Concatenate prefix + target embeddings
            inputs_embeds = torch.cat([prefix_embeds, target_embeds], dim=1)  # (B, P+T, H)

            # Create attention mask if not provided
            if attention_mask is None:
                attention_mask = torch.ones(batch_size, target_ids.size(1), device=target_ids.device)

            # Extend attention mask for prefix
            prefix_mask = torch.ones(batch_size, self.num_prefix_tokens, device=thought_vector.device)
            full_attention_mask = torch.cat([prefix_mask, attention_mask], dim=1)

            # Create labels: -100 for prefix (ignored), target_ids for rest
            labels = torch.cat([
                torch.full((batch_size, self.num_prefix_tokens), -100, device=target_ids.device),
                target_ids
            ], dim=1)

            # Forward through GPT-2
            outputs = self.gpt2(
                inputs_embeds=inputs_embeds,
                attention_mask=full_attention_mask,
                labels=labels,
                return_dict=True
            )

            return {
                'loss': outputs.loss,
                'logits': outputs.logits
            }
        else:
            # Just return prefix embeddings for generation
            return {'prefix_embeds': prefix_embeds}

    def generate(
        self,
        thought_vector: torch.Tensor,
        max_new_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 50,
        do_sample: bool = True,
        num_return_sequences: int = 1
    ) -> Union[str, List[str]]:
        """
        Generate text from thought vector.

        Args:
            thought_vector: (thought_dim,) or (1, thought_dim) thought vector
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling probability
            top_k: Top-k sampling
            do_sample: Whether to sample (vs greedy)
            num_return_sequences: Number of sequences to generate

        Returns:
            Generated text string or list of strings
        """
        self.eval()

        # Ensure batch dimension
        if thought_vector.dim() == 1:
            thought_vector = thought_vector.unsqueeze(0)

        with torch.no_grad():
            # Get prefix embeddings
            prefix_embeds = self.thought_to_embedding(thought_vector)

            # Use generate with inputs_embeds
            # Create dummy input_ids (just BOS token)
            input_ids = torch.tensor([[self.tokenizer.bos_token_id]], device=thought_vector.device)
            input_embeds = self.gpt2.transformer.wte(input_ids)

            # Concatenate prefix + BOS
            inputs_embeds = torch.cat([prefix_embeds, input_embeds], dim=1)

            # Generate attention mask
            attention_mask = torch.ones(1, inputs_embeds.size(1), device=thought_vector.device)

            # Generate
            outputs = self.gpt2.generate(
                inputs_embeds=inputs_embeds,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                temperature=temperature if do_sample else 1.0,
                top_p=top_p,
                top_k=top_k,
                do_sample=do_sample,
                num_return_sequences=num_return_sequences,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )

            # Decode (skip prefix tokens)
            generated_ids = outputs[:, self.num_prefix_tokens + 1:]  # +1 for BOS
            texts = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)

            if num_return_sequences == 1:
                return texts[0]
            return texts

    def compute_loss(
        self,
        thought_vectors: torch.Tensor,
        target_texts: List[str],
        max_length: int = 128
    ) -> torch.Tensor:
        """
        Compute loss for a batch of thought-text pairs.

        Args:
            thought_vectors: (batch, thought_dim) thought vectors
            target_texts: List of target text strings
            max_length: Maximum sequence length

        Returns:
            loss: Scalar loss tensor
        """
        # Tokenize targets
        tokenized = self.tokenizer(
            target_texts,
            max_length=max_length,
            truncation=True,
            padding='max_length',
            return_tensors='pt'
        )

        target_ids = tokenized['input_ids'].to(thought_vectors.device)
        attention_mask = tokenized['attention_mask'].to(thought_vectors.device)

        # Forward
        outputs = self.forward(thought_vectors, target_ids, attention_mask)

        return outputs['loss']

    def save(self, path: str):
        """Save decoder weights."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save thought_to_embedding
        torch.save(
            self.thought_to_embedding.state_dict(),
            path / "thought_to_embedding.pt"
        )

        # Save GPT-2 if it was fine-tuned
        if not self.freeze_gpt2:
            self.gpt2.save_pretrained(path / "gpt2")
            self.tokenizer.save_pretrained(path / "gpt2")

        # Save config
        config = {
            'thought_dim': self.thought_dim,
            'model_name': self.model_name,
            'num_prefix_tokens': self.num_prefix_tokens,
            'max_length': self.max_length,
            'freeze_gpt2': self.freeze_gpt2
        }
        torch.save(config, path / "config.pt")

        print(f"[ThoughtDecoder] Saved to {path}")

    @classmethod
    def load(cls, path: str, device: str = "cpu") -> 'ThoughtDecoder':
        """Load decoder from saved weights."""
        path = Path(path)

        # Load config
        config = torch.load(path / "config.pt", map_location=device, weights_only=False)

        # Create decoder
        decoder = cls(
            thought_dim=config['thought_dim'],
            model_name=config['model_name'],
            num_prefix_tokens=config['num_prefix_tokens'],
            max_length=config['max_length'],
            device=device,
            freeze_gpt2=config['freeze_gpt2']
        )

        # Load thought_to_embedding
        decoder.thought_to_embedding.load_state_dict(
            torch.load(path / "thought_to_embedding.pt", map_location=device, weights_only=True)
        )

        # Load fine-tuned GPT-2 if exists
        gpt2_path = path / "gpt2"
        if gpt2_path.exists():
            decoder.gpt2 = GPT2LMHeadModel.from_pretrained(gpt2_path)
            decoder.tokenizer = GPT2Tokenizer.from_pretrained(gpt2_path)

        decoder.to(device)
        print(f"[ThoughtDecoder] Loaded from {path}")

        return decoder

    def get_num_parameters(self) -> Dict[str, int]:
        """Get parameter counts."""
        total_gpt2 = sum(p.numel() for p in self.gpt2.parameters())
        trainable_gpt2 = sum(p.numel() for p in self.gpt2.parameters() if p.requires_grad)
        thought_embed = sum(p.numel() for p in self.thought_to_embedding.parameters())

        return {
            'thought_to_embedding': thought_embed,
            'gpt2_total': total_gpt2,
            'gpt2_trainable': trainable_gpt2,
            'total_trainable': thought_embed + trainable_gpt2
        }


if __name__ == "__main__":
    if not HAS_TRANSFORMERS:
        print("Skipping tests - transformers not installed")
        exit(0)

    print("=" * 60)
    print("Testing ThoughtDecoder")
    print("=" * 60)

    # Create decoder
    print("\n" + "-" * 40)
    print("Creating ThoughtDecoder:")
    print("-" * 40)

    decoder = ThoughtDecoder(
        thought_dim=2048,
        model_name="gpt2",
        num_prefix_tokens=8,
        freeze_gpt2=True
    )

    print(f"\nParameter counts:")
    for name, count in decoder.get_num_parameters().items():
        print(f"  {name}: {count:,}")

    # Test generation
    print("\n" + "-" * 40)
    print("Testing generation:")
    print("-" * 40)

    thought = torch.randn(2048)
    print(f"Input thought shape: {thought.shape}")

    generated = decoder.generate(
        thought,
        max_new_tokens=50,
        temperature=0.8
    )
    print(f"\nGenerated text:\n  {generated[:200]}...")

    # Test batch generation
    print("\n" + "-" * 40)
    print("Testing batch forward:")
    print("-" * 40)

    thoughts = torch.randn(2, 2048)
    targets = ["This is a test response about algorithms.", "Another test about data structures."]

    outputs = decoder.compute_loss(thoughts, targets)
    print(f"Loss: {outputs.item():.4f}")

    # Test save/load
    print("\n" + "-" * 40)
    print("Testing save/load:")
    print("-" * 40)

    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    try:
        save_path = Path(temp_dir) / "test_decoder"
        decoder.save(str(save_path))

        loaded = ThoughtDecoder.load(str(save_path))
        print("Load successful!")

        # Verify generation works
        generated2 = loaded.generate(thought, max_new_tokens=20)
        print(f"Loaded decoder generated: {generated2[:100]}...")

    finally:
        shutil.rmtree(temp_dir)

    # Test unfreezing
    print("\n" + "-" * 40)
    print("Testing layer unfreezing:")
    print("-" * 40)

    decoder.unfreeze_top_layers(2)
    print(f"After unfreezing top 2 layers:")
    for name, count in decoder.get_num_parameters().items():
        print(f"  {name}: {count:,}")

    print("\n" + "=" * 60)
    print("ThoughtDecoder tests PASSED!")
    print("=" * 60)
