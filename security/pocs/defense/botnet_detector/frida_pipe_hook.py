"""Frida hook on ReadFile/WriteFile in expressvpn-service.exe to intercept pipe traffic."""
import frida
import json
import subprocess
import time
from pathlib import Path

HOOK = r"""
'use strict';
var count = 0;
var MAX = 500;

// Cache of handle -> pipe name mappings
var handleMap = {};

// Build export cache (findExportByName fails on some processes)
var _cache = {};
['kernel32.dll', 'ws2_32.dll', 'KERNELBASE.dll'].forEach(function(mod) {
    try {
        var m = Process.findModuleByName(mod);
        if (m) {
            m.enumerateExports().forEach(function(e) { _cache[mod + '::' + e.name] = e.address; });
        }
    } catch(ex) {}
});
function findFn(mod, name) { return _cache[mod + '::' + name] || null; }

// Hook CreateFileW to track pipe handles
var createFile = findFn('kernel32.dll', 'CreateFileW') || findFn('KERNELBASE.dll', 'CreateFileW');
if (createFile) {
    Interceptor.attach(createFile, {
        onEnter: function(args) {
            this.path = args[0].readUtf16String();
        },
        onLeave: function(retval) {
            if (this.path && retval.toInt32() !== -1) {
                var p = this.path.toLowerCase();
                if (p.indexOf('pipe') >= 0 || p.indexOf('express') >= 0 || p.indexOf('vpn') >= 0) {
                    handleMap[retval.toInt32()] = this.path;
                    send({type: 'PIPE_OPEN', path: this.path, handle: retval.toInt32()});
                }
            }
        }
    });
}

// Hook WriteFile
var writeFile = findFn('kernel32.dll', 'WriteFile') || findFn('KERNELBASE.dll', 'WriteFile');
if (writeFile) {
    Interceptor.attach(writeFile, {
        onEnter: function(args) {
            this.handle = args[0].toInt32();
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function(retval) {
            if (count >= MAX) return;
            if (retval.toInt32() !== 0 && this.len > 0) {
                var pipeName = handleMap[this.handle] || '';
                if (pipeName || this.len > 10) {
                    count++;
                    var data = Memory.readByteArray(this.buf, Math.min(this.len, 2048));
                    var txt = '';
                    try { txt = Memory.readUtf8String(this.buf, Math.min(this.len, 500)); } catch(e) {}
                    send({
                        type: 'WRITE',
                        handle: this.handle,
                        pipe: pipeName,
                        size: this.len,
                        n: count,
                        text: txt.substring(0, 500),
                    }, data);
                }
            }
        }
    });
    send({type: 'HOOKED', name: 'WriteFile'});
}

// Hook ReadFile
var readFile = findFn('kernel32.dll', 'ReadFile') || findFn('KERNELBASE.dll', 'ReadFile');
if (readFile) {
    Interceptor.attach(readFile, {
        onEnter: function(args) {
            this.handle = args[0].toInt32();
            this.buf = args[1];
            this.pBytesRead = args[3];
        },
        onLeave: function(retval) {
            if (count >= MAX) return;
            if (retval.toInt32() !== 0 && this.pBytesRead && !this.pBytesRead.isNull()) {
                try {
                    var bytesRead = this.pBytesRead.readU32();
                    if (bytesRead > 0) {
                        var pipeName = handleMap[this.handle] || '';
                        if (pipeName || bytesRead > 10) {
                            count++;
                            var data = Memory.readByteArray(this.buf, Math.min(bytesRead, 2048));
                            var txt = '';
                            try { txt = Memory.readUtf8String(this.buf, Math.min(bytesRead, 500)); } catch(e) {}
                            send({
                                type: 'READ',
                                handle: this.handle,
                                pipe: pipeName,
                                size: bytesRead,
                                n: count,
                                text: txt.substring(0, 500),
                            }, data);
                        }
                    }
                } catch(e) {}
            }
        }
    });
    send({type: 'HOOKED', name: 'ReadFile'});
}

// Also hook send/recv for network traffic
var ws2Send = findFn('ws2_32.dll', 'send');
if (ws2Send) {
    Interceptor.attach(ws2Send, {
        onEnter: function(args) {
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function(retval) {
            if (count >= MAX) return;
            var sent = retval.toInt32();
            if (sent > 0 && this.len > 20) {
                count++;
                var data = Memory.readByteArray(this.buf, Math.min(sent, 2048));
                var txt = '';
                try { txt = Memory.readUtf8String(this.buf, Math.min(sent, 300)); } catch(e) {}
                send({type: 'NET_SEND', size: sent, n: count, text: txt.substring(0, 300)}, data);
            }
        }
    });
    send({type: 'HOOKED', name: 'ws2_32::send'});
}

var ws2Recv = findFn('ws2_32.dll', 'recv');
if (ws2Recv) {
    Interceptor.attach(ws2Recv, {
        onEnter: function(args) {
            this.buf = args[1];
        },
        onLeave: function(retval) {
            if (count >= MAX) return;
            var recvd = retval.toInt32();
            if (recvd > 0 && recvd < 65536) {
                count++;
                var data = Memory.readByteArray(this.buf, Math.min(recvd, 2048));
                var txt = '';
                try { txt = Memory.readUtf8String(this.buf, Math.min(recvd, 300)); } catch(e) {}
                send({type: 'NET_RECV', size: recvd, n: count, text: txt.substring(0, 300)}, data);
            }
        }
    });
    send({type: 'HOOKED', name: 'ws2_32::recv'});
}

send({type: 'READY'});
"""

