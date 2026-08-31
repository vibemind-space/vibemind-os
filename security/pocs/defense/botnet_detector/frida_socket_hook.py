"""
Frida Socket-Level Hook — see EXACTLY what ExpressVPN sends
================================================================
Hooks at the lowest level BEFORE data leaves the process:
- Winsock send() / WSASend() — raw TCP data
- Winsock recv() / WSARecv() — raw TCP responses
- connect() — which IPs it connects to

This catches EVERYTHING — encrypted or not.
If libxvclient.dll does TLS internally, the plaintext goes through
these functions BEFORE reaching the TLS layer.

Actually: the TLS happens INSIDE the DLL, so send() sees ciphertext.
BUT: we can hook the INTERNAL functions of libxvclient.dll that
prepare HTTP requests BEFORE they enter the TLS pipeline.

Strategy: Hook Rust's internal write functions + HTTP request builders.
"""

import frida
import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

HOOK_SCRIPT = r"""
'use strict';

var count = 0;
var MAX = 500;

// Cache exports from libxvclient.dll
var xvcExports = {};
var xvcModule = Process.findModuleByName('libxvclient.dll');
if (xvcModule) {
    var exports = xvcModule.enumerateExports();
    for (var i = 0; i < exports.length; i++) {
        xvcExports[exports[i].name] = exports[i].address;
    }
    send({type: 'INFO', msg: 'libxvclient.dll: ' + exports.length + ' exports, base=' + xvcModule.base});
}

// Also cache expressvpn-sdklib.dll exports
var sdkExports = {};
var sdkModule = Process.findModuleByName('expressvpn-sdklib.dll');
if (sdkModule) {
    var exports2 = sdkModule.enumerateExports();
    for (var i = 0; i < exports2.length; i++) {
        sdkExports[exports2[i].name] = exports2[i].address;
    }
    send({type: 'INFO', msg: 'expressvpn-sdklib.dll: ' + exports2.length + ' exports, base=' + sdkModule.base});
}

function safeRead(ptr, len) {
    try { return Memory.readUtf8String(ptr, Math.min(len || 500, 2000)); } catch(e) {}
    try { return Memory.readAnsiString(ptr, Math.min(len || 500, 2000)); } catch(e) {}
    return null;
}

// ================================================================
// HOOK 1: Winsock2 send() — ALL outbound TCP data from this process
// ================================================================
// Build export cache for ws2_32.dll (findExportByName fails on some processes)
var ws2Cache = {};
var ws2Mod = Process.findModuleByName('ws2_32.dll');
if (ws2Mod) {
    var ws2Exp = ws2Mod.enumerateExports();
    for (var i = 0; i < ws2Exp.length; i++) {
        ws2Cache[ws2Exp[i].name] = ws2Exp[i].address;
    }
    send({type: 'INFO', msg: 'ws2_32.dll: ' + ws2Exp.length + ' exports cached'});
}

function findWs2(name) { return ws2Cache[name] || null; }

var ws2_send = findWs2('send');
if (ws2_send) {
    Interceptor.attach(ws2_send, {
        onEnter: function(args) {
            this.socket = args[0].toInt32();
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function(retval) {
            if (count >= MAX) return;
            var sent = retval.toInt32();
            if (sent > 0 && this.len > 0) {
                count++;
                var data = Memory.readByteArray(this.buf, Math.min(sent, 2048));
                var preview = safeRead(this.buf, Math.min(sent, 500));

                // Check if this is plaintext HTTP
                var isHttp = false;
                var isJson = false;
                var isTls = false;
                if (preview) {
                    if (preview.indexOf('HTTP/') >= 0 || preview.indexOf('GET ') === 0 ||
                        preview.indexOf('POST ') === 0 || preview.indexOf('PUT ') === 0) {
                        isHttp = true;
                    }
                    if (preview.indexOf('{') >= 0 && preview.indexOf('}') >= 0) {
                        isJson = true;
                    }
                }
                // Check for TLS record header (0x16 = handshake, 0x17 = application data)
                if (data) {
                    var bytes = new Uint8Array(data);
                    if (bytes.length > 5 && (bytes[0] === 0x16 || bytes[0] === 0x17) &&
                        bytes[1] === 0x03 && bytes[2] <= 0x04) {
                        isTls = true;
                    }
                }

                send({
                    type: 'SEND',
                    n: count,
                    socket: this.socket,
                    size: sent,
                    isHttp: isHttp,
                    isJson: isJson,
                    isTls: isTls,
                    preview: preview ? preview.substring(0, 500) : null,
                }, data);
            }
        }
    });
    send({type: 'HOOKED', name: 'ws2_32::send'});
}

// ================================================================
// HOOK 2: Winsock2 recv() — ALL inbound TCP data
// ================================================================
var ws2_recv = findWs2('recv');
if (ws2_recv) {
    Interceptor.attach(ws2_recv, {
        onEnter: function(args) {
            this.socket = args[0].toInt32();
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function(retval) {
            if (count >= MAX) return;
            var received = retval.toInt32();
            if (received > 0) {
                count++;
                var data = Memory.readByteArray(this.buf, Math.min(received, 2048));
                var preview = safeRead(this.buf, Math.min(received, 500));

                var isHttp = false;
                var isJson = false;
                var isTls = false;
                if (preview) {
                    if (preview.indexOf('HTTP/') >= 0) isHttp = true;
                    if (preview.indexOf('{') >= 0 && preview.indexOf('}') >= 0) isJson = true;
                }
                if (data) {
                    var bytes = new Uint8Array(data);
                    if (bytes.length > 5 && (bytes[0] === 0x16 || bytes[0] === 0x17) &&
                        bytes[1] === 0x03 && bytes[2] <= 0x04) {
                        isTls = true;
                    }
                }

                send({
                    type: 'RECV',
                    n: count,
                    socket: this.socket,
                    size: received,
                    isHttp: isHttp,
                    isJson: isJson,
                    isTls: isTls,
                    preview: preview ? preview.substring(0, 500) : null,
                }, data);
            }
        }
    });
    send({type: 'HOOKED', name: 'ws2_32::recv'});
}

// ================================================================
// HOOK 3: connect() — which IPs does it connect to?
// ================================================================
var ws2_connect = findWs2('connect');
if (ws2_connect) {
    Interceptor.attach(ws2_connect, {
        onEnter: function(args) {
            this.socket = args[0].toInt32();
            var sockaddr = args[1];
            var family = sockaddr.readU16();

            if (family === 2) { // AF_INET
                var port = (sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8();
                var ip = sockaddr.add(4).readU8() + '.' +
                         sockaddr.add(5).readU8() + '.' +
                         sockaddr.add(6).readU8() + '.' +
                         sockaddr.add(7).readU8();
                send({type: 'CONNECT', socket: this.socket, ip: ip, port: port});
            }
        }
    });
    send({type: 'HOOKED', name: 'ws2_32::connect'});
}

// ================================================================
// HOOK 4: WSASend — async send (more common in modern code)
// ================================================================
var ws2_wsasend = findWs2('WSASend');
if (ws2_wsasend) {
    Interceptor.attach(ws2_wsasend, {
        onEnter: function(args) {
            if (count >= MAX) return;
            this.socket = args[0].toInt32();
            // args[1] = LPWSABUF (pointer to array of {len, buf})
            var wsabuf = args[1];
            var bufCount = args[2].toInt32();

            if (bufCount > 0 && !wsabuf.isNull()) {
                var len = wsabuf.readU32();
                var buf = wsabuf.add(Process.pointerSize).readPointer();

                if (len > 0 && len < 65536 && !buf.isNull()) {
                    count++;
                    var data = Memory.readByteArray(buf, Math.min(len, 2048));
                    var preview = safeRead(buf, Math.min(len, 500));

                    var isHttp = preview && (preview.indexOf('HTTP/') >= 0 || preview.indexOf('GET ') === 0 || preview.indexOf('POST ') === 0);
                    var isJson = preview && preview.indexOf('{') >= 0;
                    var isTls = false;
                    if (data) {
                        var bytes = new Uint8Array(data);
                        if (bytes.length > 5 && (bytes[0] === 0x16 || bytes[0] === 0x17) && bytes[1] === 0x03) {
                            isTls = true;
                        }
                    }

                    send({
                        type: 'WSASEND',
                        n: count,
                        socket: this.socket,
                        size: len,
                        isHttp: isHttp,
                        isJson: isJson,
                        isTls: isTls,
                        preview: preview ? preview.substring(0, 500) : null,
                    }, data);
                }
            }
        }
    });
    send({type: 'HOOKED', name: 'ws2_32::WSASend'});
}

send({type: 'READY', msg: 'All hooks installed. Capturing...'});
"""


