# NeuroSymbolic Klotski Integration - Complete TODO

**Date**: October 25, 2025
**Status**: 🚧 IN PROGRESS
**Goal**: Integrate real Klotski puzzle (25,955-node graph) with NeuroSymbolicBrain (3.7M params, 10 modules) into evolutionary training system

---

## 📋 Overview

Replace fake puzzle system with REAL neurosymbolic components from `learning_engine/klotski/neurosymbolic/`:
- ❌ **Remove**: Simple 8x8 grid with fake positions
- ✅ **Add**: Real 4x5 Klotski with 10 brain-module blocks
- ❌ **Remove**: Simple heuristic Heart/Brain (basic math)
- ✅ **Add**: NeuroSymbolicBrain with 10 neural modules (VIS, AUD, SOM, LAN, DLPFC, OFC, ACC, INS, MTL, DMN)
- ✅ **Keep**: All monitoring, evolutionary training, reproduction system

---

## 🎯 Tasks Breakdown

### Phase 1: Core Integration (Real Puzzle + Real Brain)

#### Task 1.1: Create `core/klotski_dark_mode_coordinator.py` ⏳
**Lines**: ~600
**Priority**: 🔴 CRITICAL
**Dependencies**: None

**What It Does**:
- Wraps 3 instances of `KlotskiGraphEnv` (one per agent)
- Each agent solves identical 4x5 Klotski puzzle with 10 blocks
- Blocks represent brain modules: G(DMN), V(VIS), A(AUD), S(SOM), L(LAN), D(DLPFC), C(ACC), I(INS), M(MTL), O(OFC)
- Real block movements validated by graph (25,955 valid states)
- Connection = all 3 agents reach solved state (G block at exit)
- Communication via neural messages (conversation penalties apply)

**Key Methods**:
```python
class KlotskiDarkModeCoordinator:
    def __init__(self, current_generation, graph_file)
    def reset() -> Dict[str, PuzzleState]
    def step(actions: Dict[str, int]) -> Tuple[Dict, float, bool, Dict]
    def is_path_connected() -> bool  # All 3 solved?
    def get_states() -> Dict[str, PuzzleState]  # Current puzzle states
    def calculate_quality() -> float  # Based on graph distance
```

**Implementation Details**:
- Import: `from learning_engine.klotski.neurosymbolic.environments.klotski_graph_env import KlotskiGraphEnv`
- Import: `from learning_engine.klotski.neurosymbolic.core.puzzle_state import PuzzleState, PuzzlePiece`
- Use real graph: `Klotski-Webpage/data.json` (25,955 nodes)
- Track distances from graph: `node['solution_dist']`
- Quality = `(initial_dist - current_dist) / initial_dist`

**Test Criteria**:
- ✅ 3 puzzles initialize with identical start state
- ✅ Valid moves constrained by graph
- ✅ Connection detected when all 3 solve
- ✅ Quality calculation from graph distance

---

#### Task 1.2: Create `core/neurosymbolic_heart_brain.py` ⏳
**Lines**: ~700
**Priority**: 🔴 CRITICAL
**Dependencies**: Task 1.1

**What It Does**:
- **HeartSystem**: Frozen NeuroSymbolicBrain (pretrained on BFS, 3.7M params, never changes)
- **BrainSystem**: Evolving NeuroSymbolicBrain (same architecture, learns per generation)
- **DualSystemAgent**: Weighted voting (70% Heart, 30% Brain)

**Key Classes**:
```python
class NeuroSymbolicHeartSystem:
    def __init__(self, feature_dim=256, num_actions=40)
    def forward(self, puzzle_state) -> torch.Tensor  # Action probs
    def get_activations() -> Dict[str, float]  # 10 module activations
    def freeze()  # Set requires_grad=False

class NeuroSymbolicBrainSystem:
    def __init__(self, feature_dim=256, num_actions=40)
    def forward(self, puzzle_state) -> torch.Tensor
    def get_activations() -> Dict[str, float]
    def learn_from_episode(states, actions, rewards)  # PPO update
    def reset_for_new_generation()  # Re-initialize weights

class DualSystemAgent:
    def __init__(self, agent_name, heart, brain)
    def decide_action(self, puzzle_state) -> Tuple[int, float, str]
    def get_module_activations() -> Dict[str, float]  # For monitoring
```