def main():
    print("="*60)
    print("  PIPE + NETWORK HOOK — expressvpn-service.exe")
    print("="*60)

    # Find PID
    pid = None
    for proc in ["expressvpn-service.exe", "ExpressVPN.AppService.exe"]:
        try:
            out = subprocess.check_output(
                ["tasklist", "/fi", f"IMAGENAME eq {proc}", "/fo", "csv", "/nh"],
                timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
            for line in out.strip().split("\n"):
                parts = line.split(",")
                if len(parts) >= 2 and parts[1].strip('"').isdigit():
                    pid = int(parts[1].strip('"'))
                    break
        except Exception:
            pass
        if pid:
            break

    if not pid:
        print("  Service not found!")
        return

    print(f"  PID: {pid}")
    captured = []
    start = time.time()

    def on_msg(msg, data):
        if msg["type"] != "send":
            if msg["type"] == "error":
                desc = msg.get("description", "")[:80]
                if "access" not in desc.lower():
                    print(f"  [ERR] {desc}")
            return

        p = msg["payload"]
        t = p.get("type", "?")
        elapsed = round(time.time() - start, 1)

        if t == "HOOKED":
            print(f"  [HOOK] {p['name']}")
        elif t == "READY":
            print(f"\n  Capturing 60s...\n")
        elif t == "PIPE_OPEN":
            print(f"  [{elapsed:5.1f}s] PIPE OPEN: {p['path']}")
        elif t in ("WRITE", "READ"):
            direction = ">>>" if t == "WRITE" else "<<<"
            pipe = p.get("pipe", "")
            txt = p.get("text", "")[:120]
            safe = txt.encode("ascii", "replace").decode()
            has_text = len(safe.replace(".", "").strip()) > 5
            print(f"  [{elapsed:5.1f}s] {direction} {t:5s} {p['size']:6d}b pipe={pipe[:40]}")
            if has_text:
                for line in safe.split("\n")[:2]:
                    if line.strip():
                        print(f"           {line.strip()[:100]}")

            captured.append({
                "time": elapsed, "type": t, "size": p["size"],
                "pipe": pipe, "text": p.get("text", "")[:500],
                "hex": data.hex()[:400] if data else "",
            })
        elif t in ("NET_SEND", "NET_RECV"):
            direction = ">>>" if t == "NET_SEND" else "<<<"
            txt = p.get("text", "")[:120]
            safe = txt.encode("ascii", "replace").decode()
            has_text = len(safe.replace(".", "").strip()) > 5
            print(f"  [{elapsed:5.1f}s] {direction} {t:8s} {p['size']:6d}b")
            if has_text:
                print(f"           {safe[:100]}")

            captured.append({
                "time": elapsed, "type": t, "size": p["size"],
                "text": p.get("text", "")[:500],
                "hex": data.hex()[:400] if data else "",
            })

    try:
        session = frida.attach(pid)
        script = session.create_script(HOOK)
        script.on("message", on_msg)
        script.load()
        time.sleep(60)
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
    finally:
        try:
            session.detach()
        except Exception:
            pass

    if captured:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = Path(f"expressvpn_pipe_traffic_{ts}.json")
        out.write_text(json.dumps(captured, indent=2, ensure_ascii=True))
        total_write = sum(c["size"] for c in captured if c["type"] == "WRITE")
        total_read = sum(c["size"] for c in captured if c["type"] == "READ")
        total_send = sum(c["size"] for c in captured if c["type"] == "NET_SEND")
        total_recv = sum(c["size"] for c in captured if c["type"] == "NET_RECV")
        print(f"\n{'='*60}")
        print(f"  CAPTURED: {len(captured)} events")
        print(f"  Pipe WRITE: {total_write:,}b | Pipe READ: {total_read:,}b")
        print(f"  Net SEND:  {total_send:,}b | Net RECV: {total_recv:,}b")
        print(f"  Saved: {out}")
    else:
        print(f"\n  No traffic captured")

if __name__ == "__main__":
    main()
