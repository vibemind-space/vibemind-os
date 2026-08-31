# Tahlamus: Brain-Inspired Cognitive Routing System

**A production-ready brain-inspired cognitive system that learns from conversation traces to predict optimal action sequences and intervention strategies.**

Tahlamus (formerly ATM-R) combines thalamic gating, hippocampal memory, multi-domain continuous thought models (CTM), and LLM-enhanced reasoning to create a self-reflective meta-cognitive architecture. The system has evolved from basic 6-modality routing to a complete cognitive system with 10 modalities, 3-layer hierarchical decision-making, and continuous learning.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## Current Status

✅ **FULLY OPERATIONAL** - Production system with:
- **Unified Brain Architecture**: Single brain instance serving all services
- **5 Microservices**: Unified brain, dashboard, API, swarm, memory
- **Multi-CTM Ensemble**: 4 specialized cognitive domains (spatial, logic, temporal, value)
- **LLM Integration**: DeepSeek R1, Claude 3.5 Sonnet, GPT-4o, Gemini 2.0 Flash
- **AutoGen Swarm**: 14 feature-based cognitive agents
- **Continuous Learning**: Real-time matrix updates from feedback
- **77% Accuracy**: Trained 10×4 routing matrix

## Features

### Core Cognitive Architecture
- **10 Modality Channels**: vision, audio, touch, taste, vestibular, threat, tool_trace, temporal_pattern, error_signal, success_signal
- **3-Layer Hierarchy**: Task features → Path planning → Multi-target decisions
- **Multi-CTM Ensemble**: Domain-specialized continuous thought models
- **Adaptive Learning**: Hebbian learning, predictive coding, homeostatic tuning
- **Memory Systems**: Working, declarative, procedural memory with Supermemory integration
- **Attention & Consciousness**: Selective attention, consciousness metrics
- **Neuromodulation**: Dopamine, serotonin, noradrenaline systems

### Production Features
- **Unified Brain Service**: Central brain instance (port 5003)
- **REST APIs**: 7+ endpoints for predictions, feedback, statistics
- **Web Dashboard**: Real-time brain visualization (port 5000)
- **AutoGen Swarm**: 14 feature-based agents (port 5002)
- **Continuous Learning**: LR=0.005, real-time matrix updates
- **Semantic Coherence**: K_min=0.55, validation before execution

## Quick Setup