**Implementation Details**:
- Import: `from learning_engine.klotski.neurosymbolic.core.neurosymbolic_brain import NeuroSymbolicBrain`
- Import: `from learning_engine.klotski.neurosymbolic.symbolic.allis_rules import AllisRuleEngine`
- Use symbolic rules: Brain outputs filtered by Allis constraints
- Weighted voting: `π_final = 0.70 * π_heart + 0.30 * π_brain`
- Heart frozen after Generation 0 pretraining

**Test Criteria**:
- ✅ Heart brain loads and runs forward pass
- ✅ Brain brain learns from episodes
- ✅ Weighted voting produces valid action
- ✅ Module activations extracted (10 values)
- ✅ Heart weights frozen, Brain weights update

---

#### Task 1.3: Create `core/neurosymbolic_trainer.py` ⏳
**Lines**: ~400
**Priority**: 🟠 HIGH
**Dependencies**: Task 1.2

**What It Does**:
- Wraps PPOTrainer and ImitationTrainer for evolutionary system
- Generation 0: Pretrain Heart from BFS demonstrations
- Generation 1+: Train Brain with PPO per generation

**Key Methods**:
```python
class NeuroSymbolicTrainer:
    def __init__(self, graph_env, heart_brain, device='cpu')

    # Generation 0: Pretrain Heart
    def pretrain_heart_from_bfs(self, num_demos=200, epochs=50)
    def _generate_bfs_demos(self, num_demos) -> List[Demonstration]

    # Generation 1+: Train Brain
    def train_brain_with_ppo(self, brain, episodes=20, max_steps=200)
    def train_brain_with_imitation(self, brain, demos, epochs=10)

    # Helper methods
    def collect_episode(self, brain) -> Tuple[states, actions, rewards]
```

**Implementation Details**:
- Import: `from learning_engine.klotski.neurosymbolic.training.ppo_trainer import PPOTrainer`
- Import: `from learning_engine.klotski.neurosymbolic.training.imitation_trainer import ImitationTrainer`
- Import: `from learning_engine.klotski.neurosymbolic.utils.demonstration_recorder import DemonstrationRecorder`
- BFS demos: Use graph to generate optimal solutions
- PPO: Standard policy gradient training
- Save pretrained Heart weights: `heart_pretrained_gen0.pth`

**Test Criteria**:
- ✅ BFS demonstrations generated from graph
- ✅ Heart pretrained via imitation learning
- ✅ Brain trained via PPO for 20 episodes
- ✅ Heart weights frozen after pretraining

---

### Phase 2: Enhanced Web Dashboard (Stunning Visual Feedback)

#### Task 2.1: Create `web/klotski_dashboard.html` ⏳
**Lines**: ~1200
**Priority**: 🟡 MEDIUM
**Dependencies**: Task 1.1, 1.2

**What It Does**:
- Visual 4x5 puzzle grid for all 3 agents (side-by-side)
- Animated block movements (CSS transitions)
- Neural brain activation heatmap (10 modules)
- Action probability bars (Heart vs Brain)
- Symbolic rules status display
- Connection celebration animation

**Visual Layout**:
```
┌──────────────────────────────────────────────────────────────┐
│              EVOLUTIONARY TRAINING - KLOTSKI PUZZLE          │
├──────────────────────────────────────────────────────────────┤
│  [Beginning Puzzle]  │  [Mid Puzzle]  │  [End Puzzle]        │
│  4x5 grid with       │  4x5 grid with │  4x5 grid with       │
│  10 colored blocks   │  10 blocks     │  10 blocks           │
│  Distance: 81        │  Distance: 45  │  Distance: 92        │
├──────────────────────────────────────────────────────────────┤
│              NEURAL BRAIN ACTIVATION HEATMAP                  │
│  VIS  ████████ 80%     DLPFC ██████ 60%                      │
│  AUD  ███████ 70%      OFC   ████████ 80%                    │
│  SOM  ████ 40%         ACC   ███████ 70%                     │
│  LAN  ██████ 60%       INS   ███ 30%                         │
│  MTL  ████████ 80%     DMN   ██████████ 100%                 │
├──────────────────────────────────────────────────────────────┤
│  ACTION PROBABILITIES │  HEART vs BRAIN DECISION             │
│  Move G down:  25%    │  Heart: 0.70 → Move G down           │
│  Move V right: 20%    │  Brain: 0.30 → Move V right          │
│  Move D left:  15%    │  Final: Move G down (weighted)       │
├──────────────────────────────────────────────────────────────┤
│  METRICS: Gen 2/10 | Episode 45/200 | Connections: 15       │
│  Quality: 85% | Success Rate: 33% | Reward: 127,500         │
└──────────────────────────────────────────────────────────────┘
```

