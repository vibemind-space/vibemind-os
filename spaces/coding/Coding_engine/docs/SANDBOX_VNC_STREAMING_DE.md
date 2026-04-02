# Sandbox & VNC Streaming - Dokumentation

## Übersicht

Das Sandbox-System ermöglicht die isolierte Ausführung und Visualisierung von generierten Anwendungen in Docker-Containern mit VNC-Streaming.

---

## Continuous Sandbox Mode

**Flag:** `--continuous-sandbox`

**Trigger:** Sofort bei Start (VOR der Code-Generierung!)

### Ablauf

```text
┌────────────────────────────────────────────────────────────┐
│  1. Container erstellen (sandbox-test Image)               │
│  2. VNC-Services starten (Xvfb + x11vnc + noVNC)          │
│  3. Projekt in Container kopieren                          │
│  4. Dependencies installieren                              │
│  5. Alle 30 Sekunden: Start App → Health Check → Kill     │
└────────────────────────────────────────────────────────────┘
```

**VNC Stream:** `http://localhost:6080/vnc.html`

---

## VNC-Architektur

### Komponenten im Container

| Komponente | Port | Beschreibung |
|------------|------|--------------|
| **Xvfb** | :99 | Virtual Framebuffer (Display) |
| **x11vnc** | 5900 | VNC Server |
| **noVNC/websockify** | 6080 | Web-Interface für VNC |
| **Chromium** | - | Browser für Web-Apps |

### Startsequenz

```bash
# 1. Virtual Display starten
Xvfb :99 -screen 0 1280x800x24 &

# 2. VNC Server starten
x11vnc -display :99 -nopw -forever -shared -rfbport 5900 -bg

# 3. Web-Interface starten
websockify --web=/usr/share/novnc 6080 localhost:5900 &
```

---

## File Sync während Generierung

### Ablauf

```text
GeneratorAgent schreibt Code
       ↓
ContinuousDebugAgent erkennt Änderung
       ↓
docker cp sync_file.tsx container:/app/src/
       ↓
Hot-Reload triggert (pkill node)
       ↓
App startet mit neuem Code
       ↓
VNC zeigt Live-Update
```

### Code-Beispiel (ContainerFileSyncer)

```python
class ContainerFileSyncer:
    """Synct Dateien zum laufenden Docker-Container."""

    async def sync_file(self, file_path: str) -> bool:
        """Einzelne Datei via docker cp synchronisieren."""
        cmd = ["docker", "cp", str(local_path), f"{container_id}:{container_path}"]
        # ...

    async def trigger_rebuild(self) -> bool:
        """Hot-Reload triggern via pkill oder touch."""
        # pkill -f node | vite | npm
```

---

## Docker Image: sandbox-test

### Enthaltene Software

- **Node.js 20** - JavaScript Runtime
- **Python 3.11** - Python Runtime
- **Xvfb** - Virtual Framebuffer
- **x11vnc** - VNC Server
- **noVNC + websockify** - Web VNC Client
- **Chromium** - Browser

### Dockerfile Location

```text
infra/docker/Dockerfile.sandbox
```

### Image bauen

```bash
docker build -t sandbox-test -f infra/docker/Dockerfile.sandbox infra/docker/
```

---

## CLI-Flags für VNC/Sandbox

| Flag | Beschreibung | Default |
|------|-------------|---------|
| `--enable-sandbox` | Docker-Sandbox aktivieren | false |
| `--enable-vnc` | VNC-Streaming aktivieren | false |
| `--continuous-sandbox` | Sandbox VOR Codegen starten | false |
| `--vnc-port PORT` | noVNC Web-Port | 6080 |
| `--sandbox-interval SEC` | Sekunden zwischen Test-Zyklen | 30 |
| `--persistent-deploy` | VNC nach Konvergenz behalten | false |

---

## Verwendung

### Standard (VNC nach Build)

```bash
python run_society_hybrid.py requirements.json \
    --enable-sandbox \
    --enable-vnc
```

### Continuous Mode (VNC von Anfang an)

```bash
python run_society_hybrid.py requirements.json \
    --continuous-sandbox \
    --enable-vnc
```

### Mit allen Features

```bash
python run_society_hybrid.py requirements.json \
    --autonomous \
    --continuous-sandbox \
    --enable-vnc \
    --dashboard \
    --enable-validation \
    --persistent-deploy
```

---

## Troubleshooting

### VNC nicht erreichbar

1. Prüfen ob Container läuft: `docker ps | findstr sandbox`
2. Ports prüfen: `netstat -an | findstr 6080`
3. Container-Logs: `docker logs <container_id>`

### Schwarzer Bildschirm im VNC

1. Xvfb prüfen: `docker exec <container> ps aux | grep Xvfb`
2. Display-Variable: `docker exec <container> echo $DISPLAY`
3. x11vnc-Logs: `docker exec <container> cat /tmp/x11vnc.log`

### Hot-Reload funktioniert nicht

1. File Sync prüfen: Logs auf "sync_file" durchsuchen
2. Prozess-Kill prüfen: `docker exec <container> ps aux`
3. Manueller Neustart: `docker exec <container> pkill -f node`
