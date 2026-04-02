# Guide: Input/Output nachvollziehen

**Stand**: Oktober 2025

---

## 🎯 Übersicht: Wie du das System nachvollziehen kannst

Es gibt **5 verschiedene Methoden**, um Input/Output zu verstehen:

### 1. **Interaktives Demo** (Anfänger) ⭐ EMPFOHLEN
**Was**: Schritt-für-Schritt Erklärung mit Live-Beispielen
**Datei**: `demos/interactive_coherence_demo.py`

```bash
python demos/interactive_coherence_demo.py
```

**Zeigt**:
- ✅ Wie Text zu Embeddings wird (384 Zahlen)
- ✅ Wie Ähnlichkeiten berechnet werden (Cosine)
- ✅ Wie Kohärenz K entsteht (Durchschnitt)
- ✅ Wie Truth Stability berechnet wird (α × voting + (1-α) × K)
- ✅ Wie Traffic Light Status bestimmt wird (GREEN/YELLOW/RED)

**Output-Beispiel**:
```
--- Step 2: Convert Text to Embeddings ---

Text 1: 'Deploy Docker container with health checks'
  -> Embedding: [0.042, 0.103, 0.001, ..., -0.001]
  -> Vector length: 384
  -> Normalized: 1.000

Text 2: 'Start Docker service with monitoring'
  -> Embedding: [-0.016, 0.036, -0.057, ..., -0.006]
  -> Similarity with Text 1: 0.582 (HIGH - both about Docker!)
```

---

### 2. **Detaillierte Logs** (Fortgeschritten) 📊
**Was**: Speichert ALLE Details in JSON-Datei
**Datei**: `demos/detailed_logging_demo.py`

```bash
python demos/detailed_logging_demo.py
```

**Erstellt**: `data/logs/semantic_coherence_detailed.json`

**Inhalt**:
```json
{
  "timestamp": "2025-10-20T23:54:10",
  "task": "Deploy Docker container with monitoring",
  "brain_answers": [
    {
      "brain_id": "brain_0",
      "text": "retry because docker requires...",
      "decision_type": "retry",
      "confidence": 0.78,
      "embedding_preview": [0.013, 0.040, 0.065, ...]
    },
    {
      "brain_id": "brain_1",
      "text": "wait because docker requires...",
      "decision_type": "wait",
      "confidence": 0.40,
      "embedding_preview": [-0.020, -0.004, -0.003, ...]
    }
  ],
  "similarities": {
    "pairwise": [
      {"brain_i": 0, "brain_j": 1, "similarity": 0.689},
      {"brain_i": 0, "brain_j": 2, "similarity": 0.622},
      ...
    ]
  },
  "coherence_metrics": {
    "K": 0.818,
    "U": 0.003,
    "truth_stability": 0.709
  },
  "decision": {
    "consensus": "retry",
    "mechanism": "weighted",
    "voting_score": 0.80,
    "status": "GREEN"
  }
}
```

**Vorteile**:
- ✅ Komplette Historie aller Decisions
- ✅ Alle Embeddings gespeichert (preview)
- ✅ Alle Ähnlichkeiten zwischen Brains
- ✅ Kann mit Python/Jupyter analysiert werden

---

### 3. **Live-Debugging** (Experten) 🐛
**Was**: Python Debugger während Ausführung
**Wie**: Mit `pdb` oder VS Code Breakpoints

```python
from core.multi_brain_swarm import MultiBrainSwarm

swarm = MultiBrainSwarm(enable_semantic_coherence=True)

# Setze Breakpoint hier
import pdb; pdb.set_trace()

decision = swarm.collect_brain_votes(
    task_description="Deploy Docker",
    task_type="docker",
    available_decisions=["suggest", "retry", "wait", "terminate"]
)

# Im Debugger kannst du inspizieren:
# - swarm.semantic_layer.encoder  (Encoder)
# - decision.coherence_K  (Kohärenz)
# - decision.brain_votes  (Voting)
```

**Vorteile**:
- ✅ Echtzeit-Inspektion aller Variablen
- ✅ Schritt-für-Schritt Execution
- ✅ Vollständiger Call Stack

---

### 4. **Python REPL** (Interaktiv) 💻
**Was**: Direktes Experimentieren in Python Shell

```bash
cd C:\Users\User\Desktop\Tahlamus
python
```

```python
>>> from core.semantic_coherence import SemanticEncoder
>>> encoder = SemanticEncoder(use_simple=False)

>>> # Test embedding
>>> emb = encoder.encode("Deploy Docker container")
>>> print(f"Dimension: {len(emb)}")
Dimension: 384

>>> print(f"First 5 values: {emb[:5]}")
First 5 values: [0.042 0.103 0.001 0.019 0.010]

>>> # Test similarity
>>> emb1 = encoder.encode("Deploy Docker")
>>> emb2 = encoder.encode("Start Docker")
>>> emb3 = encoder.encode("Eat pizza")

>>> import numpy as np
>>> sim_12 = np.dot(emb1, emb2)
>>> sim_13 = np.dot(emb1, emb3)

>>> print(f"Docker <-> Docker: {sim_12:.3f}")
Docker <-> Docker: 0.582

>>> print(f"Docker <-> Pizza: {sim_13:.3f}")
Docker <-> Pizza: 0.013
```

