"""
ExpressVPN Tracking Event Watcher
====================================
Monitors tracking_events.db in real-time:
1. Polls SQLite DB every 500ms for new events
2. Watches file size changes (WAL file grows when events are written)
3. Captures events BEFORE ExpressVPN sends and deletes them
4. Also monitors sdkcache.json and data.json for changes
"""

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path


class TrackingWatcher:

    def __init__(self):
        self.data_dir = Path(os.environ.get("PROGRAMFILES", "")) / "ExpressVPN" / "data"
        self.csdk_dir = self.data_dir / "csdk"
        self.db_path = self.csdk_dir / "tracking_events.db"
        self.wal_path = self.csdk_dir / "tracking_events.db-wal"
        self.sdkcache_path = self.data_dir / "sdkcache.json"
        self.data_json_path = self.data_dir / "data.json"

        self.captured_events = []
        self.file_changes = []
        self.last_row_id = 0
        self.last_wal_size = 0
        self.last_sdkcache_hash = ""
        self.running = False

    async def watch(self, duration: int = 300):
        """Watch for tracking events for specified duration."""
        self.running = True
        print(f"\n{'='*60}", flush=True)
        print(f"  TRACKING EVENT WATCHER", flush=True)
        print(f"  Monitoring for {duration}s (disconnect/reconnect VPN to trigger)", flush=True)
        print(f"{'='*60}\n", flush=True)

        # Get initial state
        self.last_wal_size = self.wal_path.stat().st_size if self.wal_path.exists() else 0
        self.last_sdkcache_hash = self._hash_file(self.sdkcache_path)

        # Snapshot initial sdkcache
        initial_cache = self._read_sdkcache()
        if initial_cache:
            print(f"  [INIT] TRACKING_ID: {initial_cache.get('TRACKING_ID', '?')}", flush=True)
            print(f"  [INIT] CLUSTER_METRICS_ID: {initial_cache.get('CLUSTER_METRICS_TRACKING_ID', '?')}", flush=True)
            geo = initial_cache.get("geolocation", "")
            if geo:
                try:
                    g = json.loads(geo)
                    print(f"  [INIT] Geolocation: {g.get('latitude')}, {g.get('longitude')} ({g.get('region')}, {g.get('iso_country_code')})", flush=True)
                except Exception:
                    pass

        print(f"\n  Watching...\n", flush=True)

        start = time.time()
        poll_count = 0

        while time.time() - start < duration and self.running:
            poll_count += 1
            elapsed = round(time.time() - start, 1)

            # 1. Poll tracking_events.db for new rows
            await self._poll_db(elapsed)

            # 2. Check WAL file size changes
            await self._check_wal(elapsed)

            # 3. Check sdkcache.json changes
            await self._check_sdkcache(elapsed)

            # 4. Check data.json changes
            await self._check_data_json(elapsed)

            # 5. Check http_cache.db for new entries
            await self._check_http_cache(elapsed)

            # Status every 30s
            if poll_count % 60 == 0:
                print(f"  [{elapsed:5.0f}s] Still watching... ({len(self.captured_events)} events, {len(self.file_changes)} changes)", flush=True)

            await asyncio.sleep(0.5)

        # Summary
        print(f"\n{'='*60}", flush=True)
        print(f"  WATCHER RESULTS ({duration}s)", flush=True)
        print(f"{'='*60}", flush=True)
        print(f"  Events captured: {len(self.captured_events)}", flush=True)
        print(f"  File changes: {len(self.file_changes)}", flush=True)

        if self.captured_events:
            print(f"\n  --- Captured Events ---", flush=True)
            for ev in self.captured_events:
                print(f"  [{ev['time']:5.1f}s] {ev['type']}: {str(ev.get('data', ''))[:120]}", flush=True)

        if self.file_changes:
            print(f"\n  --- File Changes ---", flush=True)
            for ch in self.file_changes:
                print(f"  [{ch['time']:5.1f}s] {ch['file']}: {ch['change'][:100]}", flush=True)

        # Save results
        result = {
            "timestamp": datetime.now().isoformat(),
            "duration": duration,
            "events": self.captured_events,
            "file_changes": self.file_changes,
        }
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = Path(f"expressvpn_tracking_captured_{ts}.json")
        out.write_text(json.dumps(result, indent=2, ensure_ascii=True))
        print(f"\n  Saved to {out}", flush=True)

        return result

    async def _poll_db(self, elapsed):
        """Poll tracking_events.db for new rows."""
        try:
            # Copy DB to avoid locking
            tmp = Path(os.environ.get("TEMP", "")) / "evpn_tracking_copy.db"
            shutil.copy2(self.db_path, tmp)
            if self.wal_path.exists():
                shutil.copy2(self.wal_path, str(tmp) + "-wal")
            shm = self.csdk_dir / "tracking_events.db-shm"
            if shm.exists():
                shutil.copy2(shm, str(tmp) + "-shm")

            db = sqlite3.connect(str(tmp))
            cursor = db.cursor()

            # Check for new events
            cursor.execute("SELECT id, event_json, created_at FROM events WHERE id > ? ORDER BY id", (self.last_row_id,))
            rows = cursor.fetchall()

            for row_id, event_json, created_at in rows:
                self.last_row_id = row_id
                event = {
                    "time": elapsed,
                    "type": "DB_EVENT",
                    "row_id": row_id,
                    "created_at": created_at,
                    "data": event_json[:500] if event_json else "",
                }
                self.captured_events.append(event)

                # Parse the event JSON
                safe = str(event_json)[:150].encode("ascii", "replace").decode()
                print(f"  [{elapsed:5.1f}s] !!! NEW TRACKING EVENT (id={row_id}): {safe}", flush=True)

                # Try to parse
                if event_json:
                    try:
                        parsed = json.loads(event_json)
                        event["parsed"] = parsed
                        print(f"           Keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'array'}", flush=True)
                        if isinstance(parsed, dict):
                            for key in ["event", "type", "name", "properties", "data", "user_id", "device_id"]:
                                if key in parsed:
                                    val = str(parsed[key])[:100]
                                    print(f"           {key}: {val}", flush=True)
                    except json.JSONDecodeError:
                        pass

            # Also check total row count
            cursor.execute("SELECT COUNT(*) FROM events")
            count = cursor.fetchone()[0]
            if count > 0 and not rows:
                # Rows exist but we already saw them
                pass

            db.close()
            tmp.unlink(missing_ok=True)
            Path(str(tmp) + "-wal").unlink(missing_ok=True)
            Path(str(tmp) + "-shm").unlink(missing_ok=True)

        except sqlite3.OperationalError:
            pass  # DB locked, try next poll
        except Exception:
            pass

    async def _check_wal(self, elapsed):
        """Check WAL file for size changes (indicates writes)."""
        try:
            if self.wal_path.exists():
                size = self.wal_path.stat().st_size
                if size != self.last_wal_size:
                    delta = size - self.last_wal_size
                    if abs(delta) > 100:  # Ignore tiny changes
                        self.file_changes.append({
                            "time": elapsed,
                            "file": "tracking_events.db-wal",
                            "change": f"Size changed: {self.last_wal_size} -> {size} ({'+' if delta > 0 else ''}{delta} bytes)",
                        })
                        print(f"  [{elapsed:5.1f}s] WAL file changed: {delta:+d} bytes (total {size})", flush=True)
                    self.last_wal_size = size
        except Exception:
            pass

    async def _check_sdkcache(self, elapsed):
        """Check sdkcache.json for content changes."""
        try:
            new_hash = self._hash_file(self.sdkcache_path)
            if new_hash != self.last_sdkcache_hash:
                self.last_sdkcache_hash = new_hash

                # Read and compare
                cache = self._read_sdkcache()
                if cache:
                    changes = []
                    geo = cache.get("geolocation", "")
                    tracking_id = cache.get("TRACKING_ID", "")

                    self.file_changes.append({
                        "time": elapsed,
                        "file": "sdkcache.json",
                        "change": f"Content changed (hash={new_hash[:16]})",
                        "tracking_id": tracking_id,
                        "geolocation": geo[:100],
                    })

                    print(f"  [{elapsed:5.1f}s] sdkcache.json CHANGED!", flush=True)

                    # Show what changed
                    if geo:
                        try:
                            g = json.loads(geo)
                            print(f"           Geo: {g.get('current_ip', '?')} | {g.get('latitude')},{g.get('longitude')} | vpn={g.get('vpn_connected')}", flush=True)
                        except Exception:
                            pass
        except Exception:
            pass

    async def _check_data_json(self, elapsed):
        """Check data.json for size changes."""
        try:
            if self.data_json_path.exists():
                size = self.data_json_path.stat().st_size
                mtime = self.data_json_path.stat().st_mtime
                # Only report if modified in last 2 seconds
                if time.time() - mtime < 2:
                    self.file_changes.append({
                        "time": elapsed,
                        "file": "data.json",
                        "change": f"Modified (size={size})",
                    })
                    print(f"  [{elapsed:5.1f}s] data.json modified ({size} bytes)", flush=True)
        except Exception:
            pass

    async def _check_http_cache(self, elapsed):
        """Check http_cache.db for new entries."""
        cache_files = list(self.csdk_dir.glob("*_http_cache.db"))
        for cf in cache_files:
            try:
                db = sqlite3.connect(str(cf))
                cursor = db.cursor()
                cursor.execute("SELECT COUNT(*) FROM http_cache")
                count = cursor.fetchone()[0]
                db.close()
                # We could track count changes here
            except Exception:
                pass

    def _hash_file(self, path):
        try:
            return hashlib.md5(path.read_bytes()).hexdigest()
        except Exception:
            return ""

    def _read_sdkcache(self):
        try:
            return json.loads(self.sdkcache_path.read_text())
        except Exception:
            return {}


if __name__ == "__main__":
    import sys

    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 120

    async def main():
        watcher = TrackingWatcher()
        await watcher.watch(duration=duration)

    asyncio.run(main())
