"""Phase 11.D.2 — MCP-Tool Discovery.

Spawns each MCP server defined in `openfang.vibemind.toml` and
`/.mcp.json`, runs the MCP handshake, calls `tools/list`, caches the
results to `data/mcp_tools_cache.json`. Used by `/api/events/mapping`
to resolve real tool-names (with description + args) instead of
hardcoded heuristics.

Discovery happens:
  - At Brain boot (parallel via ThreadPoolExecutor, ~5s for 30 servers)
  - On-demand via `/api/mcp/discover`
  - Lazy on first call if cache is missing

Public API:
  McpDiscovery.list_servers() -> list[str]
  McpDiscovery.list_tools(server) -> list[{name, description, input_schema}]
  McpDiscovery.find_tool_for_event(event_id, mcp_servers) -> tool_name|None
  McpDiscovery.discover_all() -> dict (stats)
  McpDiscovery.reload_from_cache() -> int (tools count)

Cache file is JSON for human inspection / git review:
  {
    "ts": 1234567890,
    "servers": {
      "spaces-ideas": {
        "tools": [
          {"name": "bubble_create", "description": "...", "input_schema": {...}}
        ]
      }
    }
  }
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_BRAIN_ROOT = Path(__file__).resolve().parents[1]
_VIBEMIND_OS = _BRAIN_ROOT.parents[1]
_DATA_DIR = _BRAIN_ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_PATH = _DATA_DIR / "mcp_tools_cache.json"

_OPENFANG_TOML = _VIBEMIND_OS / "openfang" / "openfang.vibemind.toml"
_MCP_JSON = _VIBEMIND_OS.parent / ".mcp.json"

_HANDSHAKE_TIMEOUT_S = 8


def _parse_openfang_toml() -> List[Dict[str, Any]]:
    """Extract [[mcp_servers]] entries from openfang.vibemind.toml.
    Each entry is followed by a [mcp_servers.transport] block — these
    are part of the same logical server. We chunk by [[mcp_servers]]
    boundary then include the transport block which lives between
    [mcp_servers.transport] and the NEXT [[ (double-bracket).
    """
    out: List[Dict[str, Any]] = []
    if not _OPENFANG_TOML.exists():
        return out
    txt = open(_OPENFANG_TOML, encoding="utf-8").read()
    blocks = re.split(r"\n\[\[mcp_servers\]\]\s*\n", "\n" + txt)[1:]
    for blk in blocks:
        # Stop at next [[ section (start of next server or unrelated section)
        end = re.search(r"\n\[\[", blk)
        if end:
            blk = blk[:end.start()]
        # Stop at next non-mcp_servers sub-section like [a2a], [channels]
        end2 = re.search(r"\n\[(?!mcp_servers\.)[a-z]", blk)
        if end2:
            blk = blk[:end2.start()]
        name_m = re.search(r'^\s*name\s*=\s*"([^"]+)"', blk, re.M)
        type_m = re.search(r'^\s*type\s*=\s*"([^"]+)"', blk, re.M)
        cmd_m = re.search(r'^\s*command\s*=\s*"([^"]+)"', blk, re.M)
        args_m = re.search(r'^\s*args\s*=\s*\[([^\]]+)\]', blk, re.M | re.S)
        url_m = re.search(r'^\s*url\s*=\s*"([^"]+)"', blk, re.M)
        if not name_m:
            continue
        entry = {
            "name": name_m.group(1),
            "transport_type": (type_m.group(1) if type_m else "stdio"),
            "command": (cmd_m.group(1) if cmd_m else ""),
            "args": [],
            "url": (url_m.group(1) if url_m else ""),
            "source": "openfang.vibemind.toml",
        }
        if args_m:
            raw = args_m.group(1)
            entry["args"] = [a.strip().strip('"').strip("'")
                             for a in raw.split(",") if a.strip()]
        out.append(entry)
    return out


def _parse_mcp_json() -> List[Dict[str, Any]]:
    """Extract servers from .mcp.json."""
    if not _MCP_JSON.exists():
        return []
    try:
        data = json.load(open(_MCP_JSON, encoding="utf-8"))
        servers = data.get("mcpServers", {})
        out = []
        for name, cfg in servers.items():
            out.append({
                "name": name,
                "transport_type": cfg.get("type", "stdio"),
                "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
                "url": cfg.get("url", ""),
                "source": ".mcp.json",
            })
        return out
    except Exception as e:
        logger.warning(f"[mcp_discovery] cannot parse .mcp.json: {e}")
        return []


def _merged_server_list() -> List[Dict[str, Any]]:
    """Merge both sources, deduping by name. openfang.vibemind.toml wins."""
    of = _parse_openfang_toml()
    of_names = {s["name"] for s in of}
    mc = _parse_mcp_json()
    out = list(of)
    for s in mc:
        if s["name"] not in of_names:
            out.append(s)
    return out


def _spawn_and_list_tools(server: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Spawn one stdio MCP server, do handshake, return tools list or None."""
    if server["transport_type"] != "stdio":
        return None  # SSE/HTTP servers — skip for now (can be added later)
    cmd = server["command"]
    args = server.get("args") or []
    if not cmd:
        return None
    full_cmd = [cmd] + args
    try:
        p = subprocess.Popen(
            full_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
    except Exception as e:
        logger.debug(f"[mcp_discovery] spawn failed for {server['name']}: {e}")
        return None

    def _send(req):
        try:
            p.stdin.write(json.dumps(req) + "\n")
            p.stdin.flush()
        except Exception:
            pass

    def _recv_with_timeout():
        # Simple line-read with a watchdog; subprocess stdin/stdout is sync.
        # We spawn a thread that reads one line; if it doesn't return in time,
        # we kill the proc.
        result = [None]
        ev = threading.Event()
        def _r():
            try:
                line = p.stdout.readline()
                result[0] = line
            except Exception:
                pass
            ev.set()
        t = threading.Thread(target=_r, daemon=True)
        t.start()
        ev.wait(_HANDSHAKE_TIMEOUT_S)
        if not ev.is_set():
            return None
        line = result[0]
        if not line:
            return None
        try:
            return json.loads(line)
        except Exception:
            return None

    try:
        # Initialize
        _send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "brain-discovery", "version": "1"},
            }
        })
        init = _recv_with_timeout()
        if not init:
            return None
        # initialized notification
        _send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        # List tools
        _send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools_msg = _recv_with_timeout()
        if not tools_msg:
            return None
        tools = (tools_msg.get("result") or {}).get("tools") or []
        # Trim to {name, description, input_schema}
        return [
            {
                "name": t.get("name", ""),
                "description": (t.get("description") or "")[:600],
                "input_schema": t.get("inputSchema") or t.get("input_schema") or {},
            }
            for t in tools
        ]
    finally:
        try:
            p.stdin.close()
        except Exception:
            pass
        try:
            p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


