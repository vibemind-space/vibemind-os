"""
Frida ncrypt.dll Hook — Intercept SslEncryptPacket/SslDecryptPacket
=====================================================================
ExpressVPN uses Windows ncrypt.dll for TLS, not OpenSSL directly.
Hook SslEncryptPacket and SslDecryptPacket to see plaintext.
"""

import frida
import json
import subprocess
import sys
import time
from pathlib import Path

HOOK_SCRIPT = r"""
'use strict';

var totalSent = 0;
var totalRecv = 0;
var messageCount = 0;
var MAX_MESSAGES = 200;

// List all loaded modules with SSL/TLS/crypto
var modules = Process.enumerateModules();
send({type: 'info', message: 'Loaded modules with crypto:'});
for (var i = 0; i < modules.length; i++) {
    var n = modules[i].name.toLowerCase();
    if (n.indexOf('crypt') >= 0 || n.indexOf('ssl') >= 0 || n.indexOf('ncrypt') >= 0 ||
        n.indexOf('schannel') >= 0 || n.indexOf('xvclient') >= 0 || n.indexOf('lightway') >= 0 ||
        n.indexOf('sspicli') >= 0 || n.indexOf('bcrypt') >= 0) {
        send({type: 'module', name: modules[i].name, base: modules[i].base.toString(),
              size: modules[i].size});
    }
}

// Hook ncrypt.dll SslEncryptPacket / SslDecryptPacket
var ncryptEncrypt = Module.findExportByName('ncrypt.dll', 'SslEncryptPacket');
var ncryptDecrypt = Module.findExportByName('ncrypt.dll', 'SslDecryptPacket');

if (ncryptEncrypt) {
    send({type: 'hook', name: 'SslEncryptPacket', addr: ncryptEncrypt.toString()});
    // SslEncryptPacket(hSslProvider, hKey, pbInput, cbInput, pbOutput, cbOutput, pcbResult, sequenceNumber, flags)
    Interceptor.attach(ncryptEncrypt, {
        onEnter: function(args) {
            this.pbInput = args[2];
            this.cbInput = args[3].toInt32();
        },
        onLeave: function(retval) {
            if (messageCount >= MAX_MESSAGES) return;
            if (retval.toInt32() === 0 && this.cbInput > 0 && this.cbInput < 65536) {
                messageCount++;
                totalSent += this.cbInput;
                try {
                    var data = Memory.readByteArray(this.pbInput, Math.min(this.cbInput, 1024));
                    var preview = '';
                    try { preview = Memory.readUtf8String(this.pbInput, Math.min(this.cbInput, 300)); } catch(e) {}
                    send({
                        type: 'encrypt',
                        size: this.cbInput,
                        total: totalSent,
                        count: messageCount,
                        preview: preview.substring(0, 300),
                    }, data);
                } catch(e) {}
            }
        }
    });
} else {
    send({type: 'warn', message: 'SslEncryptPacket not found in ncrypt.dll'});
}

if (ncryptDecrypt) {
    send({type: 'hook', name: 'SslDecryptPacket', addr: ncryptDecrypt.toString()});
    // SslDecryptPacket(hSslProvider, hKey, pbInput, cbInput, pbOutput, cbOutput, pcbResult, sequenceNumber, flags)
    Interceptor.attach(ncryptDecrypt, {
        onEnter: function(args) {
            this.pbOutput = args[4];
            this.cbOutput = args[5];
            this.pcbResult = args[6];
        },
        onLeave: function(retval) {
            if (messageCount >= MAX_MESSAGES) return;
            if (retval.toInt32() === 0) {
                try {
                    var resultSize = this.pcbResult.readU32();
                    if (resultSize > 0 && resultSize < 65536) {
                        messageCount++;
                        totalRecv += resultSize;
                        var outBuf = this.pbOutput.isNull() ? null : this.pbOutput;
                        if (!outBuf && !this.cbOutput.isNull()) {
                            // pbOutput might be at a different position
                        }
                        if (outBuf) {
                            var data = Memory.readByteArray(outBuf, Math.min(resultSize, 1024));
                            var preview = '';
                            try { preview = Memory.readUtf8String(outBuf, Math.min(resultSize, 300)); } catch(e) {}
                            send({
                                type: 'decrypt',
                                size: resultSize,
                                total: totalRecv,
                                count: messageCount,
                                preview: preview.substring(0, 300),
                            }, data);
                        }
                    }
                } catch(e) {}
            }
        }
    });
} else {
    send({type: 'warn', message: 'SslDecryptPacket not found in ncrypt.dll'});
}

// Also try hooking the higher-level sspicli EncryptMessage
var sspicliEncrypt = Module.findExportByName('sspicli.dll', 'EncryptMessage');
var sspicliDecrypt = Module.findExportByName('sspicli.dll', 'DecryptMessage');

if (sspicliEncrypt) {
    send({type: 'hook', name: 'sspicli::EncryptMessage', addr: sspicliEncrypt.toString()});
    Interceptor.attach(sspicliEncrypt, {
        onEnter: function(args) {
            // args[1] = pMessage (SecBufferDesc*)
            this.pMessage = args[1];
        },
        onLeave: function(retval) {
            if (messageCount >= MAX_MESSAGES) return;
            if (retval.toInt32() !== 0) return;
            try {
                if (this.pMessage.isNull()) return;
                var cBuffers = this.pMessage.add(4).readU32();
                var pBuffers = this.pMessage.add(8).readPointer();
                for (var i = 0; i < Math.min(cBuffers, 4); i++) {
                    var bp = pBuffers.add(i * (Process.pointerSize === 8 ? 16 : 12));
                    var cbBuffer = bp.readU32();
                    var bufType = bp.add(4).readU32();
                    var pvBuffer = bp.add(8).readPointer();
                    // SECBUFFER_DATA = 1
                    if (bufType === 1 && cbBuffer > 0 && cbBuffer < 65536 && !pvBuffer.isNull()) {
                        messageCount++;
                        totalSent += cbBuffer;
                        var data = Memory.readByteArray(pvBuffer, Math.min(cbBuffer, 1024));
                        var preview = '';
                        try { preview = Memory.readUtf8String(pvBuffer, Math.min(cbBuffer, 300)); } catch(e) {}
                        send({
                            type: 'sspi_encrypt',
                            size: cbBuffer,
                            total: totalSent,
                            count: messageCount,
                            preview: preview.substring(0, 300),
                        }, data);
                    }
                }
            } catch(e) {}
        }
    });
}

if (sspicliDecrypt) {
    send({type: 'hook', name: 'sspicli::DecryptMessage', addr: sspicliDecrypt.toString()});
    Interceptor.attach(sspicliDecrypt, {
        onEnter: function(args) {
            this.pMessage = args[1];
        },
        onLeave: function(retval) {
            if (messageCount >= MAX_MESSAGES) return;
            if (retval.toInt32() !== 0) return;
            try {
                if (this.pMessage.isNull()) return;
                var cBuffers = this.pMessage.add(4).readU32();
                var pBuffers = this.pMessage.add(8).readPointer();
                for (var i = 0; i < Math.min(cBuffers, 4); i++) {
                    var bp = pBuffers.add(i * (Process.pointerSize === 8 ? 16 : 12));
                    var cbBuffer = bp.readU32();
                    var bufType = bp.add(4).readU32();
                    var pvBuffer = bp.add(8).readPointer();
                    if (bufType === 1 && cbBuffer > 0 && cbBuffer < 65536 && !pvBuffer.isNull()) {
                        messageCount++;
                        totalRecv += cbBuffer;
                        var data = Memory.readByteArray(pvBuffer, Math.min(cbBuffer, 1024));
                        var preview = '';
                        try { preview = Memory.readUtf8String(pvBuffer, Math.min(cbBuffer, 300)); } catch(e) {}
                        send({
                            type: 'sspi_decrypt',
                            size: cbBuffer,
                            total: totalRecv,
                            count: messageCount,
                            preview: preview.substring(0, 300),
                        }, data);
                    }
                }
            } catch(e) {}
        }
    });
}

send({type: 'ready', hooks: messageCount === 0 ? 'waiting for traffic' : 'capturing'});
"""


