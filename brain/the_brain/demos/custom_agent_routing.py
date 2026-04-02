"""
Custom ATM-R mit sinnvollen Modalitäten für ein Multi-Agent OS

Statt biologischer Sinne (Geschmack, Gleichgewicht) verwenden wir
Agent-Typen und Datenquellen, die für ein Maschinensystem Sinn machen.
"""

import numpy as np
from thalamo_pc_adaptive import ThalamoPC6Adaptive

# ============================================================================
# BEISPIEL 1: Agent-Typen als Modalitäten
# ============================================================================

print("="*80)
print("BEISPIEL 1: Multi-Agent System mit Agent-Typen")
print("="*80)

# Definiere sinnvolle Agent-Typen
agent_modalities = [
    'reasoning',      # LLM für logisches Denken
    'code',          # Code-Generierung/Ausführung
    'search',        # Web/Daten-Suche
    'memory',        # RAG/Langzeit-Gedächtnis
    'tool_use',      # API/Tool-Aufrufe
    'security'       # Sicherheits-Überwachung
]

# Dimensionen: Größe der Feature-Vektoren pro Agent
agent_dimensions = {
    'reasoning': 128,    # LLM-Embeddings (groß)
    'code': 64,         # Code-Features
    'search': 64,       # Search-Result-Features
    'memory': 96,       # Memory-Retrieval-Features
    'tool_use': 32,     # Tool-Call-Features
    'security': 16      # Security-Metriken (kompakt!)
}

# Priors: Welche Agenten sind grundsätzlich wichtiger?
agent_priors = {
    'reasoning': 0.25,   # Reasoning oft zentral
    'code': 0.20,       # Code wichtig
    'search': 0.15,     # Search nach Bedarf
    'memory': 0.15,     # Memory nach Bedarf
    'tool_use': 0.10,   # Tools selektiv
    'security': 0.35    # SICHERHEIT HÖCHSTE PRIORITÄT!
}

# Time constants: Wie "träge" ist jeder Agent?
agent_tau = {
    'reasoning': 50.0,   # Langsam (komplexe Analyse)
    'code': 40.0,       # Mittel
    'search': 30.0,     # Schnell (reaktiv)
    'memory': 45.0,     # Langsam (Abruf dauert)
    'tool_use': 25.0,   # Schnell (Tool-Calls)
    'security': 15.0    # SEHR SCHNELL (Bedrohungen sofort!)
}

# ATM-R mit custom Modalitäten erstellen
agent_router = ThalamoPC6Adaptive(
    modalities=agent_modalities,
    dimensions=agent_dimensions,
    priors=agent_priors,
    tau=agent_tau,
    seed=42
)

print(f"\nErstellter Agent-Router:")
print(f"  Modalitäten: {agent_router.modalities}")
print(f"  Anzahl: {agent_router.M}")
print(f"  Dimensionen: {agent_router.d}")
print(f"  Priors: {agent_router.priors}")

# Simuliere eine Aufgabe
print("\n" + "-"*80)
print("Simuliere: Benutzer fragt nach Code mit Sicherheitsrisiko")
print("-"*80)

# Eingabe-Features (simuliert)
x_t = {
    'reasoning': np.random.randn(128) * 2.0,  # Starkes Reasoning-Signal
    'code': np.random.randn(64) * 3.0,        # Sehr starkes Code-Signal
    'search': np.random.randn(64) * 0.5,      # Wenig Search
    'memory': np.random.randn(96) * 0.5,      # Wenig Memory
    'tool_use': np.random.randn(32) * 0.3,    # Kaum Tools
    'security': np.random.randn(16) * 5.0     # SICHERHEITSALARM! (verstärkt)
}

# Verarbeite mit Hazard-Signal für Sicherheit
out = agent_router.step(
    x_t,
    hazard={'security': 1.0},  # Sicherheitswarnung!
    adapt=True
)

print("\nRouting-Entscheidung:")
for i, mod in enumerate(agent_router.modalities):
    gate = out['g'][i]
    bar = "#" * int(gate * 50)
    status = "<<< AKTIV" if gate > 0.2 else ""
    print(f"  {mod:12s} [{gate:6.1%}] {bar:50s} {status}")

print(f"\nDominanter Agent: {agent_router.modalities[np.argmax(out['g'])]}")
print(f"Vertrauen: {np.max(out['g']):.1%}")


# ============================================================================
# BEISPIEL 2: Datenquellen als Modalitäten
# ============================================================================

print("\n\n" + "="*80)
print("BEISPIEL 2: Datenquellen-Routing")
print("="*80)

# Verschiedene Datenquellen
data_modalities = [
    'user_input',    # Benutzereingaben
    'logs',          # System-Logs
    'metrics',       # Performance-Metriken
    'database',      # DB-Abfragen
    'api',           # API-Antworten
    'events'         # Event-Stream
]

data_dimensions = {
    'user_input': 128,
    'logs': 64,
    'metrics': 32,
    'database': 96,
    'api': 64,
    'events': 48
}

data_priors = {
    'user_input': 0.30,  # Benutzer hat höchste Priorität
    'logs': 0.15,
    'metrics': 0.10,
    'database': 0.20,
    'api': 0.15,
    'events': 0.10
}

