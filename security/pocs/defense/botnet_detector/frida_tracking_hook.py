"""
Frida Hook auf ExpressVPN Tracking-Funktionen
================================================
Hooked OBERHALB der TLS-Verschluesselung — direkt an den Funktionen
die Tracking-Daten vorbereiten, BEVOR sie verschluesselt werden.

Kein TLS-Bypass noetig. Wir lesen die Daten dort wo sie noch Plaintext sind.
"""

import frida
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOOK_SCRIPT = r"""
'use strict';

var captured = [];
var count = 0;

// ================================================================
// Helper: Find export by enumerating (findExportByName fails on .NET)
// ================================================================
var _exportCache = {};
(function() {
    var m = Process.findModuleByName('libxvclient.dll');
    if (m) {
        var exports = m.enumerateExports();
        for (var i = 0; i < exports.length; i++) {
            _exportCache[exports[i].name] = exports[i].address;
        }
        send({type: 'INFO', msg: 'Cached ' + Object.keys(_exportCache).length + ' exports from libxvclient.dll'});
    } else {
        send({type: 'ERR', msg: 'libxvclient.dll not found!'});
    }
})();

function findExport(name) {
    return _exportCache[name] || null;
}

// ================================================================
// Helper: Read all function arguments as strings
// ================================================================
function readArg(ptr, maxLen) {
    if (!ptr || ptr.isNull()) return null;
    try {
        return ptr.readUtf8String(maxLen || 500);
    } catch(e) {
        try {
            return ptr.readAnsiString(maxLen || 500);
        } catch(e2) {
            return null;
        }
    }
}

function readArgBytes(ptr, len) {
    if (!ptr || ptr.isNull()) return null;
    try {
        return Memory.readByteArray(ptr, Math.min(len || 256, 2048));
    } catch(e) {
        return null;
    }
}

// ================================================================
// HOOK 1: xc_client_send_tracking_event — THE MAIN TRACKING FUNCTION
// ================================================================
var sendTracking = findExport('xc_client_send_tracking_event');
if (sendTracking) {
    Interceptor.attach(sendTracking, {
        onEnter: function(args) {
            count++;
            // args[0] = xc_client*, args[1] = tracking_event*
            var eventPtr = args[1];
            send({
                type: 'TRACKING_EVENT',
                n: count,
                client_ptr: args[0].toString(),
                event_ptr: eventPtr ? eventPtr.toString() : 'null',
            });
            // Try to dump the event structure
            if (eventPtr && !eventPtr.isNull()) {
                var data = readArgBytes(eventPtr, 512);
                if (data) {
                    send({type: 'TRACKING_DATA', n: count, label: 'event_struct'}, data);
                }
            }
        }
    });
    send({type: 'HOOKED', name: 'xc_client_send_tracking_event'});
}

// ================================================================
// HOOK 2: xc_client_send_xvca_events — XVCA ANALYTICS
// ================================================================
var sendXvca = findExport('xc_client_send_xvca_events');
if (sendXvca) {
    Interceptor.attach(sendXvca, {
        onEnter: function(args) {
            count++;
            send({type: 'XVCA_EVENT', n: count, ptr: args[0].toString()});
            if (args[1] && !args[1].isNull()) {
                var data = readArgBytes(args[1], 512);
                if (data) send({type: 'XVCA_DATA', n: count}, data);
            }
        }
    });
    send({type: 'HOOKED', name: 'xc_client_send_xvca_events'});
}

// ================================================================
// HOOK 3: xc_tracking_event_set_* — See what values are SET on tracking events
// ================================================================
var trackingSetters = [
    'xc_tracking_event_set_lat',
    'xc_tracking_event_set_device_model',
    'xc_tracking_event_set_install_time',
    'xc_tracking_event_set_event_time',
    'xc_tracking_event_set_os_locale',
    'xc_tracking_event_set_rdid',
    'xc_tracking_event_set_appsflyer_id',
    'xc_tracking_event_set_user_agent',
    'xc_tracking_event_set_referrer',
    'xc_tracking_event_set_deeplink_url',
    'xc_tracking_event_set_apple_search_ads_content',
];

trackingSetters.forEach(function(name) {
    var fn = findExport(name);
    if (fn) {
        Interceptor.attach(fn, {
            onEnter: function(args) {
                count++;
                // args[0] = tracking_event*, args[1] = value (usually string)
                var value = readArg(args[1], 300);
                send({
                    type: 'TRACKING_SET',
                    n: count,
                    function: name,
                    value: value,
                });
            }
        });
        send({type: 'HOOKED', name: name});
    }
});

// ================================================================
// HOOK 4: xc_conn_status_get_* — What connection info is READ
// ================================================================
var connGetters = [
    'xc_conn_status_get_ip',
    'xc_conn_status_get_city',
    'xc_conn_status_get_country_code',
    'xc_conn_status_get_isp',
    'xc_conn_status_get_asn',
    'xc_conn_status_get_region',
    'xc_conn_status_get_location_name',
    'xc_conn_status_get_connection_type',
    'xc_conn_status_get_is_connected_to_vpn',
];

connGetters.forEach(function(name) {
    var fn = findExport(name);
    if (fn) {
        Interceptor.attach(fn, {
            onLeave: function(retval) {
                count++;
                var value = readArg(retval, 200);
                // For bool functions, retval is 0 or 1
                if (value === null && retval) {
                    value = retval.toInt32().toString();
                }
                send({
                    type: 'CONN_STATUS',
                    n: count,
                    function: name,
                    value: value,
                });
            }
        });
        send({type: 'HOOKED', name: name});
    }
});

// ================================================================
// HOOK 5: xc_xvca_mgr_* — XVCA manager calls (battery, idle, etc.)
// ================================================================
var xvcaSetters = [
    'xc_xvca_mgr_set_battery_charge_percentage',
    'xc_xvca_mgr_set_device_idle_state',
    'xc_xvca_mgr_set_battery_optimisation_enabled',
    'xc_xvca_mgr_set_network_reachability_state',
    'xc_xvca_mgr_set_network_lock_state',
    'xc_xvca_mgr_set_split_tunneling_mode',
    'xc_xvca_mgr_set_dns_config_method',
    'xc_xvca_mgr_begin_connection',
    'xc_xvca_mgr_end_connection',
    'xc_xvca_mgr_begin_session',
    'xc_xvca_mgr_end_session',
    'xc_xvca_mgr_send_xvca_events',
];

xvcaSetters.forEach(function(name) {
    var fn = findExport(name);
    if (fn) {
        Interceptor.attach(fn, {
            onEnter: function(args) {
                count++;
                // Try to read all args
                var values = [];
                for (var i = 0; i < 4; i++) {
                    try {
                        var v = readArg(args[i], 100);
                        if (v) values.push(v);
                        else values.push(args[i].toInt32().toString());
                    } catch(e) {
                        try { values.push(args[i].toString()); } catch(e2) {}
                    }
                }
                send({
                    type: 'XVCA_MGR',
                    n: count,
                    function: name,
                    args: values,
                });
            }
        });
        send({type: 'HOOKED', name: name});
    }
});

// ================================================================
// HOOK 6: xc_activation_request_* — What device info is sent during activation
// ================================================================
var activationSetters = [
    'xc_activation_request_device_information_set_bios_id',
    'xc_activation_request_device_information_set_manufacturer',
    'xc_activation_request_device_information_set_oem',
    'xc_activation_request_device_information_set_platform',
    'xc_activation_request_set_idfa',
    'xc_activation_request_set_referrer',
    'xc_activation_request_set_utm_campaign',
];

activationSetters.forEach(function(name) {
    var fn = findExport(name);
    if (fn) {
        Interceptor.attach(fn, {
            onEnter: function(args) {
                count++;
                var value = readArg(args[1], 200);
                send({
                    type: 'ACTIVATION',
                    n: count,
                    function: name,
                    value: value,
                });
            }
        });
        send({type: 'HOOKED', name: name});
    }
});

// ================================================================
// HOOK 7: xc_client_is_hacked — Anti-tamper check
// ================================================================
var isHacked = findExport('xc_client_is_hacked');
if (isHacked) {
    Interceptor.attach(isHacked, {
        onLeave: function(retval) {
            count++;
            send({
                type: 'ANTI_TAMPER',
                n: count,
                result: retval.toInt32(),
            });
        }
    });
    send({type: 'HOOKED', name: 'xc_client_is_hacked'});
}

// ================================================================
// HOOK 8: xc_in_app_message_get_* — Marketing messages
// ================================================================
var iamGetters = [
    'xc_in_app_message_get_id',
    'xc_in_app_message_get_message',
    'xc_in_app_message_get_button_text',
    'xc_in_app_message_get_button_url',
];

iamGetters.forEach(function(name) {
    var fn = findExport(name);
    if (fn) {
        Interceptor.attach(fn, {
            onLeave: function(retval) {
                count++;
                var value = readArg(retval, 500);
                if (value) {
                    send({type: 'IN_APP_MSG', n: count, function: name, value: value});
                }
            }
        });
        send({type: 'HOOKED', name: name});
    }
});

// ================================================================
// HOOK 9: Analytics callbacks
// ================================================================
var analyticsNames = [
    '?AddAnalyticsEvent@CallbackHandler@xc@@UEAAXAEBV?$FiniteString@$0BK@@Analytics@2@AEBW4xc_client_reason@@AEBV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@@Z',
    '?AddAPIEvent@CallbackHandler@xc@@UEAAXAEBW4APIRequestType@Analytics@2@AEBW4xc_client_reason@@AEBV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@@Z',
    '?AddXvcaAnalyticsEvent@CallbackHandler@xc@@UEAAXAEBW4XvcaEventType@Analytics@2@AEBV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@@Z',
];

analyticsNames.forEach(function(name) {
    var fn = findExport(name);
    if (fn) {
        Interceptor.attach(fn, {
            onEnter: function(args) {
                count++;
                // args[2] or args[3] usually contains the event string
                var eventStr = null;
                for (var i = 1; i < 5; i++) {
                    try {
                        var s = readArg(args[i], 300);
                        if (s && s.length > 3) {
                            eventStr = s;
                            break;
                        }
                    } catch(e) {}
                }
                send({
                    type: 'ANALYTICS',
                    n: count,
                    function: name.substring(0, 30),
                    event: eventStr,
                });
            }
        });
        send({type: 'HOOKED', name: name.substring(0, 40) + '...'});
    }
});

send({type: 'READY', total_hooks: count === 0 ? 'waiting' : count});
"""


