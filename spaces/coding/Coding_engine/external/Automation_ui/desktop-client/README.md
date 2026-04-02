# Desktop Streaming Client

This directory contains Python clients for streaming your desktop to the web interface.

## Quick Start

### 1. Install Dependencies

```bash
cd desktop-client
pip install -r requirements.txt
```

### 2. Run Desktop Streaming

**Option A: Direct desktop client** (recommended)
```bash
python dual_screen_capture_client.py
```

**Option B: Auto-start with monitor detection**
```bash
cd ..
python auto-start-dual-monitors.py
```

### 3. View Stream

Open your browser and navigate to the Multi-Desktop Streams page:
```
http://localhost:5173/multidesktop
```

## Configuration

### Custom FPS, Quality, Scale

```bash
python dual_screen_capture_client.py --fps 15 --quality 90 --scale 1.0
```

### Debug Mode

```bash
python dual_screen_capture_client.py --debug
```

### Custom WebSocket Server

```bash
python dual_screen_capture_client.py --server-url wss://your-custom-server.com
```

## Features

- ✅ **Dual monitor support** - Automatically detects and streams all monitors
- ✅ **Adaptive quality** - Adjusts JPEG quality based on network performance
- ✅ **Auto-reconnect** - Reconnects automatically if connection drops
- ✅ **Remote control** - Supports mouse clicks and keyboard input from web
- ✅ **Permission system** - Grants/revokes access to desktop control

## Requirements

- Python 3.8+
- Windows, macOS, or Linux
- Active internet connection for Supabase Edge Function

## Troubleshooting

### Connection Issues

If you see connection errors:

1. Check your internet connection
2. Verify the Supabase Edge Function is deployed
3. Check firewall settings

### Permission Errors

If you see permission errors on macOS/Linux:

```bash
# macOS: Grant screen recording permission in System Preferences > Security & Privacy
# Linux: Run with sudo if needed (not recommended for production)
```

### Module Not Found

If you get import errors:

```bash
pip install --upgrade -r requirements.txt
```

## Architecture

The client connects to Supabase Edge Function via WebSocket:

```
Desktop Client (Python) <--WebSocket--> Supabase Edge Function <--WebSocket--> Web UI (React)
```

All streams are relayed through the Edge Function for security and scalability.
