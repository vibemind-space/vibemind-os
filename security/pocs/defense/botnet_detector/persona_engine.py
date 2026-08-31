"""
Persona Simulation Engine
============================
Simulates a realistic daily life for a fake VPN user.
Not static data — a living, breathing digital twin.

Simulates:
  - Daily movement: home → commute → work → lunch → work → home → evening
  - Battery drain and charging cycles
  - Natural GPS drift as user moves through city
  - Active/idle state based on time of day
  - Connection patterns (connect when leaving home, disconnect at night)
  - Network changes (home WiFi → mobile → office WiFi)
  - Latency fluctuations based on network load
"""

import json
import math
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path


class Location:
    """A point in the city with GPS and context."""
    def __init__(self, lat, lon, name, wifi_ssid=None):
        self.lat = lat
        self.lon = lon
        self.name = name
        self.wifi_ssid = wifi_ssid


class PersonaEngine:
    """Simulates a complete fake user lifecycle."""

    PERSONAS = {
        "berlin": {
            "name": "Berlin Student",
            "cc": "DE", "region": "BE", "isp": "Deutsche Telekom AG", "asn": 3320,
            "ipv6_prefix": "2003:de:",
            "locations": {
                "home":   Location(52.4934, 13.4263, "Home - Neukoelln", "FritzBox7590_Student"),
                "work":   Location(52.5200, 13.4050, "TU Berlin", "eduroam"),
                "cafe":   Location(52.5105, 13.3894, "Cafe - Kreuzberg", "KaffeeHaus_Free"),
                "gym":    Location(52.4891, 13.4312, "McFit Neukoelln", None),
                "park":   Location(52.4870, 13.4230, "Tempelhofer Feld", None),
            },
            "schedule": [
                # (hour_start, hour_end, location, activity, vpn_on)
                (0, 7, "home", "sleeping", False),
                (7, 8, "home", "morning_routine", True),
                (8, 9, "commute", "transit", True),
                (9, 12, "work", "studying", True),
                (12, 13, "cafe", "lunch", True),
                (13, 17, "work", "studying", True),
                (17, 18, "commute", "transit", True),
                (18, 19, "gym", "workout", False),
                (19, 20, "home", "dinner", False),
                (20, 23, "home", "streaming", True),
                (23, 24, "home", "sleeping", False),
            ],
            "battery_profile": {
                "charge_at": ["home"],
                "drain_per_hour_active": 8,
                "drain_per_hour_idle": 2,
                "charge_rate_per_hour": 30,
            },
        },
        "london": {
            "name": "London Office Worker",
            "cc": "GB", "region": "ENG", "isp": "BT", "asn": 2856,
            "ipv6_prefix": "2a00:23c8:",
            "locations": {
                "home":   Location(51.4620, -0.1159, "Home - Brixton", "SKY_WiFi_B7X2"),
                "work":   Location(51.5155, -0.0922, "Office - City", "CorpNet_5G"),
                "pub":    Location(51.5130, -0.0870, "Pub - Liverpool St", "TheOldNick_Guest"),
                "tube":   Location(51.5030, -0.1130, "Underground", None),
            },
            "schedule": [
                (0, 6, "home", "sleeping", False),
                (6, 7, "home", "morning", True),
                (7, 8, "tube", "commute", True),
                (8, 12, "work", "working", True),
                (12, 13, "work", "lunch_desk", True),
                (13, 17, "work", "working", True),
                (17, 18, "tube", "commute", True),
                (18, 20, "pub", "after_work", False),
                (20, 22, "home", "evening", True),
                (22, 24, "home", "sleeping", False),
            ],
            "battery_profile": {
                "charge_at": ["home", "work"],
                "drain_per_hour_active": 6,
                "drain_per_hour_idle": 1.5,
                "charge_rate_per_hour": 25,
            },
        },
        "amsterdam": {
            "name": "Amsterdam Developer",
            "cc": "NL", "region": "NH", "isp": "KPN B.V.", "asn": 1136,
            "ipv6_prefix": "2001:985:",
            "locations": {
                "home":   Location(52.3590, 4.9012, "Home - De Pijp", "Ziggo_DevNest"),
                "cowork": Location(52.3667, 4.8945, "WeWork - Vijzelstraat", "WeWork_5G"),
                "coffeeshop": Location(52.3725, 4.8930, "Coffeeshop break", None),
            },
            "schedule": [
                (0, 9, "home", "sleeping", False),
                (9, 10, "home", "standup", True),
                (10, 13, "cowork", "coding", True),
                (13, 14, "coffeeshop", "lunch", False),
                (14, 19, "cowork", "coding", True),
                (19, 20, "home", "cycling_home", False),
                (20, 1, "home", "side_project", True),
            ],
            "battery_profile": {
                "charge_at": ["home", "cowork"],
                "drain_per_hour_active": 7,
                "drain_per_hour_idle": 1,
                "charge_rate_per_hour": 35,
            },
        },
    }

    def __init__(self, persona_name="berlin"):
        key = persona_name.lower()
        if key not in self.PERSONAS:
            key = random.choice(list(self.PERSONAS.keys()))
        self.persona = self.PERSONAS[key]
        self.state = {
            "battery": random.randint(60, 95),
            "is_charging": False,
            "is_idle": False,
            "vpn_connected": False,
            "current_location": "home",
            "current_activity": "idle",
            "wifi_ssid": None,
            "sessions_today": [],
            "last_gps": None,
            "movement_noise": 0,
        }
        self._fixed_ipv6_suffix = ":".join(f"{random.randint(0, 0xffff):04x}" for _ in range(6))
        self._tracking_id = str(__import__("uuid").uuid4())
        self._cluster_id = str(__import__("uuid").uuid4())

    def get_current_state(self, now=None):
        """Calculate the complete fake state for a given moment."""
        if now is None:
            now = datetime.now()

        hour = now.hour + now.minute / 60.0
        schedule = self.persona["schedule"]
        locations = self.persona["locations"]
        battery_prof = self.persona["battery_profile"]

        # Find current schedule slot
        current_slot = schedule[-1]  # Default to last slot
        for start_h, end_h, loc, activity, vpn in schedule:
            if end_h > start_h:
                if start_h <= hour < end_h:
                    current_slot = (start_h, end_h, loc, activity, vpn)
                    break
            else:  # Wraps midnight
                if hour >= start_h or hour < end_h:
                    current_slot = (start_h, end_h, loc, activity, vpn)
                    break

        _, _, loc_name, activity, vpn_on = current_slot

        # Get location with natural movement
        if loc_name == "commute":
            # Interpolate between last and next location
            progress = (hour % 1)  # How far through the hour
            home = locations["home"]
            work = locations["work"]
            lat = home.lat + (work.lat - home.lat) * progress
            lon = home.lon + (work.lon - home.lon) * progress
            wifi = None
        elif loc_name in locations:
            loc = locations[loc_name]
            # Natural GPS drift — person moves within building/area
            drift = 0.0003 + random.gauss(0, 0.0001)  # ~30 meters
            lat = loc.lat + random.uniform(-drift, drift)
            lon = loc.lon + random.uniform(-drift, drift)
            wifi = loc.wifi_ssid
        else:
            lat = locations["home"].lat
            lon = locations["home"].lon
            wifi = None

        # Battery simulation
        battery = self._simulate_battery(hour, loc_name, activity, battery_prof)

        # Idle state
        idle_activities = ["sleeping", "transit", "lunch", "dinner", "workout"]
        is_idle = activity in idle_activities

        # Network type
        if wifi:
            network_type = "wifi"
        elif loc_name == "commute":
            network_type = "cellular"
        else:
            network_type = "wifi"

        # Build complete state
        state = {
            "geolocation": {
                "current_ip": self.persona["ipv6_prefix"] + self._fixed_ipv6_suffix,
                "iso_country_code": self.persona["cc"],
                "region": self.persona["region"],
                "isp": self.persona["isp"],
                "asn": self.persona["asn"],
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "vpn_connected": vpn_on,
            },
            "tracking": {
                "TRACKING_ID": self._tracking_id,
                "CLUSTER_METRICS_TRACKING_ID": self._cluster_id,
            },
            "device": {
                "battery_percent": battery,
                "is_charging": loc_name in battery_prof["charge_at"] and battery < 90,
                "is_idle": is_idle,
                "network_type": network_type,
                "wifi_ssid": wifi,
            },
            "vpn": {
                "connected": vpn_on,
                "activity": activity,
                "location": loc_name,
            },
            "timestamps": self._generate_timestamps(now),
            "daily_usage": self._generate_daily_usage(now),
            "meta": {
                "persona": self.persona["name"],
                "simulated_time": now.isoformat()[:19],
                "hour": round(hour, 1),
            },
        }

        return state

    def _simulate_battery(self, hour, location, activity, profile):
        """Simulate battery level based on time and activity."""
        # Start of day at 100% (charged overnight)
        base = 100

        # Drain throughout the day
        if hour < 7:
            drain = hour * profile["drain_per_hour_idle"]
        elif hour < 22:
            active_hours = hour - 7
            drain = active_hours * profile["drain_per_hour_active"]
            # Charging periods
            if location in profile["charge_at"]:
                charge_hours = min(active_hours, 3)  # Max 3h charge periods
                drain -= charge_hours * profile["charge_rate_per_hour"]
        else:
            drain = 15 * profile["drain_per_hour_active"]  # Full day drain

        battery = max(5, min(100, int(base - drain + random.gauss(0, 3))))
        return battery

    def _generate_timestamps(self, now):
        """Generate realistic connection timestamps for the past few days."""
        schedule = self.persona["schedule"]
        starts = []
        ends = []

        for day_offset in range(3, -1, -1):
            day = now - timedelta(days=day_offset)
            for start_h, end_h, _, _, vpn_on in schedule:
                if vpn_on:
                    # Add some randomness to start/end times
                    s_hour = start_h + random.uniform(-0.1, 0.1)
                    e_hour = end_h + random.uniform(-0.1, 0.1)
                    if e_hour <= s_hour:
                        e_hour = s_hour + 0.5

                    s_dt = day.replace(hour=int(s_hour), minute=int((s_hour % 1) * 60),
                                       second=random.randint(0, 59), microsecond=0)
                    e_dt = day.replace(hour=min(23, int(e_hour)), minute=int((e_hour % 1) * 60),
                                       second=random.randint(0, 59), microsecond=0)

                    starts.append(int(s_dt.timestamp() * 1000))
                    ends.append(int(e_dt.timestamp() * 1000))

        # Take the most recent 13
        pairs = list(zip(starts, ends))[-13:]
        return {
            "connectionStartTimes": [s for s, _ in pairs],
            "connectionEndTimes": [e for _, e in pairs],
        }

    def _generate_daily_usage(self, now):
        """Generate realistic daily usage data."""
        schedule = self.persona["schedule"]
        total_vpn_hours = sum(
            (end - start) for start, end, _, _, vpn in schedule if vpn and end > start
        )

        days = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
        weekday = now.weekday()

        usage = []
        for i, day in enumerate(days):
            day_offset = (i - weekday) % 7
            if day_offset > 3:
                # Future days — no data yet
                hours = 0
            elif day in ("samstag", "sonntag"):
                hours = total_vpn_hours * random.uniform(0.3, 0.6)
            else:
                hours = total_vpn_hours * random.uniform(0.8, 1.1)

            # Add natural variation
            hours += random.gauss(0, 0.5)
            hours = max(0, hours)

            usage.append({
                "day": day,
                "normalizedTimeProtected": round(hours / 24, 6)
            })
        return usage

    def apply_to_files(self, data_dir=None):
        """Write current state to ExpressVPN data files."""
        if data_dir is None:
            data_dir = Path(os.environ.get("PROGRAMFILES", "")) / "ExpressVPN" / "data"

        state = self.get_current_state()
        result = {"applied": [], "errors": []}

        # 1. sdkcache.json
        sdkcache = data_dir / "sdkcache.json"
        if sdkcache.exists():
            try:
                data = json.loads(sdkcache.read_text())
                data["geolocation"] = json.dumps(state["geolocation"])
                data["TRACKING_ID"] = state["tracking"]["TRACKING_ID"]
                data["CLUSTER_METRICS_TRACKING_ID"] = state["tracking"]["CLUSTER_METRICS_TRACKING_ID"]
                sdkcache.write_text(json.dumps(data, indent=2))
                result["applied"].append("sdkcache.json")
            except Exception as e:
                result["errors"].append(f"sdkcache: {e}")

        # 2. data.json
        data_json = data_dir / "data.json"
        if data_json.exists():
            try:
                data = json.loads(data_json.read_text(encoding="utf-8", errors="replace"))
                data["connectionStartTimes"] = state["timestamps"]["connectionStartTimes"]
                data["connectionEndTimes"] = state["timestamps"]["connectionEndTimes"]
                data["timeProtectedData"] = state["daily_usage"]
                data_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                result["applied"].append("data.json")
            except Exception as e:
                result["errors"].append(f"data.json: {e}")

        result["state"] = {
            "persona": state["meta"]["persona"],
            "location": f"{state['geolocation']['latitude']}, {state['geolocation']['longitude']}",
            "activity": state["vpn"]["activity"],
            "battery": state["device"]["battery_percent"],
            "vpn": state["vpn"]["connected"],
            "network": state["device"]["network_type"],
        }

        return result