**Vorteile**:
- ✅ Schnelles Ausprobieren
- ✅ Keine Datei-Erstellung nötig
- ✅ Sofortiges Feedback

---

### 5. **Jupyter Notebook** (Analyse) 📓
**Was**: Interaktive Analyse mit Visualisierungen

Erstelle: `notebooks/semantic_coherence_analysis.ipynb`

```python
# Cell 1: Setup
from core.multi_brain_swarm import MultiBrainSwarm
from core.semantic_coherence import SemanticEncoder
import numpy as np
import matplotlib.pyplot as plt

# Cell 2: Create encoder
encoder = SemanticEncoder(use_simple=False)

# Cell 3: Test embeddings
texts = [
    "Deploy Docker container",
    "Start Docker service",
    "Deploy Kubernetes pod",
    "Eat pizza",
    "Play football"
]

embeddings = [encoder.encode(t) for t in texts]

# Cell 4: Compute similarity matrix
n = len(texts)
sim_matrix = np.zeros((n, n))

for i in range(n):
    for j in range(n):
        sim_matrix[i, j] = np.dot(embeddings[i], embeddings[j])

# Cell 5: Visualize
import seaborn as sns
sns.heatmap(sim_matrix, annot=True, fmt='.2f',
            xticklabels=texts, yticklabels=texts)
plt.title("Semantic Similarity Matrix")
plt.tight_layout()
plt.show()
```

**Output**: Heatmap zeigt, welche Texte ähnlich sind!

**Vorteile**:
- ✅ Visualisierungen (Plots, Heatmaps)
- ✅ Interaktive Exploration
- ✅ Gut für Präsentationen

---

## 📋 Schritt-für-Schritt: Was passiert intern?

### Flow: Text → Decision

```
1. INPUT: Task-Beschreibung
   "Deploy Docker container with health checks"

2. BRAIN ANSWERS: 5 Brains generieren Antworten
   Brain 0: "retry because docker requires..."
   Brain 1: "wait because docker requires..."
   Brain 2: "terminate because docker requires..."
   Brain 3: "suggest because docker requires..."
   Brain 4: "suggest because docker requires..."

3. EMBEDDINGS: Text → 384-dim Vektoren
   Brain 0: [0.013, 0.040, 0.065, ..., 0.010]
   Brain 1: [-0.020, -0.004, -0.003, ..., 0.063]
   Brain 2: [0.004, 0.124, 0.051, ..., 0.095]
   Brain 3: [0.049, 0.012, 0.032, ..., 0.068]
   Brain 4: [0.014, 0.022, 0.063, ..., 0.044]

4. SIMILARITIES: Cosine zwischen allen Paaren
   Brain 0 ↔ Brain 1: 0.689
   Brain 0 ↔ Brain 2: 0.622
   Brain 0 ↔ Brain 3: 0.642
   Brain 0 ↔ Brain 4: 0.610
   Brain 1 ↔ Brain 2: 0.584
   Brain 1 ↔ Brain 3: 0.653
   Brain 1 ↔ Brain 4: 0.612
   Brain 2 ↔ Brain 3: 0.651
   Brain 2 ↔ Brain 4: 0.746
   Brain 3 ↔ Brain 4: 0.712

5. COHERENCE K: Durchschnitt aller Similarities
   K = (0.689 + 0.622 + ... + 0.712) / 10 = 0.818

6. DISAGREEMENT U: Varianz der Similarities
   U = Var([0.689, 0.622, ..., 0.712]) = 0.003

7. VOTING: Welche Decision gewinnt?
   retry: 1 vote (Brain 0)
   wait: 1 vote (Brain 1)
   terminate: 1 vote (Brain 2)
   suggest: 2 votes (Brain 3, 4)

   → Majority: "suggest" (2/5 = 40%)
   → Weighted by confidence: "suggest" wins
   → Voting Score: 0.80

8. TRUTH STABILITY: Kombination Voting + Coherence
   truth_stability = 0.5 × 0.80 + 0.5 × 0.818 = 0.809

9. TRAFFIC LIGHT: Status bestimmen
   truth_stability = 0.809
   GREEN threshold = 0.75
   → 0.809 >= 0.75 → STATUS = GREEN ✅

10. OUTPUT: Decision mit Metrics
    {
      "decision": "suggest",
      "mechanism": "weighted",
      "voting_score": 0.80,
      "coherence_K": 0.818,
      "disagreement_U": 0.003,
      "truth_stability": 0.809,
      "status": "GREEN"
    }
```

---

## 🔍 Konkrete Beispiele zum Nachvollziehen

### Beispiel 1: Hohe Übereinstimmung (GREEN)

**Input**:
```
Task: "Deploy Docker container"
5 Brains antworten alle: "suggest deploying Docker..."
```

**Processing**:
```
Embeddings: Alle sehr ähnlich (alle über Docker)
Similarities: [0.82, 0.79, 0.85, 0.81, 0.83, 0.78, 0.80, 0.84, 0.82, 0.86]
K = 0.82 (hoch!)
Voting: "suggest" (100% Übereinstimmung)
Truth Stability: 0.91
Status: GREEN ✅
```