class McpDiscovery:
    """Boot-time + on-demand MCP server tool discovery."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: Dict[str, Any] = {"ts": 0, "servers": {}}
        self._discovery_in_progress = False
        self.reload_from_cache()

    def reload_from_cache(self) -> int:
        if not _CACHE_PATH.exists():
            return 0
        try:
            with open(_CACHE_PATH, encoding="utf-8") as f:
                self._cache = json.load(f)
            tools_count = sum(
                len((s.get("tools") or []))
                for s in (self._cache.get("servers") or {}).values()
            )
            logger.info(
                f"[mcp_discovery] loaded cache: "
                f"{len(self._cache.get('servers') or {})} servers, "
                f"{tools_count} tools"
            )
            return tools_count
        except Exception as e:
            logger.warning(f"[mcp_discovery] cache read failed: {e}")
            return 0

    def _save_cache(self) -> None:
        try:
            tmp = _CACHE_PATH.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
            os.replace(tmp, _CACHE_PATH)
        except Exception as e:
            logger.warning(f"[mcp_discovery] cache write failed: {e}")

    def discover_all(self, max_workers: int = 6) -> Dict[str, Any]:
        """Spawn all stdio MCP servers in parallel, list_tools each, cache."""
        with self._lock:
            if self._discovery_in_progress:
                return {"ok": False, "error": "discovery already running"}
            self._discovery_in_progress = True
        t0 = time.time()
        servers = _merged_server_list()
        results: Dict[str, Dict[str, Any]] = {}
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(_spawn_and_list_tools, s): s for s in servers}
                for fut in as_completed(futures, timeout=60):
                    srv = futures[fut]
                    try:
                        tools = fut.result()
                    except Exception as e:
                        tools = None
                        logger.debug(f"[mcp_discovery] {srv['name']} failed: {e}")
                    if tools is not None:
                        results[srv["name"]] = {
                            "tools": tools,
                            "transport": srv["transport_type"],
                            "source": srv.get("source", ""),
                        }
            with self._lock:
                self._cache = {
                    "ts": time.time(),
                    "servers": results,
                }
                self._save_cache()
            elapsed = time.time() - t0
            tools_count = sum(len(s["tools"]) for s in results.values())
            return {
                "ok": True,
                "elapsed_s": round(elapsed, 2),
                "servers_total": len(servers),
                "servers_responded": len(results),
                "tools_total": tools_count,
            }
        finally:
            with self._lock:
                self._discovery_in_progress = False

    def list_servers(self) -> List[str]:
        with self._lock:
            return list((self._cache.get("servers") or {}).keys())

    def list_tools(self, server: str) -> List[Dict[str, Any]]:
        with self._lock:
            srv = (self._cache.get("servers") or {}).get(server, {})
            return list(srv.get("tools") or [])

    def all_tools_flat(self) -> List[Dict[str, Any]]:
        """Returns one big list with `server` field added per tool."""
        flat: List[Dict[str, Any]] = []
        with self._lock:
            for sname, srv in (self._cache.get("servers") or {}).items():
                for t in (srv.get("tools") or []):
                    flat.append({**t, "server": sname})
        return flat

    def find_tool_for_event(
        self, event_id: str, mcp_servers: List[str],
    ) -> Optional[Dict[str, str]]:
        """Best-effort match an event to a tool from one of the agent's servers.

        Match priority:
          1. exact namespace_action match (e.g. bubble.create -> bubble_create)
          2. vibemind_<base> prefix
          3. description keyword match
        """
        if not event_id:
            return None
        base = event_id.replace(".", "_")
        ns = event_id.split(".")[0]
        short = event_id.split(".")[-1]
        for srv_name in mcp_servers:
            tools = self.list_tools(srv_name)
            for t in tools:
                tn = t.get("name", "")
                if tn == base or tn == f"vibemind_{base}":
                    return {"server": srv_name, "tool": tn,
                            "description": t.get("description", ""),
                            "input_schema": t.get("input_schema", {})}
            for t in tools:
                tn = t.get("name", "")
                if tn == f"{ns}_{short}":
                    return {"server": srv_name, "tool": tn,
                            "description": t.get("description", ""),
                            "input_schema": t.get("input_schema", {})}
            for t in tools:
                desc = (t.get("description") or "").lower()
                if event_id.lower() in desc or short.lower() in desc:
                    return {"server": srv_name, "tool": t.get("name", ""),
                            "description": t.get("description", ""),
                            "input_schema": t.get("input_schema", {})}
        return None

    def stats_dict(self) -> Dict[str, Any]:
        with self._lock:
            servers = self._cache.get("servers") or {}
            return {
                "cache_ts": self._cache.get("ts", 0),
                "servers_count": len(servers),
                "tools_total": sum(len(s.get("tools") or []) for s in servers.values()),
                "in_progress": self._discovery_in_progress,
            }


# Singleton
_INSTANCE: Optional[McpDiscovery] = None
_INSTANCE_LOCK = threading.Lock()


def get_discovery() -> McpDiscovery:
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = McpDiscovery()
        return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None
