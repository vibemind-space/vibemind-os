"""
Transformer-based CTM using Qwen2.5-0.5B as base model.

Replaces custom neural CTM architecture with a pretrained Transformer,
while maintaining CTM-like behavior:
- Iterative reasoning with shared transformer blocks
- Learned halt mechanism (consciousness-like)
- Thought vector output for decoder compatibility

This enables:
- Better language understanding out of the box
- LoRA fine-tuning for domain specialization
- Model merging with mergekit/TIES for unified CTM

Usage:
    from core.transformer_ctm import TransformerCTM

    # Create CTM
    ctm = TransformerCTM(model_name="Qwen/Qwen2.5-0.5B")

    # Reason on task
    output = ctm("Explain recursion", max_iterations=10)
    print(output.thought_vector.shape)  # (1, 2048)
    print(output.converged)  # True/False
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
import math

# Check for transformers library
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig
    from transformers import BitsAndBytesConfig
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    AutoModelForCausalLM = None
    AutoTokenizer = None

# Check for PEFT (LoRA)
try:
    from peft import get_peft_model, LoraConfig, TaskType
    HAS_PEFT = True
except ImportError:
    HAS_PEFT = False


@dataclass
class TransformerCTMOutput:
    """Output from Transformer CTM reasoning."""
    thought_vector: torch.Tensor          # (batch, thought_dim) - for decoder
    predictions: torch.Tensor              # (batch, vocab_size) - next token logits
    certainties: torch.Tensor              # (batch, iterations) - per-step certainty
    consciousness_trajectory: List[float]  # Consciousness over iterations
    converged: bool                        # Did reasoning converge?
    reasoning_steps: int                   # Number of iterations taken
    hidden_states: Optional[torch.Tensor] = None  # Final hidden states


class HaltPredictor(nn.Module):
    """
    Predicts when to halt reasoning (consciousness-like mechanism).

    Similar to ACT (Adaptive Computation Time) but learned from
    certainty signals rather than just residual magnitude.
    """

    def __init__(self, hidden_dim: int, threshold: float = 0.85):
        super().__init__()
        self.threshold = threshold

        # Predict halt probability from hidden state
        self.halt_net = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.GELU(),
            nn.Linear(hidden_dim // 4, 1),
            nn.Sigmoid()
        )

        # Certainty estimation
        self.certainty_net = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.GELU(),
            nn.Linear(hidden_dim // 4, 1),
            nn.Sigmoid()
        )

    def forward(self, hidden_state: torch.Tensor) -> tuple:
        """
        Predict halt probability and certainty.

        Args:
            hidden_state: (batch, hidden_dim) - current reasoning state

        Returns:
            halt_prob: (batch, 1) - probability of halting
            certainty: (batch, 1) - current certainty level
        """
        halt_prob = self.halt_net(hidden_state)
        certainty = self.certainty_net(hidden_state)
        return halt_prob, certainty

    def should_halt(self, hidden_state: torch.Tensor) -> tuple:
        """Check if reasoning should halt."""
        halt_prob, certainty = self.forward(hidden_state)
        should_stop = (certainty.mean() >= self.threshold).item()
        return should_stop, certainty.mean().item()


class ThoughtProjectorTransformer(nn.Module):
    """
    Projects transformer hidden states to thought vector.

    Maps from transformer's hidden_dim to standardized thought_dim (2048)
    for compatibility with ThoughtDecoder.
    """

    def __init__(
        self,
        hidden_dim: int,
        thought_dim: int = 2048,
        num_layers: int = 2
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.thought_dim = thought_dim

        # Multi-layer projection
        layers = []
        current_dim = hidden_dim

        for i in range(num_layers - 1):
            next_dim = (hidden_dim + thought_dim) // 2
            layers.extend([
                nn.Linear(current_dim, next_dim),
                nn.LayerNorm(next_dim),
                nn.GELU(),
                nn.Dropout(0.1)
            ])
            current_dim = next_dim

        layers.append(nn.Linear(current_dim, thought_dim))
        layers.append(nn.LayerNorm(thought_dim))

        self.projector = nn.Sequential(*layers)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """
        Project hidden states to thought vector.

        Args:
            hidden_states: (batch, seq_len, hidden_dim) or (batch, hidden_dim)

        Returns:
            thought_vector: (batch, thought_dim)
        """
        # If sequence, take last token (or mean pool)
        if hidden_states.dim() == 3:
            # Mean pooling over sequence
            hidden_states = hidden_states.mean(dim=1)

        return self.projector(hidden_states)


class IterativeReasoningBlock(nn.Module):
    """
    Shared reasoning block for iterative processing.

    Instead of using different layers per iteration,
    we reuse the same transformer block multiple times
    with residual connections.
    """

    def __init__(self, hidden_dim: int, num_heads: int = 8, dropout: float = 0.1):
        super().__init__()

        # Self-attention for reasoning
        self.self_attn = nn.MultiheadAttention(
            hidden_dim, num_heads, dropout=dropout, batch_first=True
        )

        # Feed-forward
        self.ff = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim * 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.Dropout(dropout)
        )

        self.norm1 = nn.LayerNorm(hidden_dim)
        self.norm2 = nn.LayerNorm(hidden_dim)

        # Iteration embedding
        self.iter_embed = nn.Embedding(100, hidden_dim)

    def forward(
        self,
        hidden_states: torch.Tensor,
        iteration: int,
        attention_mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        One iteration of reasoning.

        Args:
            hidden_states: (batch, seq_len, hidden_dim)
            iteration: Current iteration number
            attention_mask: Optional attention mask

        Returns:
            updated_hidden: (batch, seq_len, hidden_dim)
        """
        batch_size = hidden_states.size(0)

        # Add iteration embedding
        iter_emb = self.iter_embed(
            torch.tensor([iteration], device=hidden_states.device)
        ).unsqueeze(1)
        hidden_states = hidden_states + iter_emb

        # Self-attention
        residual = hidden_states
        hidden_states = self.norm1(hidden_states)
        hidden_states, _ = self.self_attn(
            hidden_states, hidden_states, hidden_states,
            key_padding_mask=attention_mask
        )
        hidden_states = residual + hidden_states

        # Feed-forward
        residual = hidden_states
        hidden_states = self.norm2(hidden_states)
        hidden_states = residual + self.ff(hidden_states)

        return hidden_states


