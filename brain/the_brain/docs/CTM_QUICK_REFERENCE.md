# CTM-ATM-R Quick Reference Card

**Schnellzugriff für CTM Continuous Thought Machines mit ATM-R Routing**

---

## 🚀 Quick Start

```bash
# Demo ausführen
python ctm_use_cases.py

# Dashboard starten
python monitor_web_ctm.py
# -> http://localhost:5001
```

---

## 📦 Use Cases auf einen Blick

| Use Case | Class | Wann verwenden? |
|----------|-------|-----------------|
| 🧮 **Math Reasoning** | `CTMMathReasoner` | Schrittweise Problemlösung, mathematische Aufgaben |
| 🗺️ **Planning** | `CTMPlanner` | Task Decomposition, hierarchisches Planning |
| 🎨 **Creative Solving** | `CTMCreativeSolver` | Exploration, Brainstorming, Innovation |
| 💻 **Code Generation** | `CTMCodeGenerator` | Code-Generierung mit iterativer Verbesserung |
| 🤖 **Agent Orchestration** | `CTMAgentOrchestrator` | Multi-Agent Systeme, dynamisches Routing |

---

## 💡 Code-Snippets

### Math Reasoning
```python
from ctm_use_cases import CTMMathReasoner

reasoner = CTMMathReasoner()
result = reasoner.solve_step_by_step(
    problem="((15 + 7) * 3) - 8 / 2",
    max_steps=15
)
```

### Planning
```python
from ctm_use_cases import CTMPlanner

planner = CTMPlanner()
plan = planner.plan_task(
    goal="Plan a trip from Berlin to Tokyo",
    max_steps=30
)
```

### Creative Solving
```python
from ctm_use_cases import CTMCreativeSolver

solver = CTMCreativeSolver(temperature=0.9)  # 0.3=focused, 0.9=creative
solutions = solver.explore_solutions(
    problem="Design innovative UI",
    iterations=25
)
```

### Code Generation
```python
from ctm_use_cases import CTMCodeGenerator

generator = CTMCodeGenerator()
result = generator.generate_code(
    spec="Implement binary search tree",
    refinement_steps=15
)
```

### Agent Orchestration
```python
from ctm_use_cases import CTMAgentOrchestrator

orchestrator = CTMAgentOrchestrator()
routing = orchestrator.route_task(
    task="Debug security vulnerability",
    task_features={
        'reasoning': reasoning_features,
        'code': code_features,
        'security': security_features,
        # ... other agents
    }
)

# Execute active agents
for agent in routing['active_agents']:
    if agent['should_execute']:  # Priority > 15%
        execute_agent(agent['agent'], task)
```

---

## 🎯 Reasoning Modes (Modalitäten)

| Code | Display Name | Icon | Wann aktiv? |
|------|-------------|------|-------------|
| `vision` | Visual Thinking | 👁️ | Visualisierung, Szenenverständnis |
| `audio` | Verbal Logic | 💬 | Logik, Regeln, Sprache |
| `touch` | Embodied Thinking | 🤲 | Handlung, Interaktion |
| `taste` | Value Reasoning | 💎 | Wert-Schätzung, Entscheidungen |
| `vestibular` | Spatial Thinking | 🧭 | Räumlich, Navigation |
| `threat` | Safety Monitoring | 🛡️ | Sicherheit, Anomalien |

---

## 🔧 Custom Modalitäten erstellen

```python
from thalamo_pc_adaptive import ThalamoPC6Adaptive

router = ThalamoPC6Adaptive(
    modalities=['agent1', 'agent2', 'agent3'],
    dimensions={
        'agent1': 128,   # Feature-Vektor-Größe
        'agent2': 64,
        'agent3': 32
    },
    priors={
        'agent1': 0.5,   # Grundlegende Priorität (summe=1.0)
        'agent2': 0.3,
        'agent3': 0.2
    },
    tau={
        'agent1': 50.0,  # Zeit-Konstante (höher=träger)
        'agent2': 40.0,
        'agent3': 30.0
    },
    seed=42
)
```

**Dimensionen wählen:**
- 128-256: Komplexe Modi (Visual, Reasoning)
- 32-64: Mittlere Modi (Code, Search)
- 8-16: Einfache Modi (Security, Metrics)

**Priors wählen:**
- Höher = grundsätzlich wichtiger
- Summe muss 1.0 ergeben
- Sicherheit oft 0.3-0.5

**Tau wählen:**
- 15-25: Sehr reaktiv (Security, Events)
- 30-45: Normal (Code, Search)
- 50-60: Träge (Reasoning, Analysis)

---

## 📊 Metriken-Schnellreferenz

### Confidence
```python
confidence = np.max(gates)
```
- **< 0.4**: Unsicher
- **0.4-0.7**: Medium
- **0.7-0.9**: Hoch
- **> 0.9**: Konvergiert

### Entropy (Diversität)
```python
entropy = -np.sum((gates + 1e-10) * np.log2(gates + 1e-10))
```
- **< 0.5 bits**: Fokussiert (Exploitation)
- **0.5-1.5 bits**: Balanciert
- **> 1.5 bits**: Divers (Exploration)

### Dominant Mode
```python
dominant = modalities[np.argmax(gates)]
```

---

## ⚙️ ATM-R Parameter

### Basic Step
```python
out = atmr.step(x_t, adapt=True)
# Returns: {'g': gates, 'pe': prediction_errors, 'x_pred': predictions}
```

### Mit Hazard (Warnung)
```python
out = atmr.step(
    x_t,
    hazard={'security': 1.0},  # Verstärke Security-Modus
    adapt=True
)
```

