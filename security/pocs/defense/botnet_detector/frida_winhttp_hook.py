"""Hook WinHTTP — ExpressVPN uses WINHTTP.dll for HTTP requests."""
import frida, subprocess, time, json
from pathlib import Path
from datetime import datetime

HOOK = r"""
var count = 0;
var cache = {};

// Cache WINHTTP exports
var m = Process.findModuleByName('WINHTTP.dll');
if (m) {
    m.enumerateExports().forEach(function(e) { cache[e.name] = e.address; });
    send({t:'info', m:'WINHTTP.dll: ' + Object.keys(cache).length + ' exports'});
}

// Also cache mswsock (lower level)
var ms = Process.findModuleByName('mswsock.dll');
if (ms) {
    ms.enumerateExports().forEach(function(e) { cache['ms_'+e.name] = e.address; });
    send({t:'info', m:'mswsock.dll: cached'});
}

// WinHttpOpen — when a new HTTP session starts
if (cache['WinHttpOpen']) {
    Interceptor.attach(cache['WinHttpOpen'], {
        onEnter: function(a) {
            var userAgent = null;
            try { userAgent = a[0].readUtf16String(); } catch(e) {}
            send({t:'OPEN', ua: userAgent});
        }
    });
    send({t:'info', m:'hooked WinHttpOpen'});
}

// WinHttpConnect — which host it connects to
if (cache['WinHttpConnect']) {
    Interceptor.attach(cache['WinHttpConnect'], {
        onEnter: function(a) {
            var host = null;
            try { host = a[1].readUtf16String(); } catch(e) {}
            var port = a[2].toInt32();
            send({t:'HTTP_CONNECT', host: host, port: port});
        }
    });
    send({t:'info', m:'hooked WinHttpConnect'});
}

// WinHttpOpenRequest — the URL path
if (cache['WinHttpOpenRequest']) {
    Interceptor.attach(cache['WinHttpOpenRequest'], {
        onEnter: function(a) {
            var verb = null;
            var path = null;
            try { verb = a[1].readUtf16String(); } catch(e) {}
            try { path = a[2].readUtf16String(); } catch(e) {}
            send({t:'HTTP_REQ', verb: verb, path: path});
        }
    });
    send({t:'info', m:'hooked WinHttpOpenRequest'});
}

// WinHttpAddRequestHeaders — HTTP headers being set
if (cache['WinHttpAddRequestHeaders']) {
    Interceptor.attach(cache['WinHttpAddRequestHeaders'], {
        onEnter: function(a) {
            var headers = null;
            try { headers = a[1].readUtf16String(); } catch(e) {}
            if (headers && headers.length > 5) {
                send({t:'HEADERS', h: headers});
            }
        }
    });
    send({t:'info', m:'hooked WinHttpAddRequestHeaders'});
}

// WinHttpSendRequest — when request is sent (includes body)
if (cache['WinHttpSendRequest']) {
    Interceptor.attach(cache['WinHttpSendRequest'], {
        onEnter: function(a) {
            count++;
            var headers = null;
            try { headers = a[1].readUtf16String(); } catch(e) {}
            var headerLen = a[2].toInt32();
            var bodyLen = a[4].toInt32();
            var totalLen = a[5].toInt32();
            send({t:'SEND_REQ', n:count, headers: headers, headerLen: headerLen, bodyLen: bodyLen, totalLen: totalLen});
        }
    });
    send({t:'info', m:'hooked WinHttpSendRequest'});
}

// WinHttpWriteData — POST body data
if (cache['WinHttpWriteData']) {
    Interceptor.attach(cache['WinHttpWriteData'], {
        onEnter: function(a) {
            count++;
            var buf = a[1];
            var len = a[2].toInt32();
            if (len > 0 && len < 65536) {
                var data = Memory.readByteArray(buf, Math.min(len, 4096));
                var preview = null;
                try { preview = Memory.readUtf8String(buf, Math.min(len, 2000)); } catch(e) {}
                send({t:'WRITE', n:count, size:len, preview: preview}, data);
            }
        }
    });
    send({t:'info', m:'hooked WinHttpWriteData'});
}

// WinHttpReadData — response data
if (cache['WinHttpReadData']) {
    Interceptor.attach(cache['WinHttpReadData'], {
        onEnter: function(a) {
            this.buf = a[1];
            this.len = a[2].toInt32();
        },
        onLeave: function(r) {
            if (count >= 500) return;
            count++;
            try {
                // Read actual bytes read from lpdwNumberOfBytesRead (would need the pointer)
                // For now, read up to requested length
                var data = Memory.readByteArray(this.buf, Math.min(this.len, 4096));
                var preview = null;
                try { preview = Memory.readUtf8String(this.buf, Math.min(this.len, 2000)); } catch(e) {}
                if (preview && preview.length > 5) {
                    send({t:'READ', n:count, size: this.len, preview: preview}, data);
                }
            } catch(e) {}
        }
    });
    send({t:'info', m:'hooked WinHttpReadData'});
}

send({t:'info', m:'READY — capturing HTTP traffic'});
"""

