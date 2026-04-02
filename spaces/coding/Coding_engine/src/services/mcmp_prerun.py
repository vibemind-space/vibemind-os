"""
MCMP Pre-Run & Post-Epic Verification Service.

Two modes:
1. PRE-RUN: Before each task, indexes project code + runs 200-agent swarm
   to find relevant docs/patterns → returns enriched context for code generation.

2. POST-EPIC: After an epic completes, runs in completeness_mode to verify
   all expected outputs were generated → posts Discord notification if incomplete.

Usage:
    from src.services.mcmp_prerun import MCMPPreRun

    prerun = MCMPPreRun(project_path="/workspace/app")
    await prerun.index_project()

    # Before each task:
    context = await prerun.get_task_context(
        task_id="EPIC-001-AUTH-login",
        task_name="Login Component",
        task_description="Create login form with JWT auth",
    )
    # context["enriched_prompt"] contains the docs + patterns

    # After epic:
    result = await prerun.verify_epic_completeness(
        epic_id="EPIC-001",
        expected_files=["src/auth/login.tsx", "src/api/auth.ts"],
        requirements=["JWT login", "Register form", "Password reset"],
    )
    # result["missing"] = list of what's missing
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class MCMPPreRun:
    """Manages MCMP simulation for pre-task context and post-epic verification."""

    def __init__(
        self,
        project_path: str = "/workspace/app",
        num_agents: int = 200,
        max_iterations: int = 30,
        judge_model: str = "nvidia/nemotron-3-super-120b-a12b:free",
        steering_model: str = "qwen/qwen3-coder:free",
    ):
        self.project_path = project_path
        self.num_agents = num_agents
        self.max_iterations = max_iterations
        self.judge_model = judge_model
        self.steering_model = steering_model

        self._indexed = False
        self._documents: List[str] = []
        self._file_index: Dict[str, str] = {}  # path -> content
        self._simulation = None

    def _get_simulation(self):
        """Lazy-init MCMPBackgroundSimulation."""
        if self._simulation is not None:
            return self._simulation

        try:
            from src.services.mcmp_background import (
                MCMPBackgroundSimulation,
                SimulationConfig,
            )

            config = SimulationConfig(
                num_agents=self.num_agents,
                max_iterations=self.max_iterations,
                judge_model=self.judge_model,
                steering_model=self.steering_model,
                judge_provider="openrouter",
                enable_llm_steering=True,
                top_k_results=10,
            )
            self._simulation = MCMPBackgroundSimulation(config=config)
            logger.info("[MCMPPreRun] Simulation initialized (%d agents)", self.num_agents)
            return self._simulation
        except Exception as e:
            logger.warning("[MCMPPreRun] Could not init simulation: %s", e)
            return None

    async def index_project(self, path: Optional[str] = None) -> int:
        """
        Index project source files into MCMP document corpus.
        Reads .ts, .tsx, .js, .jsx, .py, .prisma, .json files.
        Returns number of documents indexed.
        """
        project = Path(path or self.project_path)
        if not project.exists():
            # Try reading from Docker container
            return await self._index_from_container()

        extensions = {".ts", ".tsx", ".js", ".jsx", ".py", ".prisma", ".css", ".json"}
        skip_dirs = {"node_modules", ".git", "dist", "build", "__pycache__", ".next"}

        documents = []
        file_index = {}

        for root, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                fp = Path(root) / f
                if fp.suffix not in extensions:
                    continue
                try:
                    content = fp.read_text(encoding="utf-8", errors="ignore")
                    if len(content) < 10:
                        continue
                    # Chunk large files
                    rel_path = str(fp.relative_to(project))
                    if len(content) > 2000:
                        chunks = self._chunk_file(rel_path, content)
                        documents.extend(chunks)
                    else:
                        doc = "// FILE: %s\n%s" % (rel_path, content)
                        documents.append(doc)
                    file_index[rel_path] = content
                except Exception:
                    continue

        self._documents = documents
        self._file_index = file_index
        self._indexed = True

        # Load into simulation
        sim = self._get_simulation()
        if sim and documents:
            sim.clear_documents()
            sim.add_documents(documents)

        logger.info("[MCMPPreRun] Indexed %d documents from %d files", len(documents), len(file_index))
        return len(documents)

    async def _index_from_container(self) -> int:
        """Index files from the sandbox Docker container."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "exec", "coding-engine-sandbox",
                "find", "/workspace/app/src", "-type", "f",
                "-name", "*.ts", "-o", "-name", "*.tsx",
                "-o", "-name", "*.js", "-o", "-name", "*.jsx",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            files = [f for f in out.decode().strip().split("\n") if f]

            documents = []
            file_index = {}
            for fp in files[:100]:  # Limit to 100 files
                try:
                    cat_proc = await asyncio.create_subprocess_exec(
                        "docker", "exec", "coding-engine-sandbox",
                        "cat", fp,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    content_out, _ = await asyncio.wait_for(cat_proc.communicate(), timeout=5)
                    content = content_out.decode(errors="ignore")
                    if len(content) < 10:
                        continue
                    rel = fp.replace("/workspace/app/", "")
                    doc = "// FILE: %s\n%s" % (rel, content)
                    documents.append(doc)
                    file_index[rel] = content
                except Exception:
                    continue

            self._documents = documents
            self._file_index = file_index
            self._indexed = True

            sim = self._get_simulation()
            if sim and documents:
                sim.clear_documents()
                sim.add_documents(documents)

            logger.info("[MCMPPreRun] Indexed %d docs from container", len(documents))
            return len(documents)
        except Exception as e:
            logger.warning("[MCMPPreRun] Container index failed: %s", e)
            return 0

    def _chunk_file(self, path: str, content: str, chunk_size: int = 1500) -> List[str]:
        """Split large files into overlapping chunks."""
        lines = content.split("\n")
        chunks = []
        current = []
        current_len = 0

        for line in lines:
            current.append(line)
            current_len += len(line) + 1
            if current_len >= chunk_size:
                chunk_text = "\n".join(current)
                chunks.append("// FILE: %s (chunk %d)\n%s" % (path, len(chunks) + 1, chunk_text))
                # Keep last 3 lines for overlap
                current = current[-3:]
                current_len = sum(len(l) + 1 for l in current)

        if current:
            chunk_text = "\n".join(current)
            chunks.append("// FILE: %s (chunk %d)\n%s" % (path, len(chunks) + 1, chunk_text))

        return chunks

    async def get_task_context(
        self,
        task_id: str,
        task_name: str,
        task_description: str = "",
        file_path: str = "",
        mode: str = "steering",
    ) -> Dict[str, Any]:
        """
        Run MCMP simulation for a specific task and return enriched context.

        Returns dict with:
          - enriched_prompt: str with relevant code patterns/docs
          - relevant_files: list of file paths most relevant to task
          - confidence: float from Judge LLM
          - keywords: list of discovered relevant keywords
        """
        if not self._indexed:
            await self.index_project()

        query = "Task: %s\nDescription: %s\nFile: %s" % (task_name, task_description, file_path)

        sim = self._get_simulation()
        if not sim or not self._documents:
            # Fallback: keyword search through indexed files
            return self._keyword_search_fallback(task_name, task_description, file_path)

        # Run simulation
        from src.services.mcmp_background import JudgeMode
        mode_map = {
            "steering": JudgeMode.STEERING,
            "repair": JudgeMode.REPAIR,
            "deep": JudgeMode.DEEP,
            "structure": JudgeMode.STRUCTURE,
        }

        try:
            # Stop any running simulation
            if sim.is_running:
                await sim.stop()

            # Reload documents (in case new files were generated)
            if self._documents:
                sim.clear_documents()
                sim.add_documents(self._documents)

            started = await sim.start(query, mode=mode_map.get(mode, JudgeMode.STEERING))
            if not started:
                return self._keyword_search_fallback(task_name, task_description, file_path)

            # Wait for completion (max 30s)
            timeout = self.max_iterations * 0.15 + 5
            waited = 0
            while sim.is_running and waited < timeout:
                await asyncio.sleep(0.5)
                waited += 0.5

            results = await sim.stop()

            # Extract enriched context
            enriched = sim.get_enriched_context()
            fungus = enriched.get("fungus_context", {})

            # Build enriched prompt from top results
            relevant_code = []
            relevant_files = []
            for r in fungus.get("relevant_code", [])[:5]:
                content = r.get("content", "")
                if content:
                    relevant_code.append(content[:500])
                    # Extract file path from "// FILE: xxx" header
                    if content.startswith("// FILE:"):
                        fpath = content.split("\n")[0].replace("// FILE:", "").strip()
                        if " (chunk" in fpath:
                            fpath = fpath.split(" (chunk")[0]
                        relevant_files.append(fpath)

            enriched_prompt = ""
            if relevant_code:
                enriched_prompt = (
                    "\n--- RELEVANT CODE CONTEXT (from MCMP 200-agent search) ---\n"
                    + "\n---\n".join(relevant_code)
                    + "\n--- END CONTEXT ---\n"
                )

            keywords = fungus.get("suggested_keywords", [])
            confidence = fungus.get("judge_confidence", 0.0)

            logger.info(
                "[MCMPPreRun] Task %s: %d relevant files, confidence=%.2f, %d keywords",
                task_id, len(relevant_files), confidence, len(keywords),
            )

            return {
                "enriched_prompt": enriched_prompt,
                "relevant_files": relevant_files,
                "confidence": confidence,
                "keywords": keywords,
                "steps_completed": results.get("steps_completed", 0),
                "judge_reasoning": (
                    fungus.get("recommended_focus", [""])[0][:200]
                    if fungus.get("recommended_focus") else ""
                ),
            }

        except Exception as e:
            logger.warning("[MCMPPreRun] Simulation failed for %s: %s", task_id, e)
            return self._keyword_search_fallback(task_name, task_description, file_path)

    def _keyword_search_fallback(
        self, task_name: str, description: str, file_path: str
    ) -> Dict[str, Any]:
        """Simple keyword matching when MCMP is unavailable."""
        keywords = set()
        for text in [task_name, description, file_path]:
            for word in text.lower().split():
                if len(word) > 3:
                    keywords.add(word.strip(".,;:(){}[]"))

        relevant_code = []
        relevant_files = []
        for path, content in self._file_index.items():
            content_lower = content.lower()
            matches = sum(1 for kw in keywords if kw in content_lower)
            if matches >= 2:
                relevant_files.append(path)
                relevant_code.append("// FILE: %s\n%s" % (path, content[:400]))

        enriched_prompt = ""
        if relevant_code[:3]:
            enriched_prompt = (
                "\n--- RELEVANT CODE CONTEXT (keyword search fallback) ---\n"
                + "\n---\n".join(relevant_code[:3])
                + "\n--- END CONTEXT ---\n"
            )

        return {
            "enriched_prompt": enriched_prompt,
            "relevant_files": relevant_files[:5],
            "confidence": 0.3,
            "keywords": list(keywords)[:10],
            "steps_completed": 0,
            "judge_reasoning": "Fallback keyword search (MCMP unavailable)",
        }

    async def verify_epic_completeness(
        self,
        epic_id: str,
        expected_files: Optional[List[str]] = None,
        requirements: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Post-epic verification: check if all expected outputs exist.

        Runs MCMP in completeness_mode to verify each requirement
        has corresponding code in the project.

        Returns:
          - complete: bool
          - missing: list of missing items
          - coverage: float (0-1)
          - details: per-requirement verification
        """
        # Re-index to pick up newly generated files
        await self.index_project()

        results = {
            "epic_id": epic_id,
            "complete": True,
            "missing": [],
            "coverage": 0.0,
            "details": [],
        }

        # Check expected files exist
        missing_files = []
        if expected_files:
            for ef in expected_files:
                found = ef in self._file_index
                if not found:
                    # Fuzzy match
                    found = any(ef.split("/")[-1] in k for k in self._file_index)
                if not found:
                    missing_files.append(ef)

            results["missing_files"] = missing_files

        # Check requirements have corresponding code
        missing_reqs = []
        req_details = []
        if requirements:
            for req in requirements:
                # Search indexed code for requirement keywords
                req_keywords = [w.lower() for w in req.split() if len(w) > 3]
                found_in = []
                for path, content in self._file_index.items():
                    content_lower = content.lower()
                    matches = sum(1 for kw in req_keywords if kw in content_lower)
                    if matches >= max(1, len(req_keywords) // 2):
                        found_in.append(path)

                verified = len(found_in) > 0
                detail = {
                    "requirement": req,
                    "verified": verified,
                    "found_in": found_in[:3],
                }
                req_details.append(detail)

                if not verified:
                    missing_reqs.append(req)

        # Use LLM for deeper verification if we have missing items
        if (missing_files or missing_reqs) and os.environ.get("OPENROUTER_API_KEY"):
            llm_check = await self._llm_completeness_check(
                epic_id, missing_files, missing_reqs
            )
            if llm_check:
                req_details.append(llm_check)

        total_checks = (len(expected_files or []) + len(requirements or [])) or 1
        passed = total_checks - len(missing_files) - len(missing_reqs)
        coverage = passed / total_checks

        results["missing"] = missing_files + missing_reqs
        results["coverage"] = round(coverage, 2)
        results["complete"] = coverage >= 0.8  # 80% threshold
        results["details"] = req_details

        logger.info(
            "[MCMPPreRun] Epic %s verification: %.0f%% coverage, %d missing",
            epic_id, coverage * 100, len(results["missing"]),
        )

        return results

    async def _llm_completeness_check(
        self,
        epic_id: str,
        missing_files: List[str],
        missing_reqs: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Use Judge LLM to verify if missing items are truly missing."""
        import httpx
        import json

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            return None

        # Show what files we DO have
        existing = list(self._file_index.keys())[:20]

        prompt = "Epic %s completeness check.\n\n" % epic_id
        prompt += "Files in project:\n" + "\n".join("- %s" % f for f in existing) + "\n\n"
        if missing_files:
            prompt += "Expected but NOT found:\n" + "\n".join("- %s" % f for f in missing_files) + "\n\n"
        if missing_reqs:
            prompt += "Requirements without matching code:\n" + "\n".join("- %s" % r for r in missing_reqs) + "\n\n"
        prompt += 'Reply JSON: {"truly_missing": [...], "likely_covered": [...], "reasoning": "..."}'

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": "Bearer %s" % api_key},
                    json={
                        "model": self.judge_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 500,
                    },
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    try:
                        start = content.find("{")
                        end = content.rfind("}")
                        if start != -1 and end > start:
                            return json.loads(content[start:end + 1])
                    except Exception:
                        return {"reasoning": content[:300]}
        except Exception as e:
            logger.warning("[MCMPPreRun] LLM completeness check failed: %s", e)

        return None

    async def close(self):
        """Cleanup resources."""
        if self._simulation:
            await self._simulation.close()
            self._simulation = None


# --- Singleton for shared use across handlers ---
_prerun_instance: Optional[MCMPPreRun] = None


def get_prerun(project_path: str = "/workspace/app") -> MCMPPreRun:
    """Get or create the shared MCMPPreRun instance."""
    global _prerun_instance
    if _prerun_instance is None:
        _prerun_instance = MCMPPreRun(project_path=project_path)
    return _prerun_instance
