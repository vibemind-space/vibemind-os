"""Train Brain with samples for ALL 14 spaces — balanced distribution."""
import json
import urllib.request

BRAIN = "http://127.0.0.1:5000"

SAMPLES = [
    # N8n (needs more samples)
    {"user_text": "N8n Status", "correct_space": "n8n"},
    {"user_text": "Zeig alle Workflows", "correct_space": "n8n"},
    {"user_text": "Erstelle einen Workflow", "correct_space": "n8n"},
    {"user_text": "Workflow aktivieren", "correct_space": "n8n"},
    {"user_text": "Automatisierung erstellen", "correct_space": "n8n"},
    # Minibook
    {"user_text": "Minibook Status", "correct_space": "minibook"},
    {"user_text": "Starte eine Diskussion", "correct_space": "minibook"},
    {"user_text": "Diskussion ueber Architektur", "correct_space": "minibook"},
    {"user_text": "Zusammenarbeit starten", "correct_space": "minibook"},
    {"user_text": "Agents sollen zusammen diskutieren", "correct_space": "minibook"},
    # Research
    {"user_text": "Recherchiere kuenstliche Intelligenz", "correct_space": "research"},
    {"user_text": "Web Recherche starten", "correct_space": "research"},
    {"user_text": "Suche im Internet nach VibeMind", "correct_space": "research"},
    {"user_text": "Recherchiere Konkurrenten", "correct_space": "research"},
    {"user_text": "Finde Informationen ueber Robotik", "correct_space": "research"},
    # AgentFarm
    {"user_text": "Agent Farm Status", "correct_space": "agentfarm"},
    {"user_text": "Erstelle ein Agent Team", "correct_space": "agentfarm"},
    {"user_text": "Starte die Agent Pipeline", "correct_space": "agentfarm"},
    {"user_text": "Welche Teams gibt es", "correct_space": "agentfarm"},
    {"user_text": "Agent Team fuer Code Review", "correct_space": "agentfarm"},
    # MiroFish
    {"user_text": "Bewerte die Bubble", "correct_space": "mirofish"},
    {"user_text": "Simuliere wie der Post ankommt", "correct_space": "mirofish"},
    {"user_text": "MiroFish Simulation starten", "correct_space": "mirofish"},
    {"user_text": "Ist das Projekt bereit fuer Produktion", "correct_space": "mirofish"},
    {"user_text": "Go oder No-Go fuer Marketing", "correct_space": "mirofish"},
    # Flowzen
    {"user_text": "Was empfiehlst du", "correct_space": "flowzen"},
    {"user_text": "Womit soll ich anfangen", "correct_space": "flowzen"},
    {"user_text": "Was ist die beste Aufgabe jetzt", "correct_space": "flowzen"},
    {"user_text": "Empfehlung bitte", "correct_space": "flowzen"},
    {"user_text": "Wie ist meine Stimmung", "correct_space": "flowzen"},
    # Rowboat (more samples)
    {"user_text": "Rowboat Status", "correct_space": "rowboat"},
    {"user_text": "Knowledge Graph durchsuchen", "correct_space": "rowboat"},
    {"user_text": "Wissen abfragen", "correct_space": "rowboat"},
    {"user_text": "Frag die Wissensdatenbank", "correct_space": "rowboat"},
    # Desktop (more samples)
    {"user_text": "Screenshot machen", "correct_space": "desktop"},
    {"user_text": "Klick auf den Button", "correct_space": "desktop"},
    {"user_text": "Tippe Hallo", "correct_space": "desktop"},
    # Schedule (more samples)
    {"user_text": "Erinnere mich morgen", "correct_space": "schedule"},
    {"user_text": "Aufgabe planen", "correct_space": "schedule"},
    {"user_text": "Timer stellen", "correct_space": "schedule"},
    # Bubbles (separate from ideas)
    {"user_text": "Zeig alle Bubbles", "correct_space": "bubbles"},
    {"user_text": "Loesche Bubble Test", "correct_space": "bubbles"},
]


def train(s):
    data = json.dumps(s).encode()
    req = urllib.request.Request(f"{BRAIN}/api/cortex/route/train", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return True
    except:
        return False


def route(text):
    data = json.dumps({"user_text": text}).encode()
    req = urllib.request.Request(f"{BRAIN}/api/cortex/route", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


print(f"Training {len(SAMPLES)} samples x 10 rounds...")
for r in range(10):
    ok = sum(1 for s in SAMPLES if train(s))
    if (r + 1) % 5 == 0:
        print(f"  Round {r+1}: {ok}/{len(SAMPLES)}")

print(f"\n=== ALL-SPACE ROUTING TEST ===\n")
tests = [
    ("Zeig meine Spaces", "ideas"),
    ("Erstelle eine App", "coding"),
    ("Oeffne Chrome", "desktop"),
    ("Screenshot machen", "desktop"),
    ("Disk Status", "openfang"),
    ("Video erstellen", "video"),
    ("Zeig geplante Aufgaben", "schedule"),
    ("Erinnere mich morgen", "schedule"),
    ("N8n Status", "n8n"),
    ("Zeig alle Workflows", "n8n"),
    ("Minibook Status", "minibook"),
    ("Starte eine Diskussion", "minibook"),
    ("Rowboat Status", "rowboat"),
    ("Suche im Knowledge Graph", "rowboat"),
    ("Recherchiere KI", "research"),
    ("Agent Farm Status", "agentfarm"),
    ("Bewerte die Bubble", "mirofish"),
    ("Simuliere den Post", "mirofish"),
    ("Was empfiehlst du", "flowzen"),
    ("Zeig alle Bubbles", "bubbles"),
]

ok = 0
for text, expected in tests:
    r = route(text)
    space = r.get("primary_space", "?")
    conf = r.get("confidence", 0)
    ms = r.get("latency_ms", 0)
    match = "OK" if space == expected else "MISS"
    if match == "OK":
        ok += 1
    safe = text.encode("ascii", errors="replace").decode()
    print(f"  [{match:4s}] {safe:35s} -> {space:12s} (exp: {expected:10s}) conf={conf:.3f} {ms:.0f}ms")

print(f"\n  Score: {ok}/{len(tests)} ({ok/len(tests)*100:.0f}%)")
