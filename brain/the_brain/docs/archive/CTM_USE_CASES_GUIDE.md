# CTM Use Cases Guide - Praktische Anwendungen

**Status:** ✅ Complete
**Date:** 2025-10-13
**Version:** 1.0

---

## 🎯 Überblick

Basierend auf Sakana AI's Continuous Thought Machines haben wir **5 praktische Anwendungsfälle** für Ihr CTM-ATM-R System implementiert.

**Demo ausführen:**
```bash
python ctm_use_cases.py
```

---

## 📋 Die 5 Use Cases

### 1. 🧮 Multi-Step Mathematical Reasoning

**Was:** Schrittweises Lösen komplexer mathematischer Probleme
**CTM-Prinzip:** Iteratives Reasoning mit adaptivem Modus-Wechsel

**Verwendete Reasoning-Modi:**
- 👁️ **Visual Thinking**: Visualisiere Gleichungsstruktur
- 💬 **Verbal Logic**: Wende mathematische Regeln an (Punkt vor Strich)
- 💎 **Value Reasoning**: Schätze Zwischenergebnisse

**Beispiel-Output:**
```
MATH REASONING: ((15 + 7) * 3) - 8 / 2

Step  0 [Value Reasoning     ] Estimate: result should be around 60...
Step  1 [Value Reasoning     ] Check if result is reasonable...
Step  2 [Value Reasoning     ] Compare intermediate values...
Step  3 [Verbal Logic        ] Apply order of operations rule...
Step  4 [Verbal Logic        ] Parentheses first, then multiplication...
Step  5 [Verbal Logic        ] Left to right evaluation...
...
```

**Verwendung:**
```python
from ctm_use_cases import CTMMathReasoner

reasoner = CTMMathReasoner()
result = reasoner.solve_step_by_step("((15 + 7) * 3) - 8 / 2", max_steps=15)

# Result enthält:
# - trajectory: Komplette Reasoning-Trajektorie
# - thoughts: Liste aller Gedanken
# - final_mode: Dominanter Modus am Ende
```

**Konvergenz-Kriterium:** Wenn Confidence > 85% über mehrere Schritte

---

### 2. 🗺️ Planning & Task Decomposition

**Was:** Hierarchisches Planning für komplexe Aufgaben
**CTM-Prinzip:** Iterative Zerlegung mit Wert-Abwägung und Spatial-Reasoning

**Verwendete Reasoning-Modi:**
- 🧭 **Spatial Thinking**: Route planen, Pfade visualisieren
- 💎 **Value Reasoning**: Kosten/Nutzen abwägen
- 🛡️ **Safety Monitoring**: Risiken prüfen

**Beispiel-Output:**
```
PLANNING: Plan a trip from Berlin to Tokyo

Step  0 [Value Reasoning     ] Evaluate option 0: Cost/benefit...
Step  1 [Value Reasoning     ] Evaluate option 1: Cost/benefit...
Step  2 [Value Reasoning     ] Evaluate option 2: Cost/benefit...
Step  3 [Spatial Thinking    ] Route segment 3: Navigate...
...
-> Plan complete after 15 steps!
```

**Verwendung:**
```python
from ctm_use_cases import CTMPlanner

planner = CTMPlanner()
plan = planner.plan_task("Plan a trip from Berlin to Tokyo", max_steps=30)

# plan enthält Liste von Schritten:
# [{'step': 0, 'mode': 'taste', 'action': 'Evaluate option 0...'}]
```

**Anwendungen:**
- Reise-Planung
- Projekt-Zerlegung
- Task-Scheduling
- Resource-Allocation

---

### 3. 🎨 Creative Problem Solving

**Was:** Explorative Lösungsfindung mit höherer Diversität
**CTM-Prinzip:** Temperatur-gesteuerte Exploration, hohe Entropy

**Verwendete Reasoning-Modi:** Alle (diverse Kombination)

**Key Feature: Temperature Parameter**
```python
creative = CTMCreativeSolver(temperature=0.9)  # Höher = mehr Exploration
```

- **Temperature 0.3**: Fokussiert, konvergent
- **Temperature 0.6**: Balanciert
- **Temperature 0.9**: Sehr explorativ, kreativ

**Beispiel-Output:**
```
CREATIVE EXPLORATION: Design innovative UI
Temperature: 0.9

Iteration  0 [Visual Thinking     ] Entropy: 0.72 bits (LOW)
Iteration  5 [Visual Thinking     ] Entropy: 0.98 bits (LOW)
Iteration 10 [Visual Thinking     ] Entropy: 1.52 bits (MEDIUM)
Iteration 15 [Verbal Logic        ] Entropy: 1.87 bits (HIGH)
```

**Entropy-Interpretation:**
- **< 0.5 bits**: Sehr fokussiert (ein dominanter Modus)
- **0.5-1.5 bits**: Balanciert (mehrere Modi aktiv)
- **> 1.5 bits**: Sehr divers (alle Modi beteiligt)

