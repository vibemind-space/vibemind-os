"""Simplest possible Frida socket hook — just log what goes through."""
import frida, subprocess, time, json
from pathlib import Path
from datetime import datetime

HOOK = r"""
var count = 0;
var bytesOut = 0;
var bytesIn = 0;

// Cache ws2_32 exports
var cache = {};
var m = Process.findModuleByName('ws2_32.dll');
if (m) {
    m.enumerateExports().forEach(function(e) { cache[e.name] = e.address; });
    send({t: 'info', m: 'ws2_32: ' + Object.keys(cache).length + ' exports'});
}

// SEND
if (cache['send']) {
    Interceptor.attach(cache['send'], {
        onEnter: function(a) { this.buf = a[1]; this.len = a[2].toInt32(); },
        onLeave: function(r) {
            var n = r.toInt32();
            if (n > 0 && count < 500) {
                count++;
                bytesOut += n;
                var raw = Memory.readByteArray(this.buf, Math.min(n, 1024));
                send({t:'S', n:count, s:n, total:bytesOut}, raw);
            }
        }
    });
    send({t:'info', m:'hooked send'});
}

// RECV
if (cache['recv']) {
    Interceptor.attach(cache['recv'], {
        onEnter: function(a) { this.buf = a[1]; },
        onLeave: function(r) {
            var n = r.toInt32();
            if (n > 0 && count < 500) {
                count++;
                bytesIn += n;
                var raw = Memory.readByteArray(this.buf, Math.min(n, 1024));
                send({t:'R', n:count, s:n, total:bytesIn}, raw);
            }
        }
    });
    send({t:'info', m:'hooked recv'});
}

// CONNECT
if (cache['connect']) {
    Interceptor.attach(cache['connect'], {
        onEnter: function(a) {
            try {
                var sa = a[1];
                var fam = sa.readU16();
                if (fam === 2) {
                    var port = (sa.add(2).readU8() << 8) | sa.add(3).readU8();
                    var ip = sa.add(4).readU8()+'.'+sa.add(5).readU8()+'.'+sa.add(6).readU8()+'.'+sa.add(7).readU8();
                    send({t:'C', ip:ip, port:port});
                }
            } catch(e) {}
        }
    });
    send({t:'info', m:'hooked connect'});
}

send({t:'info', m:'ready'});
"""

out = subprocess.check_output(
    ["tasklist", "/fi", "IMAGENAME eq expressvpn-service.exe", "/fo", "csv", "/nh"],
    timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
pid = int([l.split(",")[1].strip('"') for l in out.strip().split("\n") if "," in l and l.split(",")[1].strip('"').isdigit()][0])

print(f"PID: {pid}")
captured = []
start = time.time()

def on_msg(msg, data):
    if msg["type"] != "send": return
    p = msg["payload"]
    t = p.get("t","?")
    elapsed = round(time.time() - start, 1)

    if t == "info":
        print(f"  [{t}] {p['m']}")
    elif t == "C":
        print(f"  [{elapsed:5.1f}s] CONNECT -> {p['ip']}:{p['port']}")
        captured.append({"time": elapsed, "type": "CONNECT", "ip": p["ip"], "port": p["port"]})
    elif t == "S":
        # Analyze the raw bytes
        if data:
            raw = bytes(data)
            is_tls = len(raw) > 5 and raw[0] in (0x16, 0x17) and raw[1] == 0x03
            # Extract readable strings
            readable = "".join(chr(b) if 32 <= b < 127 else "." for b in raw[:200])
            strings = [s for s in readable.split(".") if len(s) >= 4]

            if not is_tls:
                print(f"  [{elapsed:5.1f}s] >>> SEND {p['s']:5d}b PLAINTEXT")
                if strings:
                    print(f"           {' | '.join(strings[:5])}")
                captured.append({"time": elapsed, "type": "SEND_PLAIN", "size": p["s"],
                    "strings": strings[:10], "hex": raw[:100].hex()})
            else:
                # TLS — just count, don't print every packet
                captured.append({"time": elapsed, "type": "SEND_TLS", "size": p["s"]})
    elif t == "R":
        if data:
            raw = bytes(data)
            is_tls = len(raw) > 5 and raw[0] in (0x16, 0x17) and raw[1] == 0x03
            if not is_tls:
                readable = "".join(chr(b) if 32 <= b < 127 else "." for b in raw[:200])
                strings = [s for s in readable.split(".") if len(s) >= 4]
                print(f"  [{elapsed:5.1f}s] <<< RECV {p['s']:5d}b PLAINTEXT")
                if strings:
                    print(f"           {' | '.join(strings[:5])}")
                captured.append({"time": elapsed, "type": "RECV_PLAIN", "size": p["s"],
                    "strings": strings[:10], "hex": raw[:100].hex()})
            else:
                captured.append({"time": elapsed, "type": "RECV_TLS", "size": p["s"]})

try:
    session = frida.attach(pid)
    script = session.create_script(HOOK)
    script.on("message", on_msg)
    script.load()
    print(f"\n  Capturing 60 seconds...\n")
    time.sleep(60)
except Exception as e:
    print(f"  {type(e).__name__}: {e}")
finally:
    try: session.detach()
    except: pass

# Summary
tls_out = sum(c["size"] for c in captured if c.get("type") == "SEND_TLS")
tls_in = sum(c["size"] for c in captured if c.get("type") == "RECV_TLS")
plain_out = [c for c in captured if c.get("type") == "SEND_PLAIN"]
plain_in = [c for c in captured if c.get("type") == "RECV_PLAIN"]
connects = [c for c in captured if c.get("type") == "CONNECT"]

print(f"\n{'='*60}")
print(f"  TLS encrypted sent:     {tls_out:>10,} bytes")
print(f"  TLS encrypted received: {tls_in:>10,} bytes")
print(f"  Plaintext sent:         {sum(c['size'] for c in plain_out):>10,} bytes ({len(plain_out)} packets)")
print(f"  Plaintext received:     {sum(c['size'] for c in plain_in):>10,} bytes ({len(plain_in)} packets)")
print(f"  Connections:            {len(connects)}")
print(f"{'='*60}")

if plain_out:
    print(f"\n  PLAINTEXT DATA SENT:")
    for p in plain_out[:20]:
        print(f"    {p['size']:5d}b: {' | '.join(p.get('strings',[])[:5])}")

if connects:
    print(f"\n  CONNECTIONS:")
    for c in connects:
        print(f"    -> {c['ip']}:{c['port']}")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
Path(f"expressvpn_tracking_captured_{ts}.json").write_text(json.dumps(captured, indent=2, ensure_ascii=True))