# ================================================================
# CLI
# ================================================================

if __name__ == "__main__":
    import sys

    persona = sys.argv[1] if len(sys.argv) > 1 else "berlin"
    engine = PersonaEngine(persona)

    print(f"\n{'='*60}")
    print(f"  PERSONA ENGINE — {engine.persona['name']}")
    print(f"{'='*60}")

    # Simulate a full day
    now = datetime.now()
    print(f"\n  Simulating 24 hours:\n")

    for hour in range(24):
        t = now.replace(hour=hour, minute=30)
        state = engine.get_current_state(t)

        geo = state["geolocation"]
        dev = state["device"]
        vpn = state["vpn"]

        bat_icon = "+" if dev["is_charging"] else "-"
        vpn_icon = "ON " if vpn["connected"] else "OFF"
        idle_icon = "ZZZ" if dev["is_idle"] else "   "

        print(f"  {hour:02d}:30  "
              f"GPS {geo['latitude']:8.4f},{geo['longitude']:9.4f}  "
              f"Bat {dev['battery_percent']:3d}%{bat_icon}  "
              f"VPN {vpn_icon}  "
              f"{idle_icon}  "
              f"{vpn['location']:10s}  "
              f"{vpn['activity']:15s}  "
              f"{dev['network_type']:8s}  "
              f"{dev.get('wifi_ssid', '') or ''}")