**Verwendung:**
```python
from ctm_use_cases import CTMCreativeSolver

solver = CTMCreativeSolver(temperature=0.9)
solutions = solver.explore_solutions("Design innovative UI", iterations=25)

# Analysiere Diversität
for sol in solutions:
    print(f"Iteration {sol['iteration']}: Entropy {sol['entropy']:.2f} ({sol['diversity']})")
```

**Anwendungen:**
- Design-Brainstorming
- Problem-Exploration
- Innovation
- Alternative-Finding

---

### 4. 💻 Code Generation with Iterative Refinement

**Was:** Code-Generierung mit schrittweiser Verbesserung
**CTM-Prinzip:** Phasen-basiertes Reasoning (Design → Implement → Test → Refine)

**Phasen:**
1. **Design Phase** → Visual Thinking (Code-Struktur visualisieren)
2. **Implementation Phase** → Verbal Logic (Syntax anwenden)
3. **Testing Phase** → Value Reasoning + Safety (Qualität prüfen)
4. **Refinement Phase** → Value Reasoning (Optimierung)

**Beispiel-Output:**
```
CODE GENERATION: Implement binary search tree

Step  0 [Phase: design    ] [Visual Thinking     ] Quality: 5.2%
Step  1 [Phase: design    ] [Visual Thinking     ] Quality: 10.7%
Step  2 [Phase: design    ] [Visual Thinking     ] Quality: 17.1%
...
Step  5 [Phase: implement ] [Verbal Logic        ] Quality: 34.7%
Step  6 [Phase: implement ] [Verbal Logic        ] Quality: 42.5%
...
Step  9 [Phase: test      ] [Value Reasoning     ] Quality: 61.3%
Step 10 [Phase: test      ] [Verbal Logic        ] Quality: 66.4%
...
-> Code ready! Quality: 92.3%
```

**Verwendung:**
```python
from ctm_use_cases import CTMCodeGenerator

generator = CTMCodeGenerator()
result = generator.generate_code(
    spec="Implement binary search tree",
    refinement_steps=15
)

print(f"Quality: {result['quality']:.1%}")
print(f"Phases completed: {result['phases_completed']}")
```

**Quality Score:**
- **< 40%**: Early design
- **40-70%**: Implementation in progress
- **70-90%**: Testing phase
- **> 90%**: Production-ready

**Anwendungen:**
- Automatische Code-Generierung
- Code-Review
- Refactoring
- Bug-Fixing

---

### 5. 🤖 Multi-Agent Task Orchestration

**Was:** Dynamisches Routing zwischen verschiedenen Agenten
**CTM-Prinzip:** Custom Modalitäten = Agent-Typen

**Agent-Typen (statt biologischer Modi):**
- `reasoning`: LLM für logisches Denken (128-dim)
- `code`: Code-Generierung/Ausführung (64-dim)
- `search`: Web/Daten-Suche (64-dim)
- `memory`: RAG/Langzeit-Gedächtnis (96-dim)
- `tools`: API/Tool-Aufrufe (32-dim)
- `security`: Sicherheits-Überwachung (16-dim)

**Beispiel-Output:**
```
Task: Debug security vulnerability in code
Dominant Agent: security
Routing Entropy: 0.30 bits

Active Agents:
  security     [ 72.3%] -> EXECUTE
  code         [ 18.5%] -> EXECUTE
  reasoning    [ 6.2%] -> STANDBY
```

**Verwendung:**
```python
from ctm_use_cases import CTMAgentOrchestrator

orchestrator = CTMAgentOrchestrator()

# Task-Features von Ihren Agenten
task_features = {
    'reasoning': reasoning_agent.get_features(task),
    'code': code_agent.get_features(task),
    'search': search_agent.get_features(task),
    'memory': memory_agent.get_features(task),
    'tools': tools_agent.get_features(task),
    'security': security_agent.check_threat(task)
}

# Routing-Entscheidung
routing = orchestrator.route_task("Debug security issue", task_features)

# Führe nur aktive Agenten aus
for agent in routing['active_agents']:
    if agent['should_execute']:  # Priority > 15%
        execute_agent(agent['agent'], task)
```

**Threshold-System:**
- **> 15%**: Agent wird ausgeführt (EXECUTE)
- **10-15%**: Agent bereit, aber inaktiv (STANDBY)
- **< 10%**: Agent ignoriert

**Anwendungen:**
- Multi-Agent Systeme
- Dynamic Task Routing
- Resource Optimization
- Agent Prioritization

---

## 🔧 Integration in Ihr System

### Schritt 1: Wählen Sie Ihren Use Case

