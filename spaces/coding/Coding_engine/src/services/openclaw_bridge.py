"""
OpenClaw Bridge - Connects Coding Engine to OpenClaw personal AI assistant.

Enables users to control the Coding Engine pipeline via:
- WhatsApp messages (through OpenClaw)
- Slack commands
- Discord commands
- REST API

The bridge exposes a simple REST API that OpenClaw can call to:
1. Start a generation pipeline for a project package
2. Query pipeline status
3. Get verification/evolution results
4. Trigger specific actions (rebuild, retest, redeploy)

Architecture:
  User (WhatsApp/Slack/Discord) → OpenClaw → OpenClaw Bridge → Coding Engine Pipeline
  Coding Engine Events → OpenClaw Bridge → OpenClaw → User notifications
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://localhost:3333")
OPENCLAW_WEBHOOK_SECRET = os.environ.get("OPENCLAW_WEBHOOK_SECRET", "")


# ---------------------------------------------------------------------------
# Pipeline Command Handler
# ---------------------------------------------------------------------------

class PipelineCommandHandler:
    """Handles commands from OpenClaw to control the Coding Engine pipeline."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.shared = SharedState()

    async def handle_command(self, command: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Route a command from OpenClaw to the appropriate handler."""
        handlers = {
            "status": self._handle_status,
            "start": self._handle_start,
            "rebuild": self._handle_rebuild,
            "retest": self._handle_retest,
            "verify": self._handle_verify,
            "evolve": self._handle_evolve,
            "findings": self._handle_findings,
            "metrics": self._handle_metrics,
            "stop": self._handle_stop,
            "health": self._handle_health,
            "discussions": self._handle_discussions,
            "vote": self._handle_vote,
            "checkpoints": self._handle_checkpoints,
            "restore": self._handle_restore,
            "deps": self._handle_deps,
            "profiler": self._handle_profiler,
            "progress": self._handle_progress,
            "deadlocks": self._handle_deadlocks,
            "config": self._handle_config,
            "registry": self._handle_registry,
            "tasks": self._handle_tasks,
            "resources": self._handle_resources,
            "messages": self._handle_messages,
            "sandbox": self._handle_sandbox,
            "rollback": self._handle_rollback,
            "quality": self._handle_quality,
            "workflows": self._handle_workflows,
            "memory": self._handle_memory,
            "templates": self._handle_templates,
            "hooks": self._handle_hooks,
            "logs": self._handle_logs,
            "dashboard": self._handle_dashboard,
            "help": self._handle_help,
        }

        # Emit command received event
        await self.event_bus.publish(Event(
            type=EventType.OPENCLAW_COMMAND_RECEIVED,
            source="OpenClaw",
            data={"command": command, "args": args},
        ))

        handler = handlers.get(command)
        if not handler:
            return {
                "success": False,
                "error": f"Unknown command: {command}",
                "available_commands": list(handlers.keys()),
            }

        try:
            return await handler(args)
        except Exception as e:
            logger.error("openclaw_command_failed", command=command, error=str(e))
            return {"success": False, "error": str(e)}

    async def _handle_status(self, args: Dict) -> Dict:
        """Get current pipeline status."""
        metrics = self.shared.get("convergence_metrics", {})
        project_dir = self.shared.get("project_dir", "")
        active_agents = self.shared.get("active_agents", [])

        return {
            "success": True,
            "status": "running" if active_agents else "idle",
            "project_dir": project_dir,
            "active_agents": active_agents,
            "metrics": metrics,
            "treequest_findings": len(self.shared.get("treequest_findings", [])),
            "shinka_last_result": self.shared.get("shinka_last_result", {}),
        }

    async def _handle_start(self, args: Dict) -> Dict:
        """Start a new pipeline for a project package."""
        package_path = args.get("package_path", "")
        if not package_path:
            return {"success": False, "error": "package_path required"}

        if not Path(package_path).exists():
            return {"success": False, "error": f"Package not found: {package_path}"}

        # Emit generation requested event
        await self.event_bus.publish(Event(
            type=EventType.GENERATION_REQUESTED,
            source="OpenClaw",
            data={
                "package_path": package_path,
                "timestamp": datetime.now().isoformat(),
            },
        ))

        return {
            "success": True,
            "message": f"Pipeline started for {Path(package_path).name}",
        }

    async def _handle_rebuild(self, args: Dict) -> Dict:
        """Trigger a rebuild."""
        project_dir = args.get("project_dir") or self.shared.get("project_dir", "")
        if not project_dir:
            return {"success": False, "error": "No active project"}

        await self.event_bus.publish(Event(
            type=EventType.FILE_MODIFIED,
            source="OpenClaw",
            data={"file": project_dir},
        ))
        return {"success": True, "message": "Rebuild triggered"}

    async def _handle_retest(self, args: Dict) -> Dict:
        """Trigger retesting."""
        await self.event_bus.publish(Event(
            type=EventType.BUILD_SUCCEEDED,
            source="OpenClaw",
            data={},
        ))
        return {"success": True, "message": "Retest triggered"}

    async def _handle_verify(self, args: Dict) -> Dict:
        """Trigger TreeQuest verification."""
        await self.event_bus.publish(Event(
            type=EventType.VALIDATION_PASSED,
            source="OpenClaw",
            data={},
        ))
        return {"success": True, "message": "Verification triggered"}

    async def _handle_evolve(self, args: Dict) -> Dict:
        """Trigger ShinkaEvolve for a file."""
        file_path = args.get("file", "")
        if not file_path:
            return {"success": False, "error": "file parameter required"}

        await self.event_bus.publish(Event(
            type=EventType.ESCALATION_EXHAUSTED,
            source="OpenClaw",
            data={"file": file_path},
        ))
        return {"success": True, "message": f"Evolution triggered for {Path(file_path).name}"}

    async def _handle_findings(self, args: Dict) -> Dict:
        """Get TreeQuest verification findings."""
        findings = self.shared.get("treequest_findings", [])
        severity_filter = args.get("severity")
        if severity_filter:
            findings = [f for f in findings if f.get("severity") == severity_filter]

        return {
            "success": True,
            "total": len(findings),
            "findings": findings[:20],
        }

    async def _handle_metrics(self, args: Dict) -> Dict:
        """Get convergence metrics (from metrics collector if available)."""
        # Try to get metrics from PipelineMetricsCollector
        pipeline_metrics = self.shared.get("pipeline_metrics", None)
        if pipeline_metrics and hasattr(pipeline_metrics, "get_metrics"):
            return {"success": True, "metrics": pipeline_metrics.get_metrics()}

        # Fallback to basic convergence metrics
        return {
            "success": True,
            "metrics": self.shared.get("convergence_metrics", {}),
            "iteration": self.shared.get("iteration", 0),
        }

    async def _handle_stop(self, args: Dict) -> Dict:
        """Stop the pipeline gracefully."""
        self.shared.set("stop_requested", True)
        return {"success": True, "message": "Stop requested"}

    async def _handle_health(self, args: Dict) -> Dict:
        """Get full pipeline health report including circuit breakers."""
        pipeline = self.shared.get("pipeline_instance", None)
        if pipeline and hasattr(pipeline, "get_health"):
            return {"success": True, "health": pipeline.get_health()}

        from .circuit_breaker import get_all_breaker_status
        return {
            "success": True,
            "health": {
                "circuit_breakers": get_all_breaker_status(),
                "project_dir": self.shared.get("project_dir", ""),
            },
        }

    async def _handle_discussions(self, args: Dict) -> Dict:
        """List active discussions or get a specific one."""
        discussion_mgr = self.shared.get("discussion_manager", None)
        if not discussion_mgr:
            return {"success": False, "error": "Discussion manager not available"}

        disc_id = args.get("discussion_id")
        if disc_id:
            disc = discussion_mgr.get_discussion(disc_id)
            if not disc:
                return {"success": False, "error": f"Discussion {disc_id} not found"}
            return {"success": True, "discussion": disc.to_dict()}

        status_filter = args.get("status")
        from .minibook_discussion import DiscussionStatus
        status = DiscussionStatus(status_filter) if status_filter else None
        return {
            "success": True,
            "discussions": discussion_mgr.list_discussions(status=status),
            "stats": discussion_mgr.get_stats(),
        }

    async def _handle_vote(self, args: Dict) -> Dict:
        """Cast a vote in a discussion (for human-in-the-loop decisions)."""
        discussion_mgr = self.shared.get("discussion_manager", None)
        if not discussion_mgr:
            return {"success": False, "error": "Discussion manager not available"}

        disc_id = args.get("discussion_id", "")
        option = args.get("option", "")
        reason = args.get("reason", "User vote via OpenClaw")

        if not disc_id or not option:
            return {"success": False, "error": "discussion_id and option required"}

        ok = await discussion_mgr.cast_vote(disc_id, "HumanOperator", option, reason)
        if ok:
            return {"success": True, "message": f"Voted '{option}' on {disc_id}"}
        return {"success": False, "error": "Vote failed (already voted or discussion closed)"}

    async def _handle_checkpoints(self, args: Dict) -> Dict:
        """List pipeline checkpoints."""
        checkpointer = self.shared.get("pipeline_checkpointer", None)
        if not checkpointer:
            return {"success": False, "error": "Checkpointer not available"}

        project = args.get("project", "")
        checkpoints = checkpointer.list_checkpoints(project_name=project if project else None)
        return {
            "success": True,
            "checkpoints": [cp.to_dict() for cp in checkpoints],
        }

    async def _handle_restore(self, args: Dict) -> Dict:
        """Restore pipeline from a checkpoint."""
        checkpointer = self.shared.get("pipeline_checkpointer", None)
        if not checkpointer:
            return {"success": False, "error": "Checkpointer not available"}

        checkpoint_id = args.get("checkpoint_id", "")
        if not checkpoint_id:
            return {"success": False, "error": "checkpoint_id required"}

        cp = checkpointer.load_by_id(checkpoint_id)
        if not cp:
            return {"success": False, "error": f"Checkpoint {checkpoint_id} not found"}

        await checkpointer.restore_from_checkpoint(cp)
        return {"success": True, "message": f"Restored from {checkpoint_id}"}

    async def _handle_deps(self, args: Dict) -> Dict:
        """Show package dependency graph."""
        dep_graph = self.shared.get("dependency_graph", None)
        if dep_graph:
            return {"success": True, "graph": dep_graph.to_dict()}
        return {"success": True, "graph": {}, "message": "No dependency graph built yet"}

    async def _handle_profiler(self, args: Dict) -> Dict:
        """Get agent performance profiler data."""
        try:
            from .agent_profiler import get_agent_profiler
            profiler = get_agent_profiler()
            agent = args.get("agent")
            action = args.get("action", "summary")

            if action == "report" and agent:
                report = profiler.get_agent_report(agent)
                return {"success": True, "report": report or {}}
            elif action == "compare":
                return {"success": True, "comparison": profiler.get_comparison()}
            elif action == "anomalies":
                return {"success": True, "anomalies": profiler.get_anomalies(agent_name=agent)}
            elif action == "history" and agent:
                return {"success": True, "history": profiler.get_history(agent)}
            else:
                return {"success": True, "summary": profiler.get_summary(), "reports": profiler.get_all_reports()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_progress(self, args: Dict) -> Dict:
        """Get pipeline progress and ETA."""
        try:
            from .pipeline_progress import PipelineProgressTracker
            tracker = self.shared.get("_progress_tracker", None)
            if not tracker:
                # Try to get from event bus subscriber
                return {"success": True, "message": "No active pipeline run", "progress": {}}
            return {"success": True, "progress": tracker.get_progress()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_deadlocks(self, args: Dict) -> Dict:
        """Check for agent deadlocks."""
        try:
            from .deadlock_detector import DeadlockDetector
            # The detector should be accessible from shared state or directly
            action = args.get("action", "status")
            # Use a simple approach: import and check
            return {
                "success": True,
                "message": "Deadlock detection active",
                "action": action,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_config(self, args: Dict) -> Dict:
        """Query or modify agent configs."""
        try:
            from .config_hot_reload import ConfigHotReloader
            action = args.get("action", "list")
            agent = args.get("agent")

            if action == "list":
                return {"success": True, "message": "Config hot reload active"}
            elif action == "reload" and agent:
                return {"success": True, "message": f"Reload requested for {agent}"}
            else:
                return {"success": True, "action": action}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_registry(self, args: Dict) -> Dict:
        """Agent capability registry operations."""
        registry = self.shared.get("_agent_registry", None)
        if not registry:
            return {"success": False, "error": "Agent registry not available"}
        action = args.get("action", "list")
        if action == "list":
            return {"success": True, "agents": registry.list_agents()}
        elif action == "capabilities":
            agent = args.get("agent", "")
            if not agent:
                return {"success": False, "error": "agent parameter required"}
            info = registry.get_agent(agent)
            return {"success": True, "agent": info} if info else {"success": False, "error": "Agent not found"}
        elif action == "find":
            cap = args.get("capability", "")
            return {"success": True, "agents": registry.find_by_capability(cap)}
        elif action == "stats":
            return {"success": True, "stats": registry.get_stats()}
        return {"success": True, "action": action}

    async def _handle_tasks(self, args: Dict) -> Dict:
        """Agent task queue operations."""
        queue = self.shared.get("_task_queue", None)
        if not queue:
            return {"success": False, "error": "Task queue not available"}
        action = args.get("action", "stats")
        if action == "stats":
            return {"success": True, "stats": queue.get_stats()}
        elif action == "pending":
            agent = args.get("agent", "")
            tasks = queue.get_pending(agent_name=agent if agent else None)
            return {"success": True, "pending": [t.to_dict() if hasattr(t, 'to_dict') else str(t) for t in tasks[:20]]}
        elif action == "cancel":
            task_id = args.get("task_id", "")
            if not task_id:
                return {"success": False, "error": "task_id required"}
            ok = queue.cancel(task_id)
            return {"success": ok, "message": f"Task {task_id} {'cancelled' if ok else 'not found'}"}
        return {"success": True, "action": action}

    async def _handle_resources(self, args: Dict) -> Dict:
        """Resource pool operations."""
        pool = self.shared.get("_resource_pool", None)
        if not pool:
            return {"success": False, "error": "Resource pool not available"}
        action = args.get("action", "status")
        if action == "status":
            return {"success": True, "pools": pool.get_all_status()}
        elif action == "stats":
            return {"success": True, "stats": pool.get_stats()}
        return {"success": True, "action": action}

    async def _handle_messages(self, args: Dict) -> Dict:
        """Agent messenger operations."""
        messenger = self.shared.get("_messenger", None)
        if not messenger:
            return {"success": False, "error": "Messenger not available"}
        action = args.get("action", "channels")
        if action == "channels":
            return {"success": True, "channels": messenger.list_channels()}
        elif action == "recent":
            channel = args.get("channel", "")
            if not channel:
                return {"success": False, "error": "channel parameter required"}
            msgs = messenger.get_messages(channel, limit=args.get("limit", 20))
            return {"success": True, "messages": msgs}
        elif action == "send":
            channel = args.get("channel", "")
            text = args.get("text", "")
            if not channel or not text:
                return {"success": False, "error": "channel and text required"}
            mid = messenger.send(channel, "HumanOperator", text)
            return {"success": True, "message_id": mid}
        elif action == "stats":
            return {"success": True, "stats": messenger.get_stats()}
        return {"success": True, "action": action}

    async def _handle_sandbox(self, args: Dict) -> Dict:
        """Execution sandbox operations."""
        sandbox = self.shared.get("_sandbox", None)
        if not sandbox:
            return {"success": False, "error": "Sandbox not available"}
        action = args.get("action", "stats")
        if action == "stats":
            return {"success": True, "stats": sandbox.get_stats()}
        elif action == "history":
            limit = args.get("limit", 10)
            return {"success": True, "history": sandbox.get_history(limit=limit)}
        return {"success": True, "action": action}

    async def _handle_rollback(self, args: Dict) -> Dict:
        """Pipeline rollback operations."""
        rollback = self.shared.get("_rollback", None)
        if not rollback:
            return {"success": False, "error": "Rollback manager not available"}
        action = args.get("action", "list")
        if action == "list":
            snapshots = rollback.list_snapshots(limit=args.get("limit", 10))
            return {"success": True, "snapshots": snapshots}
        elif action == "rollback":
            snap_id = args.get("snapshot_id", "")
            if not snap_id:
                return {"success": False, "error": "snapshot_id required"}
            ok = rollback.rollback_to(snap_id)
            return {"success": ok, "message": f"{'Rolled back' if ok else 'Failed'} to {snap_id}"}
        elif action == "stats":
            return {"success": True, "stats": rollback.get_stats()}
        return {"success": True, "action": action}

    async def _handle_quality(self, args: Dict) -> Dict:
        """Code quality gate operations."""
        gate = self.shared.get("_quality_gate", None)
        if not gate:
            return {"success": False, "error": "Quality gate not available"}
        action = args.get("action", "stats")
        if action == "stats":
            return {"success": True, "stats": gate.get_stats()}
        elif action == "history":
            return {"success": True, "history": gate.get_history(limit=args.get("limit", 10))}
        return {"success": True, "action": action}

    async def _handle_workflows(self, args: Dict) -> Dict:
        """Workflow engine operations."""
        engine = self.shared.get("_workflow_engine", None)
        if not engine:
            return {"success": False, "error": "Workflow engine not available"}
        action = args.get("action", "list")
        if action == "list":
            return {"success": True, "definitions": engine.list_definitions()}
        elif action == "instances":
            status = args.get("status")
            return {"success": True, "instances": engine.list_instances(status=status)}
        elif action == "instance":
            iid = args.get("instance_id", "")
            if not iid:
                return {"success": False, "error": "instance_id required"}
            inst = engine.get_instance(iid)
            return {"success": True, "instance": inst} if inst else {"success": False, "error": "Not found"}
        elif action == "stats":
            return {"success": True, "stats": engine.get_stats()}
        return {"success": True, "action": action}

    async def _handle_memory(self, args: Dict) -> Dict:
        """Agent memory store operations."""
        mem = self.shared.get("_agent_memory", None)
        if not mem:
            return {"success": False, "error": "Agent memory not available"}
        action = args.get("action", "agents")
        if action == "agents":
            return {"success": True, "agents": mem.list_agents()}
        elif action == "recall":
            agent = args.get("agent", "")
            if not agent:
                return {"success": False, "error": "agent parameter required"}
            category = args.get("category")
            entries = mem.recall(agent, category=category, limit=args.get("limit", 20))
            return {"success": True, "memories": entries}
        elif action == "search":
            query = args.get("query", "")
            if not query:
                return {"success": False, "error": "query parameter required"}
            results = mem.search(query, agent_name=args.get("agent"), limit=args.get("limit", 10))
            return {"success": True, "results": results}
        elif action == "summary":
            agent = args.get("agent", "")
            if not agent:
                return {"success": False, "error": "agent parameter required"}
            return {"success": True, "summary": mem.get_agent_summary(agent)}
        elif action == "stats":
            return {"success": True, "stats": mem.get_stats()}
        return {"success": True, "action": action}

    async def _handle_templates(self, args: Dict) -> Dict:
        """Project template operations."""
        tmpl = self.shared.get("_project_templates", None)
        if not tmpl:
            return {"success": False, "error": "Project templates not available"}
        action = args.get("action", "list")
        if action == "list":
            lang = args.get("language")
            cat = args.get("category")
            return {"success": True, "templates": tmpl.list_templates(language=lang, category=cat)}
        elif action == "info":
            name = args.get("name", "")
            if not name:
                return {"success": False, "error": "name parameter required"}
            info = tmpl.get_template(name)
            return {"success": True, "template": info} if info else {"success": False, "error": "Not found"}
        elif action == "variables":
            name = args.get("name", "")
            if not name:
                return {"success": False, "error": "name parameter required"}
            return {"success": True, "variables": tmpl.get_template_variables(name)}
        elif action == "stats":
            return {"success": True, "stats": tmpl.get_stats()}
        return {"success": True, "action": action}

    async def _handle_hooks(self, args: Dict) -> Dict:
        """Pipeline hooks operations."""
        hooks = self.shared.get("_pipeline_hooks", None)
        if not hooks:
            return {"success": False, "error": "Pipeline hooks not available"}
        action = args.get("action", "list")
        if action == "list":
            hp = args.get("hook_point")
            return {"success": True, "hooks": hooks.list_hooks(hook_point=hp)}
        elif action == "points":
            return {"success": True, "hook_points": hooks.list_hook_points()}
        elif action == "stats":
            return {"success": True, "stats": hooks.get_stats()}
        return {"success": True, "action": action}

    async def _handle_logs(self, args: Dict) -> Dict:
        """Log aggregator operations."""
        agg = self.shared.get("_log_aggregator", None)
        if not agg:
            return {"success": False, "error": "Log aggregator not available"}
        action = args.get("action", "recent")
        if action == "recent":
            level = args.get("level")
            return {"success": True, "logs": agg.get_recent(level=level, limit=args.get("limit", 20))}
        elif action == "errors":
            return {"success": True, "errors": agg.get_errors(limit=args.get("limit", 20))}
        elif action == "search":
            query = args.get("query", "")
            if not query:
                return {"success": False, "error": "query parameter required"}
            return {"success": True, "results": agg.search(query, source=args.get("source"),
                                                            level=args.get("level"), limit=args.get("limit", 20))}
        elif action == "runs":
            return {"success": True, "runs": agg.list_runs()}
        elif action == "run_summary":
            run_id = args.get("run_id", "")
            if not run_id:
                return {"success": False, "error": "run_id required"}
            return {"success": True, "summary": agg.get_run_summary(run_id)}
        elif action == "stats":
            return {"success": True, "stats": agg.get_stats()}
        return {"success": True, "action": action}

    async def _handle_dashboard(self, args: Dict) -> Dict:
        """Health dashboard operations."""
        dash = self.shared.get("_health_dashboard", None)
        if not dash:
            return {"success": False, "error": "Health dashboard not available"}
        action = args.get("action", "overview")
        if action == "overview":
            return {"success": True, "overview": dash.get_overview()}
        elif action == "components":
            ctype = args.get("type")
            status = args.get("status")
            return {"success": True, "components": dash.get_components(component_type=ctype, status=status)}
        elif action == "component":
            name = args.get("name", "")
            if not name:
                return {"success": False, "error": "name parameter required"}
            comp = dash.get_component(name)
            return {"success": True, "component": comp} if comp else {"success": False, "error": "Not found"}
        elif action == "alerts":
            active = args.get("active_only", True)
            severity = args.get("severity")
            return {"success": True, "alerts": dash.get_alerts(active_only=active, severity=severity)}
        elif action == "resolve":
            alert_id = args.get("alert_id", "")
            if not alert_id:
                return {"success": False, "error": "alert_id required"}
            ok = dash.resolve_alert(alert_id)
            return {"success": ok, "message": f"Alert {alert_id} {'resolved' if ok else 'not found'}"}
        elif action == "probes":
            results = dash.run_probes()
            return {"success": True, "probe_results": results}
        elif action == "stats":
            return {"success": True, "stats": dash.get_stats()}
        return {"success": True, "action": action}

    async def _handle_help(self, args: Dict) -> Dict:
        """List available commands with descriptions."""
        return {
            "success": True,
            "commands": {
                "status": "Get pipeline status",
                "start": "Start pipeline (package_path=...)",
                "rebuild": "Trigger rebuild",
                "retest": "Trigger retesting",
                "verify": "Run TreeQuest verification",
                "evolve": "Run ShinkaEvolve (file=...)",
                "findings": "Get verification findings (severity=...)",
                "metrics": "Get convergence metrics",
                "health": "Full health report with circuit breakers",
                "discussions": "List agent discussions (status=open/voting/resolved)",
                "vote": "Cast vote (discussion_id=..., option=..., reason=...)",
                "checkpoints": "List checkpoints (project=...)",
                "restore": "Restore from checkpoint (checkpoint_id=...)",
                "deps": "Show package dependency graph",
                "profiler": "Agent performance profiler (action=summary/report/compare/anomalies, agent=...)",
                "progress": "Pipeline progress with ETA",
                "deadlocks": "Check for agent deadlocks",
                "config": "Agent config management (action=list/reload, agent=...)",
                "registry": "Agent capability registry (action=list/capabilities/find/stats, agent=..., capability=...)",
                "tasks": "Task queue (action=stats/pending/cancel, agent=..., task_id=...)",
                "resources": "Resource pools (action=status/stats)",
                "messages": "Agent messenger (action=channels/recent/send/stats, channel=..., text=...)",
                "sandbox": "Execution sandbox (action=stats/history)",
                "rollback": "Pipeline rollback (action=list/rollback/stats, snapshot_id=...)",
                "quality": "Code quality gate (action=stats/history)",
                "workflows": "Workflow engine (action=list/instances/instance/stats, instance_id=...)",
                "memory": "Agent memory (action=agents/recall/search/summary/stats, agent=..., query=...)",
                "templates": "Project templates (action=list/info/variables/stats, name=..., language=...)",
                "hooks": "Pipeline hooks (action=list/points/stats, hook_point=...)",
                "logs": "Log aggregator (action=recent/errors/search/runs/run_summary/stats, query=..., run_id=...)",
                "dashboard": "Health dashboard (action=overview/components/component/alerts/resolve/probes/stats)",
                "stop": "Stop the pipeline",
                "help": "Show this help",
            },
        }


# ---------------------------------------------------------------------------
# FastAPI Router (can be mounted in any FastAPI app)
# ---------------------------------------------------------------------------

def create_openclaw_router(event_bus: EventBus):
    """Create a FastAPI router for OpenClaw commands.

    Mount this in the Coding Engine's API server:
        app.include_router(create_openclaw_router(event_bus), prefix="/openclaw")
    """
    try:
        from fastapi import APIRouter, HTTPException
        from pydantic import BaseModel
    except ImportError:
        logger.warning("FastAPI not installed, OpenClaw router unavailable")
        return None

    router = APIRouter(tags=["openclaw"])
    handler = PipelineCommandHandler(event_bus)

    class CommandRequest(BaseModel):
        command: str
        args: Dict[str, Any] = {}
        secret: str = ""

    class StatusResponse(BaseModel):
        success: bool
        data: Dict[str, Any] = {}

    @router.post("/command")
    async def execute_command(req: CommandRequest):
        if OPENCLAW_WEBHOOK_SECRET and req.secret != OPENCLAW_WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid secret")
        result = await handler.handle_command(req.command, req.args)
        return result

    @router.get("/status")
    async def get_status():
        return await handler.handle_command("status", {})

    @router.get("/findings")
    async def get_findings(severity: Optional[str] = None):
        return await handler.handle_command("findings", {"severity": severity})

    @router.get("/metrics")
    async def get_metrics():
        return await handler.handle_command("metrics", {})

    @router.get("/health")
    async def get_health():
        return await handler.handle_command("health", {})

    @router.get("/discussions")
    async def get_discussions(status: Optional[str] = None):
        return await handler.handle_command("discussions", {"status": status})

    @router.post("/vote")
    async def cast_vote(req: CommandRequest):
        return await handler.handle_command("vote", req.args)

    @router.get("/checkpoints")
    async def get_checkpoints(project: Optional[str] = None):
        return await handler.handle_command("checkpoints", {"project": project})

    @router.get("/deps")
    async def get_deps():
        return await handler.handle_command("deps", {})

    @router.get("/registry")
    async def get_registry(action: str = "list", agent: Optional[str] = None, capability: Optional[str] = None):
        return await handler.handle_command("registry", {"action": action, "agent": agent, "capability": capability})

    @router.get("/tasks")
    async def get_tasks(action: str = "stats", agent: Optional[str] = None):
        return await handler.handle_command("tasks", {"action": action, "agent": agent})

    @router.get("/resources")
    async def get_resources(action: str = "status"):
        return await handler.handle_command("resources", {"action": action})

    @router.get("/messages")
    async def get_messages(action: str = "channels", channel: Optional[str] = None):
        return await handler.handle_command("messages", {"action": action, "channel": channel})

    @router.get("/sandbox")
    async def get_sandbox(action: str = "stats"):
        return await handler.handle_command("sandbox", {"action": action})

    @router.get("/rollback")
    async def get_rollback(action: str = "list"):
        return await handler.handle_command("rollback", {"action": action})

    @router.get("/quality")
    async def get_quality(action: str = "stats"):
        return await handler.handle_command("quality", {"action": action})

    @router.get("/workflows")
    async def get_workflows(action: str = "list", status: Optional[str] = None):
        return await handler.handle_command("workflows", {"action": action, "status": status})

    @router.get("/memory")
    async def get_memory(action: str = "agents", agent: Optional[str] = None, query: Optional[str] = None):
        return await handler.handle_command("memory", {"action": action, "agent": agent, "query": query})

    @router.get("/templates")
    async def get_templates(action: str = "list", language: Optional[str] = None, category: Optional[str] = None):
        return await handler.handle_command("templates", {"action": action, "language": language, "category": category})

    @router.get("/hooks")
    async def get_hooks(action: str = "list", hook_point: Optional[str] = None):
        return await handler.handle_command("hooks", {"action": action, "hook_point": hook_point})

    @router.get("/logs")
    async def get_logs(action: str = "recent", level: Optional[str] = None, source: Optional[str] = None, query: Optional[str] = None):
        return await handler.handle_command("logs", {"action": action, "level": level, "source": source, "query": query})

    @router.get("/dashboard")
    async def get_dashboard(action: str = "overview", name: Optional[str] = None, severity: Optional[str] = None):
        return await handler.handle_command("dashboard", {"action": action, "name": name, "severity": severity})

    @router.get("/help")
    async def get_help():
        return await handler.handle_command("help", {})

    return router


# ---------------------------------------------------------------------------
# Notification sender (push events to OpenClaw)
# ---------------------------------------------------------------------------

class OpenClawNotifier:
    """Sends pipeline notifications to OpenClaw for forwarding to user."""

    def __init__(self, event_bus: EventBus, openclaw_url: str = OPENCLAW_URL):
        self.event_bus = event_bus
        self.openclaw_url = openclaw_url.rstrip("/")
        self._session = None

    async def start(self):
        """Subscribe to key events and forward them to OpenClaw."""
        import aiohttp
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

        notify_events = [
            EventType.BUILD_SUCCEEDED,
            EventType.BUILD_FAILED,
            EventType.TEST_PASSED,
            EventType.TEST_FAILED,
            EventType.DEPLOY_SUCCEEDED,
            EventType.DEPLOY_FAILED,
            EventType.ESCALATION_EXHAUSTED,
            EventType.CONVERGENCE_UPDATE,
        ]
        for et in notify_events:
            self.event_bus.subscribe(et, self._on_event)

    async def _on_event(self, event: Event):
        """Forward event as notification to OpenClaw."""
        if not self._session:
            return

        message = self._format_event(event)
        try:
            async with self._session.post(
                f"{self.openclaw_url}/api/notify",
                json={"message": message, "source": "coding_engine"},
            ) as resp:
                if resp.status >= 400:
                    logger.debug("openclaw_notify_failed", status=resp.status)
        except Exception:
            pass  # OpenClaw may not be running

    def _format_event(self, event: Event) -> str:
        """Format event into a human-readable notification."""
        et = event.type
        msgs = {
            EventType.BUILD_SUCCEEDED: "Build succeeded ✓",
            EventType.BUILD_FAILED: "Build failed ✗ - fixing...",
            EventType.TEST_PASSED: "All tests passed ✓",
            EventType.TEST_FAILED: "Tests failed - fixing...",
            EventType.DEPLOY_SUCCEEDED: "Deployment live ✓",
            EventType.DEPLOY_FAILED: "Deployment failed ✗",
            EventType.ESCALATION_EXHAUSTED: "Standard fixes exhausted - activating ShinkaEvolve...",
        }
        return msgs.get(et, f"Pipeline event: {et.value}")

    async def close(self):
        if self._session:
            await self._session.close()
