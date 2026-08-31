"""
Frida SSL Hook — Intercept ExpressVPN TLS Traffic
=====================================================
Hooks into ExpressVPN.AppService.exe and intercepts:
- SSL_read() — data received from server
- SSL_write() — data sent to server
- SSL_connect() — TLS handshake (shows server cert)

This shows the DECRYPTED plaintext inside the TLS tunnel.
"""

import frida
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Frida JavaScript hook script
HOOK_SCRIPT = r"""
'use strict';

// Intercept OpenSSL SSL_write and SSL_read
// These are the functions that handle plaintext data BEFORE encryption / AFTER decryption

var captured = [];
var totalSent = 0;
var totalRecv = 0;

// Find SSL_write and SSL_read in loaded modules
var modules = Process.enumerateModules();
var sslModule = null;

for (var i = 0; i < modules.length; i++) {
    var name = modules[i].name.toLowerCase();
    if (name.indexOf('libssl') >= 0 || name.indexOf('ssl') >= 0 ||
        name.indexOf('libxvclient') >= 0 || name.indexOf('lightway') >= 0 ||
        name.indexOf('schannel') >= 0) {
        send({type: 'module', name: modules[i].name, base: modules[i].base.toString(), size: modules[i].size});
        sslModule = modules[i];
    }
}

// Try to find SSL_write/SSL_read exports
function hookSSL(moduleName) {
    try {
        var ssl_write = Module.findExportByName(moduleName, 'SSL_write');
        var ssl_read = Module.findExportByName(moduleName, 'SSL_read');

        if (ssl_write) {
            send({type: 'hook', function: 'SSL_write', module: moduleName, address: ssl_write.toString()});

            Interceptor.attach(ssl_write, {
                onEnter: function(args) {
                    this.ssl = args[0];
                    this.buf = args[1];
                    this.len = args[2].toInt32();
                },
                onLeave: function(retval) {
                    var written = retval.toInt32();
                    if (written > 0 && this.len > 0) {
                        totalSent += written;
                        var data = Memory.readByteArray(this.buf, Math.min(written, 512));
                        var preview = '';
                        try {
                            preview = Memory.readUtf8String(this.buf, Math.min(written, 200));
                        } catch(e) {
                            preview = '[binary]';
                        }
                        send({
                            type: 'ssl_write',
                            size: written,
                            totalSent: totalSent,
                            preview: preview.substring(0, 200),
                        }, data);
                    }
                }
            });
        }

        if (ssl_read) {
            send({type: 'hook', function: 'SSL_read', module: moduleName, address: ssl_read.toString()});

            Interceptor.attach(ssl_read, {
                onEnter: function(args) {
                    this.ssl = args[0];
                    this.buf = args[1];
                    this.len = args[2].toInt32();
                },
                onLeave: function(retval) {
                    var bytesRead = retval.toInt32();
                    if (bytesRead > 0) {
                        totalRecv += bytesRead;
                        var data = Memory.readByteArray(this.buf, Math.min(bytesRead, 512));
                        var preview = '';
                        try {
                            preview = Memory.readUtf8String(this.buf, Math.min(bytesRead, 200));
                        } catch(e) {
                            preview = '[binary]';
                        }
                        send({
                            type: 'ssl_read',
                            size: bytesRead,
                            totalRecv: totalRecv,
                            preview: preview.substring(0, 200),
                        }, data);
                    }
                }
            });
        }

        if (ssl_write || ssl_read) {
            return true;
        }
    } catch(e) {
        send({type: 'error', module: moduleName, error: e.toString()});
    }
    return false;
}

// Also try to hook Windows Schannel (EncryptMessage/DecryptMessage)
function hookSchannel() {
    try {
        var encryptMessage = Module.findExportByName('sspicli.dll', 'EncryptMessage');
        var decryptMessage = Module.findExportByName('sspicli.dll', 'DecryptMessage');

        if (!encryptMessage) {
            encryptMessage = Module.findExportByName('secur32.dll', 'EncryptMessage');
            decryptMessage = Module.findExportByName('secur32.dll', 'DecryptMessage');
        }

        if (encryptMessage) {
            send({type: 'hook', function: 'EncryptMessage', module: 'sspicli/secur32'});
            Interceptor.attach(encryptMessage, {
                onEnter: function(args) {
                    // SecBufferDesc at args[1]
                    this.pMessage = args[1];
                },
                onLeave: function(retval) {
                    if (retval.toInt32() === 0 && this.pMessage && !this.pMessage.isNull()) {
                        try {
                            // Read SecBufferDesc.cBuffers
                            var cBuffers = this.pMessage.add(4).readU32();
                            var pBuffers = this.pMessage.add(8).readPointer();

                            for (var i = 0; i < Math.min(cBuffers, 4); i++) {
                                var bufferPtr = pBuffers.add(i * 16); // sizeof(SecBuffer) = 16
                                var cbBuffer = bufferPtr.readU32();
                                var bufferType = bufferPtr.add(4).readU32();
                                var pvBuffer = bufferPtr.add(8).readPointer();

                                // Type 1 = SECBUFFER_DATA (plaintext before encryption)
                                if (bufferType === 1 && cbBuffer > 0 && cbBuffer < 65536) {
                                    totalSent += cbBuffer;
                                    var data = Memory.readByteArray(pvBuffer, Math.min(cbBuffer, 512));
                                    var preview = '';
                                    try {
                                        preview = Memory.readUtf8String(pvBuffer, Math.min(cbBuffer, 200));
                                    } catch(e) {}
                                    send({
                                        type: 'encrypt',
                                        size: cbBuffer,
                                        totalSent: totalSent,
                                        preview: preview.substring(0, 200),
                                    }, data);
                                }
                            }
                        } catch(e) {}
                    }
                }
            });
        }

        if (decryptMessage) {
            send({type: 'hook', function: 'DecryptMessage', module: 'sspicli/secur32'});
            Interceptor.attach(decryptMessage, {
                onEnter: function(args) {
                    this.pMessage = args[1];
                },
                onLeave: function(retval) {
                    if (retval.toInt32() === 0 && this.pMessage && !this.pMessage.isNull()) {
                        try {
                            var cBuffers = this.pMessage.add(4).readU32();
                            var pBuffers = this.pMessage.add(8).readPointer();

                            for (var i = 0; i < Math.min(cBuffers, 4); i++) {
                                var bufferPtr = pBuffers.add(i * 16);
                                var cbBuffer = bufferPtr.readU32();
                                var bufferType = bufferPtr.add(4).readU32();
                                var pvBuffer = bufferPtr.add(8).readPointer();

                                if (bufferType === 1 && cbBuffer > 0 && cbBuffer < 65536) {
                                    totalRecv += cbBuffer;
                                    var data = Memory.readByteArray(pvBuffer, Math.min(cbBuffer, 512));
                                    var preview = '';
                                    try {
                                        preview = Memory.readUtf8String(pvBuffer, Math.min(cbBuffer, 200));
                                    } catch(e) {}
                                    send({
                                        type: 'decrypt',
                                        size: cbBuffer,
                                        totalRecv: totalRecv,
                                        preview: preview.substring(0, 200),
                                    }, data);
                                }
                            }
                        } catch(e) {}
                    }
                }
            });
        }

        return (encryptMessage || decryptMessage) ? true : false;
    } catch(e) {
        send({type: 'error', module: 'schannel', error: e.toString()});
        return false;
    }
}

// Try all SSL modules
var hooked = false;
var sslModuleNames = ['libssl-1_1-x64.dll', 'libssl-3-x64.dll', 'libxvclient.dll', 'lightway-client.exe'];
for (var i = 0; i < sslModuleNames.length; i++) {
    if (hookSSL(sslModuleNames[i])) {
        hooked = true;
        break;
    }
}

// Also try Schannel (Windows native TLS)
if (hookSchannel()) {
    hooked = true;
}

if (!hooked) {
    // List ALL exports that contain "ssl" or "encrypt" or "write"
    send({type: 'no_hooks', message: 'Could not find SSL functions. Listing all modules...'});
    for (var i = 0; i < modules.length; i++) {
        try {
            var exports = modules[i].enumerateExports();
            for (var j = 0; j < exports.length; j++) {
                var name = exports[j].name.toLowerCase();
                if (name.indexOf('ssl_write') >= 0 || name.indexOf('ssl_read') >= 0 ||
                    name.indexOf('encrypt') >= 0 || name.indexOf('decrypt') >= 0) {
                    send({type: 'candidate', module: modules[i].name, export: exports[j].name, address: exports[j].address.toString()});
                }
            }
        } catch(e) {}
    }
}

send({type: 'ready', hooked: hooked});
"""


