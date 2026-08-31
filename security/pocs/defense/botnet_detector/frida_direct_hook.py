"""Direct Frida hook using NativeFunction on exported addresses."""
import frida, subprocess, sys, time, json
from pathlib import Path

HOOK = r"""
'use strict';

// Find exports by enumerating, not by findExportByName (which fails on .NET)
var targets = {};

var mods = Process.enumerateModules();
for (var i = 0; i < mods.length; i++) {
    var m = mods[i];
    var n = m.name.toLowerCase();
    if (n === 'sspicli.dll' || n === 'ncrypt.dll') {
        try {
            var exports = m.enumerateExports();
            for (var j = 0; j < exports.length; j++) {
                var e = exports[j];
                if (e.name === 'EncryptMessage' || e.name === 'DecryptMessage' ||
                    e.name === 'SslEncryptPacket' || e.name === 'SslDecryptPacket') {
                    targets[m.name + '::' + e.name] = e.address;
                    send({type: 'found', name: m.name + '::' + e.name, addr: e.address.toString()});
                }
            }
        } catch(ex) {
            send({type: 'err', msg: m.name + ': ' + ex.toString()});
        }
    }
}

var count = 0;
var totalOut = 0;
var totalIn = 0;

// Hook EncryptMessage from sspicli.dll
var emAddr = targets['sspicli.dll::EncryptMessage'];
if (emAddr) {
    Interceptor.attach(emAddr, {
        onEnter: function(args) {
            // args[0] = phContext, args[1] = fQOP, args[2] = pMessage, args[3] = MessageSeqNo
            // Actually: EncryptMessage(PCtxtHandle, ULONG, PSecBufferDesc, ULONG)
            this.pMsg = args[2];
        },
        onLeave: function(retval) {
            if (count > 500) return;
            try {
                if (!this.pMsg || this.pMsg.isNull()) return;
                if (retval.toInt32() !== 0) return;

                var ulVersion = this.pMsg.readU32();
                var cBuffers = this.pMsg.add(4).readU32();
                var pBuffers = this.pMsg.add(8).readPointer();

                for (var i = 0; i < Math.min(cBuffers, 8); i++) {
                    var offset = i * 16; // SecBuffer = {cbBuffer(4), BufferType(4), pvBuffer(8)} = 16 bytes on x64
                    var cbBuffer = pBuffers.add(offset).readU32();
                    var bufType = pBuffers.add(offset + 4).readU32();
                    var pvBuffer = pBuffers.add(offset + 8).readPointer();

                    // Type 1 = SECBUFFER_DATA (plaintext before encryption)
                    if (bufType === 1 && cbBuffer > 0 && cbBuffer < 65536 && !pvBuffer.isNull()) {
                        count++;
                        totalOut += cbBuffer;
                        var raw = Memory.readByteArray(pvBuffer, Math.min(cbBuffer, 2048));
                        var txt = '';
                        try { txt = Memory.readUtf8String(pvBuffer, Math.min(cbBuffer, 500)); } catch(e) {}
                        send({type: 'OUT', size: cbBuffer, total: totalOut, n: count, txt: txt.substring(0,500)}, raw);
                        return;
                    }
                }
            } catch(e) {}
        }
    });
    send({type: 'hooked', name: 'EncryptMessage'});
}

// Hook DecryptMessage
var dmAddr = targets['sspicli.dll::DecryptMessage'];
if (dmAddr) {
    Interceptor.attach(dmAddr, {
        onEnter: function(args) {
            this.pMsg = args[1];
        },
        onLeave: function(retval) {
            if (count > 500) return;
            try {
                if (!this.pMsg || this.pMsg.isNull()) return;
                if (retval.toInt32() !== 0) return;

                var cBuffers = this.pMsg.add(4).readU32();
                var pBuffers = this.pMsg.add(8).readPointer();

                for (var i = 0; i < Math.min(cBuffers, 8); i++) {
                    var offset = i * 16;
                    var cbBuffer = pBuffers.add(offset).readU32();
                    var bufType = pBuffers.add(offset + 4).readU32();
                    var pvBuffer = pBuffers.add(offset + 8).readPointer();

                    if (bufType === 1 && cbBuffer > 0 && cbBuffer < 65536 && !pvBuffer.isNull()) {
                        count++;
                        totalIn += cbBuffer;
                        var raw = Memory.readByteArray(pvBuffer, Math.min(cbBuffer, 2048));
                        var txt = '';
                        try { txt = Memory.readUtf8String(pvBuffer, Math.min(cbBuffer, 500)); } catch(e) {}
                        send({type: 'IN', size: cbBuffer, total: totalIn, n: count, txt: txt.substring(0,500)}, raw);
                        return;
                    }
                }
            } catch(e) {}
        }
    });
    send({type: 'hooked', name: 'DecryptMessage'});
}

send({type: 'ready', targets: Object.keys(targets).length});
"""