**Block Color Scheme**:
- **G (DMN)**: Purple gradient (integration)
- **V (VIS)**: Blue (sensory visual)
- **A (AUD)**: Yellow (sensory auditory)
- **S (SOM)**: Green (sensory somatosensory)
- **L (LAN)**: Orange (sensory language)
- **D (DLPFC)**: Red (cognitive planning)
- **C (ACC)**: Cyan (cognitive conflict)
- **I (INS)**: Brown (cognitive interoception)
- **M (MTL)**: Teal (memory)
- **O (OFC)**: Pink (value/reward)

**Key Features**:
- Drag blocks manually (debug mode)
- Click block to see module details (Brodmann areas, math type)
- Hover over activation bar to see connections
- Animated "SEX/REPRODUCTION" banner on connection
- Real-time updates via polling (500ms)

**Test Criteria**:
- ✅ 3 puzzles render with correct block positions
- ✅ Blocks animate when moved
- ✅ Heatmap updates with neural activations
- ✅ Action bars show probabilities
- ✅ Connection animation triggers

---

#### Task 2.2: Create `web/klotski_dashboard_server.py` ⏳
**Lines**: ~350
**Priority**: 🟡 MEDIUM
**Dependencies**: Task 2.1

**What It Does**:
- Flask server with neurosymbolic-specific endpoints
- Serve enhanced dashboard HTML
- Provide puzzle state, brain activations, action probs via API

**New API Endpoints**:
```python
GET  /                       # Serve klotski_dashboard.html
GET  /api/training_status    # Overall training metrics
GET  /api/puzzle_states      # 3 puzzle board configurations
GET  /api/brain_activations  # 10-module activations for each agent
GET  /api/action_probs       # Action probabilities (heart/brain/final)
GET  /api/symbolic_rules     # Active Allis rule constraints
POST /api/manual_move        # Manual block movement (debug)
GET  /api/graph_info         # Graph statistics (25,955 nodes, etc.)
```

**JSON Response Example**:
```json
{
  "puzzle_states": {
    "beginning": {
      "blocks": [
        {"id": "G", "x": 1, "y": 0, "w": 2, "h": 2, "module": "DMN", "color": "#9b59b6"},
        {"id": "V", "x": 0, "y": 0, "w": 2, "h": 1, "module": "VIS", "color": "#3498db"},
        ...
      ],
      "distance_to_solution": 81,
      "current_node_hash": "abc123...",
      "solved": false
    }
  },
  "brain_activations": {
    "beginning": {
      "VIS": 0.80, "AUD": 0.70, "SOM": 0.40, "LAN": 0.60,
      "DLPFC": 0.60, "OFC": 0.80, "ACC": 0.70, "INS": 0.30,
      "MTL": 0.80, "DMN": 1.00
    }
  },
  "action_probs": {
    "beginning": {
      "heart_probs": [0.25, 0.20, 0.15, ...],  // 40 moves
      "brain_probs": [0.30, 0.15, 0.10, ...],
      "final_probs": [0.265, 0.185, 0.14, ...],  // Weighted
      "top_moves": [
        {"move": "G down", "prob": 0.265},
        {"move": "V right", "prob": 0.185}
      ]
    }
  }
}
```

**Test Criteria**:
- ✅ Server starts on port 5004
- ✅ Dashboard HTML served correctly
- ✅ All API endpoints return valid JSON
- ✅ Real puzzle data flows to frontend
- ✅ Brain activations update in real-time

---

### Phase 3: Integration & Testing

#### Task 3.1: Modify `core/multi_generational_trainer.py` ⏳
**Lines**: +300 modifications
**Priority**: 🔴 CRITICAL
**Dependencies**: Task 1.1, 1.2, 1.3

**Changes Needed**:

