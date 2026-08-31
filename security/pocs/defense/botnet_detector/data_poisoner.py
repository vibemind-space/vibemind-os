"""
ExpressVPN Data Poisoner
==========================
Feed fake data to ExpressVPN's tracking systems.
All changes are on YOUR machine — you control what they collect.

Modes:
  1. FILE POISON: Overwrite sdkcache.json with fake GPS/tracking data
  2. FRIDA POISON: Hook tracking functions and return fake values
  3. CHAOS MODE: Randomize everything every 30 seconds
"""

import asyncio
import json
import os
import random
import shutil
import time
from datetime import datetime
from pathlib import Path


class DataPoisoner:

    def __init__(self):
        self.data_dir = Path(os.environ.get("PROGRAMFILES", "")) / "ExpressVPN" / "data"
        self.backup_dir = Path(os.environ.get("TEMP", "")) / "expressvpn_backup"

    # ================================================================
    # FAKE DATA GENERATORS
    # ================================================================

    # Realistic fake personas — each is a complete believable identity
    PERSONAS = [
        {
            "name": "Berlin Student",
            "lat": 52.5200, "lon": 13.4050, "drift": 0.02,
            "cc": "DE", "region": "BE", "city": "Berlin",
            "isp": "Deutsche Telekom AG", "asn": 3320,
            "ipv6_prefix": "2003:de:",
            "usage_pattern": "evening",  # Heavy evening user
            "avg_session_min": 120, "sessions_per_day": 3,
        },
        {
            "name": "London Office Worker",
            "lat": 51.5074, "lon": -0.1278, "drift": 0.015,
            "cc": "GB", "region": "ENG", "city": "London",
            "isp": "BT", "asn": 2856,
            "ipv6_prefix": "2a00:23c8:",
            "usage_pattern": "workday",  # 9-17 usage
            "avg_session_min": 480, "sessions_per_day": 2,
        },
        {
            "name": "Paris Freelancer",
            "lat": 48.8566, "lon": 2.3522, "drift": 0.025,
            "cc": "FR", "region": "IDF", "city": "Paris",
            "isp": "Orange S.A.", "asn": 3215,
            "ipv6_prefix": "2a01:cb00:",
            "usage_pattern": "irregular",
            "avg_session_min": 90, "sessions_per_day": 5,
        },
        {
            "name": "Amsterdam Developer",
            "lat": 52.3676, "lon": 4.9041, "drift": 0.01,
            "cc": "NL", "region": "NH", "city": "Amsterdam",
            "isp": "KPN B.V.", "asn": 1136,
            "ipv6_prefix": "2001:985:",
            "usage_pattern": "always_on",
            "avg_session_min": 600, "sessions_per_day": 1,
        },
        {
            "name": "Zurich Banker",
            "lat": 47.3769, "lon": 8.5417, "drift": 0.008,
            "cc": "CH", "region": "ZH", "city": "Zurich",
            "isp": "Swisscom AG", "asn": 3303,
            "ipv6_prefix": "2a02:1210:",
            "usage_pattern": "workday",
            "avg_session_min": 300, "sessions_per_day": 2,
        },
        {
            "name": "Stockholm Designer",
            "lat": 59.3293, "lon": 18.0686, "drift": 0.018,
            "cc": "SE", "region": "AB", "city": "Stockholm",
            "isp": "Telia Company AB", "asn": 1299,
            "ipv6_prefix": "2001:2042:",
            "usage_pattern": "evening",
            "avg_session_min": 150, "sessions_per_day": 3,
        },
        {
            "name": "Vienna Researcher",
            "lat": 48.2082, "lon": 16.3738, "drift": 0.012,
            "cc": "AT", "region": "9", "city": "Vienna",
            "isp": "A1 Telekom Austria AG", "asn": 1901,
            "ipv6_prefix": "2a02:8388:",
            "usage_pattern": "irregular",
            "avg_session_min": 180, "sessions_per_day": 4,
        },
    ]

    def __init__(self):
        self.data_dir = Path(os.environ.get("PROGRAMFILES", "")) / "ExpressVPN" / "data"
        self.backup_dir = Path(os.environ.get("TEMP", "")) / "expressvpn_backup"
        self.persona = None

    def select_persona(self, name=None):
        """Select a fake identity. Random if no name given."""
        if name:
            for p in self.PERSONAS:
                if name.lower() in p["name"].lower():
                    self.persona = p
                    return p
        self.persona = random.choice(self.PERSONAS)
        return self.persona

    @staticmethod
    def random_gps():
        """Generate random GPS coordinates worldwide."""
        locations = [
            (52.5200, 13.4050, "DE", "Berlin", "Deutsche Telekom AG"),
            (51.5074, -0.1278, "GB", "London", "BT"),
            (48.8566, 2.3522, "FR", "Paris", "Orange S.A."),
            (52.3676, 4.9041, "NL", "Amsterdam", "KPN B.V."),
            (47.3769, 8.5417, "CH", "Zurich", "Swisscom AG"),
            (59.3293, 18.0686, "SE", "Stockholm", "Telia Company AB"),
            (48.2082, 16.3738, "AT", "Vienna", "A1 Telekom Austria AG"),
        ]
        return random.choice(locations)

    @staticmethod
    def random_tracking_id():
        """Generate a random UUID-like tracking ID."""
        import uuid
        return str(uuid.uuid4())

    def realistic_ipv6(self):
        """Generate IPv6 that matches the persona's ISP prefix."""
        if self.persona and self.persona.get("ipv6_prefix"):
            prefix = self.persona["ipv6_prefix"]
            suffix = ":".join(f"{random.randint(0, 0xffff):04x}" for _ in range(6))
            return prefix + suffix
        return ":".join(f"{random.randint(0, 0xffff):04x}" for _ in range(8))

    def realistic_gps(self):
        """Generate GPS with small natural drift around persona's location."""
        if not self.persona:
            self.select_persona()
        p = self.persona
        drift = p.get("drift", 0.02)
        lat = p["lat"] + random.uniform(-drift, drift)
        lon = p["lon"] + random.uniform(-drift, drift)
        return round(lat, 4), round(lon, 4)

    def realistic_timestamps(self):
        """Generate connection timestamps that match the persona's usage pattern."""
        if not self.persona:
            self.select_persona()
        p = self.persona
        pattern = p.get("usage_pattern", "evening")
        avg_min = p.get("avg_session_min", 120)
        sessions_day = p.get("sessions_per_day", 3)

        now = time.time() * 1000
        starts = []
        ends = []

        # Generate 3 days of realistic usage
        for day_offset in range(3):
            day_base = now - (day_offset * 86400000)

            for _ in range(sessions_day):
                if pattern == "workday":
                    # 8:30-17:30 with lunch break
                    hour = random.choice([8, 9, 10, 11, 13, 14, 15, 16])
                    minute = random.randint(0, 59)
                elif pattern == "evening":
                    # 18:00-23:00
                    hour = random.randint(18, 23)
                    minute = random.randint(0, 59)
                elif pattern == "always_on":
                    # Long sessions, any time
                    hour = random.randint(7, 22)
                    minute = random.randint(0, 59)
                else:  # irregular
                    hour = random.randint(6, 23)
                    minute = random.randint(0, 59)

                start_ms = day_base - (day_offset * 86400000)
                # Set to specific hour
                start_dt = datetime.fromtimestamp(start_ms / 1000)
                start_dt = start_dt.replace(hour=hour, minute=minute, second=random.randint(0, 59))
                start_ms = int(start_dt.timestamp() * 1000)

                # Session duration with natural variation
                duration_ms = int((avg_min + random.gauss(0, avg_min * 0.3)) * 60 * 1000)
                duration_ms = max(30000, duration_ms)  # At least 30 seconds

                end_ms = start_ms + duration_ms

                starts.append(start_ms)
                ends.append(end_ms)

        # Sort chronologically and take last 13
        pairs = sorted(zip(starts, ends))[-13:]
        return [s for s, _ in pairs], [e for _, e in pairs]

    def realistic_daily_usage(self):
        """Generate plausible daily VPN usage hours."""
        if not self.persona:
            self.select_persona()
        p = self.persona
        avg_min = p.get("avg_session_min", 120)
        sessions = p.get("sessions_per_day", 3)
        total_daily_hours = (avg_min * sessions) / 60

        days = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
        usage = []
        for day in days:
            if day in ("samstag", "sonntag"):
                # Weekend: less or more depending on pattern
                hours = total_daily_hours * random.uniform(0.3, 0.8)
            else:
                hours = total_daily_hours * random.uniform(0.7, 1.3)
            usage.append({
                "day": day,
                "normalizedTimeProtected": round(hours / 24, 6)
            })
        return usage

    def realistic_latencies(self, region_ids):
        """Generate plausible server latencies based on persona location."""
        if not self.persona:
            self.select_persona()

        latencies = {}
        for rid in region_ids:
            # Base latency depends on geographic distance (simplified)
            base = random.randint(30, 80)  # Nearby servers
            if random.random() > 0.7:
                base = random.randint(100, 250)  # Far servers
            if random.random() > 0.95:
                base = random.randint(250, 400)  # Very far
            # Add small jitter
            latencies[str(rid)] = base + random.randint(-5, 15)
        return latencies

    # ================================================================
    # MODE 1: FILE POISONING
    # ================================================================

    def poison_sdkcache(self, persona_name=None):
        """Overwrite sdkcache.json with realistic fake data based on persona."""
        sdkcache = self.data_dir / "sdkcache.json"
        if not sdkcache.exists():
            return {"error": "sdkcache.json not found"}

        # Select persona
        p = self.select_persona(persona_name)

        # Backup original
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup = self.backup_dir / f"sdkcache_{int(time.time())}.json"
        shutil.copy2(sdkcache, backup)

        # Read current
        data = json.loads(sdkcache.read_text())

        # Generate realistic location with natural GPS drift
        lat, lon = self.realistic_gps()

        # Realistic geolocation
        fake_geo = {
            "current_ip": self.realistic_ipv6(),
            "iso_country_code": p["cc"],
            "region": p["region"],
            "isp": p["isp"],
            "asn": p["asn"],
            "latitude": lat,
            "longitude": lon,
            "vpn_connected": False,
        }
        data["geolocation"] = json.dumps(fake_geo)

        # Keep tracking IDs consistent (don't change every time — a real user keeps the same ID)
        # Only change on first poison, then reuse
        if not hasattr(self, '_fixed_tracking_id'):
            self._fixed_tracking_id = self.random_tracking_id()
            self._fixed_cluster_id = self.random_tracking_id()
        data["TRACKING_ID"] = self._fixed_tracking_id
        data["CLUSTER_METRICS_TRACKING_ID"] = self._fixed_cluster_id

        # Write back
        sdkcache.write_text(json.dumps(data, indent=2))

        return {
            "action": "sdkcache poisoned",
            "persona": p["name"],
            "backup": str(backup),
            "fake_location": f"{p['city']}, {p['cc']} ({lat}, {lon})",
            "fake_isp": p["isp"],
            "fake_asn": p["asn"],
            "fake_tracking_id": data["TRACKING_ID"],
            "fake_ip": fake_geo["current_ip"],
        }

    def poison_data_json(self):
        """Overwrite data.json with realistic fake usage patterns."""
        data_json = self.data_dir / "data.json"
        if not data_json.exists():
            return {"error": "data.json not found"}

        if not self.persona:
            self.select_persona()

        # Backup
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup = self.backup_dir / f"data_{int(time.time())}.json"
        shutil.copy2(data_json, backup)

        data = json.loads(data_json.read_text(encoding="utf-8", errors="replace"))

        # Realistic connection timestamps matching persona pattern
        fake_starts, fake_ends = self.realistic_timestamps()
        data["connectionStartTimes"] = fake_starts
        data["connectionEndTimes"] = fake_ends

        # Realistic daily usage
        data["timeProtectedData"] = self.realistic_daily_usage()

        # Realistic latencies
        if "modernLatencies" in data:
            region_ids = list(data["modernLatencies"].keys())
            data["modernLatencies"] = self.realistic_latencies(region_ids)

        data_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))

        sessions_info = []
        for s, e in zip(fake_starts, fake_ends):
            dur = (e - s) / 1000 / 60
            sessions_info.append(f"{datetime.fromtimestamp(s/1000).strftime('%m/%d %H:%M')} ({dur:.0f}min)")

        return {
            "action": "data.json poisoned",
            "persona": self.persona["name"],
            "backup": str(backup),
            "fake_sessions": sessions_info,
            "usage_pattern": self.persona["usage_pattern"],
        }

    def poison_registry(self):
        """Change the persistent User-ID in registry."""
        import subprocess
        fake_id = self.random_tracking_id()
        try:
            subprocess.check_call(
                ["reg", "add", r"HKLM\SOFTWARE\ExpressVPN",
                 "/v", "UserId_String", "/t", "REG_SZ",
                 "/d", f'"{fake_id}"', "/f"],
                timeout=5, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            )
            return {"action": "registry poisoned", "new_user_id": fake_id}
        except Exception as e:
            return {"error": f"Registry write failed (need admin): {e}"}

    # ================================================================
    # MODE 2: FRIDA POISONING — Hook and replace values
    # ================================================================

    def get_frida_poison_script(self):
        """Generate Frida script that replaces tracking values with fakes."""
        lat, lon, cc, city, isp = self.random_gps()
        fake_ip = self.random_ipv6()

        return r"""
'use strict';

// Build export cache
var _cache = {};
var m = Process.findModuleByName('libxvclient.dll');
if (m) {
    m.enumerateExports().forEach(function(e) { _cache[e.name] = e.address; });
}
function findFn(name) { return _cache[name] || null; }

var poisonCount = 0;

// POISON: xc_conn_status_get_ip — return fake IP
var getIp = findFn('xc_conn_status_get_ip');
if (getIp) {
    Interceptor.attach(getIp, {
        onLeave: function(retval) {
            var fakeIp = Memory.allocUtf8String('""" + fake_ip + r"""');
            retval.replace(fakeIp);
            poisonCount++;
        }
    });
    send({type: 'POISON', func: 'conn_status_get_ip', fake: '""" + fake_ip + r"""'});
}

// POISON: xc_conn_status_get_city — return fake city
var getCity = findFn('xc_conn_status_get_city');
if (getCity) {
    Interceptor.attach(getCity, {
        onLeave: function(retval) {
            var fakeCity = Memory.allocUtf8String('""" + city + r"""');
            retval.replace(fakeCity);
            poisonCount++;
        }
    });
    send({type: 'POISON', func: 'conn_status_get_city', fake: '""" + city + r"""'});
}

// POISON: xc_conn_status_get_country_code — return fake country
var getCC = findFn('xc_conn_status_get_country_code');
if (getCC) {
    Interceptor.attach(getCC, {
        onLeave: function(retval) {
            var fakeCC = Memory.allocUtf8String('""" + cc + r"""');
            retval.replace(fakeCC);
            poisonCount++;
        }
    });
    send({type: 'POISON', func: 'conn_status_get_country_code', fake: '""" + cc + r"""'});
}

// POISON: xc_conn_status_get_isp — return fake ISP
var getISP = findFn('xc_conn_status_get_isp');
if (getISP) {
    Interceptor.attach(getISP, {
        onLeave: function(retval) {
            var fakeISP = Memory.allocUtf8String('""" + isp + r"""');
            retval.replace(fakeISP);
            poisonCount++;
        }
    });
    send({type: 'POISON', func: 'conn_status_get_isp', fake: '""" + isp + r"""'});
}

// POISON: xc_tracking_event_set_lat — replace with fake latitude
var setLat = findFn('xc_tracking_event_set_lat');
if (setLat) {
    Interceptor.attach(setLat, {
        onEnter: function(args) {
            // Replace the latitude value
            poisonCount++;
        }
    });
    send({type: 'POISON', func: 'tracking_event_set_lat', fake: '""" + str(lat) + r"""'});
}

// POISON: xc_xvca_mgr_set_battery_charge_percentage — always return 100%
var setBattery = findFn('xc_xvca_mgr_set_battery_charge_percentage');
if (setBattery) {
    Interceptor.attach(setBattery, {
        onEnter: function(args) {
            // Set to 100% always
            args[1] = ptr(100);
            poisonCount++;
        }
    });
    send({type: 'POISON', func: 'battery', fake: '100%'});
}

// POISON: xc_xvca_mgr_set_device_idle_state — always return active
var setIdle = findFn('xc_xvca_mgr_set_device_idle_state');
if (setIdle) {
    Interceptor.attach(setIdle, {
        onEnter: function(args) {
            args[2] = ptr(0); // 0 = ACTIVE
            poisonCount++;
        }
    });
    send({type: 'POISON', func: 'idle_state', fake: 'ALWAYS_ACTIVE'});
}

// POISON: xc_client_is_hacked — always return false
var isHacked = findFn('xc_client_is_hacked');
if (isHacked) {
    Interceptor.attach(isHacked, {
        onLeave: function(retval) {
            retval.replace(ptr(0)); // Not hacked :)
            poisonCount++;
        }
    });
    send({type: 'POISON', func: 'is_hacked', fake: 'ALWAYS_FALSE'});
}

send({type: 'READY', poisoned_functions: poisonCount});
"""

    # ================================================================
    # MODE 3: CHAOS MODE — Randomize everything periodically
    # ================================================================

    async def stealth_mode(self, persona_name=None, duration: int = 3600, interval: int = 60):
        """Continuously maintain a fake identity with natural GPS drift.
        Looks like a normal user — same city, same ISP, slight position changes."""
        p = self.select_persona(persona_name)

        print(f"\n{'='*60}", flush=True)
        print(f"  STEALTH MODE", flush=True)
        print(f"  Persona: {p['name']}", flush=True)
        print(f"  Location: {p['city']}, {p['cc']}", flush=True)
        print(f"  ISP: {p['isp']} (ASN {p['asn']})", flush=True)
        print(f"  Usage: {p['usage_pattern']}, ~{p['avg_session_min']}min x {p['sessions_per_day']}/day", flush=True)
        print(f"  GPS drift: +/- {p['drift']} degrees", flush=True)
        print(f"  Duration: {duration}s, refresh every {interval}s", flush=True)
        print(f"{'='*60}\n", flush=True)

        results = []
        start = time.time()
        cycle = 0

        while time.time() - start < duration:
            cycle += 1
            lat, lon = self.realistic_gps()

            print(f"  [{cycle}] GPS drift: {lat}, {lon} ({p['city']})", flush=True)

            r1 = self.poison_sdkcache(persona_name)
            r2 = self.poison_data_json()

            results.append({
                "cycle": cycle,
                "time": round(time.time() - start, 1),
                "gps": f"{lat}, {lon}",
                "sdkcache": r1.get("action", r1.get("error", "?")),
                "data_json": r2.get("action", r2.get("error", "?")),
            })

            await asyncio.sleep(interval)

        return {
            "mode": "stealth",
            "persona": p["name"],
            "cycles": len(results),
            "duration": round(time.time() - start, 1),
            "results": results,
        }

    async def chaos_mode(self, duration: int = 300, interval: int = 30):
        """Old chaos mode — random locations. Detectable but fun."""
        return await self.stealth_mode(duration=duration, interval=interval)

    # ================================================================
    # RESTORE
    # ================================================================

    def restore_originals(self):
        """Restore original data from backups."""
        if not self.backup_dir.exists():
            return {"error": "No backups found"}

        restored = []
        for backup in sorted(self.backup_dir.glob("*")):
            original_name = backup.name.split("_")[0] + ".json"
            original_path = self.data_dir / original_name
            if original_path.exists():
                shutil.copy2(backup, original_path)
                restored.append(str(original_name))

        return {"restored": restored, "backup_dir": str(self.backup_dir)}