def find_pid():
    try:
        out = subprocess.check_output(
            ["tasklist", "/fi", "IMAGENAME eq ExpressVPN.AppService.exe", "/fo", "csv", "/nh"],
            timeout=5, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        for line in out.strip().split("\n"):
            parts = line.split(",")
            if len(parts) >= 2 and parts[1].strip('"').isdigit():
                return int(parts[1].strip('"'))
    except Exception:
        pass
    return None


def main():
    print("="*60)
    print("  FRIDA ncrypt/sspicli HOOK")
    print("="*60)

    pid = find_pid()
    if not pid:
        print("  ExpressVPN not found!")
        return

    print(f"  Target PID: {pid}")
    print(f"  Hooking ncrypt.dll + sspicli.dll...")

    captured = []
    start = time.time()

    def on_message(msg, data):
        if msg["type"] == "send":
            p = msg["payload"]
            t = p.get("type", "?")
            elapsed = round(time.time() - start, 1)

            if t == "module":
                print(f"  [MOD] {p['name']:30s} {p['size']:>10d} bytes")
            elif t == "hook":
                print(f"  [HOOK] {p['name']} at {p['addr']}")
            elif t == "warn":
                print(f"  [WARN] {p['message']}")
            elif t == "ready":
                print(f"  [READY] {p['hooks']}")
            elif t in ("encrypt", "sspi_encrypt"):
                preview = p.get("preview", "")[:150]
                safe = preview.encode("ascii", "replace").decode()
                print(f"  [{elapsed:5.1f}s] >>> SEND {p['size']:6d} bytes (#{p['count']})")
                if safe.strip() and len(safe.strip()) > 3:
                    print(f"          {safe[:120]}")
                captured.append({"time": elapsed, "dir": "SEND", "size": p["size"],
                    "preview": p.get("preview", ""), "hex": data.hex()[:300] if data else ""})
            elif t in ("decrypt", "sspi_decrypt"):
                preview = p.get("preview", "")[:150]
                safe = preview.encode("ascii", "replace").decode()
                print(f"  [{elapsed:5.1f}s] <<< RECV {p['size']:6d} bytes (#{p['count']})")
                if safe.strip() and len(safe.strip()) > 3:
                    print(f"          {safe[:120]}")
                captured.append({"time": elapsed, "dir": "RECV", "size": p["size"],
                    "preview": p.get("preview", ""), "hex": data.hex()[:300] if data else ""})
            elif t in ("info", "error"):
                print(f"  [{t.upper()}] {p.get('message', p.get('error', '?'))}")

        elif msg["type"] == "error":
            desc = msg.get("description", str(msg))
            if "access" not in desc.lower():
                print(f"  [ERR] {desc[:100]}")

    try:
        session = frida.attach(pid)
        script = session.create_script(HOOK_SCRIPT)
        script.on("message", on_message)
        script.load()

        print(f"\n  Capturing 30 seconds of traffic...\n")
        time.sleep(30)

    except frida.ProcessNotFoundError:
        print(f"  Process not found — need admin?")
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
    finally:
        try:
            session.detach()
        except Exception:
            pass

    if captured:
        Path("expressvpn_decrypted.json").write_text(json.dumps(captured, indent=2))
        total_s = sum(c["size"] for c in captured if c["dir"] == "SEND")
        total_r = sum(c["size"] for c in captured if c["dir"] == "RECV")
        print(f"\n  {'='*50}")
        print(f"  CAPTURED: {len(captured)} messages")
        print(f"  SENT: {total_s:,} bytes | RECV: {total_r:,} bytes")
        print(f"  Saved to expressvpn_decrypted.json")
    else:
        print(f"\n  No traffic intercepted")


if __name__ == "__main__":
    main()
