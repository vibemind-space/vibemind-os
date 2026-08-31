"""Train Brain with multilingual samples (DE, EN, ZH, FR, ES)."""
import json
import urllib.request

BRAIN = "http://127.0.0.1:5000"

SAMPLES = [
    # German
    {"user_text": "Zeig meine Spaces", "correct_space": "ideas"},
    {"user_text": "Erstelle Bubble Marketing", "correct_space": "ideas"},
    {"user_text": "Notiere eine Idee", "correct_space": "ideas"},
    {"user_text": "Erstelle eine App", "correct_space": "coding"},
    {"user_text": "Code Status", "correct_space": "coding"},
    {"user_text": "Oeffne Chrome", "correct_space": "desktop"},
    {"user_text": "Screenshot machen", "correct_space": "desktop"},
    {"user_text": "Disk Status", "correct_space": "openfang"},
    {"user_text": "Scanne auf Sicherheitsluecken", "correct_space": "openfang"},
    {"user_text": "Welche Agents laufen", "correct_space": "openfang"},
    {"user_text": "Video erstellen", "correct_space": "video"},
    {"user_text": "Zeig geplante Aufgaben", "correct_space": "schedule"},
    {"user_text": "Suche im Knowledge Graph", "correct_space": "rowboat"},

    # English
    {"user_text": "Show my spaces", "correct_space": "ideas"},
    {"user_text": "Create a new bubble", "correct_space": "ideas"},
    {"user_text": "Create an app for notes", "correct_space": "coding"},
    {"user_text": "Open Chrome", "correct_space": "desktop"},
    {"user_text": "Disk status check", "correct_space": "openfang"},
    {"user_text": "Scan for vulnerabilities", "correct_space": "openfang"},
    {"user_text": "Which agents are running", "correct_space": "openfang"},
    {"user_text": "Make a video", "correct_space": "video"},
    {"user_text": "Show scheduled tasks", "correct_space": "schedule"},
    {"user_text": "Search knowledge graph", "correct_space": "rowboat"},

    # Chinese
    {"user_text": "显示我的空间", "correct_space": "ideas"},
    {"user_text": "创建一个气泡", "correct_space": "ideas"},
    {"user_text": "创建一个应用", "correct_space": "coding"},
    {"user_text": "打开浏览器", "correct_space": "desktop"},
    {"user_text": "磁盘状态", "correct_space": "openfang"},
    {"user_text": "扫描安全漏洞", "correct_space": "openfang"},
    {"user_text": "哪些代理在运行", "correct_space": "openfang"},
    {"user_text": "制作视频", "correct_space": "video"},
    {"user_text": "显示计划任务", "correct_space": "schedule"},
    {"user_text": "搜索知识图谱", "correct_space": "rowboat"},

    # French
    {"user_text": "Montre mes espaces", "correct_space": "ideas"},
    {"user_text": "Cree une application", "correct_space": "coding"},
    {"user_text": "Ouvre Chrome", "correct_space": "desktop"},
    {"user_text": "Statut du disque", "correct_space": "openfang"},
    {"user_text": "Analyse de securite", "correct_space": "openfang"},
    {"user_text": "Creer une video", "correct_space": "video"},

    # Spanish
    {"user_text": "Muestra mis espacios", "correct_space": "ideas"},
    {"user_text": "Crear una aplicacion", "correct_space": "coding"},
    {"user_text": "Abrir Chrome", "correct_space": "desktop"},
    {"user_text": "Estado del disco", "correct_space": "openfang"},
    {"user_text": "Escaneo de seguridad", "correct_space": "openfang"},
    {"user_text": "Crear un video", "correct_space": "video"},
]

def train(sample):
    data = json.dumps(sample).encode()
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
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

# Train 10 rounds
print(f"Training Brain with {len(SAMPLES)} multilingual samples...")
for r in range(10):
    ok = sum(1 for s in SAMPLES if train(s))
    print(f"  Round {r+1}: {ok}/{len(SAMPLES)}")

# Test multilingual routing
print(f"\n=== MULTILINGUAL ROUTING TEST ===\n")
tests = [
    ("Disk Status", "openfang", "DE"),
    ("磁盘状态", "openfang", "ZH"),
    ("Statut du disque", "openfang", "FR"),
    ("Estado del disco", "openfang", "ES"),
    ("Zeig meine Spaces", "ideas", "DE"),
    ("显示我的空间", "ideas", "ZH"),
    ("Show my spaces", "ideas", "EN"),
    ("Erstelle eine App", "coding", "DE"),
    ("创建一个应用", "coding", "ZH"),
    ("Video erstellen", "video", "DE"),
    ("制作视频", "video", "ZH"),
    ("Make a video", "video", "EN"),
]

correct = 0
for text, expected, lang in tests:
    r = route(text)
    space = r.get("primary_space", "?")
    conf = r.get("confidence", 0)
    ms = r.get("latency_ms", 0)
    ok = "OK" if space == expected else "MISS"
    if ok == "OK":
        correct += 1
    safe_text = text.encode("ascii", errors="replace").decode()
    print(f"  [{ok}] [{lang}] '{safe_text:25s}' -> {space:12s} (exp: {expected:10s}) conf={conf:.3f} {ms:.0f}ms")

print(f"\n  Score: {correct}/{len(tests)} ({correct/len(tests)*100:.0f}%)")