def main():
    print("="*60)
    print("  EXPRESSVPN SOCKET INTERCEPTOR")
    print("  See EXACTLY what goes over the wire")
    print("="*60)

    try:
        out = subprocess.check_output(
            ["tasklist", "/fi", "IMAGENAME eq expressvpn-service.exe", "/fo", "csv", "/nh"],
            timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
        pid = None
        for line in out.strip().split("\n"):
            parts = line.split(",")
            if len(parts) >= 2 and parts[1].strip('"').isdigit():
                pid = int(parts[1].strip('"'))
                break
    except Exception:
        pid = None

    if not pid:
        print("  expressvpn-service.exe not found!")
        return

    print(f"  Target PID: {pid}")

    captured = []
    stats = {"send": 0, "recv": 0, "connect": 0, "tls": 0, "http": 0, "json": 0, "bytes_out": 0, "bytes_in": 0}
    start = time.time()

    def on_msg(msg, data):
        if msg["type"] != "send":
            if msg["type"] == "error":
                desc = msg.get("description", "")
                if len(desc) > 5 and "access" not in desc.lower():
                    print(f"  [ERR] {desc[:80]}")
            return

        p = msg["payload"]
        t = p.get("type", "?")
        elapsed = round(time.time() - start, 1)

        if t == "INFO":
            print(f"  [INFO] {p['msg']}")
        elif t == "HOOKED":
            print(f"  [HOOK] {p['name']}")
        elif t == "READY":
            print(f"\n  {p['msg']} (60 seconds)\n")

        elif t == "CONNECT":
            stats["connect"] += 1
            print(f"  [{elapsed:5.1f}s] CONNECT -> {p['ip']}:{p['port']}")
            captured.append({"time": elapsed, "type": "CONNECT", "ip": p["ip"], "port": p["port"]})

        elif t in ("SEND", "WSASEND"):
            stats["send"] += 1
            stats["bytes_out"] += p.get("size", 0)

            label = ""
            if p.get("isTls"):
                stats["tls"] += 1
                label = "[TLS]"
            elif p.get("isHttp"):
                stats["http"] += 1
                label = "[HTTP PLAINTEXT!]"
            elif p.get("isJson"):
                stats["json"] += 1
                label = "[JSON!]"
            else:
                label = "[DATA]"

            preview = p.get("preview", "")
            if preview:
                safe = preview[:120].encode("ascii", "replace").decode()
            else:
                safe = ""

            # Only print interesting (non-TLS) traffic
            if not p.get("isTls"):
                print(f"  [{elapsed:5.1f}s] >>> SEND {p['size']:6d}b {label} sock={p.get('socket','?')}")
                if safe.strip() and len(safe.strip()) > 5:
                    for line in safe.split("\n")[:3]:
                        if line.strip():
                            print(f"           {line.strip()[:100]}")

            entry = {"time": elapsed, "type": t, "size": p["size"],
                     "tls": p.get("isTls"), "http": p.get("isHttp"), "json": p.get("isJson")}
            if not p.get("isTls") and preview:
                entry["preview"] = preview[:500]
            if data and not p.get("isTls"):
                entry["hex"] = data.hex()[:400]
            captured.append(entry)

        elif t == "RECV":
            stats["recv"] += 1
            stats["bytes_in"] += p.get("size", 0)

            if not p.get("isTls"):
                preview = p.get("preview", "")
                safe = preview[:120].encode("ascii", "replace").decode() if preview else ""
                label = "[HTTP]" if p.get("isHttp") else "[JSON]" if p.get("isJson") else "[DATA]"
                print(f"  [{elapsed:5.1f}s] <<< RECV {p['size']:6d}b {label} sock={p.get('socket','?')}")
                if safe.strip() and len(safe.strip()) > 5:
                    for line in safe.split("\n")[:3]:
                        if line.strip():
                            print(f"           {line.strip()[:100]}")

    try:
        session = frida.attach(pid)
        script = session.create_script(HOOK_SCRIPT)
        script.on("message", on_msg)
        script.load()
        time.sleep(60)
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
    finally:
        try:
            session.detach()
        except:
            pass

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(f"expressvpn_tracking_captured_{ts}.json")
    out_file.write_text(json.dumps(captured, indent=2, ensure_ascii=True))

    print(f"\n{'='*60}")
    print(f"  RESULTS — 60 seconds capture")
    print(f"{'='*60}")
    print(f"  Packets sent:     {stats['send']}")
    print(f"  Packets received: {stats['recv']}")
    print(f"  Connections:      {stats['connect']}")
    print(f"  Bytes out:        {stats['bytes_out']:,}")
    print(f"  Bytes in:         {stats['bytes_in']:,}")
    print(f"  TLS encrypted:    {stats['tls']}")
    print(f"  HTTP plaintext:   {stats['http']}")
    print(f"  JSON data:        {stats['json']}")
    print(f"  Saved to:         {out_file}")

    # Show non-TLS traffic summary
    plaintext = [c for c in captured if c.get("type") in ("SEND", "WSASEND") and not c.get("tls") and c.get("preview")]
    if plaintext:
        print(f"\n  === PLAINTEXT TRAFFIC ({len(plaintext)} packets) ===")
        for p in plaintext[:20]:
            safe = p["preview"][:150].encode("ascii", "replace").decode()
            print(f"  [{p['time']:5.1f}s] {p['size']:6d}b: {safe[:120]}")
    else:
        print(f"\n  ALL traffic is TLS encrypted — no plaintext found")
        print(f"  ExpressVPN encrypts everything before it reaches Winsock")


if __name__ == "__main__":
    main()
