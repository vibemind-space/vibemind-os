# Tahlamus Quick Start Guide

## 🚀 Start Everything (One Command)

```batch
START_ALL_SERVICES.bat
```

This opens 6 terminal windows with all services running together.

## 📍 Access Points

| Service | URL | What You Can Do |
|---------|-----|-----------------|
| **Brain Dashboard** | http://localhost:5000 | Visualize brain, chat, run simulations |
| **Production API** | http://localhost:5001 | REST API for predictions |
| **Autonomous Swarm** | http://localhost:5002 | Watch multi-agent swarm coordination |
| **Memory API** | http://localhost:8001/docs | API documentation (optional) |

## 🎯 Common Tasks

### Make a Prediction

```bash
curl -X POST http://localhost:5001/predict \
  -H "Content-Type: application/json" \
  -d "{\"task\": \"Deploy with Docker urgently\"}"
```

### Chat with Brain

1. Go to http://localhost:5000
2. Type in chat box
3. Watch brain state change in real-time

### Run Simulation

1. Go to http://localhost:5000
2. Click "Error Accumulation" or "Stuck in Loop"
3. Watch intervention trigger

### Submit Feedback

```bash
curl -X POST http://localhost:5001/feedback \
  -H "Content-Type: application/json" \
  -d "{\"task\": \"Deploy Docker\", \"success\": true, \"user_rating\": 0.9}"
```

### Check System Stats

```bash
curl http://localhost:5001/stats
```

## 🛑 Stop Everything

Close all terminal windows or:

```batch
taskkill /F /FI "WINDOWTITLE eq Tahlamus*"
```

## 🔧 Troubleshooting

**Port in use?**
```batch
netstat -ano | findstr "5001"
taskkill /PID <PID> /F
```

**Services not starting?**
```batch
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

**GPU not detected?**
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

## 📚 Full Documentation

See **`SYSTEM_STARTUP_GUIDE.md`** for complete details about all services, configuration, and advanced features

---

## 🚀 Ready-to-Run Demos

### Basic Demos
```bash
# Quick feature overview
python demos/quick_demo.py

# All CTM use cases (Math, Planning, Creative, Code, Multi-Agent)
python demos/ctm_use_cases.py

# Smart calculator (ATM-R routes to +, -, *, /, ^)
python demos/calculator_with_routing.py

# Root finding (routes to Newton, Bisection, Secant, Brent's)
python demos/root_finding_routing.py

# ODE solvers (routes to Euler, RK2, RK4, Scipy)
python demos/ode_solver_routing.py

# Simple routing example
python demos/simple_routing_example.py
```

### Monitoring & Visualization
```bash
# Web dashboard (opens in browser)
python monitoring/monitor_web.py
# Then visit: http://localhost:5000

# CTM-specific monitoring
python monitoring/monitor_web_ctm.py

# Terminal dashboard
python monitoring/monitor_dashboard.py
```

### Testing
```bash
# All core tests
pytest tests/test_core.py -v

# Validation suite
python tests/validate_atmr.py

# Threat detection diagnostic
python tests/diagnose_threat.py
```

---

## 🧪 Your Own Experiments

### 1. Input Routing Experiment
```bash
python demos/experiment_routing.py
```
**Tests:** Different input combinations (strong vision, strong audio, balanced, etc.)

### 2. Adaptive Learning Experiment
```bash
python demos/experiment_learning.py
```
**Tests:** How the system learns from hazard/reward signals over 100 steps

### 3. Context Switching Experiment
```bash
python demos/experiment_context.py
```
**Tests:** How context vectors influence routing behavior

---

## ⚙️ Custom Configuration

### Edit Your Config
```bash
# Open and edit
notepad configs/my_custom.yaml
```

**Key parameters to experiment with:**
- `gating.temperature`: 0.1 (sharp) to 1.5 (soft)
- `priors`: Baseline importance (sum should ≈ 1.0)
- `tau`: Response speed (lower = faster)
- `dimensions`: Capacity per modality

### Test Your Config
```bash
python test_my_config.py
```

---

## 📊 What Each Component Does

### Core Models

| File | Purpose | Location |
|------|---------|----------|
| `thalamo_pc_live.py` | Base routing model (fixed params) | `core/` |
| `thalamo_pc_adaptive.py` | Adaptive version with learning | `core/` |
| `config_loader.py` | Load YAML configs | `core/` |
| `ctm_integration.py` | Continuous Thinking Models | `core/` |

### Integration Layers

| File | Purpose | Location |
|------|---------|----------|
| `mamba_integration.py` | State Space Model integration (simulation) | `integrations/` |
| `atmr_torch.py` | PyTorch wrapper (differentiable) | `integrations/` |
| `atmr_jax.py` | JAX wrapper (JIT-compiled) | `integrations/` |

### Demos & Applications

| File | Purpose | Location |
|------|---------|----------|
| `calculator_with_routing.py` | Smart calculator demo | `demos/` |
| `root_finding_routing.py` | Root-finding methods routing | `demos/` |
| `ode_solver_routing.py` | ODE solver routing | `demos/` |
| `ctm_use_cases.py` | 5 practical reasoning scenarios | `demos/` |
| `custom_agent_routing.py` | Multi-agent orchestration | `demos/` |

### Production

| File | Purpose | Location |
|------|---------|----------|
| `adaptive_router.py` | Production router with feedback | `production/` |
| `root_finding_production.py` | Full production example (1000 problems) | `production/` |

### Monitoring

| File | Purpose | Location |
|------|---------|----------|
| `monitor_web.py` | Flask web dashboard | `monitoring/` |
| `monitor_web_ctm.py` | CTM-specific dashboard | `monitoring/` |
| `monitor_dashboard.py` | Terminal UI | `monitoring/` |

---

## 🎯 Common Use Cases

### Use Case 1: Production System with Learning (NEW!)
```python
from production.adaptive_router import ProductionRouter, MethodRegistry