1. **Add imports**:
```python
from core.klotski_dark_mode_coordinator import KlotskiDarkModeCoordinator
from core.neurosymbolic_heart_brain import (
    NeuroSymbolicHeartSystem,
    NeuroSymbolicBrainSystem,
    DualSystemAgent
)
from core.neurosymbolic_trainer import NeuroSymbolicTrainer
```

2. **Add mode flag**:
```python
def __init__(self, ..., neurosymbolic_mode=True, graph_file="Klotski-Webpage/data.json"):
    self.neurosymbolic_mode = neurosymbolic_mode
    self.graph_file = graph_file
```

3. **Update `_train_generation_0`**:
```python
if self.neurosymbolic_mode:
    # Pretrain Heart from BFS
    trainer = NeuroSymbolicTrainer(graph_env, heart_brain)
    trainer.pretrain_heart_from_bfs(num_demos=200, epochs=50)
else:
    # Old system (synthetic + real episodes)
    self.base_system = MaxPerformanceTrainingSystem(...)
```

4. **Update `_freeze_heart_from_gen0`**:
```python
if self.neurosymbolic_mode:
    self.heart_system = NeuroSymbolicHeartSystem()
    self.heart_system.load_state_dict(pretrained_weights)
    self.heart_system.freeze()
else:
    self.heart_system = HeartSystem()
```

5. **Update `_run_multi_generational_evolution`**:
```python
if self.neurosymbolic_mode:
    coordinator = KlotskiDarkModeCoordinator(gen, self.graph_file)
else:
    coordinator = DarkModeCoordinator(gen)
```

6. **Update `_create_dual_system_agents`**:
```python
if self.neurosymbolic_mode:
    brain = NeuroSymbolicBrainSystem()
    agent = DualSystemAgent(agent_name, self.heart_system, brain)
else:
    brain = BrainSystem()
    agent = DualSystemAgent(agent_name, self.heart_system, brain)
```

7. **Update `_run_generation_episodes`**:
```python
# Get action from agent (now returns move index 0-39)
action, confidence, reasoning = agent.decide_action(puzzle_state)

# Execute action on real Klotski
next_states, reward, done, info = coordinator.step(actions)

# Update monitoring with neural data
self._update_monitoring(
    ...,
    brain_activations=agent.get_module_activations(),
    action_probs=agent.get_action_probs()
)
```

**Test Criteria**:
- ✅ Neurosymbolic mode uses real Klotski
- ✅ Simple mode still works (backward compatible)
- ✅ Heart pretrains from BFS in Generation 0
- ✅ Brain trains with PPO in Generation 1+
- ✅ Episodes run with real puzzle solving

---

#### Task 3.2: Modify `demos/run_evolutionary_training.py` ⏳
**Lines**: +100 modifications
**Priority**: 🟡 MEDIUM
**Dependencies**: Task 3.1

**Add CLI Flags**:
```python
parser.add_argument('--neurosymbolic-mode', action='store_true', default=True,
    help='Use real Klotski puzzle with NeuroSymbolicBrain (default)')
parser.add_argument('--simple-mode', action='store_true', default=False,
    help='Use fake puzzle for quick testing')
parser.add_argument('--graph-file', type=str,
    default='Klotski-Webpage/data.json',
    help='Path to Klotski graph JSON')
parser.add_argument('--pretrain-heart', action='store_true', default=True,
    help='Pretrain heart from BFS demonstrations (Generation 0)')
parser.add_argument('--use-ppo', action='store_true', default=True,
    help='Use PPO for brain training')
parser.add_argument('--device', type=str, default='cpu',
    choices=['cpu', 'cuda'], help='Device for neural training')
```

**Update Trainer Creation**:
```python
trainer = MultiGenerationalTrainer(
    max_generations=args.generations,
    episodes_per_generation=args.episodes,
    max_steps_per_episode=args.steps,
    difficulty_multiplier=args.difficulty,
    save_dir=args.save_dir,
    enable_terminal_monitor=not args.no_terminal_monitor,
    enable_web_monitor=args.web_monitor,
    neurosymbolic_mode=not args.simple_mode,  # Default True
    graph_file=args.graph_file
)
```

**Test Criteria**:
- ✅ `--neurosymbolic-mode` flag works
- ✅ `--simple-mode` falls back to old system
- ✅ `--graph-file` specifies custom graph
- ✅ CLI shows mode in startup banner

---