def main():
    print("=" * 60)
    print("  EXPRESSVPN TRACKING INTERCEPTOR")
    print("  Hooks ABOVE TLS — reads plaintext before encryption")
    print("=" * 60)

    # Find PID
    try:
        # Try new version first, then old
        for proc_name in ["expressvpn-service.exe", "ExpressVPN.AppService.exe"]:
            out = subprocess.check_output(
                ["tasklist", "/fi", f"IMAGENAME eq {proc_name}", "/fo", "csv", "/nh"],
                timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
            for line in out.strip().split("\n"):
                parts = line.split(",")
                if len(parts) >= 2 and parts[1].strip('"').isdigit():
                    pid = int(parts[1].strip('"'))
                    break
            if pid:
                break
    except Exception:
        pid = None

    if not pid:
        print("  ExpressVPN.AppService.exe not found!")
        return

    print(f"  Target PID: {pid}")
    captured = []
    hooks_installed = 0
    start = time.time()

    def on_msg(msg, data):
        nonlocal hooks_installed
        if msg["type"] != "send":
            if msg["type"] == "error":
                desc = msg.get("description", "")
                if "access" not in desc.lower() and len(desc) > 5:
                    print(f"  [ERR] {desc[:80]}")
            return

        p = msg["payload"]
        t = p.get("type", "?")
        elapsed = round(time.time() - start, 1)

        if t == "HOOKED":
            hooks_installed += 1
            name = p["name"]
            if len(name) > 50:
                name = name[:47] + "..."
            print(f"  [HOOK {hooks_installed:2d}] {name}")

        elif t == "READY":
            print(f"\n  {hooks_installed} hooks installed. Capturing for 60s...\n")

        elif t == "TRACKING_EVENT":
            print(f"  [{elapsed:5.1f}s] >>> TRACKING EVENT SENT! (#{p['n']})")
            captured.append({"time": elapsed, "type": t, **p})

        elif t == "TRACKING_DATA":
            if data:
                # Try to extract readable strings from the tracking event struct
                readable = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
                strings = [s for s in readable.split(".") if len(s) >= 4]
                if strings:
                    print(f"           Data: {' | '.join(strings[:10])}")
                captured.append({"time": elapsed, "type": t, "strings": strings[:20],
                                 "hex": data.hex()[:200]})

        elif t == "TRACKING_SET":
            val = p.get("value", "?")
            func = p.get("function", "?").replace("xc_tracking_event_set_", "")
            if val:
                safe = str(val)[:100].encode("ascii", "replace").decode()
                print(f"  [{elapsed:5.1f}s] SET tracking.{func} = {safe}")
                captured.append({"time": elapsed, "type": t, "field": func, "value": str(val)[:200]})

        elif t == "CONN_STATUS":
            val = p.get("value", "?")
            func = p.get("function", "?").replace("xc_conn_status_get_", "")
            if val:
                safe = str(val)[:100].encode("ascii", "replace").decode()
                print(f"  [{elapsed:5.1f}s] GET conn.{func} = {safe}")
                captured.append({"time": elapsed, "type": t, "field": func, "value": str(val)[:200]})

        elif t == "XVCA_EVENT":
            print(f"  [{elapsed:5.1f}s] >>> XVCA ANALYTICS EVENT (#{p['n']})")
            captured.append({"time": elapsed, "type": t, **p})

        elif t == "XVCA_MGR":
            func = p.get("function", "?").replace("xc_xvca_mgr_", "")
            args = p.get("args", [])
            print(f"  [{elapsed:5.1f}s] XVCA.{func}({', '.join(str(a)[:30] for a in args[:3])})")
            captured.append({"time": elapsed, "type": t, "function": func, "args": args})

        elif t == "ACTIVATION":
            func = p.get("function", "?").split("_set_")[-1] if "_set_" in p.get("function", "") else p.get("function", "?")
            val = p.get("value", "?")
            if val:
                safe = str(val)[:100].encode("ascii", "replace").decode()
                print(f"  [{elapsed:5.1f}s] ACTIVATION.{func} = {safe}")
                captured.append({"time": elapsed, "type": t, "field": func, "value": str(val)[:200]})

        elif t == "ANTI_TAMPER":
            result = "NOT HACKED" if p.get("result", 0) == 0 else "HACKED DETECTED!"
            print(f"  [{elapsed:5.1f}s] ANTI-TAMPER CHECK: {result}")
            captured.append({"time": elapsed, "type": t, "hacked": p.get("result", 0)})

        elif t == "IN_APP_MSG":
            func = p.get("function", "?").replace("xc_in_app_message_get_", "")
            val = p.get("value", "")
            if val:
                safe = val[:150].encode("ascii", "replace").decode()
                print(f"  [{elapsed:5.1f}s] IN-APP MESSAGE: {func} = {safe}")
                captured.append({"time": elapsed, "type": t, "field": func, "value": val[:500]})

        elif t == "ANALYTICS":
            event = p.get("event", "?")
            if event:
                safe = str(event)[:120].encode("ascii", "replace").decode()
                print(f"  [{elapsed:5.1f}s] ANALYTICS: {safe}")
                captured.append({"time": elapsed, "type": t, "event": str(event)[:300]})

        elif t == "XVCA_DATA":
            if data:
                readable = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
                strings = [s for s in readable.split(".") if len(s) >= 4]
                if strings:
                    print(f"           XVCA Data: {' | '.join(strings[:10])}")
                captured.append({"time": elapsed, "type": t, "strings": strings[:20]})

    try:
        session = frida.attach(pid)
        script = session.create_script(HOOK_SCRIPT)
        script.on("message", on_msg)
        script.load()

        time.sleep(180)

    except frida.ProcessNotFoundError:
        print(f"  Process {pid} not found!")
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
    finally:
        try:
            session.detach()
        except Exception:
            pass

    # Save results
    out_file = Path("expressvpn_tracking_captured.json")
    out_file.write_text(json.dumps(captured, indent=2, ensure_ascii=True))

    print(f"\n{'='*60}")
    print(f"  CAPTURED: {len(captured)} events in 60 seconds")
    print(f"  Saved to: {out_file}")
    print(f"{'='*60}")

    # Summary by type
    types = {}
    for c in captured:
        t = c.get("type", "?")
        types[t] = types.get(t, 0) + 1

    if types:
        print(f"\n  By type:")
        for t, n in sorted(types.items(), key=lambda x: -x[1]):
            print(f"    {t:25s} {n:4d}")

    # Show all captured values
    if captured:
        print(f"\n  All captured data points:")
        for c in captured:
            if c.get("value"):
                safe = str(c["value"])[:80].encode("ascii", "replace").decode()
                print(f"    {c.get('field', c.get('function', '?')):30s} = {safe}")


if __name__ == "__main__":
    main()