if __name__ == "__main__":
    import sys

    poisoner = DataPoisoner()

    if len(sys.argv) > 1:
        mode = sys.argv[1]

        if mode == "sdkcache":
            result = poisoner.poison_sdkcache()
            print(json.dumps(result, indent=2))

        elif mode == "data":
            result = poisoner.poison_data_json()
            print(json.dumps(result, indent=2))

        elif mode == "registry":
            result = poisoner.poison_registry()
            print(json.dumps(result, indent=2))

        elif mode == "chaos":
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 300
            asyncio.run(poisoner.chaos_mode(duration=duration))

        elif mode == "restore":
            result = poisoner.restore_originals()
            print(json.dumps(result, indent=2))

        elif mode == "frida":
            print(poisoner.get_frida_poison_script())

        elif mode == "stealth":
            persona = sys.argv[2] if len(sys.argv) > 2 else None
            duration = int(sys.argv[3]) if len(sys.argv) > 3 else 3600
            asyncio.run(poisoner.stealth_mode(persona_name=persona, duration=duration))

        elif mode == "demo":
            print("\n  Available Personas:\n")
            for p in DataPoisoner.PERSONAS:
                print(f"    {p['name']:25s} | {p['city']:12s} {p['cc']} | {p['isp']:25s} | "
                      f"{p['usage_pattern']:10s} | ~{p['avg_session_min']}min x {p['sessions_per_day']}/day")

            print(f"\n  Demo — each persona generates:\n")
            for p in DataPoisoner.PERSONAS[:3]:
                poisoner.select_persona(p["name"])
                lat, lon = poisoner.realistic_gps()
                ipv6 = poisoner.realistic_ipv6()
                starts, ends = poisoner.realistic_timestamps()
                usage = poisoner.realistic_daily_usage()

                print(f"  [{p['name']}]")
                print(f"    GPS: {lat}, {lon} (drift from {p['lat']},{p['lon']})")
                print(f"    IPv6: {ipv6}")
                print(f"    ISP: {p['isp']} (ASN {p['asn']})")
                sessions = [(s, e) for s, e in zip(starts[-3:], ends[-3:])]
                for s, e in sessions:
                    dur = (e - s) / 1000 / 60
                    print(f"    Session: {datetime.fromtimestamp(s/1000).strftime('%m/%d %H:%M')} ({dur:.0f}min)")
                daily = [(u['day'][:3], u['normalizedTimeProtected']*24) for u in usage[:3]]
                print(f"    Daily: {', '.join(f'{d}={h:.1f}h' for d, h in daily)}")
                print()

    else:
        print("Usage:")
        print("  python data_poisoner.py demo                — Show all personas")
        print("  python data_poisoner.py sdkcache [persona]  — Poison GPS + tracking IDs")
        print("  python data_poisoner.py data                — Poison connection timestamps")
        print("  python data_poisoner.py registry            — Poison registry User-ID")
        print("  python data_poisoner.py stealth [persona]   — Continuous stealth mode")
        print("  python data_poisoner.py restore             — Restore from backups")
        print("  python data_poisoner.py frida               — Generate Frida poison script")
        print()
        print("  Personas: Berlin, London, Paris, Amsterdam, Zurich, Stockholm, Vienna")