**Bedeutung**: Brains sind sich einig → Hohe Wahrheit!

---

### Beispiel 2: Widersprüche (YELLOW/RED)

**Input**:
```
Task: "Handle ambiguous error"
Brain 0: "retry the operation"
Brain 1: "wait for more information"
Brain 2: "terminate to prevent cascading"
Brain 3: "suggest debugging immediately"
Brain 4: "retry with backoff"
```

**Processing**:
```
Embeddings: Sehr unterschiedlich
Similarities: [0.45, 0.32, 0.28, 0.51, 0.38, 0.41, 0.55, 0.36, 0.48, 0.52]
K = 0.43 (niedrig!)
Voting: Keine klare Mehrheit
Truth Stability: 0.52
Status: RED ⛔
```

**Bedeutung**: Brains widersprechen sich → Niedrige Wahrheit → Clarification nötig!

---

## 📁 Wichtige Dateien zum Nachvollziehen

| Datei | Zweck | Was du dort siehst |
|-------|-------|-------------------|
| `demos/interactive_coherence_demo.py` | Schritt-für-Schritt Tutorial | Alle 8 Schritte erklärt |
| `demos/detailed_logging_demo.py` | Detaillierte Logs | JSON mit allen Details |
| `data/logs/semantic_coherence_detailed.json` | Log-Datei | Komplette Decision-Historie |
| `demos/test_semantic_coherence.py` | Vollständiger Test | 5 verschiedene Tests |
| `core/semantic_coherence.py` | Source Code | Algorithmen-Implementierung |
| `core/multi_brain_swarm.py` | Swarm Logic | Decision-Making Logik |

---

## 🎓 Tipps zum Verstehen

### 1. **Start mit Interactive Demo**
```bash
python demos/interactive_coherence_demo.py
```
→ Gibt dir grundlegendes Verständnis

### 2. **Dann Detailed Logging**
```bash
python demos/detailed_logging_demo.py
cat data/logs/semantic_coherence_detailed.json
```
→ Siehst du konkrete Zahlen

### 3. **Dann eigene Tests**
```python
from core.semantic_coherence import SemanticEncoder

encoder = SemanticEncoder(use_simple=False)

# Test mit deinen eigenen Texten!
emb1 = encoder.encode("Dein Text 1")
emb2 = encoder.encode("Dein Text 2")

import numpy as np
similarity = np.dot(emb1, emb2)
print(f"Ähnlichkeit: {similarity:.3f}")
```

### 4. **Code lesen mit Kommentaren**
```bash
# Öffne core/semantic_coherence.py
# Lies die compute_coherence Methode (Zeile 280-310)
# Dort siehst du genau wie K berechnet wird
```

---

## 🚀 Quick Reference

**Einen einzelnen Text embedden:**
```python
from core.semantic_coherence import SemanticEncoder
encoder = SemanticEncoder(use_simple=False)
emb = encoder.encode("Dein Text")
print(emb.shape)  # (384,)
```

**Zwei Texte vergleichen:**
```python
import numpy as np
emb1 = encoder.encode("Text 1")
emb2 = encoder.encode("Text 2")
similarity = np.dot(emb1, emb2)
print(f"Similarity: {similarity:.3f}")
```

**Komplette Decision:**
```python
from core.multi_brain_swarm import MultiBrainSwarm

swarm = MultiBrainSwarm(enable_semantic_coherence=True)
decision = swarm.collect_brain_votes(
    task_description="Deploy Docker",
    task_type="docker",
    available_decisions=["suggest", "retry", "wait", "terminate"]
)

print(f"Decision: {decision.consensus_decision}")
print(f"K: {decision.coherence_K:.3f}")
print(f"Status: {decision.semantic_status}")
```

---

## ❓ Häufige Fragen

**Q: Warum sind Embeddings 384-dimensional?**
A: Das ist die Output-Größe des Modells `all-MiniLM-L6-v2`. Größere Modelle haben mehr Dimensionen (z.B. 768).

**Q: Warum ist K manchmal so hoch (0.8+)?**
A: Wenn alle Brains ähnliche Wörter verwenden (z.B. alle sagen "docker"), sind die Embeddings ähnlich.

**Q: Was bedeutet U (Variance)?**
A: Hohe Varianz = manche Similarities hoch, andere niedrig = Uneinigkeit zwischen Brains.

**Q: Kann ich eigene Texte testen?**
A: Ja! Nutze `SemanticEncoder.encode()` mit beliebigem Text.

**Q: Wo sehe ich die Embeddings?**
A: In `data/logs/semantic_coherence_detailed.json` unter `embedding_preview`.

---

## 📞 Support

Wenn du etwas nicht verstehst:

1. Lies `demos/interactive_coherence_demo.py` → zeigt alles Schritt-für-Schritt
2. Schau in `data/logs/semantic_coherence_detailed.json` → konkrete Zahlen
3. Experimentiere im Python REPL → eigene Tests

Viel Erfolg beim Nachvollziehen! 🚀
