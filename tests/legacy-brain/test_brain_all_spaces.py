"""Test Brain routing for ALL 14 spaces."""
import json
import urllib.request

BRAIN = "http://127.0.0.1:5000"

def route(text):
    data = json.dumps({"user_text": text}).encode()
    req = urllib.request.Request(f"{BRAIN}/api/cortex/route", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())

tests = [
    # Ideas
    ("Zeig meine Spaces", "ideas"),
    ("Erstelle eine Bubble", "ideas"),
    ("Notiere eine Idee", "ideas"),
    # Coding
    ("Erstelle eine App", "coding"),
    ("Code Status", "coding"),
    # Desktop
    ("Oeffne Chrome", "desktop"),
    ("Screenshot machen", "desktop"),
    # OpenFang
    ("Disk Status", "openfang"),
    ("Welche Agents laufen", "openfang"),
    ("Scanne auf Sicherheitsluecken", "openfang"),
    # Video
    ("Ich will ein Video machen", "video"),
    ("Video Status", "video"),
    # Schedule
    ("Zeig geplante Aufgaben", "schedule"),
    ("Erinnere mich morgen", "schedule"),
    # N8n
    ("N8n Status", "n8n"),
    ("Zeig alle Workflows", "n8n"),
    # Minibook
    ("Minibook Status", "minibook"),
    ("Starte eine Diskussion", "minibook"),
    # Rowboat
    ("Rowboat Status", "rowboat"),
    ("Suche im Knowledge Graph", "rowboat"),
    ("Wissen durchsuchen", "rowboat"),
    # Research
    ("Recherchiere kuenstliche Intelligenz", "research"),
    # AgentFarm
    ("Agent Farm Status", "agentfarm"),
    ("Erstelle ein Agent Team", "agentfarm"),
    # MiroFish
    ("Bewerte die Bubble", "mirofish"),
    ("Simuliere wie der Post ankommt", "mirofish"),
    # Flowzen
    ("Was empfiehlst du", "flowzen"),
]

ok = 0
total = len(tests)
for text, expected in tests:
    r = route(text)
    space = r.get("primary_space", "?")
    conf = r.get("confidence", 0)
    ms = r.get("latency_ms", 0)
    match = "OK" if space == expected else "MISS"
    if match == "OK":
        ok += 1
    safe = text.encode("ascii", errors="replace").decode()
    print(f"  [{match:4s}] {safe:40s} -> {space:12s} (exp: {expected:10s}) conf={conf:.3f} {ms:.0f}ms")

print(f"\n  Score: {ok}/{total} ({ok/total*100:.0f}%)")
