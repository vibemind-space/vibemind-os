"""Train Brain (Tahlamus) with ground truth routing examples."""
import json
import urllib.request
import time

BRAIN_URL = "http://127.0.0.1:5000"

SAMPLES = [
    # Ideas Space
    {"user_text": "Zeig meine Spaces", "correct_space": "ideas", "event_type": "bubble.list"},
    {"user_text": "Erstelle Bubble Marketing", "correct_space": "ideas", "event_type": "bubble.create"},
    {"user_text": "Notiere API Design", "correct_space": "ideas", "event_type": "idea.create"},
    {"user_text": "Zeig alle Ideen", "correct_space": "ideas", "event_type": "idea.list"},
    {"user_text": "Verlinke die Ideen", "correct_space": "ideas", "event_type": "idea.auto_link"},
    # Coding Space
    {"user_text": "Erstelle eine App fuer Notizen", "correct_space": "coding", "event_type": "code.generate"},
    {"user_text": "Code Status", "correct_space": "coding", "event_type": "code.status"},
    # Desktop Space
    {"user_text": "Oeffne Chrome", "correct_space": "desktop", "event_type": "desktop.open_app"},
    {"user_text": "Screenshot machen", "correct_space": "desktop", "event_type": "desktop.screenshot"},
    {"user_text": "Klick auf OK", "correct_space": "desktop", "event_type": "desktop.click"},
    # OpenFang Space
    {"user_text": "Disk Status", "correct_space": "openfang", "event_type": "openfang.disk_status"},
    {"user_text": "Scanne auf Sicherheitsluecken", "correct_space": "openfang", "event_type": "openfang.vuln_scan"},
    {"user_text": "Welche Agents laufen", "correct_space": "openfang", "event_type": "openfang.agent_status"},
    {"user_text": "Canary Status", "correct_space": "openfang", "event_type": "openfang.canary_status"},
    {"user_text": "Pruefe meinen PC", "correct_space": "openfang", "event_type": "openfang.os_shield"},
    {"user_text": "Analysiere die Logs", "correct_space": "openfang", "event_type": "openfang.log_analysis"},
    # Video Space
    {"user_text": "Ich will ein Video machen", "correct_space": "video", "event_type": "video.workflow"},
    {"user_text": "Video Status", "correct_space": "video", "event_type": "video.status"},
    {"user_text": "Zeig meine Videos", "correct_space": "video", "event_type": "video.gallery"},
    {"user_text": "Demo Video erstellen", "correct_space": "video", "event_type": "video.workflow"},
    # Schedule Space
    {"user_text": "Zeig geplante Aufgaben", "correct_space": "schedule", "event_type": "schedule.list"},
    {"user_text": "Erinnere mich morgen um 9", "correct_space": "schedule", "event_type": "schedule.create"},
    # N8n Space
    {"user_text": "N8n Status", "correct_space": "n8n", "event_type": "n8n.status"},
    {"user_text": "Zeig alle Workflows", "correct_space": "n8n", "event_type": "n8n.list"},
    # Minibook Space
    {"user_text": "Minibook Status", "correct_space": "minibook", "event_type": "minibook.status"},
    {"user_text": "Starte Diskussion", "correct_space": "minibook", "event_type": "minibook.discuss"},
    # Rowboat Space
    {"user_text": "Rowboat Status", "correct_space": "rowboat", "event_type": "roarboot.status"},
    {"user_text": "Suche im Knowledge Graph", "correct_space": "rowboat", "event_type": "roarboot.search"},
    # Research Space
    {"user_text": "Recherchiere kuenstliche Intelligenz", "correct_space": "research", "event_type": "research.web"},
    # AgentFarm Space
    {"user_text": "Agent Farm Status", "correct_space": "agentfarm", "event_type": "agentfarm.status"},
]


def train_sample(sample):
    data = json.dumps(sample).encode()
    req = urllib.request.Request(
        f"{BRAIN_URL}/api/cortex/route/train",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return True
    except Exception:
        return False


def route(user_text, event_type=""):
    data = json.dumps({"user_text": user_text, "event_type": event_type}).encode()
    req = urllib.request.Request(
        f"{BRAIN_URL}/api/cortex/route",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


# Train multiple rounds
ROUNDS = 10
print(f"Training Brain with {len(SAMPLES)} samples x {ROUNDS} rounds...")
for r in range(ROUNDS):
    ok = sum(1 for s in SAMPLES if train_sample(s))
    print(f"  Round {r+1}: {ok}/{len(SAMPLES)}")

# Test after training
print(f"\n=== POST-TRAINING ROUTING TEST ===\n")
tests = [
    ("Zeig meine Spaces", "ideas"),
    ("Erstelle eine App", "coding"),
    ("Oeffne Chrome", "desktop"),
    ("Disk Status", "openfang"),
    ("Video Status", "video"),
    ("Zeig geplante Aufgaben", "schedule"),
    ("N8n Status", "n8n"),
    ("Minibook Status", "minibook"),
    ("Rowboat Status", "rowboat"),
    ("Recherchiere KI", "research"),
    ("Agent Farm Status", "agentfarm"),
]

correct = 0
for text, expected in tests:
    result = route(text)
    space = result.get("primary_space", "?")
    conf = result.get("confidence", 0)
    ms = result.get("latency_ms", 0)
    ok = "OK" if space == expected else "MISS"
    if ok == "OK":
        correct += 1
    print(f"  [{ok}] '{text:35s}' -> {space:12s} (expected {expected:10s}) conf={conf:.3f} {ms:.0f}ms")

print(f"\n  Score: {correct}/{len(tests)} ({correct/len(tests)*100:.0f}%)")
