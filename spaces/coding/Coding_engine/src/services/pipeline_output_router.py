"""Pipeline output router - routes pipeline outputs to named destinations."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineOutputRouter:
    """Routes pipeline outputs to named destinations."""

    max_entries: int = 10000
    _routes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_routes_added: int = field(default=0)
    _total_routes_removed: int = field(default=0)
    _total_outputs_routed: int = field(default=0)

    def _next_id(self, pipeline_id: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{pipeline_id}{self._seq}".encode()).hexdigest()[:12]
        return f"por-{raw}"

    def _prune(self) -> None:
        while len(self._routes) > self.max_entries:
            oldest_id = min(
                self._routes,
                key=lambda rid: self._routes[rid]["created_at"],
            )
            del self._routes[oldest_id]
            logger.debug("pipeline_output_router.pruned", route_id=oldest_id)

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "pipeline_output_router.callback_error",
                    callback=name,
                    event=event,
                )

    # -- public API ----------------------------------------------------------

    def add_route(
        self, pipeline_id: str, output_type: str, destination: str
    ) -> str:
        """Add a route from a pipeline output type to a named destination.

        Returns the route_id (prefixed with 'por-').
        """
        route_id = self._next_id(pipeline_id)
        now = time.time()
        entry: Dict[str, Any] = {
            "route_id": route_id,
            "pipeline_id": pipeline_id,
            "output_type": output_type,
            "destination": destination,
            "created_at": now,
        }
        self._routes[route_id] = entry
        self._total_routes_added += 1
        self._prune()
        logger.info(
            "pipeline_output_router.route_added",
            route_id=route_id,
            pipeline_id=pipeline_id,
            output_type=output_type,
            destination=destination,
        )
        self._fire("route_added", {"route_id": route_id, "pipeline_id": pipeline_id})
        return route_id

    def remove_route(self, route_id: str) -> bool:
        """Remove a route by its ID. Returns True if found and removed."""
        if route_id not in self._routes:
            return False
        del self._routes[route_id]
        self._total_routes_removed += 1
        logger.info("pipeline_output_router.route_removed", route_id=route_id)
        self._fire("route_removed", {"route_id": route_id})
        return True

    def route_output(
        self, pipeline_id: str, output_type: str, data: Any
    ) -> List[str]:
        """Route data to all matching destinations.

        Returns a list of destination names that received the data.
        """
        matched: List[str] = []
        for route in self._routes.values():
            if route["pipeline_id"] != pipeline_id:
                continue
            if route["output_type"] != output_type:
                continue
            matched.append(route["destination"])

        self._total_outputs_routed += 1
        if matched:
            logger.info(
                "pipeline_output_router.output_routed",
                pipeline_id=pipeline_id,
                output_type=output_type,
                destinations=matched,
            )
            self._fire(
                "output_routed",
                {
                    "pipeline_id": pipeline_id,
                    "output_type": output_type,
                    "destinations": matched,
                },
            )
        return matched

    def get_routes(
        self, pipeline_id: str, output_type: str = ""
    ) -> List[Dict[str, Any]]:
        """Get routes for a pipeline, optionally filtered by output_type."""
        results: List[Dict[str, Any]] = []
        for route in self._routes.values():
            if route["pipeline_id"] != pipeline_id:
                continue
            if output_type and route["output_type"] != output_type:
                continue
            results.append(dict(route))
        return results

    def get_route_count(self) -> int:
        """Return the total number of routes."""
        return len(self._routes)

    def list_pipelines(self) -> List[str]:
        """Return a list of unique pipeline IDs that have routes."""
        seen: set[str] = set()
        result: List[str] = []
        for route in self._routes.values():
            pid = route["pipeline_id"]
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        self._callbacks[name] = callback
        logger.debug("pipeline_output_router.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if found, False otherwise."""
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("pipeline_output_router.callback_removed", name=name)
            return True
        return False

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_routes": len(self._routes),
            "total_routes_added": self._total_routes_added,
            "total_routes_removed": self._total_routes_removed,
            "total_outputs_routed": self._total_outputs_routed,
            "max_entries": self.max_entries,
            "pipelines": len(self.list_pipelines()),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._routes.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_routes_added = 0
        self._total_routes_removed = 0
        self._total_outputs_routed = 0
        logger.info("pipeline_output_router.reset")