data_tau = {
    'user_input': 40.0,
    'logs': 30.0,
    'metrics': 35.0,
    'database': 45.0,
    'api': 35.0,
    'events': 25.0
}

data_router = ThalamoPC6Adaptive(
    modalities=data_modalities,
    dimensions=data_dimensions,
    priors=data_priors,
    tau=data_tau,
    seed=42
)

print(f"\nDatenquellen-Router:")
print(f"  Modalitäten: {data_router.modalities}")

# Simuliere: DB-Fehler + Benutzer wartet
x_t = {
    'user_input': np.random.randn(128) * 1.5,  # Benutzer fragt
    'logs': np.random.randn(64) * 4.0,         # FEHLER-LOGS! (viele Fehler)
    'metrics': np.random.randn(32) * 0.8,      # Normale Metriken
    'database': np.random.randn(96) * 3.5,     # DB meldet Problem
    'api': np.random.randn(64) * 0.5,
    'events': np.random.randn(48) * 0.5
}

out = data_router.step(x_t, adapt=True)

print("\n Routing-Entscheidung:")
for i, mod in enumerate(data_router.modalities):
    gate = out['g'][i]
    bar = "#" * int(gate * 50)
    print(f"  {mod:12s} [{gate:6.1%}] {bar}")


# ============================================================================
# BEISPIEL 3: Hybrides System (Das Beste aus beiden Welten)
# ============================================================================

print("\n\n" + "="*80)
print("BEISPIEL 3: Hybrid - Wichtige Sensoren + Sicherheit")
print("="*80)

# Für einen Roboter/IoT-System: Nur relevante Modalitäten
hybrid_modalities = [
    'camera',        # Kamera-Input (statt "vision")
    'microphone',    # Audio-Input (statt "audio")
    'lidar',         # 3D-Scan (statt "touch")
    'imu',           # Bewegungssensor (statt "vestibular")
    'network',       # Netzwerk-Status
    'security'       # Sicherheits-Check
]

hybrid_dimensions = {
    'camera': 128,
    'microphone': 64,
    'lidar': 96,
    'imu': 16,
    'network': 32,
    'security': 16
}

hybrid_priors = {
    'camera': 0.20,
    'microphone': 0.15,
    'lidar': 0.15,
    'imu': 0.10,
    'network': 0.15,
    'security': 0.25  # Sicherheit wichtig!
}

hybrid_tau = {
    'camera': 50.0,
    'microphone': 40.0,
    'lidar': 35.0,
    'imu': 20.0,
    'network': 30.0,
    'security': 15.0
}

hybrid_router = ThalamoPC6Adaptive(
    modalities=hybrid_modalities,
    dimensions=hybrid_dimensions,
    priors=hybrid_priors,
    tau=hybrid_tau,
    seed=42
)

print(f"\nHybrid-Router für Roboter/IoT:")
print(f"  Modalitäten: {hybrid_router.modalities}")
print(f"  Anzahl: {hybrid_router.M} (keine nutzlosen Modalitäten!)")


# ============================================================================
# INTEGRATION IN IHR SYSTEM
# ============================================================================

print("\n\n" + "="*80)
print("INTEGRATION IN IHR MULTI-AGENT OS")
print("="*80)

print("""
So integrieren Sie custom Modalitäten in Ihr System:

1. DEFINIEREN SIE IHRE AGENTEN/DATENQUELLEN:

   my_agents = ['reasoning', 'code', 'search', 'memory', 'security']

2. SETZEN SIE DIMENSIONEN (Feature-Vektor-Größen):

   my_dims = {
       'reasoning': 128,  # LLM-Embedding-Größe
       'code': 64,        # Code-Feature-Größe
       'search': 64,
       'memory': 96,
       'security': 16
   }

3. DEFINIEREN SIE PRIORITÄTEN:

   my_priors = {
       'reasoning': 0.25,
       'code': 0.20,
       'search': 0.15,
       'memory': 0.15,
       'security': 0.35  # SICHERHEIT HOCH!
   }

4. ERSTELLEN SIE ATM-R:

   router = ThalamoPC6Adaptive(
       modalities=my_agents,
       dimensions=my_dims,
       priors=my_priors
   )

5. IN IHRER VERARBEITUNGSSCHLEIFE:

   # Extrahieren Sie Features von jedem Agenten
   x_t = {
       'reasoning': reasoning_agent.get_features(task),
       'code': code_agent.get_features(task),
       'search': search_agent.get_features(task),
       'memory': memory_agent.get_features(task),
       'security': security_agent.check_threat(task)
   }

   # Routing-Entscheidung
   out = router.step(x_t, adapt=True)

   # Nutze die Entscheidung
   active_agents = [
       my_agents[i] for i, g in enumerate(out['g'])
       if g > 0.1  # Schwellwert: 10% Aufmerksamkeit
   ]

   # Führe nur aktive Agenten aus
   for agent_name in active_agents:
       execute_agent(agent_name, task)

6. MIT SICHERHEITS-HAZARD:

   if security_threat_detected:
       out = router.step(x_t, hazard={'security': 1.0}, adapt=True)
       # Security-Agent bekommt Priorität!

""")

print("="*80)
print("FAZIT: 'Geschmack' und 'Vestibulär' sind für Sie irrelevant!")
print("       Definieren Sie eigene, sinnvolle Modalitäten!")
print("="*80)