# Create router
router = ProductionRouter(name="my_router", learning_rate=0.1)

# Register methods
registry = MethodRegistry()
registry.register('vision', method_a, 'Method A')
registry.register('audio', method_b, 'Method B')

# Training loop
for problem in dataset:
    x = encode_problem(problem, router)
    modality, confidence, _ = router.route(x, adapt=True)
    result, success = registry.execute(modality, problem)
    router.feedback(success, reward=1.0 if success else -0.5)

# Save learned router
router.save()
```

### Use Case 2: Vision-Heavy Application (Demo)
```python
from core.thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np

model = ThalamoPC6Adaptive(seed=42)

# Create vision-dominant input
x = {m: np.zeros(model.d[m]) for m in model.modalities}
x['vision'] = np.random.randn(model.d['vision']) * 2.0

# Process
out = model.step(x, adapt=True)
print(f"Vision gate: {out['g'][0]:.1%}")  # Should be high!
```

### Use Case 3: Task-Specific Routing
```python
# Create context for specific task
ctx = np.zeros(6)  # 6 modalities
ctx[0] = 1.0  # Prefer vision for this task

out = model.step(x, ctx=ctx, adapt=True)
```

### Use Case 4: Safety-Critical System
```python
# Inject threat signal
x['threat'] = threat_detection_output
hazard = {'threat': 1.0}

out = model.step(x, hazard=hazard, adapt=True)
# System learns to prioritize threat channel
```

---

## 📈 Performance Tips

### For Best Performance
1. **Use smaller dimensions** for prototyping (e.g., vision: 64 instead of 256)
2. **Lower gate_temp** (0.2-0.3) for faster, decisive routing
3. **Higher gate_temp** (0.8-1.0) for exploration/diversity
4. **Adjust tau** to match your data frequency

### Memory Usage
- Base model: ~10 MB
- With all modalities (default dims): ~50 MB
- Large config (vision: 512): ~200 MB

### Speed
- **Simulation mode:** ~10 ms/step (CPU)
- **No Mamba:** ~1 ms/step (faster)
- Real Mamba would be: ~0.1 ms/step (GPU) - not available due to compilation issues

---

## 🔧 Troubleshooting

### Tests fail?
```bash
# Check specific test
pytest tests/test_core.py::TestThalamoPC6::test_gate_normalization -v

# Verbose output
pytest tests/test_core.py -vv
```

### Routing not working as expected?
```bash
# Run diagnostic
python diagnose_threat.py
python validate_atmr.py
```

### Want to reset everything?
```python
model.reset_state()  # Resets internal state
# Or create new model
model = ThalamoPC6Adaptive(seed=new_seed)
```

---

## 📚 Documentation Files

- **CLAUDE.md** - Architecture guide for AI assistants
- **README.md** - Full project documentation
- **STATUS.md** - Project roadmap
- **MAMBA_INSTALLATION_FAILED.md** - Mamba installation attempts
- **CTM_QUICK_REFERENCE.md** - CTM integration guide
- **MONITORING_GUIDE.md** - Monitoring setup

---

## 🎮 Next Steps

1. **Try the experiments:**
   ```bash
   python experiment_routing.py
   python experiment_learning.py
   python experiment_context.py
   ```

2. **Create your own config:**
   - Edit `configs/my_custom.yaml`
   - Test with `python test_my_config.py`

3. **Build something:**
   - Use `thalamo_pc_adaptive.py` as base
   - Add your own input processing
   - Integrate with your ML pipeline

4. **Explore monitoring:**
   ```bash
   python monitor_web.py
   # Visit http://localhost:5000
   ```

---

## 💡 Pro Tips

1. **Start simple:** Use `quick_demo.py` to understand basics
2. **Experiment:** Modify configs and see what changes
3. **Monitor:** Use web dashboard to visualize behavior
4. **Test:** Run tests after changes (`pytest`)
5. **Document:** Keep notes on what configs work best for your use case

---

## ✅ System Status

- ✅ **Production System:** Fully functional with real adaptive learning!
- ✅ **ATM-R Core:** Fully Functional
- ✅ **Adaptive Learning:** Working (demos + production)
- ✅ **CTM Integration:** Working
- ✅ **Mamba Integration:** Simulation Mode
- ✅ **Model Persistence:** Save/load working
- ✅ **Feedback Loops:** Implemented and tested
- ⚠️ **Threat Override:** Needs Tuning (see validate_atmr.py)
- ✅ **All Core Tests:** Passing (7/7)

**Latest Update (Oct 14, 2025):**
- 🎉 Production system added with REAL adaptive learning
- 🎉 Feedback-based routing optimization
- 🎉 Model persistence (save/load)
- 🎉 Comprehensive metrics tracking
- 🎉 Tested on 1000 problems: 65% success rate, Newton 95%!

---

**Ready to build!** 🚀

**Quick Links:**
- **Production Guide:** `production/README.md`
- **Production Summary:** `PRODUCTION_SYSTEM.md`
- **Architecture:** `CLAUDE.md`
- **Full Docs:** `README.md`
- **Tests:** `tests/test_core.py`