def find_expressvpn_pid():
    """Find ExpressVPN.AppService.exe PID."""
    try:
        output = subprocess.check_output(
            ["tasklist", "/fi", "IMAGENAME eq ExpressVPN.AppService.exe", "/fo", "csv", "/nh"],
            timeout=5, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        for line in output.strip().split("\n"):
            parts = line.split(",")
            if len(parts) >= 2:
                pid = parts[1].strip('"')
                if pid.isdigit():
                    return int(pid)
    except Exception:
        pass
    return None


def main():
    print("=" * 60)
    print("  FRIDA SSL HOOK — ExpressVPN Traffic Intercept")
    print("=" * 60)

    pid = find_expressvpn_pid()
    if not pid:
        print("  ExpressVPN.AppService.exe not found!")
        sys.exit(1)

    print(f"  Target: ExpressVPN.AppService.exe (PID {pid})")
    print(f"  Attaching Frida...")

    captured_data = []
    start_time = time.time()

    def on_message(message, data):
        """Handle messages from Frida hook."""
        if message["type"] == "send":
            payload = message["payload"]
            msg_type = payload.get("type", "?")
            elapsed = round(time.time() - start_time, 1)

            if msg_type == "module":
                print(f"  [MODULE] {payload['name']} at {payload['base']} ({payload['size']} bytes)")

            elif msg_type == "hook":
                print(f"  [HOOK] {payload['function']} in {payload['module']} at {payload.get('address', '?')}")

            elif msg_type == "ready":
                print(f"  [READY] Hooked: {payload['hooked']}")
                if payload["hooked"]:
                    print(f"  [READY] Capturing traffic... Press Ctrl+C to stop")

            elif msg_type in ("ssl_write", "encrypt"):
                preview = payload.get("preview", "")[:100]
                safe = preview.encode("ascii", "replace").decode()
                print(f"  [{elapsed:6.1f}s] SEND {payload['size']:6d} bytes (total {payload.get('totalSent', 0):,})")
                if safe.strip():
                    print(f"           {safe}")
                captured_data.append({
                    "time": elapsed, "direction": "SEND",
                    "size": payload["size"],
                    "preview": payload.get("preview", "")[:200],
                    "hex": data.hex()[:200] if data else "",
                })

            elif msg_type in ("ssl_read", "decrypt"):
                preview = payload.get("preview", "")[:100]
                safe = preview.encode("ascii", "replace").decode()
                print(f"  [{elapsed:6.1f}s] RECV {payload['size']:6d} bytes (total {payload.get('totalRecv', 0):,})")
                if safe.strip():
                    print(f"           {safe}")
                captured_data.append({
                    "time": elapsed, "direction": "RECV",
                    "size": payload["size"],
                    "preview": payload.get("preview", "")[:200],
                    "hex": data.hex()[:200] if data else "",
                })

            elif msg_type == "candidate":
                print(f"  [CANDIDATE] {payload['module']}::{payload['export']} at {payload['address']}")

            elif msg_type == "no_hooks":
                print(f"  [WARN] {payload['message']}")

            elif msg_type == "error":
                print(f"  [ERROR] {payload.get('module', '?')}: {payload.get('error', '?')}")

        elif message["type"] == "error":
            print(f"  [FRIDA ERROR] {message.get('description', message)}")

    try:
        session = frida.attach(pid)
        script = session.create_script(HOOK_SCRIPT)
        script.on("message", on_message)
        script.load()

        print(f"\n  Capturing for 30 seconds...")
        time.sleep(30)

    except frida.ProcessNotFoundError:
        print(f"  Process {pid} not found — may need admin rights")
    except frida.PermissionError:
        print(f"  Permission denied — run as Administrator!")
    except KeyboardInterrupt:
        print(f"\n  Stopped by user")
    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
    finally:
        try:
            session.detach()
        except Exception:
            pass

    # Save results
    if captured_data:
        out_file = Path("expressvpn_captured_traffic.json")
        out_file.write_text(json.dumps(captured_data, indent=2))
        print(f"\n  Saved {len(captured_data)} messages to {out_file}")

        # Summary
        total_sent = sum(d["size"] for d in captured_data if d["direction"] == "SEND")
        total_recv = sum(d["size"] for d in captured_data if d["direction"] == "RECV")
        print(f"\n  SUMMARY:")
        print(f"    Messages: {len(captured_data)}")
        print(f"    Sent: {total_sent:,} bytes")
        print(f"    Received: {total_recv:,} bytes")

        # Show most interesting messages
        print(f"\n  INTERESTING CONTENT:")
        for d in captured_data:
            p = d.get("preview", "")
            if any(kw in p.lower() for kw in ("user", "email", "token", "password", "location",
                "device", "analytics", "event", "track", "braze", "sentry")):
                print(f"    [{d['direction']}] {p[:120]}")
    else:
        print(f"\n  No traffic captured")


if __name__ == "__main__":
    main()
