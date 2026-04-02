# Clawdbot Integration

Control desktop automation via WhatsApp, Telegram, Discord, Slack, Signal, and iMessage.

## Quick Start

### 1. Install Clawdbot

```bash
npm i -g clawdbot
clawdbot onboard
```

### 2. Connect Messaging Platforms

```bash
# WhatsApp (QR code)
clawdbot channels login --channel whatsapp

# Telegram (Bot Token)
clawdbot channels login --channel telegram

# Discord
clawdbot channels login --channel discord
```

### 3. Install the Plugin

Copy or symlink the plugin to Clawdbot's extensions folder:

```bash
# Windows
xcopy /E /I clawdbot\plugins\automation-ui "%USERPROFILE%\.clawdbot\extensions\automation-ui"

# Linux/macOS
cp -r clawdbot/plugins/automation-ui ~/.clawdbot/extensions/

# Or symlink
ln -s $(pwd)/clawdbot/plugins/automation-ui ~/.clawdbot/extensions/automation-ui
```

### 4. Install the Skill

```bash
# Copy skill
cp -r clawdbot/skills/desktop-automation ~/.clawdbot/skills/
```

### 5. Start Services

```bash
# Start everything (including Clawdbot)
scripts\start-all.bat

# Or manually:
clawdbot gateway  # Port 18789
```

## Usage

Send commands via connected messaging platforms:

| Command | Description |
|---------|-------------|
| `öffne chrome` | Open Chrome browser |
| `öffne google.com` | Open website |
| `tippe Hallo Welt` | Type text |
| `scrolle nach unten` | Scroll down |
| `screenshot` | Send screenshot |
| `lesen` / `ocr` | Read screen text |
| `drücke strg+c` | Press Ctrl+C |
| `hilfe` | Show help |

## Architecture

```
WhatsApp/Telegram/Discord
         │
         ▼
   Clawdbot Gateway (Port 18789)
         │
         │ HTTP/WebSocket
         ▼
   FastAPI Backend (Port 8007)
   /api/clawdbot/*
         │
         ▼
   IntentParser + CommandExecutor
         │
         ▼
   PyAutoGUI / Tesseract OCR
```

## Files

| File | Purpose |
|------|---------|
| `plugins/automation-ui/` | Clawdbot plugin (TypeScript) |
| `skills/desktop-automation/` | Skill definition (SKILL.md) |
| `config/clawdbot.json` | Configuration |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/clawdbot/command` | POST | Execute command |
| `/api/clawdbot/screenshot` | GET | Get screenshot |
| `/api/clawdbot/status` | GET | Get bridge status |
| `/api/clawdbot/sessions` | GET | List active sessions |
| `/api/clawdbot/webhook` | POST | Webhook callback |
| `/api/clawdbot/health` | GET | Health check |

## Configuration

Edit `config/clawdbot.json`:

```json
{
  "enabled": true,
  "platforms": {
    "whatsapp": { "enabled": true },
    "telegram": { "enabled": true }
  },
  "security": {
    "rate_limit": {
      "commands_per_minute": 10
    }
  }
}
```

## Troubleshooting

### Clawdbot not starting

```bash
# Check if installed
clawdbot --version

# Re-onboard
clawdbot onboard
```

### Plugin not loading

```bash
# Check plugin location
ls ~/.clawdbot/extensions/

# Restart gateway
clawdbot gateway
```

### Commands not working

```bash
# Test API directly
curl http://localhost:8007/api/clawdbot/status

# Test command
curl -X POST http://localhost:8007/api/clawdbot/command \
  -H "Content-Type: application/json" \
  -d '{"command": "screenshot"}'
```