out = subprocess.check_output(
    ["tasklist", "/fi", "IMAGENAME eq expressvpn-service.exe", "/fo", "csv", "/nh"],
    timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
pid = int([l.split(",")[1].strip('"') for l in out.strip().split("\n") if "," in l and l.split(",")[1].strip('"').isdigit()][0])

print(f"="*60)
print(f"  WINHTTP INTERCEPTOR — PID {pid}")
print(f"="*60)

captured = []
start = time.time()

def on_msg(msg, data):
    if msg["type"] != "send": return
    p = msg["payload"]
    t = p.get("t","?")
    elapsed = round(time.time() - start, 1)

    if t == "info":
        print(f"  [{t}] {p['m']}")
    elif t == "OPEN":
        ua = p.get("ua","?")
        if ua:
            safe = ua[:100].encode("ascii","replace").decode()
            print(f"  [{elapsed:5.1f}s] HTTP SESSION: User-Agent={safe}")
            captured.append({"time": elapsed, "type": "OPEN", "user_agent": ua})
    elif t == "HTTP_CONNECT":
        host = p.get("host","?")
        port = p.get("port",0)
        print(f"  [{elapsed:5.1f}s] CONNECT: {host}:{port}")
        captured.append({"time": elapsed, "type": "CONNECT", "host": host, "port": port})
    elif t == "HTTP_REQ":
        verb = p.get("verb","?")
        path = p.get("path","?")
        print(f"  [{elapsed:5.1f}s] REQUEST: {verb} {path}")
        captured.append({"time": elapsed, "type": "REQUEST", "verb": verb, "path": path})
    elif t == "HEADERS":
        h = p.get("h","")
        if h:
            safe = h[:200].encode("ascii","replace").decode()
            print(f"  [{elapsed:5.1f}s] HEADERS: {safe}")
            captured.append({"time": elapsed, "type": "HEADERS", "headers": h[:500]})
    elif t == "SEND_REQ":
        print(f"  [{elapsed:5.1f}s] SEND REQUEST: bodyLen={p.get('bodyLen',0)} totalLen={p.get('totalLen',0)}")
        h = p.get("headers","")
        if h:
            safe = h[:200].encode("ascii","replace").decode()
            print(f"           Headers: {safe}")
        captured.append({"time": elapsed, "type": "SEND", "bodyLen": p.get("bodyLen",0), "totalLen": p.get("totalLen",0)})
    elif t == "WRITE":
        preview = p.get("preview","")
        size = p.get("size",0)
        print(f"  [{elapsed:5.1f}s] POST BODY: {size} bytes")
        if preview:
            safe = preview[:300].encode("ascii","replace").decode()
            for line in safe.split("\n")[:5]:
                if line.strip():
                    print(f"           {line.strip()[:120]}")
        captured.append({"time": elapsed, "type": "WRITE", "size": size, "preview": preview[:1000] if preview else ""})
    elif t == "READ":
        preview = p.get("preview","")
        if preview and len(preview) > 5:
            safe = preview[:300].encode("ascii","replace").decode()
            print(f"  [{elapsed:5.1f}s] RESPONSE: {p.get('size',0)} bytes")
            for line in safe.split("\n")[:5]:
                if line.strip():
                    print(f"           {line.strip()[:120]}")
            captured.append({"time": elapsed, "type": "RESPONSE", "size": p.get("size",0), "preview": preview[:1000]})

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

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
Path(f"expressvpn_tracking_captured_{ts}.json").write_text(json.dumps(captured, indent=2, ensure_ascii=True))

print(f"\n{'='*60}")
print(f"  CAPTURED: {len(captured)} events")
print(f"  Saved to: expressvpn_tracking_captured_{ts}.json")
print(f"{'='*60}")
