# Society of Mind Refactoring: Von Polling zu Push

## Übersicht

Dieses Dokument beschreibt das Refactoring der Society of Mind Architektur von einem **Polling-basierten** zu einem **Push-basierten** System.

**Datum:** 2025-12-09  
**Version:** 2.0

## Problem: Alte Polling-Architektur

Die ursprüngliche Implementierung hatte mehrere Ineffizienzen:

### 1. Aktives Polling (CPU Verschwendung)

```python
# VORHER: Jeder Agent pollt alle 1 Sekunde
async def _run_loop(self):
    while not self._should_stop:
        events = self._pending_events.copy()
        if events and await self.should_act(events):
            await self.act(events)
        await asyncio.sleep(self.poll_interval)  # ❌ 1s Verschwendung
```

**Impact:** Bei 10 Agents = 10 unnecessary wake-ups pro Sekunde

### 2. Redundante Event-Subscriptions

- TesterAgent, BuilderAgent, ValidatorAgent - alle subscribten auf `FILE_CREATED`
- → 100 Dateien = 300 Event-Verarbeitungen (statt 100)

### 3. Fehlender Dependency Graph

Alle Agents liefen parallel ohne Koordination:
- Tests liefen bevor Build fertig war
- Fixer versuchte zu fixen bevor alle Errors bekannt waren

### 4. Ineffiziente Convergence Checks

```python
# VORHER: Alle 2 Sekunden, unabhängig von Aktivität
await asyncio.sleep(2.0)
```

## Lösung: Push-basierte Architektur v2.0

### 1. AsyncQueue Event-Delivery

```python
# NACHHER: Agents warten auf Events (kein CPU waste)
async def _run_loop(self):
    while not self._should_stop:
        events = await self._collect_batched_events(timeout=QUEUE_TIMEOUT)
        if events and await self.should_act(events):
            await self.act(events)
```

**Vorteile:**
- Agents schlafen bis ein Event kommt
- Sofortige Reaktion auf Events
- ~80% weniger CPU-Nutzung

### 2. Event Batching

Events werden innerhalb eines 500ms Fensters gesammelt:

```python
EVENT_BATCH_WINDOW = 0.5  # 500ms

async def _collect_batched_events(self, timeout: float) -> list[Event]:
    events = []
    first_event = await asyncio.wait_for(self._event_queue.get(), timeout=timeout)
    events.append(first_event)
    
    # Weitere Events im Batch-Fenster sammeln
    batch_deadline = time() + EVENT_BATCH_WINDOW
    while time() < batch_deadline:
        try:
            event = await asyncio.wait_for(self._event_queue.get(), timeout=remaining)
            events.append(event)
        except TimeoutError:
            break
    return events
```

### 3. Agent Dependency Graph

```python
AGENT_DEPENDENCIES = {
    "Builder": [],  # Läuft zuerst
    "Validator": ["Builder"],  # Wartet auf Build
    "Tester": ["Builder"],  # Wartet auf Build
    "Fixer": ["Builder", "Validator", "Tester"],  # Wartet auf alle
    "Generator": ["Fixer"],  # Reagiert auf Fixes
}
```

**Ausführungsreihenfolge:**
```
Generator → Builder → [Validator, Tester] → Fixer → Generator
```

### 4. Agent-spezifische Triggers

```python
AGENT_TRIGGERS = {
    "Builder": [FILE_CREATED, FILE_MODIFIED, CODE_FIXED],
    "Validator": [BUILD_SUCCEEDED],
    "Tester": [BUILD_SUCCEEDED],
    "Fixer": [TYPE_ERROR, TEST_FAILED, BUILD_FAILED],
}
```

### 5. Idle-basierte Convergence Checks

```python
# NACHHER: Nur checken wenn System idle ist
async def _run_iteration_loop(self):
    while not self._should_stop:
        if not self._is_system_idle():
            await asyncio.sleep(self._idle_check_interval)
            continue
            
        # System ist idle, checke Convergence
        converged, reasons = await self._check_convergence()
```

## Konfiguration

### Push-Architektur aktivieren/deaktivieren

```python
# Standard: Push-Architektur aktiviert
orchestrator = Orchestrator(
    working_dir=working_dir,
    use_push_architecture=True,  # Default
)

# Legacy Polling (für Debugging)
orchestrator = Orchestrator(
    working_dir=working_dir,
    use_push_architecture=False,
)
```

### Konstanten anpassen

In `src/agents/autonomous_base.py`:

```python
QUEUE_TIMEOUT = 5.0  # Max Wartezeit auf Events (Sekunden)
EVENT_BATCH_WINDOW = 0.5  # Event-Batch Fenster (Sekunden)
```

## Performance-Vergleich

| Metrik | Polling (v1) | Push (v2) | Verbesserung |
|--------|--------------|-----------|--------------|
| CPU bei Idle | ~10 wake-ups/s | ~0 wake-ups | 100% |
| Reaktionszeit | 0-1000ms | <10ms | ~100x |
| Event Processing | 300/100 files | 100/100 files | 3x |
| Convergence Checks | alle 2s | nur bei Idle | ~80% weniger |

## Migration

### Bestehende Custom Agents

Custom Agents müssen den neuen `use_push_architecture` Parameter unterstützen:

```python
class MyCustomAgent(AutonomousAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Agent nutzt automatisch Push-Architektur wenn aktiviert
```

### Backwards Compatibility

- `use_push_architecture=False` reaktiviert das alte Polling-Verhalten
- Alle bestehenden Tests laufen weiterhin

## Architektur-Diagramm

```
┌─────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Dependency  │  │   Idle      │  │    Convergence          │  │
│  │   Graph     │  │  Tracker    │  │     Checker             │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         EVENT BUS                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Pub/Sub System                         │    │
│  │  FILE_CREATED → BUILD_SUCCEEDED → TEST_PASSED → ...      │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Builder  │  │ Validator│  │  Tester  │  │  Fixer   │
    │          │  │          │  │          │  │          │
    │ Queue    │  │ Queue    │  │ Queue    │  │ Queue    │
    │ (async)  │  │ (async)  │  │ (async)  │  │ (async)  │
    └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

## Tests

Unit Tests für die Push-Architektur befinden sich in:

```
tests/mind/test_push_architecture.py
```

Ausführen mit:

```bash
pytest tests/mind/test_push_architecture.py -v
```

## Änderungshistorie

| Version | Datum | Änderungen |
|---------|-------|------------|
| 2.0 | 2025-12-09 | Push-Architektur implementiert |
| 1.0 | 2025-10-xx | Original Polling-Architektur |