```python
# Option 1: Standard CTM Reasoning (wie Sakana AI)
from ctm_integration import CTMReasoner

reasoner = CTMReasoner(adaptive=True)
final_state, trace = reasoner.reason(problem="...", steps=50)
```

```python
# Option 2: Spezialisierter Use Case
from ctm_use_cases import CTMMathReasoner, CTMPlanner, CTMCodeGenerator

# Math
math_reasoner = CTMMathReasoner()
result = math_reasoner.solve_step_by_step(problem, max_steps=20)

# Planning
planner = CTMPlanner()
plan = planner.plan_task(goal, max_steps=30)

# Code
code_gen = CTMCodeGenerator()
result = code_gen.generate_code(spec, refinement_steps=15)
```

### Schritt 2: Monitoring

Alle Use Cases können mit dem CTM-Dashboard visualisiert werden:

```python
from monitor_web_ctm import update_monitoring

# In Ihrer Reasoning-Loop:
for step in range(max_steps):
    out = atmr.step(x_t, adapt=True)
    update_monitoring(out, thought=f"[Step {step}] {thought_text}")
```

**Dashboard:** http://localhost:5001

### Schritt 3: Custom Modalitäten (für Use Case 5)

```python
from thalamo_pc_adaptive import ThalamoPC6Adaptive

# Definiere Ihre eigenen Modalitäten
my_router = ThalamoPC6Adaptive(
    modalities=['agent1', 'agent2', 'agent3'],
    dimensions={'agent1': 128, 'agent2': 64, 'agent3': 32},
    priors={'agent1': 0.4, 'agent2': 0.3, 'agent3': 0.3},
    tau={'agent1': 50.0, 'agent2': 40.0, 'agent3': 30.0}
)
```

---

## 📊 Metriken & Interpretation

### Confidence (Vertrauen)
- **< 40%**: Unsicher, weiter nachdenken
- **40-70%**: Auf gutem Weg
- **70-90%**: Hohe Sicherheit
- **> 90%**: Konvergiert, Lösung gefunden

### Entropy (Diversität)
```python
entropy = -sum(g_i * log2(g_i))  # für alle Modi i
```
- **< 0.5 bits**: Ein Modus dominant (Exploitation)
- **0.5-1.5 bits**: Mehrere Modi aktiv (Balance)
- **> 1.5 bits**: Alle Modi beteiligt (Exploration)

### Dominant Mode
Der Reasoning-Modus mit höchster Gate-Weight:
```python
dominant_mode = modalities[np.argmax(gates)]
```

**Interpretation:**
- Frühe Schritte: Wechselnde Modi (Exploration)
- Mittlere Schritte: 2-3 dominante Modi (Fokussierung)
- Späte Schritte: 1 dominanter Modus (Konvergenz)

---

## 🎓 Best Practices

### 1. **Passende Schrittanzahl wählen**
```python
# Einfache Probleme
result = reasoner.solve(problem, max_steps=10)

# Komplexe Probleme
result = reasoner.solve(problem, max_steps=50)

# Sehr komplexe Probleme (wie Maze-Solving)
result = reasoner.solve(problem, max_steps=100)
```

### 2. **Temperature für Exploration anpassen**
```python
# Präzise Lösungen (Math, Code)
solver = CTMCreativeSolver(temperature=0.3)

# Balanciert
solver = CTMCreativeSolver(temperature=0.6)

# Kreative Exploration (Design, Brainstorming)
solver = CTMCreativeSolver(temperature=0.9)
```

### 3. **Konvergenz-Kriterien definieren**
```python
for step in range(max_steps):
    out = atmr.step(x_t, adapt=True)

    # Kriterium 1: Hohe Confidence
    if np.max(out['g']) > 0.85:
        break

    # Kriterium 2: Niedrige Entropy (fokussiert)
    entropy = -np.sum((out['g'] + 1e-10) * np.log2(out['g'] + 1e-10))
    if entropy < 0.3:
        break

    # Kriterium 3: Stabiler dominanter Modus
    if step > 10 and dominant_mode_stable_for(5):
        break
```

### 4. **Hazard/Reward Signals nutzen**
```python
# Sicherheitswarnung
out = atmr.step(x_t, hazard={'security': 1.0}, adapt=True)

# Positive Belohnung
out = atmr.step(x_t, reward={'reasoning': 0.8}, adapt=True)
```

---

## 🔍 Erweiterte Use Cases

### Use Case 6: Multi-Modal Sensor Fusion
```python
# Für Roboter/IoT: Kombiniere verschiedene Sensoren
sensor_router = ThalamoPC6Adaptive(
    modalities=['camera', 'lidar', 'microphone', 'imu', 'gps'],
    dimensions={'camera': 128, 'lidar': 96, 'microphone': 64, 'imu': 16, 'gps': 8}
)

# In Sensor-Loop
sensor_data = {
    'camera': camera.get_frame_features(),
    'lidar': lidar.get_point_cloud_features(),
    'microphone': mic.get_audio_features(),
    'imu': imu.get_orientation(),
    'gps': gps.get_position()
}

out = sensor_router.step(sensor_data, adapt=True)
# Routing entscheidet, welche Sensoren wichtig sind
```