#### Task 3.3: Update Monitoring Integration ⏳
**Lines**: +150 modifications
**Priority**: 🟠 HIGH
**Dependencies**: Task 2.2, 3.1

**Update `web/evolutionary_training_server.py`**:
- Import KlotskiDashboardServer components
- Add neurosymbolic data to global monitor
- Track brain activations, action probs

**Update `core/terminal_monitor.py`**:
- Add module activation display (optional, in "expanded mode")
- Show puzzle distance instead of fake path length

**Update monitoring calls in trainer**:
```python
self._update_monitoring(
    generation=gen,
    episode=ep,
    connected=connected,
    quality=path_quality,

    # NEW: Neurosymbolic data
    puzzle_states=coordinator.get_states(),
    brain_activations=agent.get_module_activations(),
    action_probs=agent.get_action_probs(),
    symbolic_rules=coordinator.get_active_rules()
)
```

**Test Criteria**:
- ✅ Terminal shows real puzzle metrics
- ✅ Web dashboard receives neurosymbolic data
- ✅ Brain activations display correctly
- ✅ Action probabilities update

---

#### Task 3.4: Comprehensive Testing ⏳
**Priority**: 🔴 CRITICAL
**Dependencies**: All above tasks

**Test Suite**:

1. **Unit Tests**:
   - `test_klotski_coordinator.py` - Puzzle loading, moves, connection
   - `test_neurosymbolic_agent.py` - Brain forward pass, learning
   - `test_neurosymbolic_trainer.py` - BFS demos, PPO training

2. **Integration Tests**:
   - Single agent solves one puzzle (5 moves)
   - 3 agents in dark mode (20 episodes)
   - Full evolutionary training (2 generations, 10 episodes)

3. **Visual Tests**:
   - Web dashboard shows real blocks
   - Brain heatmap updates
   - Action bars show correct probs

4. **Performance Tests**:
   - Episode time with 3.7M param brain
   - Memory usage (3 brains × 3.7M params)
   - GPU acceleration if available

**Test Commands**:
```bash
# Unit tests
pytest tests/test_neurosymbolic_integration.py -v

# Quick integration test (simple mode, 2 min)
python -m demos.run_evolutionary_training \
    --simple-mode \
    --generations 2 \
    --episodes 5

# Full neurosymbolic test (real puzzles, 20 min)
python -m demos.run_evolutionary_training \
    --neurosymbolic-mode \
    --pretrain-heart \
    --use-ppo \
    --generations 2 \
    --episodes 10 \
    --web-monitor \
    --device cpu

# GPU accelerated (if available, 10 min)
python -m demos.run_evolutionary_training \
    --neurosymbolic-mode \
    --generations 3 \
    --episodes 20 \
    --device cuda
```

**Success Criteria**:
- ✅ All unit tests pass
- ✅ Integration test completes without errors
- ✅ Web dashboard shows real puzzle solving
- ✅ Terminal monitor displays correct metrics
- ✅ Reproduction events trigger correctly
- ✅ Heart stays frozen, Brain evolves

---

## 📊 Progress Tracking

### File Creation Progress:
- [ ] `core/klotski_dark_mode_coordinator.py` (600 lines)
- [ ] `core/neurosymbolic_heart_brain.py` (700 lines)
- [ ] `core/neurosymbolic_trainer.py` (400 lines)
- [ ] `web/klotski_dashboard.html` (1200 lines)
- [ ] `web/klotski_dashboard_server.py` (350 lines)

### File Modification Progress:
- [ ] `core/multi_generational_trainer.py` (+300 lines)
- [ ] `demos/run_evolutionary_training.py` (+100 lines)
- [ ] `web/evolutionary_training_server.py` (+50 lines)
- [ ] `core/terminal_monitor.py` (+100 lines)

### Testing Progress:
- [ ] Unit tests written
- [ ] Integration tests passing
- [ ] Visual tests verified
- [ ] Performance benchmarks run

### Documentation Progress:
- [x] TODO list created (this file)
- [ ] API documentation updated
- [ ] User guide for neurosymbolic mode
- [ ] Architecture diagram created

---

## 🎯 Success Metrics

### Technical Metrics:
- ✅ Real Klotski puzzle (25,955-node graph) loads and runs
- ✅ NeuroSymbolicBrain (3.7M params, 10 modules) trains and infers
- ✅ 3-agent system solves puzzles independently
- ✅ Heart pretrained from BFS (200 demos, >80% accuracy)
- ✅ Brain learns via PPO (20 episodes, quality improving)
- ✅ Reproduction triggers on successful connection
- ✅ Web dashboard shows real blocks and neural activations

