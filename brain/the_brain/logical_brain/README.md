# Logical Brain - Hierarchical Routing Architecture

Kopiert von: `C:\Users\User\Desktop\klotskipuzzle\neurosymbolic\core\`

## 📁 Dateien

### Core Architecture
- **`routed_brain.py`** (739 lines) - Hauptarchitektur
  - `RoutedNeuroSymbolicBrain`: Complete 3-layer system
  - `SensoryATMRouter`: Layer 1 - Sensory → Brain routing
  - `ModuleATMRouter`: Layer 3 - Brain → Output routing
  - `RoutingConfig`: Configuration dataclass

### Dependencies
- **`neurosymbolic_brain.py`** - 10-module brain with K₅/K₃,₃ connectivity
- **`brain_graph.py`** - Graph structure for brain modules
- **`ctm_layer.py`** - Continuous Thinking Model (CTM) integration
- **`puzzle_state.py`** - State representation for Klotski puzzles
- **`state_graph_mapper.py`** - Maps puzzle states to graph

---

## 🏗️ Architecture Overview

### 3-Layer Hierarchical Routing

```
┌─────────────────────────────────────────────────────────────┐
│  INPUT: Board State / Sensory Inputs                        │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: SensoryATMRouter                                  │
│  - 6 sensory modalities → 10 brain modules                  │
│  - Prediction errors (PE_j = ||x_j - G_j @ v_j||)          │
│  - Salience-based gating                                    │
│  - TRN inhibition matrix                                    │
│  - Learnable gate temperature                               │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: NeuroSymbolicBrain                                │
│  - 10 modules: VIS, AUD, SOM, LAN, DLPFC, OFC, ACC,        │
│                INS, MTL, DMN                                │
│  - K₅ graph connectivity                                    │
│  - Symbolic rules + neural processing                       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: ModuleATMRouter                                   │
│  - 10 module outputs → final decision                       │
│  - Adaptive gating based on module PEs                      │
│  - Multi-target routing                                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  OUTPUT: Action logits, value, consciousness                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Concepts to Adapt

### 1. **Learnable Gate Temperature**
```python
self.log_gate_temp = nn.Parameter(torch.log(torch.tensor(gate_temp)))

@property
def gate_temp(self):
    return torch.exp(self.log_gate_temp)
```

**For Tahlamus**: Statt fixed τ_g = 0.5, lernt das System wann sharp vs. soft routing

---

### 2. **Multi-Target Routing Matrix**
```python
self.routing_matrix = nn.Parameter(torch.randn(num_inputs, num_outputs) * 0.1)
routing_weights = torch.matmul(gates, self.routing_matrix)
routing_weights = F.softmax(routing_weights, dim=-1)
```

**For Tahlamus**: Route zu mehreren Interventionen gleichzeitig mit Gewichten

---

### 3. **Prediction Error-Based Routing**
```python
# Generate prediction from prediction vector
v_j = self.predictions[m].unsqueeze(0).expand(batch_size, -1)
x_pred = self.generative_models[m](v_j)

# Prediction error (L2 norm)
pe = torch.norm(x_j - x_pred, dim=-1, keepdim=True)
```

**For Tahlamus**: Jedes modality bekommt eigenen PE

---

### 4. **Online Hebbian Adaptation**
```python
def _adapt_predictions(self, inputs, context):
    with torch.no_grad():
        for m in self.modalities:
            hebbian_input = torch.matmul(self.input_weights[m], x_j)
            update = torch.tanh(hebbian_input)
            self.predictions[m].data = (
                (1 - lr) * self.predictions[m].data + lr * update
            )
```

**For Tahlamus**: Continuous online learning während Conversations

---

## 📊 Integration Plan

### Phase 1: Analysis ✅
- [x] Copy all files to `logical_brain/`
- [ ] Analyze architecture
- [ ] Identify transferable concepts

### Phase 2: Adaptation
- [ ] Adapt SensoryATMRouter for conversation features
- [ ] Integrate learnable gate temperature
- [ ] Add multi-target routing for interventions
- [ ] Implement per-modality prediction errors

### Phase 3: Integration
- [ ] Create HierarchicalConversationSolver
- [ ] Layer 1: TaskFeatureRouter
- [ ] Layer 2: Keep existing PathPlanner
- [ ] Layer 3: DecisionRouter → [terminate, retry, suggest, wait]

### Phase 4: Testing
- [ ] Test on 39 sessions
- [ ] Compare performance vs. baseline
- [ ] Visualize in web dashboard

---

## 🎯 Differences: Klotski vs. Conversations

| Aspect | Klotski Puzzle | Tahlamus Conversations |
|--------|----------------|------------------------|
| **Input** | Board state [5,4] | Task description + session logs |
| **Output** | Action logits (40 moves) | Command sequence + confidence |
| **States** | Board configurations | Conversation states (tools, errors) |
| **Goal** | Move red block to exit | Complete task successfully |
| **Learning** | RL (policy gradients) | Self-supervised (past sessions) |
| **Search** | Not used | A* search through graph |

**Key Insight**: We use the **routing architecture** but not the **puzzle-solving logic**!

---

## 📝 Notes

- Original use case: Solving Klotski sliding block puzzles
- Our use case: Predicting optimal conversation paths
- Adaptation: Keep routing layers, replace brain processing with our PathPlanner

---

## 🔗 Related Files

In main Tahlamus project:
- `core/conversation_graph.py` - Our state space representation
- `core/conversation_path_planner.py` - Our A* search
- `core/meta_router.py` - Our thalamic routing (simpler, NumPy-based)
- `core/hippocampus.py` - Our episodic memory

Integration target:
- Create `core/hierarchical_router.py` combining both approaches