### 1. Prerequisites
- Python 3.8+
- Windows OS (for .bat scripts) or Linux/Mac (manual setup)
- API keys from [OpenRouter](https://openrouter.ai/) and [Supermemory](https://supermemory.ai/)

### 2. Installation

```bash
# Clone repository
git clone <your-repo-url>
cd the_brain

# Create virtual environment
python -m venv .venv

# Activate environment
.venv\Scripts\activate.bat  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

**Alternative installations:**
- **Minimal** (core brain only): `pip install -r requirements-minimal.txt`
- **Full** (with PyTorch, JAX): `pip install -r requirements-full.txt`

### 3. Configuration

```bash
# Copy environment template
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac

# Edit .env and add your API keys:
# OPENROUTER_API_KEY=sk-or-v1-your-key-here
# SUPERMEMORY_API_KEY=sk-your-key-here
```

**Required API Keys:**
- **OPENROUTER_API_KEY**: Get from [openrouter.ai](https://openrouter.ai/) - Required for LLM features
- **SUPERMEMORY_API_KEY**: Get from [supermemory.ai](https://supermemory.ai/) - Required for memory features

### 4. Start System

```bash
# One-command startup (Windows)
START_ALL_SERVICES.bat

# Or start services manually:
python production/unified_brain_service.py   # Port 5003 (START FIRST!)
python web/brain_dashboard_server.py         # Port 5000
python web/autonomous_swarm_server.py        # Port 5002
```

### 5. Access Services

- **Brain Dashboard**: http://localhost:5000 - Interactive chat + visualizations
- **Unified Brain**: http://localhost:5003 - Central brain instance
- **Autonomous Swarm**: http://localhost:5002 - 14 brain-feature agents
- **Production API**: http://localhost:5001 - REST API (optional, legacy)

See [SYSTEM_STARTUP_GUIDE.md](SYSTEM_STARTUP_GUIDE.md) for detailed instructions.

## Essential Documentation

**Getting Started:**
- [QUICK_START.md](QUICK_START.md) - Quick setup guide
- [SYSTEM_STARTUP_GUIDE.md](SYSTEM_STARTUP_GUIDE.md) - Detailed startup
- [STRUCTURE.md](STRUCTURE.md) - Repository structure

**Architecture:**
- [CLAUDE.md](CLAUDE.md) - Comprehensive AI assistant guide
- [UNIFIED_BRAIN_SYSTEM.md](UNIFIED_BRAIN_SYSTEM.md) - Unified architecture
- [MULTI_CTM_ENSEMBLE_ARCHITECTURE.md](MULTI_CTM_ENSEMBLE_ARCHITECTURE.md) - Multi-CTM design
- [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) - Backend systems

**Features:**
- [MEMORY_QUICK_START.md](MEMORY_QUICK_START.md) - Memory setup
- [SWARM_QUICKSTART.md](SWARM_QUICKSTART.md) - Swarm setup
- [LLM_ENHANCEMENT_GUIDE.md](LLM_ENHANCEMENT_GUIDE.md) - LLM integration
- [CTM_QUICK_REFERENCE.md](CTM_QUICK_REFERENCE.md) - CTM usage
- [WEB_DASHBOARD_GUIDE.md](WEB_DASHBOARD_GUIDE.md) - Dashboard guide
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - Testing instructions

## Optional Features

### C++ Acceleration (10-100x speedup)

```bash
# Requires Visual Studio Build Tools
python setup/setup_cpp.py build_ext --inplace
```

### Mamba Integration (experimental)

```bash
# See setup/install_mamba_*.bat for instructions
# Requires CUDA toolkit and compilation
```

### PyTorch/JAX (for deep learning)

```bash
pip install -r requirements-full.txt
```

## Quick Start

```python
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from config_loader import load_config, create_model_from_config
import numpy as np

# Load configuration
config = load_config('configs/default.yaml')

# Create adaptive ATM-R
atmr = create_model_from_config(config, adaptive=True)

# Prepare multimodal input
x_t = {
    'vision': np.random.randn(128),
    'audio': np.random.randn(64),
    'touch': np.zeros(32),
    'taste': np.zeros(16),
    'vestibular': np.zeros(16),
    'threat': np.zeros(8)
}

# Context: prefer vision for this task
ctx = np.zeros(6)
ctx[0] = 1.0  # vision index

# Step forward
out = atmr.step(x_t, ctx=ctx, adapt=True)

print("Gates:", out['g'])
print("Routed output shape:", out['y'].shape)
```

## Architecture

ATM-R implements a discrete-time dynamical system inspired by thalamic gating:

### Core Equations

**Thalamic State Update:**
```
v_i[t+1] = (1-α_i)v_i[t] + α_i·f(W_i^in·x_i + W_i^fb·c_i - λ·Σ_j L_ij·v_j + b_i)
```

**Relevance Score:**
```
s_i = β₁‖v_i‖ + β₂·PE_i + β₃·π_i + β₄·ctx_i
```

**Softmax Gating:**
```
g_i = exp(s_i/τ_g) / Σ_j exp(s_j/τ_g)
```

**Routing to K Targets:**
```
y_k = Σ_i g_i·R_ki·v_i
```

### Components

- **Latent States (v_i)**: Each modality maintains a latent representation
- **Gates (g_i)**: Softmax-normalized attention weights
- **TRN Inhibition (L)**: Competitive inhibition matrix
- **Prediction Error (PE_i)**: Novelty signal from predictive coding
- **Priors (π_i)**: Learned importance weights (safety, task relevance)
- **Phase (φ_i)**: Optional Kuramoto oscillators

## Models

### ThalamoPC6 (Base)
Step-based thalamus with fixed parameters. Good for testing and inference.

```python
from thalamo_pc_live import ThalamoPC6

model = ThalamoPC6(
    tau={'vision': 50.0, 'audio': 40.0, ...},
    priors={'vision': 0.2, 'threat': 0.25, ...},
    gate_temp=0.5
)
```

### ThalamoPC6Adaptive
Extends ThalamoPC6 with online learning:
- Hebbian input weight adaptation
- Predictive coding for PE computation
- Homeostatic parameter tuning (π, τ, τ_g)
- Hazard/reward-driven prior adaptation

```python
from thalamo_pc_adaptive import ThalamoPC6Adaptive

model = ThalamoPC6Adaptive(
    lr_input=0.001,
    lr_generative=0.01,
    target_entropy=1.5
)
```

## Usage Examples

### Example 1: Context-Driven Routing

```python
# Co-present vision and audio
x_t = {
    'vision': vision_features,  # e.g., CNN output
    'audio': audio_features,    # e.g., log-mel spectrogram
    # ... other modalities
}

# Task 1: prefer vision
ctx = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
out1 = atmr.step(x_t, ctx=ctx)
print("Vision-focused gates:", out1['g'])

# Task 2: prefer audio
ctx = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
out2 = atmr.step(x_t, ctx=ctx)
print("Audio-focused gates:", out2['g'])
```

### Example 2: Safety Override

```python
# Normal operation
x_normal = {'vision': vis, 'audio': aud, 'threat': np.zeros(8), ...}
out = atmr.step(x_normal)
print("Normal gates:", out['g'])  # vision/audio dominant

# Threat detected!
x_threat = {'vision': vis, 'audio': aud, 'threat': threat_signal, ...}
out = atmr.step(x_threat, hazard={'threat': 1.0})
print("Threat gates:", out['g'])  # threat now dominant
```

### Example 3: Adaptive Learning

```python
# Train with hazard/reward signals
for epoch in range(num_epochs):
    for x_batch, labels in dataloader:
        # Forward
        out = atmr.step(x_batch, adapt=True)

        # Classify
        pred = classifier(out['y'])

        # Reward on correct prediction
        if pred == label:
            atmr.step(x_batch, reward={'vision': 0.1}, adapt=True)
```

## Notebooks

### 01_mnist_atmr.ipynb
MNIST classification with ATM-R routing. Compares ATM-R + classifier vs. baseline.

```bash
jupyter notebook notebooks/01_mnist_atmr.ipynb
```

### 02_multimodal_demo.ipynb
Comprehensive demo with synthetic data for all 6 modalities. Experiments:
1. Single-modality sanity check
2. Context-driven routing
3. Safety override (threat)
4. Adaptive learning dynamics
5. Phase coupling visualization

```bash
jupyter notebook notebooks/02_multimodal_demo.ipynb
```

## Scripts

### run_demo.py
Interactive demo with synthetic data.

```bash
# Standard model, multimodal scenario
python scripts/run_demo.py --steps 200 --plot

# Adaptive model, threat scenario
python scripts/run_demo.py --adaptive --scenario threat --plot

# Context switching
python scripts/run_demo.py --scenario conflict --steps 150 --plot
```

### train_ctm_mnist.py
Train ATM-R on MNIST (standalone, CTM-ready).

```bash
# Standard training
python scripts/train_ctm_mnist.py --n-samples 5000 --plot

# Adaptive training
python scripts/train_ctm_mnist.py --adaptive --n-samples 10000 --plot
```

## Configuration

All parameters are configurable via YAML files (see `configs/default.yaml`):

```yaml
# Modality dimensions
dimensions:
  vision: 128
  audio: 64
  threat: 8

# Time constants (dynamics speed)
tau:
  vision: 50.0
  threat: 20.0  # faster for safety

# Priority priors
priors:
  threat: 0.25  # high baseline

# Gating temperature
gating:
  temperature: 0.5  # lower = sharper selection

# Learning rates (adaptive only)
learning:
  lr_input: 0.001
  lr_prior: 0.0001
  target_entropy: 1.5
```

## Testing

Run unit tests:

```bash
pytest tests/test_core.py -v
```

Tests cover:
- Gate normalization
- Determinism with seeds
- Stability under zero input
- Context switching
- Safety override
- Adaptive parameter bounds
- Config loading

## Logging & Visualization

ATM-R includes comprehensive logging and visualization:

```python
from logger_viz import ATMRLogger, ATMRVisualizer, ATMRMetrics

# Logger
logger = ATMRLogger(log_dir='data/exp', save_interval=10)

# Log each step
for t in range(num_steps):
    out = atmr.step(x_t)
    logger.log_step(t, out['g'], out['pe'], out['v_next'])

# Save to CSV
logger.save_csv()

# Visualize
ATMRVisualizer.plot_gates(logger, atmr.modalities, save_path='gates.png')
ATMRVisualizer.plot_latent_trajectory_3d(logger, 'vision', atmr.modalities)

# Metrics
gates_array = np.array(logger.history['gates'])
purity = ATMRMetrics.routing_purity(gates_array[-1])
entropy = ATMRMetrics.gate_entropy(gates_array[-1])
```

## Metrics

- **Routing Purity**: `max_i g_i` (decisiveness)
- **Gate Entropy**: `-Σ g_i log₂(g_i)` (diversity)
- **Switch Latency**: Time to reallocate after context change
- **Energy Proxy**: Fraction of suppressed channels
- **Stability**: Inverse variance of gates over time

## Integration with Downstream Models

ATM-R is designed to plug into any ML pipeline:

```python
# Example: Integrate with PyTorch model
import torch
import torch.nn as nn

class ATMRClassifier(nn.Module):
    def __init__(self, atmr, num_classes=10):
        super().__init__()
        self.atmr = atmr
        routed_dim = atmr.K * max(atmr.d.values())
        self.classifier = nn.Linear(routed_dim, num_classes)

    def forward(self, multimodal_input):
        # ATM-R routing
        out = self.atmr.step(multimodal_input)
        routed = torch.tensor(out['y'].flatten(), dtype=torch.float32)

        # Classification
        logits = self.classifier(routed)
        return logits
```

## PyTorch Wrapper

ATM-R includes a differentiable PyTorch wrapper for end-to-end training:

```python
from atmr_torch import ATMRModule, ATMRClassifier
import torch

# Create differentiable ATM-R module
atmr = ATMRModule(config='configs/default.yaml', adaptive=True, device='cuda')

# Prepare input (batched)
x = {
    'vision': torch.randn(32, 128),  # batch_size=32
    'audio': torch.randn(32, 64),
    # ... other modalities
}
ctx = torch.zeros(32, 6)
ctx[:, 0] = 1.0  # prefer vision

# Forward pass
routed_output, gates = atmr(x, ctx=ctx)

# Or use end-to-end classifier
classifier = ATMRClassifier(num_classes=10, device='cuda')
logits = classifier(x, ctx=ctx)
loss = F.cross_entropy(logits, labels)
loss.backward()  # gradients flow through routing!
```

**Example: Train on MNIST**

```bash
python examples/train_pytorch_mnist.py --adaptive --epochs 10
```

## C++ Acceleration

For 10-100x speedup on large-scale routing:

```python
from atmr_fast import ThalamoPC6Fast

# Drop-in replacement with C++ backend
model = ThalamoPC6Fast(use_cpp=True)
out = model.step(x_t)  # much faster!
```

**Build C++ extension:**

```bash
python setup_cpp.py build_ext --inplace
```

**Benchmark:**

```bash
python atmr_fast.py  # runs performance comparison
```

## Real-Time Demos

### Webcam Demo
Process webcam video through ATM-R in real-time with gate visualization:

```bash
# Basic demo
python demos/realtime_webcam.py --adaptive --show-gates

# Test threat override (press 't' to trigger)
python demos/realtime_webcam.py --adaptive --camera 0
```

**Features:**
- Real-time CNN feature extraction (MobileNetV2)
- Live gate dynamics visualization
- Threat trigger simulation
- FPS counter

### Microphone Demo
Capture and route audio features in real-time:

```bash
# Terminal mode
python demos/realtime_microphone.py --adaptive --duration 60

# Visual mode (with spectrogram)
python demos/realtime_microphone.py --adaptive --visual

# List available audio devices
python demos/realtime_microphone.py --list-devices
```

**Features:**
- Real-time mel-spectrogram extraction
- Gate timeline visualization
- Frequency analysis

## JAX Wrapper

ATM-R includes a high-performance JAX wrapper with JIT compilation and automatic vectorization:

```python
from atmr_jax import ATMRModule, ATMRClassifier, atmr_forward
import jax
import jax.numpy as jnp

# Functional API (maximum performance)
from atmr_jax import create_atmr_state, atmr_forward

rng = jax.random.PRNGKey(42)
params, state = create_atmr_state(config, rng)

# JIT-compiled forward pass
routed, gates, state = atmr_forward(params, state, x_dict, config, modalities)

# Or use Flax module
model = ATMRModule(config=config)
variables = model.init(rng, x_batch)
routed, gates = model.apply(variables, x_batch, ctx_batch)

# Automatic parallelization with vmap
routed_batch, gates_batch, _ = atmr_forward_batch(params, state, x_batch, config, modalities)
```

**Features:**
- JIT compilation for 2-5x speedup over PyTorch
- `vmap` for automatic parallelization across modalities
- Pure functional API (no side effects)
- Seamless Flax/Optax integration
- First-class TPU support

**Example: Train on MNIST**

```bash
python examples/train_jax_mnist.py --epochs 5
```

## CTM Integration

ATM-R integrates with Continuous Thinking Models (CTM) for multi-step reasoning:

```python
from ctm_integration import CTMReasoner

# Create continuous reasoner
reasoner = CTMReasoner(adaptive=True)

# Perform multi-step reasoning
final_state, thought_trace = reasoner.reason(
    problem="Navigate through mental space",
    initial_visual=initial_state,
    goal=goal_representation,
    steps=50
)

# Access thought stream
for thought in thought_trace:
    print(thought)
```

**CTM Features:**
- **Continuous thinking loop** with adaptive attention
- **Multi-modal reasoning**: Visual, verbal, spatial, value-based
- **Safety interrupts**: Threat channel can halt reasoning
- **Thought tracing**: Natural language reasoning history
- **Adaptive allocation**: ATM-R routes between reasoning modalities

**Example: Run reasoning tasks**

```bash
# Spatial reasoning
python examples/ctm_reasoning_demo.py --task spatial

# Mathematical reasoning
python examples/ctm_reasoning_demo.py --task math

# Safety-critical with interrupts
python examples/ctm_reasoning_demo.py --task safety

# All tasks
python examples/ctm_reasoning_demo.py --task all
```

## Roadmap

- [x] v0.1: Core implementation + logging
- [x] v0.2: Adaptive online learning
- [x] v0.3: Notebooks + demo scripts
- [x] v0.4: PyTorch wrapper
- [x] v0.5: C++ acceleration
- [x] v0.6: Real-time webcam/mic demos
- [x] v0.7: JAX wrapper
- [x] v0.8: CTM integration
- [ ] v0.9: Benchmark suite (routing efficiency, gate purity, switch latency)
- [ ] v1.0: Production deployment (TorchServe, TensorRT, ONNX)
- [ ] v1.1: Robotics examples (ROS integration)
- [ ] v1.2: XR/VR demos (Unity/Unreal)

## Use Cases

- **Robotics**: Sensor fusion with safety prioritization
- **XR/AR/VR**: Multimodal attention for immersive experiences
- **Autonomous Systems**: Context-aware perception
- **Multimodal ML**: Adaptive routing for vision+audio+text models
- **Continuous Reasoning**: Plug ATM-R into CTM or other planning systems

## Safety & Ethics

- **Threat channel** is a control signal, not a moral judgment
- Gate decisions are logged for auditability
- Entropy targets prevent pathological lock-in
- Respects data privacy (anonymize sensor streams)

## Citation

If you use ATM-R in academic work, please cite:

```bibtex
@software{atmr2025,
  author = {ATM-R Project},
  title = {Adaptive Thalamic Multimodal Routing},
  year = {2025},
  url = {https://github.com/yourusername/atmr}
}
```

## License

MIT License - see [LICENSE](LICENSE) file.

## Acknowledgments

Inspired by neuroscience research on thalamic gating, predictive coding, and attention mechanisms.

## Contributing

Contributions welcome! Please:
1. Fork the repo
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Contact

- Issues: [GitHub Issues](https://github.com/yourusername/atmr/issues)
- Discussions: [GitHub Discussions](https://github.com/yourusername/atmr/discussions)

---

**ATM-R**: Make your AI systems attentive, adaptive, and interpretable.
