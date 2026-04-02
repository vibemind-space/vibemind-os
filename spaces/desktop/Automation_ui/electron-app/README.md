# Desktop Streaming Electron App

Eine Electron-Desktop-Anwendung, die den Desktop-Streaming-Service automatisch startet und den OCR Designer anzeigt.

## Features

- 🖥️ **OCR Designer**: Zeigt den OCR Designer zum Einrichten von Capture-Regionen
- 🔄 **Auto-Start Services**: Startet automatisch den Dev-Server und Desktop-Client
- 📱 **System Tray**: Minimiert in den System Tray (versteckt im Hintergrund)
- 🔁 **Auto-Restart**: Startet abgestürzte Prozesse automatisch neu
- 🚀 **Windows Autostart**: Kann beim Systemstart automatisch starten

## Installation

### Voraussetzungen

- Node.js 18+ (https://nodejs.org/)
- Python 3.10+ mit den Desktop-Client Dependencies

### Setup

1. **Dependencies installieren**:
   ```cmd
   cd electron-app
   npm install
   ```

2. **Starten**:
   ```cmd
   npm start
   ```
   
   Oder einfach **`START-ELECTRON-APP.bat`** ausführen.

## Konfiguration

Die Konfiguration ist in [`main.js`](main.js:9) definiert:

```javascript
const CONFIG = {
  devServerUrl: 'http://localhost:5173',    // Dev-Server URL
  ocrDesignerPath: '/ocr-designer',          // OCR Designer Pfad
  pythonPath: 'python',                      // Python Executable
  desktopClientScript: '../desktop-client/dual_screen_capture_client.py'
};
```

## Verwendung

### Start
- **Doppelklick auf `START-ELECTRON-APP.bat`** oder
- **`npm start`** im Terminal

### System Tray
- Die App minimiert sich beim Schließen in den System Tray
- Rechtsklick auf das Tray-Icon zeigt das Kontextmenü:
  - **Fenster anzeigen**: Öffnet das Hauptfenster
  - **Dev Tools**: Öffnet die Entwickler-Tools
  - **Beenden**: Schließt die App komplett

### Auto-Restart
Falls der Desktop-Client oder Dev-Server abstürzt, wird er automatisch nach 5 Sekunden neu gestartet.

## Windows Installer erstellen

```cmd
npm run dist
```

Erstellt einen Windows NSIS Installer im `dist/` Ordner.

## Logs

Die App zeigt alle Logs in der Konsole:
- 🟢 **INFO**: Normale Nachrichten
- 🟡 **WARNING**: Warnungen
- 🔴 **ERROR**: Fehler
- 📊 **STDOUT**: Ausgabe von Child-Prozessen
- 📛 **STDERR**: Fehlerausgabe von Child-Prozessen

## Fehlerbehebung

### "Dev-Server nicht erreichbar"
1. Prüfe ob Port 5173 frei ist
2. Starte die App neu

### "Python nicht gefunden"
1. Stelle sicher dass Python im PATH ist
2. Oder ändere `pythonPath` in der Config

### "Desktop-Client startet nicht"
1. Prüfe ob alle Python-Dependencies installiert sind
2. Führe manuell aus: `python dual_screen_capture_client.py`

## Architektur

```
┌─────────────────────────────────────────────────┐
│                 Electron App                     │
│  ┌───────────────┐    ┌───────────────────────┐ │
│  │  Main Process │    │    Renderer Process   │ │
│  │               │    │                       │ │
│  │  - Dev Server │    │  - OCR Designer UI    │ │
│  │  - Py Client  │    │  - WebSocket Stream   │ │
│  │  - System Tray│    │                       │ │
│  └───────────────┘    └───────────────────────┘ │
└─────────────────────────────────────────────────┘
         │                      │
         ▼                      ▼
┌─────────────────┐    ┌─────────────────────────┐
│   Vite Dev      │    │   Supabase Edge         │
│   Server        │◄───│   Function              │
│   :5173         │    │   (WebSocket Relay)     │
└─────────────────┘    └─────────────────────────┘
```

## Lizenz

MIT