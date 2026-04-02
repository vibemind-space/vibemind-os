"""
PyTorch wrapper for ATM-R.

Enables differentiable ATM-R routing in PyTorch pipelines.
Supports backpropagation through routing gates.

Usage:
    from atmr_torch import ATMRModule

    # Create PyTorch module
    atmr = ATMRModule(config='configs/default.yaml', adaptive=True)

    # Forward pass
    multimodal_input = {...}  # dict of tensors
    routed_output, gates = atmr(multimodal_input, ctx=ctx_tensor)

    # Use in training loop
    loss.backward()  # gradients flow through routing
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Optional, Tuple, Union

from thalamo_pc_adaptive import ThalamoPC6Adaptive
from thalamo_pc_live import ThalamoPC6
from config_loader import load_config, create_model_from_config


class ATMRModule(nn.Module):
    """
    PyTorch module wrapper for ATM-R.

    Wraps ThalamoPC6 or ThalamoPC6Adaptive in a differentiable PyTorch module.
    Supports backpropagation through gates and routed outputs.
    """

    def __init__(
        self,
        config: Union[str, Dict] = 'configs/default.yaml',
        adaptive: bool = True,
        learnable_routing: bool = True,
        learnable_priors: bool = True,
        device: str = 'cpu'
    ):
        """
        Initialize ATMRModule.

        Args:
            config: Path to config or dict
            adaptive: Use adaptive model (recommended for training)
            learnable_routing: Make routing matrix R learnable via PyTorch
            learnable_priors: Make priors π learnable via PyTorch
            device: 'cpu' or 'cuda'
        """
        super().__init__()

        self.device = device

        # Create underlying ATM-R model
        if isinstance(config, str):
            cfg = load_config(config)
        else:
            cfg = config

        self.atmr = create_model_from_config(cfg, adaptive=adaptive)
        self.adaptive = adaptive

        # Store modality info
        self.modalities = self.atmr.modalities
        self.M = self.atmr.M
        self.d = self.atmr.d

        # Convert routing matrix to PyTorch parameter (if learnable)
        if learnable_routing:
            self.R = nn.Parameter(torch.from_numpy(self.atmr.R).float())
        else:
            self.register_buffer('R', torch.from_numpy(self.atmr.R).float())

        # Convert priors to PyTorch parameter (if learnable)
        if learnable_priors:
            priors_array = np.array([self.atmr.priors[m] for m in self.modalities])
            self.priors = nn.Parameter(torch.from_numpy(priors_array).float())
        else:
            priors_array = np.array([self.atmr.priors[m] for m in self.modalities])
            self.register_buffer('priors', torch.from_numpy(priors_array).float())

        # Input projections (learnable)
        self.input_projs = nn.ModuleDict({
            m: nn.Linear(self.d[m], self.d[m], bias=True)
            for m in self.modalities
        })

        # Initialize from ATM-R weights
        with torch.no_grad():
            for m in self.modalities:
                W = torch.from_numpy(self.atmr.W_in[m]).float()
                b = torch.from_numpy(self.atmr.b[m]).float()
                self.input_projs[m].weight.copy_(W)
                self.input_projs[m].bias.copy_(b)

        self.to(device)

    def forward(
        self,
        x: Dict[str, torch.Tensor],
        ctx: Optional[torch.Tensor] = None,
        return_all: bool = False
    ) -> Union[Tuple[torch.Tensor, torch.Tensor], Dict]:
        """
        Forward pass.

        Args:
            x: Dict mapping modality -> input tensor [batch, dim] or [dim]
            ctx: Context tensor [batch, M] or [M] (optional)
            return_all: Return full state dict (gates, latents, PE, etc.)

        Returns:
            If return_all=False: (routed_output, gates)
                routed_output: [batch, K, max_dim] or [K, max_dim]
                gates: [batch, M] or [M]
            If return_all=True: dict with keys {y, g, v, pe, ...}
        """
        # Determine batch mode
        first_mod = list(x.keys())[0]
        batched = x[first_mod].ndim == 2
        batch_size = x[first_mod].shape[0] if batched else 1

        # Ensure context is provided
        if ctx is None:
            ctx = torch.zeros(batch_size, self.M, device=self.device) if batched else torch.zeros(self.M, device=self.device)

        # Process each sample in batch
        if batched:
            outputs = []
            for i in range(batch_size):
                x_i = {m: x[m][i] for m in x.keys()}
                ctx_i = ctx[i] if ctx.ndim == 2 else ctx
                out_i = self._forward_single(x_i, ctx_i, return_all)
                outputs.append(out_i)

            # Stack batch
            if return_all:
                batched_out = {
                    'y': torch.stack([o['y'] for o in outputs]),
                    'g': torch.stack([o['g'] for o in outputs]),
                    'v': {m: torch.stack([o['v'][m] for o in outputs]) for m in self.modalities},
                    'pe': torch.stack([o['pe'] for o in outputs])
                }
                return batched_out
            else:
                y_batch = torch.stack([o[0] for o in outputs])
                g_batch = torch.stack([o[1] for o in outputs])
                return y_batch, g_batch
        else:
            return self._forward_single(x, ctx, return_all)

    def _forward_single(
        self,
        x: Dict[str, torch.Tensor],
        ctx: torch.Tensor,
        return_all: bool
    ) -> Union[Tuple[torch.Tensor, torch.Tensor], Dict]:
        """Forward pass for single sample."""
        # Project inputs through learnable weights
        v = {}
        for m in self.modalities:
            if m in x:
                x_m = x[m].to(self.device)
                v[m] = torch.tanh(self.input_projs[m](x_m))
            else:
                v[m] = torch.zeros(self.d[m], device=self.device)

        # Compute prediction errors (simple L2 norm for now)
        pe = torch.stack([torch.norm(v[m]) for m in self.modalities])

        # Relevance scores
        activity = torch.stack([torch.norm(v[m]) for m in self.modalities])
        novelty = pe
        priors = self.priors
        context_weight = ctx

        # Combine with beta weights (hardcoded for now, could be learnable)
        beta = torch.tensor([0.3, 0.3, 0.2, 0.2], device=self.device)
        s = beta[0] * activity + beta[1] * novelty + beta[2] * priors + beta[3] * context_weight

        # Softmax gating
        gate_temp = torch.tensor(self.atmr.gate_temp, device=self.device)
        g = torch.softmax(s / gate_temp, dim=0)

        # Routing: y_k = Σ_i g_i R_ki v_i
        max_dim = max(self.d.values())
        v_padded = []
        for i, m in enumerate(self.modalities):
            v_pad = torch.zeros(max_dim, device=self.device)
            v_pad[:self.d[m]] = v[m]
            v_padded.append(v_pad)

        v_stacked = torch.stack(v_padded)  # [M, max_dim]

        # Route to K targets
        y = torch.zeros(self.atmr.K, max_dim, device=self.device)
        for k in range(self.atmr.K):
            y[k] = torch.sum(g.unsqueeze(1) * self.R[k].unsqueeze(1) * v_stacked, dim=0)

        if return_all:
            return {
                'y': y,
                'g': g,
                'v': v,
                'pe': pe
            }
        else:
            return y, g

    def get_gates(self) -> torch.Tensor:
        """Get current gate values (for inspection during training)."""
        # Run dummy forward to get gates
        dummy_x = {m: torch.zeros(self.d[m], device=self.device) for m in self.modalities}
        _, gates = self.forward(dummy_x)
        return gates

    def sync_with_numpy_model(self):
        """Sync PyTorch parameters back to underlying numpy ATM-R model."""
        with torch.no_grad():
            # Sync routing matrix
            self.atmr.R = self.R.cpu().numpy()

            # Sync priors
            for i, m in enumerate(self.modalities):
                self.atmr.priors[m] = self.priors[i].item()

            # Sync input projections
            for m in self.modalities:
                self.atmr.W_in[m] = self.input_projs[m].weight.cpu().numpy()
                self.atmr.b[m] = self.input_projs[m].bias.cpu().numpy()


class ATMRClassifier(nn.Module):
    """
    ATM-R + Classifier for end-to-end training.

    Example:
        model = ATMRClassifier(num_classes=10)
        logits = model(multimodal_input)
        loss = F.cross_entropy(logits, labels)
    """

    def __init__(
        self,
        config: Union[str, Dict] = 'configs/default.yaml',
        num_classes: int = 10,
        adaptive: bool = True,
        hidden_dim: Optional[int] = None,
        device: str = 'cpu'
    ):
        """
        Initialize ATMRClassifier.

        Args:
            config: ATM-R config
            num_classes: Number of output classes
            adaptive: Use adaptive ATM-R
            hidden_dim: Hidden layer dimension (None = direct classification)
            device: 'cpu' or 'cuda'
        """
        super().__init__()

        self.atmr = ATMRModule(config=config, adaptive=adaptive, device=device)

        # Classifier head
        routed_dim = self.atmr.atmr.K * max(self.atmr.d.values())

        if hidden_dim is not None:
            self.classifier = nn.Sequential(
                nn.Linear(routed_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(hidden_dim, num_classes)
            )
        else:
            self.classifier = nn.Linear(routed_dim, num_classes)

        self.to(device)

    def forward(self, x: Dict[str, torch.Tensor], ctx: Optional[torch.Tensor] = None):
        """
        Forward pass.

        Args:
            x: Multimodal input dict
            ctx: Context tensor

        Returns:
            logits: [batch, num_classes]
        """
        # Route through ATM-R
        y, g = self.atmr(x, ctx=ctx)

        # Flatten routed output
        if y.ndim == 3:  # batched
            y_flat = y.view(y.shape[0], -1)
        else:
            y_flat = y.view(-1)

        # Classify
        logits = self.classifier(y_flat)

        return logits

    def get_gates(self) -> torch.Tensor:
        """Get current gate values."""
        return self.atmr.get_gates()


# Example usage
if __name__ == "__main__":
    print("ATM-R PyTorch Wrapper Demo")
    print("=" * 60)

    # Create module
    atmr = ATMRModule(adaptive=True, device='cpu')
    print(f"Created ATMRModule with {atmr.M} modalities")
    print(f"  Modalities: {atmr.modalities}")

    # Dummy input
    batch_size = 4
    x = {
        'vision': torch.randn(batch_size, atmr.d['vision']),
        'audio': torch.randn(batch_size, atmr.d['audio']),
        'touch': torch.zeros(batch_size, atmr.d['touch']),
        'taste': torch.zeros(batch_size, atmr.d['taste']),
        'vestibular': torch.zeros(batch_size, atmr.d['vestibular']),
        'threat': torch.zeros(batch_size, atmr.d['threat'])
    }

    ctx = torch.zeros(batch_size, atmr.M)
    ctx[:, 0] = 1.0  # prefer vision

    # Forward
    y, g = atmr(x, ctx=ctx)

    print(f"\nInput batch size: {batch_size}")
    print(f"Routed output shape: {y.shape}")
    print(f"Gates shape: {g.shape}")
    print(f"Gates (sample 0): {g[0].detach().numpy()}")

    # Test classifier
    print("\n" + "=" * 60)
    print("ATMRClassifier Demo")

    classifier = ATMRClassifier(num_classes=10, device='cpu')
    logits = classifier(x, ctx=ctx)

    print(f"Logits shape: {logits.shape}")
    print(f"Predicted classes: {torch.argmax(logits, dim=1).numpy()}")

    print("\nPyTorch wrapper ready for training!")