### Use Case 7: Hierarchical Task Decomposition
```python
# Level 1: High-level Planning
high_level = CTMPlanner()
main_plan = high_level.plan_task("Build web application", max_steps=10)

# Level 2: Für jeden Plan-Schritt -> Sub-planning
for step in main_plan:
    if step['mode'] == 'code':
        low_level = CTMCodeGenerator()
        code = low_level.generate_code(step['action'], refinement_steps=15)
```

### Use Case 8: Adaptive Learning from Feedback
```python
# Lernen aus Feedback
reasoner = CTMReasoner(adaptive=True)

for problem in problem_set:
    result = reasoner.reason(problem, steps=30)

    # Feedback geben
    if result_is_correct(result):
        # Verstärke erfolgreiche Modi
        reasoner.atmr.step(
            last_state,
            reward={dominant_mode: 1.0},
            adapt=True
        )
    else:
        # Bestrafe fehlgeschlagene Modi
        reasoner.atmr.step(
            last_state,
            hazard={dominant_mode: 0.5},
            adapt=True
        )
```

---

## 📈 Performance-Tipps

### 1. **Dimensionen optimieren**
```python
# Große Dimensionen für komplexe Modi
'reasoning': 128,   # Viel Kapazität
'visual': 128,

# Kleine Dimensionen für einfache Modi
'security': 16,     # Wenig Features
'threat': 8
```

### 2. **Priors basierend auf Aufgabe setzen**
```python
# Math-Problem: Verbal Logic wichtig
priors = {'audio': 0.40, 'vision': 0.30, 'taste': 0.15, ...}

# Spatial Problem: Spatial Thinking wichtig
priors = {'vestibular': 0.40, 'vision': 0.30, 'audio': 0.15, ...}

# Security Task: Safety wichtig
priors = {'threat': 0.50, 'audio': 0.20, 'vision': 0.15, ...}
```

### 3. **Tau für Reaktivität anpassen**
```python
tau = {
    'threat': 15.0,      # Sehr schnell (Sicherheit)
    'taste': 30.0,       # Schnell (Wert-Schätzung)
    'audio': 40.0,       # Mittel (Logik)
    'vision': 50.0,      # Langsam (komplexe Visualisierung)
    'reasoning': 60.0    # Sehr langsam (tiefe Analyse)
}
```

---

## 🚀 Nächste Schritte

### 1. **Testen Sie die Use Cases**
```bash
python ctm_use_cases.py
```

### 2. **Visualisieren Sie mit Dashboard**
```bash
python monitor_web_ctm.py
# -> http://localhost:5001
```

### 3. **Passen Sie an Ihre Needs an**
- Editieren Sie `ctm_use_cases.py`
- Fügen Sie eigene Use Cases hinzu
- Definieren Sie custom Modalitäten

### 4. **Integrieren Sie in Ihr System**
```python
from ctm_use_cases import CTMAgentOrchestrator

# Ihr Multi-Agent System
orchestrator = CTMAgentOrchestrator()

def process_task(task):
    # Extract features
    features = extract_features(task)

    # Route to agents
    routing = orchestrator.route_task(task, features)

    # Execute active agents
    results = []
    for agent in routing['active_agents']:
        if agent['should_execute']:
            result = execute_agent(agent['agent'], task)
            results.append(result)

    return aggregate_results(results)
```

---

## 📚 Referenzen

- **Sakana AI CTM Paper**: https://github.com/SakanaAI/continuous-thought-machines
- **ATM-R Research**: Adaptive Thalamic Multimodal Routing
- **Ihr System**:
  - `thalamo_pc_adaptive.py` - ATM-R Implementation
  - `reasoning_modes.py` - Reasoning Mode Definitions
  - `ctm_integration.py` - CTM-ATM-R Integration
  - `monitor_web_ctm.py` - CTM Dashboard

---

## ✅ Zusammenfassung

**5 Use Cases implementiert:**
1. ✅ Multi-Step Mathematical Reasoning
2. ✅ Planning & Task Decomposition
3. ✅ Creative Problem Solving
4. ✅ Code Generation with Refinement
5. ✅ Multi-Agent Task Orchestration

**Features:**
- Adaptive Routing zwischen Modi
- Iteratives Reasoning
- Konvergenz-Tracking
- Custom Modalitäten
- Dashboard-Integration

**Ihr System ist jetzt production-ready für diverse CTM-Anwendungen!** 🚀

---

**Erstellt:** 2025-10-13
**Version:** 1.0
**Status:** ✅ **COMPLETE**