### Mit Reward (Belohnung)
```python
out = atmr.step(
    x_t,
    reward={'reasoning': 0.8},  # Belohne Reasoning-Modus
    adapt=True
)
```

### Mit Context
```python
out = atmr.step(
    x_t,
    ctx={'global_context': context_vector},
    adapt=True
)
```

---

## 🎨 Temperature Guide

| Temperature | Use Case | Beschreibung |
|-------------|----------|--------------|
| 0.1-0.3 | Math, Logic | Sehr fokussiert, präzise |
| 0.4-0.6 | Planning, Code | Balanciert |
| 0.7-0.9 | Creative, Design | Explorativ, kreativ |
| 0.9-1.2 | Brainstorming | Sehr divers |

```python
solver = CTMCreativeSolver(temperature=0.9)
```

---

## 🛑 Konvergenz-Kriterien

### Kriterium 1: Hohe Confidence
```python
if np.max(out['g']) > 0.85:
    print("Konvergiert!")
    break
```

### Kriterium 2: Niedrige Entropy
```python
entropy = -np.sum((out['g'] + 1e-10) * np.log2(out['g'] + 1e-10))
if entropy < 0.3:
    print("Fokussiert!")
    break
```

### Kriterium 3: Stabiler Modus
```python
if dominant_mode_unchanged_for_n_steps(5):
    print("Stabil!")
    break
```

### Kriterium 4: Quality Threshold
```python
if quality_score > 0.90:
    print("Qualität erreicht!")
    break
```

---

## 📈 Monitoring Integration

```python
from monitor_web_ctm import update_monitoring

# In Ihrer Reasoning-Loop
for step in range(max_steps):
    out = atmr.step(x_t, adapt=True)

    # Update Dashboard
    update_monitoring(
        atmr_output=out,
        thought=f"[Step {step}] Current reasoning..."
    )

    time.sleep(0.5)  # Optional: Visualization
```

**Dashboard öffnen:** http://localhost:5001

---

## 🔍 Debugging

### Gates prüfen
```python
for i, mod in enumerate(atmr.modalities):
    print(f"{mod:12s} [{out['g'][i]:6.1%}]")
```

### Prediction Errors prüfen
```python
for mod in atmr.modalities:
    pe = out['pe'].get(mod, 0.0)
    print(f"{mod:12s} PE: {pe:.3f}")
```

### Priors anzeigen
```python
print(f"Priors: {atmr.priors}")
```

### Dimensionen anzeigen
```python
print(f"Dimensions: {atmr.d}")
```

---

## 📚 File Structure

```
Tahlamus/
├── thalamo_pc_live.py              # ATM-R Base
├── thalamo_pc_adaptive.py          # ATM-R Adaptive
├── reasoning_modes.py              # Mode Definitions
├── ctm_integration.py              # CTM Integration
├── ctm_use_cases.py               # 5 Use Cases ⭐
├── custom_agent_routing.py         # Custom Modalities
├── monitor_web_ctm.py              # CTM Dashboard
├── CTM_REASONING_GUIDE.md          # Main Guide
├── CTM_USE_CASES_GUIDE.md          # Use Cases Guide
└── CTM_QUICK_REFERENCE.md          # This file
```

---

## 🎯 Cheat Sheet: Wann welchen Use Case?

| Problem | Use Case | Code |
|---------|----------|------|
| "Löse diese Mathe-Aufgabe" | Math Reasoning | `CTMMathReasoner()` |
| "Plane diese Reise/Task" | Planning | `CTMPlanner()` |
| "Finde kreative Lösungen" | Creative Solving | `CTMCreativeSolver(temp=0.9)` |
| "Generiere Code für X" | Code Generation | `CTMCodeGenerator()` |
| "Welcher Agent soll Task X machen?" | Agent Orchestration | `CTMAgentOrchestrator()` |
| "Kombiniere mehrere Sensoren" | Custom Modalities | `ThalamoPC6Adaptive(modalities=[...])` |

---

## ⚡ Performance-Tipps

### 1. Schrittanzahl
- Einfach: 10-20 Schritte
- Medium: 20-50 Schritte
- Komplex: 50-100 Schritte

### 2. Dimensionen optimieren
- Wichtige Modi: 128-256 dim
- Normale Modi: 32-64 dim
- Einfache Modi: 8-16 dim

### 3. Priors task-spezifisch
```python
# Math Task
priors = {'audio': 0.40, 'vision': 0.30, ...}  # Verbal Logic wichtig

# Spatial Task
priors = {'vestibular': 0.40, 'vision': 0.30, ...}  # Spatial wichtig

# Security Task
priors = {'threat': 0.50, ...}  # Safety kritisch
```

---

## 🚨 Häufige Fehler

### Fehler: KeyError 'modality_name'
**Ursache:** Tau nicht definiert
**Fix:**
```python
router = ThalamoPC6Adaptive(
    modalities=[...],
    dimensions={...},
    priors={...},
    tau={...}  # ← WICHTIG!
)
```

### Fehler: Summe der Priors != 1.0
**Fix:**
```python
priors = {'a': 0.5, 'b': 0.3, 'c': 0.2}  # Summe = 1.0 ✅
```

### Fehler: Unicode in Terminal (Windows)
**Fix:**
```python
# Statt get_icon() in print():
print(f"[{get_display_name(mode)}]")  # Keine Emojis
```

---

## 📞 Weitere Hilfe

- **CTM Reasoning Guide**: `CTM_REASONING_GUIDE.md`
- **Use Cases Guide**: `CTM_USE_CASES_GUIDE.md`
- **Demo**: `python ctm_use_cases.py`
- **Dashboard**: `python monitor_web_ctm.py`

---

**Version:** 1.0
**Updated:** 2025-10-13
**Status:** ✅ Production-ready