def main():
    print("="*60)
    print("  FRIDA DIRECT HOOK — sspicli EncryptMessage/DecryptMessage")
    print("="*60)

    # Find PID
    try:
        out = subprocess.check_output(
            ["tasklist", "/fi", "IMAGENAME eq ExpressVPN.AppService.exe", "/fo", "csv", "/nh"],
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
        print("  ExpressVPN not found!")
        return

    print(f"  PID: {pid}")
    captured = []
    start = time.time()

    def on_msg(msg, data):
        if msg["type"] != "send":
            if msg["type"] == "error":
                print(f"  [FRIDA ERR] {msg.get('description','?')[:80]}")
            return

        p = msg["payload"]
        t = p.get("type", "?")
        elapsed = round(time.time() - start, 1)

        if t == "found":
            print(f"  [FOUND] {p['name']} @ {p['addr']}")
        elif t == "hooked":
            print(f"  [HOOKED] {p['name']}")
        elif t == "ready":
            print(f"  [READY] {p['targets']} targets found")
            print(f"\n  Listening for 30s...\n")
        elif t == "err":
            print(f"  [ERR] {p['msg'][:80]}")
        elif t in ("OUT", "IN"):
            arrow = ">>>" if t == "OUT" else "<<<"
            txt = p.get("txt", "")[:150]
            safe = txt.encode("ascii", "replace").decode()
            # Only show if there's readable content
            has_text = len(safe.replace(".", "").replace("\x00", "").strip()) > 5
            print(f"  [{elapsed:5.1f}s] {arrow} {p['size']:6d} bytes  (#{p['n']}, total {p['total']:,})")
            if has_text:
                # Show readable portions
                for line in safe.split("\n")[:3]:
                    line = line.strip()
                    if len(line) > 5:
                        print(f"          {line[:120]}")

            captured.append({
                "time": elapsed, "dir": t, "size": p["size"],
                "text": p.get("txt", "")[:500],
                "hex": data.hex()[:600] if data else "",
            })

    try:
        session = frida.attach(pid)
        script = session.create_script(HOOK)
        script.on("message", on_msg)
        script.load()
        time.sleep(30)
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
    finally:
        try:
            session.detach()
        except Exception:
            pass

    if captured:
        Path("expressvpn_plaintext.json").write_text(json.dumps(captured, indent=2, ensure_ascii=True))
        out_total = sum(c["size"] for c in captured if c["dir"] == "OUT")
        in_total = sum(c["size"] for c in captured if c["dir"] == "IN")
        print(f"\n  {'='*50}")
        print(f"  CAPTURED: {len(captured)} messages")
        print(f"  SENT: {out_total:,} bytes")
        print(f"  RECV: {in_total:,} bytes")
        print(f"  Saved to expressvpn_plaintext.json")

        # Show messages with interesting content
        print(f"\n  INTERESTING CONTENT:")
        keywords = ["user", "email", "token", "password", "location", "device",
                     "analytics", "event", "track", "braze", "sentry", "POST",
                     "GET", "HTTP", "grpc", "proto", "json", "api"]
        for c in captured:
            txt = c.get("text", "").lower()
            for kw in keywords:
                if kw in txt:
                    safe = c["text"][:200].encode("ascii", "replace").decode()
                    print(f"    [{c['dir']}] ({kw}) {safe[:150]}")
                    break
    else:
        print(f"\n  No traffic intercepted")
        print(f"  Note: ExpressVPN may use libxvclient.dll (custom TLS) instead of Windows Schannel")
        print(f"  The 8MB libxvclient.dll is their own TLS implementation — standard hooks don't work")

if __name__ == "__main__":
    main()