### Performance Metrics:
- Episode time: <5 seconds per episode (CPU)
- Episode time: <1 second per episode (GPU)
- Memory usage: <2GB (3 brains)
- Training time: <30 minutes for 3 generations, 20 episodes

### User Experience Metrics:
- ✅ Beautiful visual feedback (colored blocks, animations)
- ✅ Real-time neural brain visualization (module activations)
- ✅ Understandable romantic metaphor (3 agents finding each other)
- ✅ Exciting reproduction events (celebration animations)

---

## 🚀 Implementation Order

### Day 1 (Core - 6 hours):
1. Create `klotski_dark_mode_coordinator.py` (2 hours)
2. Create `neurosymbolic_heart_brain.py` (2 hours)
3. Create `neurosymbolic_trainer.py` (1 hour)
4. Test: Single agent solves puzzle (1 hour)

### Day 2 (Dashboard - 6 hours):
5. Create `klotski_dashboard.html` (3 hours)
6. Create `klotski_dashboard_server.py` (1 hour)
7. Test: Dashboard shows real puzzle (2 hours)

### Day 3 (Integration - 6 hours):
8. Modify `multi_generational_trainer.py` (2 hours)
9. Modify `run_evolutionary_training.py` (1 hour)
10. Update monitoring integration (1 hour)
11. Comprehensive testing (2 hours)

**Total Estimated Time**: 18 hours (3 days)

---

## 🔧 Technical Notes

### Dependencies:
- PyTorch (for NeuroSymbolicBrain)
- Graph file: `Klotski-Webpage/data.json` (must exist)
- All neurosymbolic modules in `learning_engine/klotski/neurosymbolic/`

### Performance Considerations:
- 3.7M params × 3 agents = 11.1M total params
- Forward pass: ~50ms on CPU, ~5ms on GPU
- Training: PPO requires multiple forward/backward passes
- Consider smaller networks for quick testing

### Backward Compatibility:
- `--simple-mode` flag keeps old fake puzzle system
- All monitoring works with both modes
- Gradual migration: Test components individually

### Known Limitations:
- BFS pretraining requires graph traversal (slow first time)
- PPO training is stochastic (results vary)
- GPU required for fast training (>20 episodes)
- Web dashboard polling at 500ms (may lag with slow episodes)

---

## 📝 Notes

**Why This Integration Matters**:
- Currently using FAKE puzzles (simple 8x8 grid)
- Currently using FAKE brains (basic heuristics)
- User has COMPLETE neurosymbolic system (45+ files) NOT being used!
- This integration activates ALL of it:
  - Real Klotski puzzle with 25,955 states
  - Real neural brain with 10 modules
  - Real symbolic rules (Allis constraints)
  - Real training (BFS imitation + PPO)
  - Stunning visual feedback showing it all!

**User's Feedback**:
> "okay looks good but it's not a klotski puzzle that puzzle should be solved and i think the rest is not involved yet? what i mean is the entrie learning_engine\klotski\neurosymbolic project?"

User is 100% correct - we need to activate the REAL system!

---

## ✅ Completion Checklist

When all tasks complete, verify:
- [ ] Can run: `python -m demos.run_evolutionary_training --neurosymbolic-mode`
- [ ] Web dashboard shows 3 real Klotski puzzles with 10 blocks each
- [ ] Blocks animate when agents make moves
- [ ] Neural brain activation heatmap updates in real-time
- [ ] Action probability bars show Heart vs Brain decisions
- [ ] Terminal monitor shows real puzzle metrics (graph distances)
- [ ] Reproduction events trigger when all 3 solve their puzzles
- [ ] Heart stays frozen (pretrained), Brain evolves per generation
- [ ] All neurosymbolic components activated (not fake placeholders)

**When complete**: User can watch 3 NeuroSymbolicBrains (10 modules, 3.7M params each) solve real Klotski puzzles, find each other, reproduce, and evolve across generations - with stunning visual feedback! 🧩🧠💕

---

**Last Updated**: October 25, 2025
**Next Action**: Start with Task 1.1 (klotski_dark_mode_coordinator.py)