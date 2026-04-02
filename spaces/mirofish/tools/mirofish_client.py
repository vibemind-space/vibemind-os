"""
MiroFish Client - Wrapper around MiroFish-Offline Flask API

Provides VibeMind-compatible interface to communicate with
MiroFish's HTTP API running in Docker.

MiroFish-Offline API endpoints:
  POST /api/graph/ontology/generate  - Upload seed files + generate ontology
  POST /api/graph/build              - Build knowledge graph from project
  GET  /api/graph/task/<task_id>     - Poll build progress
  GET  /api/graph/data/<graph_id>    - Full graph dump
  GET  /api/graph/project/<id>       - Project details
  GET  /api/graph/project/list       - List all projects
  POST /api/simulation/configure     - Configure simulation
  POST /api/simulation/start         - Start simulation
  GET  /api/simulation/status/<id>   - Poll simulation status
  POST /api/simulation/interview     - Interview a simulated agent
  POST /api/report/generate          - Generate prediction report
  GET  /api/report/<id>              - Get report
  GET  /api/report/<id>/download     - Download report as markdown
  POST /api/report/chat              - Chat with report agent
  POST /api/report/tools/search      - Search graph directly
  GET  /health                       - Health check
"""

import logging
import os
import time
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class MiroFishClient:
    """
    Client for communicating with MiroFish-Offline API.

    Wraps the Flask REST API for graph building, simulation,
    and report generation.
    """

    def __init__(self, url: str = None):
        self._url = url or os.getenv("MIROFISH_URL", "http://localhost:5001")

    # -------------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Check MiroFish connection status."""
        try:
            resp = requests.get(f"{self._url}/health", timeout=5)
            if resp.status_code == 200:
                return {
                    "success": True,
                    "status": "connected",
                    "url": self._url,
                    "message": "MiroFish ist verbunden und bereit.",
                }
            return {
                "success": False,
                "status": "error",
                "url": self._url,
                "message": f"MiroFish antwortet mit Status {resp.status_code}",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "status": "disconnected",
                "url": self._url,
                "message": "MiroFish nicht erreichbar. Docker-Container gestartet?",
            }
        except Exception as e:
            return {
                "success": False,
                "status": "disconnected",
                "url": self._url,
                "message": f"MiroFish nicht erreichbar: {e}",
            }

    # -------------------------------------------------------------------------
    # Graph / Ontology
    # -------------------------------------------------------------------------

    def generate_ontology(
        self,
        requirement: str,
        file_paths: List[str] = None,
        text_content: str = None,
        project_name: str = None,
    ) -> Dict[str, Any]:
        """
        Upload seed data and generate ontology.

        Args:
            requirement: Simulation requirement description
            file_paths: List of file paths (PDF, MD, TXT) to upload
            text_content: Raw text content as seed (alternative to files)
            project_name: Optional project name

        Returns:
            Dict with project_id and ontology
        """
        try:
            files = []
            if file_paths:
                for path in file_paths:
                    if os.path.exists(path):
                        files.append(
                            ("files", (os.path.basename(path), open(path, "rb")))
                        )
                    else:
                        logger.warning(f"MiroFishClient: File not found: {path}")

            # If no files but text content, create a temp file
            if not files and text_content:
                import tempfile
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                )
                tmp.write(text_content)
                tmp.close()
                files.append(("files", ("seed_data.txt", open(tmp.name, "rb"))))

            if not files:
                return {
                    "success": False,
                    "error": "No seed data provided",
                    "message": "Keine Seed-Daten angegeben.",
                }

            data = {"simulation_requirement": requirement}
            if project_name:
                data["project_name"] = project_name

            resp = requests.post(
                f"{self._url}/api/graph/ontology/generate",
                files=files,
                data=data,
                timeout=600,  # LLM ontology generation can take 5+ minutes
            )

            # Close file handles
            for _, file_tuple in files:
                file_tuple[1].close()

            if resp.status_code == 200:
                result = resp.json()
                # API returns {data: {project_id, ontology, ...}, success: true}
                data = result.get("data", result)
                project_id = data.get("project_id") or result.get("project_id")
                ontology = data.get("ontology") or result.get("ontology")
                return {
                    "success": True,
                    "project_id": project_id,
                    "ontology": ontology,
                    "message": f"Ontologie erstellt. Projekt: {project_id}",
                }
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {resp.text}",
                "message": f"Ontologie-Erstellung fehlgeschlagen: HTTP {resp.status_code}",
            }

        except Exception as e:
            logger.error(f"MiroFishClient: ontology error: {e}")
            return {"success": False, "error": str(e), "message": f"Fehler: {e}"}

    def build_graph(self, project_id: str) -> Dict[str, Any]:
        """
        Build knowledge graph from a project.

        Args:
            project_id: Project ID from generate_ontology

        Returns:
            Dict with task_id for polling
        """
        try:
            resp = requests.post(
                f"{self._url}/api/graph/build",
                json={"project_id": project_id},
                timeout=30,
            )
            if resp.status_code == 200:
                result = resp.json()
                data = result.get("data", result)
                task_id = data.get("task_id") or result.get("task_id")
                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "Graph-Aufbau gestartet.",
                }
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                "message": f"Graph-Aufbau fehlgeschlagen: HTTP {resp.status_code}",
            }
        except Exception as e:
            logger.error(f"MiroFishClient: build_graph error: {e}")
            return {"success": False, "error": str(e), "message": f"Fehler: {e}"}

    def poll_build(self, task_id: str) -> Dict[str, Any]:
        """Poll graph build progress (0-100%)."""
        try:
            resp = requests.get(
                f"{self._url}/api/graph/task/{task_id}", timeout=10
            )
            if resp.status_code == 200:
                result = resp.json()
                return {
                    "success": True,
                    "progress": result.get("progress", 0),
                    "status": result.get("status", "unknown"),
                    "graph_id": result.get("graph_id"),
                }
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Get full graph dump (nodes + edges)."""
        try:
            resp = requests.get(
                f"{self._url}/api/graph/data/{graph_id}", timeout=30
            )
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_projects(self) -> Dict[str, Any]:
        """List all MiroFish projects."""
        try:
            resp = requests.get(
                f"{self._url}/api/graph/project/list", timeout=10
            )
            if resp.status_code == 200:
                return {"success": True, "projects": resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_graph(self, graph_id: str, query: str) -> Dict[str, Any]:
        """Search the knowledge graph directly."""
        try:
            resp = requests.post(
                f"{self._url}/api/report/tools/search",
                json={"graph_id": graph_id, "query": query},
                timeout=30,
            )
            if resp.status_code == 200:
                return {"success": True, "results": resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Simulation
    # -------------------------------------------------------------------------

    def configure_simulation(
        self,
        graph_id: str,
        agent_count: int = 100,
        rounds: int = 10,
        platform: str = "twitter",
    ) -> Dict[str, Any]:
        """
        Configure a simulation.

        Args:
            graph_id: Knowledge graph to simulate from
            agent_count: Number of simulated agents
            rounds: Simulation rounds
            platform: Simulation platform (twitter, reddit)
        """
        try:
            resp = requests.post(
                f"{self._url}/api/simulation/configure",
                json={
                    "graph_id": graph_id,
                    "agent_count": agent_count,
                    "rounds": rounds,
                    "platform": platform,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                result = resp.json()
                return {
                    "success": True,
                    "simulation_id": result.get("simulation_id"),
                    "message": f"Simulation konfiguriert: {agent_count} Agenten, {rounds} Runden.",
                }
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def start_simulation(self, simulation_id: str) -> Dict[str, Any]:
        """Start a configured simulation."""
        try:
            resp = requests.post(
                f"{self._url}/api/simulation/start",
                json={"simulation_id": simulation_id},
                timeout=30,
            )
            if resp.status_code == 200:
                return {
                    "success": True,
                    "message": "Simulation gestartet.",
                    "simulation_id": simulation_id,
                }
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def poll_simulation(self, simulation_id: str) -> Dict[str, Any]:
        """Poll simulation status."""
        try:
            resp = requests.get(
                f"{self._url}/api/simulation/status/{simulation_id}",
                timeout=10,
            )
            if resp.status_code == 200:
                return {"success": True, **resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def interview_agent(
        self, simulation_id: str, agent_name: str, question: str
    ) -> Dict[str, Any]:
        """Interview a simulated agent."""
        try:
            resp = requests.post(
                f"{self._url}/api/simulation/interview",
                json={
                    "simulation_id": simulation_id,
                    "agent_name": agent_name,
                    "question": question,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                return {"success": True, **resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Reports
    # -------------------------------------------------------------------------

    def generate_report(self, simulation_id: str) -> Dict[str, Any]:
        """Generate prediction report from simulation."""
        try:
            resp = requests.post(
                f"{self._url}/api/report/generate",
                json={"simulation_id": simulation_id},
                timeout=30,
            )
            if resp.status_code == 200:
                result = resp.json()
                return {
                    "success": True,
                    "task_id": result.get("task_id"),
                    "message": "Report-Generierung gestartet.",
                }
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_report(self, report_id: str) -> Dict[str, Any]:
        """Get a completed report."""
        try:
            resp = requests.get(
                f"{self._url}/api/report/{report_id}", timeout=30
            )
            if resp.status_code == 200:
                return {"success": True, "report": resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def chat_report(self, report_id: str, question: str) -> Dict[str, Any]:
        """Chat with the report agent about findings."""
        try:
            resp = requests.post(
                f"{self._url}/api/report/chat",
                json={"report_id": report_id, "question": question},
                timeout=60,
            )
            if resp.status_code == 200:
                return {"success": True, **resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Graph-Only Pipeline (no simulation)
    # -------------------------------------------------------------------------

    def build_graph_from_text(
        self,
        requirement: str,
        text_content: str,
        project_name: str = None,
        poll_interval: int = 5,
    ) -> Dict[str, Any]:
        """
        Build a knowledge graph from raw text (no simulation, no report).

        Steps:
        1. generate_ontology(requirement, text_content)
        2. build_graph(project_id)
        3. Poll until complete
        4. Return graph_id + summary

        Args:
            requirement: Description of what the graph represents
            text_content: Raw text content to build graph from
            project_name: Optional project name
            poll_interval: Seconds between polls

        Returns:
            Dict with project_id, graph_id, summary
        """
        # Step 1: Generate ontology
        ontology_result = self.generate_ontology(
            requirement=requirement,
            text_content=text_content,
            project_name=project_name,
        )
        if not ontology_result.get("success"):
            return ontology_result

        project_id = ontology_result["project_id"]
        if not project_id:
            return {
                "success": False,
                "message": "Ontologie erstellt, aber keine project_id erhalten.",
            }

        # Step 2: Build graph
        build_result = self.build_graph(project_id)
        if not build_result.get("success"):
            return build_result

        task_id = build_result.get("task_id")
        if not task_id:
            return {
                "success": False,
                "message": "Graph-Build gestartet, aber keine task_id erhalten.",
            }

        # Step 3: Poll build progress
        from spaces.mirofish.config import get_config
        config = get_config()
        deadline = time.time() + config.build_timeout

        graph_id = None
        while time.time() < deadline:
            poll = self.poll_build(task_id)
            if poll.get("status") == "completed":
                graph_id = poll.get("graph_id")
                break
            if poll.get("status") == "failed":
                return {"success": False, "message": "Graph-Aufbau fehlgeschlagen."}
            time.sleep(poll_interval)

        if not graph_id:
            return {"success": False, "message": "Graph-Aufbau Timeout."}

        # Step 4: Get summary
        summary = self.get_graph_summary(graph_id)

        return {
            "success": True,
            "project_id": project_id,
            "graph_id": graph_id,
            "summary": summary,
            "message": f"Knowledge Graph erstellt: {graph_id}",
        }

    def get_graph_summary(self, graph_id: str) -> str:
        """
        Get a compact text summary of a graph (entities, relations, counts).

        Args:
            graph_id: Graph to summarize

        Returns:
            Human-readable summary string
        """
        try:
            result = self.get_graph_data(graph_id)
            if not result.get("success"):
                return ""

            data = result.get("data", {})
            nodes = data.get("nodes", [])
            edges = data.get("edges", [])

            # Extract entity names and types
            entity_names = []
            entity_types = set()
            for node in nodes[:50]:  # limit
                name = node.get("name") or node.get("label", "")
                ntype = node.get("type") or node.get("entity_type", "")
                if name:
                    entity_names.append(f"{name} ({ntype})" if ntype else name)
                if ntype:
                    entity_types.add(ntype)

            # Extract relation types
            relation_types = set()
            for edge in edges[:50]:
                rtype = edge.get("type") or edge.get("relation_type", "")
                if rtype:
                    relation_types.add(rtype)

            parts = [
                f"Graph {graph_id}: {len(nodes)} Entities, {len(edges)} Relations",
            ]
            if entity_types:
                parts.append(f"Entity-Typen: {', '.join(sorted(entity_types))}")
            if relation_types:
                parts.append(f"Relation-Typen: {', '.join(sorted(relation_types))}")
            if entity_names:
                parts.append(f"Entities: {', '.join(entity_names[:20])}")

            return "\n".join(parts)

        except Exception as e:
            logger.warning(f"MiroFishClient: graph summary error: {e}")
            return ""

    # -------------------------------------------------------------------------
    # End-to-End Pipeline
    # -------------------------------------------------------------------------

    def run_prediction(
        self,
        requirement: str,
        text_content: str = None,
        file_paths: List[str] = None,
        agent_count: int = 100,
        rounds: int = 10,
        poll_interval: int = 5,
    ) -> Dict[str, Any]:
        """
        Run full prediction pipeline: ontology → graph → simulation → report.

        This is a blocking, long-running operation. For async usage,
        call each step individually and poll.

        Args:
            requirement: What to predict/simulate
            text_content: Seed text content
            file_paths: Seed file paths
            agent_count: Number of simulated agents
            rounds: Simulation rounds
            poll_interval: Seconds between polls

        Returns:
            Dict with report content
        """
        # Step 1: Generate ontology
        ontology_result = self.generate_ontology(
            requirement=requirement,
            text_content=text_content,
            file_paths=file_paths,
        )
        if not ontology_result.get("success"):
            return ontology_result

        project_id = ontology_result["project_id"]

        # Step 2: Build graph
        build_result = self.build_graph(project_id)
        if not build_result.get("success"):
            return build_result

        task_id = build_result["task_id"]

        # Poll build progress
        from spaces.mirofish.config import get_config
        config = get_config()
        deadline = time.time() + config.build_timeout

        graph_id = None
        while time.time() < deadline:
            poll = self.poll_build(task_id)
            if poll.get("status") == "completed":
                graph_id = poll.get("graph_id")
                break
            if poll.get("status") == "failed":
                return {"success": False, "message": "Graph-Aufbau fehlgeschlagen."}
            time.sleep(poll_interval)

        if not graph_id:
            return {"success": False, "message": "Graph-Aufbau Timeout."}

        # Step 3: Configure + start simulation
        sim_result = self.configure_simulation(
            graph_id=graph_id,
            agent_count=agent_count,
            rounds=rounds,
        )
        if not sim_result.get("success"):
            return sim_result

        simulation_id = sim_result["simulation_id"]
        start_result = self.start_simulation(simulation_id)
        if not start_result.get("success"):
            return start_result

        # Poll simulation
        deadline = time.time() + config.simulation_timeout
        while time.time() < deadline:
            poll = self.poll_simulation(simulation_id)
            if poll.get("status") == "completed":
                break
            if poll.get("status") == "failed":
                return {"success": False, "message": "Simulation fehlgeschlagen."}
            time.sleep(poll_interval)
        else:
            return {"success": False, "message": "Simulation Timeout."}

        # Step 4: Generate report
        report_result = self.generate_report(simulation_id)
        if not report_result.get("success"):
            return report_result

        report_task_id = report_result["task_id"]

        # Poll report - reuse task polling pattern
        deadline = time.time() + config.report_timeout
        while time.time() < deadline:
            try:
                resp = requests.post(
                    f"{self._url}/api/report/generate/status",
                    json={"task_id": report_task_id},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "completed":
                        report_id = data.get("report_id")
                        report = self.get_report(report_id)
                        return {
                            "success": True,
                            "report_id": report_id,
                            "report": report.get("report", {}),
                            "graph_id": graph_id,
                            "simulation_id": simulation_id,
                            "message": "Vorhersage-Report fertig.",
                        }
                    if data.get("status") == "failed":
                        return {"success": False, "message": "Report-Generierung fehlgeschlagen."}
            except Exception:
                pass
            time.sleep(poll_interval)

        return {"success": False, "message": "Report-Generierung Timeout."}


# Singleton
_client: Optional[MiroFishClient] = None


def get_mirofish_client() -> MiroFishClient:
    """Get or create MiroFishClient singleton."""
    global _client
    if _client is None:
        _client = MiroFishClient()
    return _client


__all__ = ["MiroFishClient", "get_mirofish_client"]
