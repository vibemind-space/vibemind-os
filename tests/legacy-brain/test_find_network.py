"""Find which DLL expressvpn-service.exe uses for network I/O."""
import frida, subprocess

out = subprocess.check_output(
    ["tasklist", "/fi", "IMAGENAME eq expressvpn-service.exe", "/fo", "csv", "/nh"],
    timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
pid = int([l.split(",")[1].strip('"') for l in out.strip().split("\n") if "," in l and l.split(",")[1].strip('"').isdigit()][0])

SCRIPT = r"""
// Find ALL network-related exports across ALL modules
var results = [];
var modules = Process.enumerateModules();

send({type:'info', msg: modules.length + ' modules loaded'});

for (var i = 0; i < modules.length; i++) {
    var m = modules[i];
    try {
        var exports = m.enumerateExports();
        for (var j = 0; j < exports.length; j++) {
            var n = exports[j].name.toLowerCase();
            if (n === 'send' || n === 'recv' || n === 'connect' || n === 'wsasend' || n === 'wsarecv' ||
                n === 'ntdeviceiocontrolfile' || n === 'ntwfsrequest' ||
                n.indexOf('socket') >= 0 || n.indexOf('sendto') >= 0 || n.indexOf('recvfrom') >= 0 ||
                n.indexOf('wsk') >= 0 || n.indexOf('wspi') >= 0 ||
                n.indexOf('httpsendrequestex') >= 0 || n.indexOf('winhttp') >= 0 ||
                n.indexOf('internetopen') >= 0 || n.indexOf('curl_') >= 0) {
                results.push({module: m.name, export: exports[j].name, addr: exports[j].address.toString()});
            }
        }
    } catch(e) {}
}

send({type:'exports', data: results});

// Also check which modules are loaded that handle networking
var netModules = [];
for (var i = 0; i < modules.length; i++) {
    var n = modules[i].name.toLowerCase();
    if (n.indexOf('ws2') >= 0 || n.indexOf('winhttp') >= 0 || n.indexOf('wininet') >= 0 ||
        n.indexOf('ntdll') >= 0 || n.indexOf('curl') >= 0 || n.indexOf('ssl') >= 0 ||
        n.indexOf('http') >= 0 || n.indexOf('net') >= 0 || n.indexOf('socket') >= 0 ||
        n.indexOf('winsock') >= 0 || n.indexOf('mswsock') >= 0) {
        netModules.push({name: modules[i].name, size: modules[i].size, base: modules[i].base.toString()});
    }
}
send({type:'netmods', data: netModules});
"""

import time
session = frida.attach(pid)
script = session.create_script(SCRIPT)

def on_msg(msg, data):
    if msg["type"] != "send": return
    p = msg["payload"]
    if p.get("type") == "info":
        print(f"  {p['msg']}")
    elif p.get("type") == "netmods":
        print(f"\n  Network-related modules loaded:")
        for m in p["data"]:
            print(f"    {m['name']:40s} {m['size']:>10d} bytes  {m['base']}")
    elif p.get("type") == "exports":
        print(f"\n  Network exports ({len(p['data'])}):")
        for e in sorted(p["data"], key=lambda x: x["module"]):
            print(f"    {e['module']:30s} :: {e['export']:30s} @ {e['addr']}")

script.on("message", on_msg)
script.load()
time.sleep(3)
session.detach()