class TransformerCTM(nn.Module):
    """
    Transformer-based Continuous Thought Machine.

    Uses Qwen2.5-0.5B (or similar) as base model with CTM-like
    iterative reasoning on top.

    Architecture:
        Task → Tokenize → Transformer Encoder → Iterative Reasoning Block (×N)
                                                        ↓
                                              Halt Predictor (stop?)
                                                        ↓
                                              Thought Projector → 2048-dim

    Features:
        - Pretrained language understanding from Qwen
        - Iterative reasoning with shared weights
        - Learned halt for adaptive computation
        - Compatible thought vector output
        - LoRA-ready for domain specialization
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-0.5B",
        thought_dim: int = 2048,
        max_iterations: int = 20,
        consciousness_threshold: float = 0.85,
        use_lora: bool = False,
        lora_r: int = 16,
        lora_alpha: int = 32,
        load_in_8bit: bool = False,
        load_in_4bit: bool = False,
        device: str = 'cpu',
        use_flash_attention: bool = False,
        cache_dir: Optional[str] = None
    ):
        super().__init__()

        if not HAS_TRANSFORMERS:
            raise ImportError(
                "transformers library required. Install with: "
                "pip install transformers"
            )

        self.model_name = model_name
        self.thought_dim = thought_dim
        self.max_iterations = max_iterations
        self.consciousness_threshold = consciousness_threshold
        self.device = device
        self.use_lora = use_lora

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True,
            cache_dir=cache_dir
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Quantization config
        quantization_config = None
        if load_in_4bit:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
        elif load_in_8bit:
            quantization_config = BitsAndBytesConfig(load_in_8bit=True)

        # Load base model
        model_kwargs = {
            "trust_remote_code": True,
            "cache_dir": cache_dir,
        }

        if quantization_config:
            model_kwargs["quantization_config"] = quantization_config
            model_kwargs["device_map"] = "auto"

        if use_flash_attention:
            model_kwargs["attn_implementation"] = "flash_attention_2"
            model_kwargs["torch_dtype"] = torch.float16

        self.base_model = AutoModelForCausalLM.from_pretrained(
            model_name,
            **model_kwargs
        )

        # Get hidden dimension from config
        self.hidden_dim = self.base_model.config.hidden_size

        # Apply LoRA if requested
        if use_lora and HAS_PEFT:
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=lora_r,
                lora_alpha=lora_alpha,
                lora_dropout=0.1,
                target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
                bias="none"
            )
            self.base_model = get_peft_model(self.base_model, lora_config)
            print(f"LoRA applied. Trainable params: {self.get_trainable_parameters():,}")

        # CTM components
        self.reasoning_block = IterativeReasoningBlock(
            hidden_dim=self.hidden_dim,
            num_heads=8,
            dropout=0.1
        )

        self.halt_predictor = HaltPredictor(
            hidden_dim=self.hidden_dim,
            threshold=consciousness_threshold
        )

        self.thought_projector = ThoughtProjectorTransformer(
            hidden_dim=self.hidden_dim,
            thought_dim=thought_dim,
            num_layers=2
        )

        # Move to device if not using quantization
        if not quantization_config:
            self.to(device)

    def encode_task(self, task: Union[str, List[str]]) -> Dict[str, torch.Tensor]:
        """
        Encode task string(s) to token IDs.

        Args:
            task: Single task string or list of tasks

        Returns:
            Dict with input_ids and attention_mask
        """
        if isinstance(task, str):
            task = [task]

        encoded = self.tokenizer(
            task,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        )

        return {k: v.to(self.device) for k, v in encoded.items()}

    def get_base_hidden_states(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor
    ) -> torch.Tensor:
        """
        Get hidden states from base transformer.

        Args:
            input_ids: (batch, seq_len)
            attention_mask: (batch, seq_len)

        Returns:
            hidden_states: (batch, seq_len, hidden_dim)
        """
        with torch.no_grad() if not self.training else torch.enable_grad():
            outputs = self.base_model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                output_hidden_states=True,
                return_dict=True
            )

        # Get last hidden state
        return outputs.hidden_states[-1]

    def forward(
        self,
        task: Union[str, List[str], torch.Tensor],
        max_iterations: Optional[int] = None,
        attention_mask: Optional[torch.Tensor] = None,
        return_all_states: bool = False
    ) -> TransformerCTMOutput:
        """
        Full CTM reasoning pass.

        Args:
            task: Task string, list of strings, or pre-encoded input_ids
            max_iterations: Override default max iterations
            attention_mask: Attention mask if task is tensor
            return_all_states: Return hidden states from all iterations

        Returns:
            TransformerCTMOutput with thought_vector and metadata
        """
        max_iters = max_iterations or self.max_iterations

        # Encode task if string
        if isinstance(task, (str, list)):
            encoded = self.encode_task(task)
            input_ids = encoded["input_ids"]
            attention_mask = encoded["attention_mask"]
        else:
            input_ids = task
            if attention_mask is None:
                attention_mask = torch.ones_like(input_ids)

        batch_size = input_ids.size(0)

        # Get initial hidden states from base model
        hidden_states = self.get_base_hidden_states(input_ids, attention_mask)

        # Tracking
        certainties = torch.zeros(batch_size, max_iters, device=self.device)
        consciousness_trajectory = []
        all_hidden_states = [hidden_states] if return_all_states else None

        converged = False
        final_step = max_iters

        # Iterative reasoning
        for step in range(max_iters):
            # Apply reasoning block
            hidden_states = self.reasoning_block(
                hidden_states,
                iteration=step,
                attention_mask=attention_mask == 0  # Convert to key_padding_mask format
            )

            if return_all_states:
                all_hidden_states.append(hidden_states)

            # Get pooled representation for halt decision
            # Use mean pooling over non-padded tokens
            mask_expanded = attention_mask.unsqueeze(-1).float()
            pooled = (hidden_states * mask_expanded).sum(1) / mask_expanded.sum(1)

            # Check halt condition
            should_stop, certainty = self.halt_predictor.should_halt(pooled)

            certainties[:, step] = certainty
            consciousness_trajectory.append(certainty)

            if should_stop:
                converged = True
                final_step = step + 1
                break

        # Final hidden state (mean pooled)
        mask_expanded = attention_mask.unsqueeze(-1).float()
        final_hidden = (hidden_states * mask_expanded).sum(1) / mask_expanded.sum(1)

        # Project to thought vector
        thought_vector = self.thought_projector(final_hidden)

        # Get prediction logits (optional, for language modeling)
        with torch.no_grad():
            predictions = self.base_model.lm_head(hidden_states[:, -1, :])

        return TransformerCTMOutput(
            thought_vector=thought_vector,
            predictions=predictions,
            certainties=certainties[:, :final_step],
            consciousness_trajectory=consciousness_trajectory,
            converged=converged,
            reasoning_steps=final_step,
            hidden_states=torch.stack(all_hidden_states) if return_all_states else None
        )

    def think(self, task: str, max_iterations: Optional[int] = None) -> TransformerCTMOutput:
        """Alias for forward with single task."""
        return self.forward(task, max_iterations=max_iterations)

    def get_num_parameters(self) -> int:
        """Get total number of parameters."""
        return sum(p.numel() for p in self.parameters())

    def get_trainable_parameters(self) -> int:
        """Get number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def freeze_base_model(self):
        """Freeze base transformer weights."""
        for param in self.base_model.parameters():
            param.requires_grad = False

    def unfreeze_base_model(self, layers: Optional[int] = None):
        """
        Unfreeze base transformer weights.

        Args:
            layers: Number of top layers to unfreeze. None = all.
        """
        if layers is None:
            for param in self.base_model.parameters():
                param.requires_grad = True
        else:
            # Unfreeze top N layers
            total_layers = self.base_model.config.num_hidden_layers
            for i, layer in enumerate(self.base_model.model.layers):
                if i >= total_layers - layers:
                    for param in layer.parameters():
                        param.requires_grad = True

    def save_ctm_components(self, path: str):
        """Save only CTM-specific components (not base model)."""
        torch.save({
            'reasoning_block': self.reasoning_block.state_dict(),
            'halt_predictor': self.halt_predictor.state_dict(),
            'thought_projector': self.thought_projector.state_dict(),
            'config': {
                'model_name': self.model_name,
                'thought_dim': self.thought_dim,
                'max_iterations': self.max_iterations,
                'consciousness_threshold': self.consciousness_threshold,
                'hidden_dim': self.hidden_dim
            }
        }, path)

    def load_ctm_components(self, path: str):
        """Load CTM-specific components."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.reasoning_block.load_state_dict(checkpoint['reasoning_block'])
        self.halt_predictor.load_state_dict(checkpoint['halt_predictor'])
        self.thought_projector.load_state_dict(checkpoint['thought_projector'])


class TransformerCTMDistiller:
    """
    Distill knowledge from existing trained CTM to TransformerCTM.

    Uses thought vectors from original CTM as supervision signal.
    """

    def __init__(
        self,
        teacher_ctm: nn.Module,  # Existing HybridCTM
        student_ctm: TransformerCTM,
        device: str = 'cpu'
    ):
        self.teacher = teacher_ctm
        self.student = student_ctm
        self.device = device

        # Freeze teacher
        self.teacher.eval()
        for param in self.teacher.parameters():
            param.requires_grad = False

    def distill_step(
        self,
        tasks: List[str],
        task_encodings: torch.Tensor  # For teacher (board format)
    ) -> Dict[str, float]:
        """
        One distillation step.

        Args:
            tasks: Task strings for student
            task_encodings: Encoded tasks for teacher (e.g., board tensor)

        Returns:
            Dict with loss values
        """
        # Teacher forward
        with torch.no_grad():
            teacher_output = self.teacher(task_encodings)
            teacher_thought = teacher_output.thought_vector
            teacher_certainty = teacher_output.certainties[:, -1]

        # Student forward
        student_output = self.student(tasks)
        student_thought = student_output.thought_vector
        student_certainty = student_output.certainties[:, -1]

        # Thought vector MSE loss
        thought_loss = F.mse_loss(student_thought, teacher_thought)

        # Certainty loss
        certainty_loss = F.mse_loss(student_certainty, teacher_certainty)

        # Cosine similarity loss (encourage same direction)
        cos_sim = F.cosine_similarity(student_thought, teacher_thought, dim=-1)
        cosine_loss = (1 - cos_sim).mean()

        total_loss = thought_loss + 0.1 * certainty_loss + 0.5 * cosine_loss

        return {
            'total_loss': total_loss,
            'thought_loss': thought_loss.item(),
            'certainty_loss': certainty_loss.item(),
            'cosine_loss': cosine_loss.item()
        }


def create_transformer_ctm(
    size: str = 'small',
    domain: Optional[str] = None,
    device: str = 'cpu',
    **kwargs
) -> TransformerCTM:
    """
    Factory function for creating TransformerCTM with preset configs.

    Args:
        size: 'small' (0.5B), 'medium' (1.5B), 'large' (7B)
        domain: Optional domain specialization hint
        device: Torch device
        **kwargs: Override config values

    Returns:
        Configured TransformerCTM instance
    """
    CONFIGS = {
        'small': {
            'model_name': 'Qwen/Qwen2.5-0.5B',
            'max_iterations': 15,
            'consciousness_threshold': 0.85,
        },
        'medium': {
            'model_name': 'Qwen/Qwen2.5-1.5B',
            'max_iterations': 20,
            'consciousness_threshold': 0.85,
        },
        'large': {
            'model_name': 'Qwen/Qwen2.5-7B',
            'max_iterations': 25,
            'consciousness_threshold': 0.80,
            'load_in_4bit': True,  # Quantize for memory
        }
    }

    config = CONFIGS.get(size, CONFIGS['small']).copy()
    config['device'] = device
    config.update(kwargs)

    return TransformerCTM(**config)


if __name__ == "__main__":
    print("=" * 60)
    print("Testing TransformerCTM")
    print("=" * 60)

    if not HAS_TRANSFORMERS:
        print("ERROR: transformers library not installed")
        print("Install with: pip install transformers")
        exit(1)

    # Test with small model (will download if needed)
    print("\nCreating TransformerCTM (this may download the model)...")

    try:
        ctm = TransformerCTM(
            model_name="Qwen/Qwen2.5-0.5B",
            thought_dim=2048,
            max_iterations=10,
            consciousness_threshold=0.85,
            device='cpu'  # Use 'cuda' if available
        )

        print(f"Model loaded successfully!")
        print(f"  Base model: {ctm.model_name}")
        print(f"  Hidden dim: {ctm.hidden_dim}")
        print(f"  Thought dim: {ctm.thought_dim}")
        print(f"  Total params: {ctm.get_num_parameters():,}")
        print(f"  Trainable params: {ctm.get_trainable_parameters():,}")

        # Test forward pass
        print("\nTesting forward pass...")
        task = "Explain what recursion is in programming"

        output = ctm.think(task, max_iterations=5)

        print(f"  Task: {task}")
        print(f"  Thought vector shape: {output.thought_vector.shape}")
        print(f"  Reasoning steps: {output.reasoning_steps}")
        print(f"  Converged: {output.converged}")
        print(f"  Final certainty: {output.consciousness_trajectory[-1]:.3f}")

        # Test batch
        print("\nTesting batch processing...")
        tasks = [
            "What is machine learning?",
            "Explain the concept of gravity",
            "How do neural networks work?"
        ]

        output = ctm(tasks, max_iterations=5)
        print(f"  Batch size: {len(tasks)}")
        print(f"  Thought vectors shape: {output.thought_vector.shape}")

        # Test save/load
        print("\nTesting save/load CTM components...")
        ctm.save_ctm_components("test_ctm_components.pt")
        ctm.load_ctm_components("test_ctm_components.pt")
        print("  Save/load successful!")

        # Cleanup
        import os
        os.remove("test_ctm_components.pt")

        print("\n" + "=" * 60)
        print("TransformerCTM tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")
        print("\nNote: This test requires downloading Qwen2.5-0.5B (~1GB)")
        print("Make sure you have internet connection and sufficient disk space.")
