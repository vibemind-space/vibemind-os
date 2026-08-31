"""
Shuttle Wizard Handler — orchestrates interactive wizard steps
within a shuttle lifecycle, reusing agent teams from SWE Design.

Each shuttle checkpoint maps to a wizard step:
  1. Mining     → Project Context (ContextEnricher)
  2. Requirements → Stakeholders + Requirements (StakeholderTeam, RequirementGapTeam)
  3. Knowledge Graph → Constraints + Validation (ConstraintTeam)
  4. TechStack  → Finalize & send to SWE Design
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from llm_config import get_model

logger = logging.getLogger(__name__)

# Wizard steps mapped to shuttle stages
WIZARD_STEPS = {
    "mining": 1,
    "requirements": 2,
    "knowledge_graph": 3,
    "techstack": 4,
}


def _load_wizard_config() -> Dict[str, Any]:
    """Load wizard config from SWE Design's re_config.yaml."""
    try:
        import yaml
        config_path = os.path.join(
            os.path.dirname(__file__),
            "swe_desgine", "requirements_engineer", "re_config.yaml",
        )
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                full = yaml.safe_load(f) or {}
            return full.get("wizard", {})
    except Exception as e:
        logger.debug(f"[WizardHandler] Config load failed: {e}")
    return {}


class ShuttleWizardHandler:
    """Orchestrates wizard steps within a shuttle lifecycle.

    Manages per-shuttle wizard state and delegates to SWE Design
    agent teams for AI-powered enrichment.
    """

    def __init__(self):
        self._config = _load_wizard_config()
        # Per-shuttle wizard state: { shuttle_id: { step, data } }
        self._states: Dict[str, Dict[str, Any]] = {}
        self._teams_loaded = False
        self._stakeholder_team = None
        self._context_enricher = None
        self._gap_team = None
        self._constraint_team = None
        self._suggestion_queue = None

    def _ensure_teams(self):
        """Lazy-load agent teams from SWE Design submodule."""
        if self._teams_loaded:
            return
        try:
            from spaces.shuttles.swe_desgine.requirements_engineer.wizard.wizard_agents import (
                StakeholderTeam, ContextEnricher, RequirementGapTeam, ConstraintTeam,
            )
            self._stakeholder_team = StakeholderTeam(self._config)
            self._context_enricher = ContextEnricher(self._config)
            self._gap_team = RequirementGapTeam(self._config)
            self._constraint_team = ConstraintTeam(self._config)
            self._teams_loaded = True
            logger.info("[WizardHandler] Agent teams loaded from SWE Design")
        except ImportError as e:
            logger.warning(f"[WizardHandler] SWE Design agents unavailable: {e}")
            self._teams_loaded = True  # Don't retry

    def _ensure_queue(self, emitter=None):
        """Lazy-load suggestion queue."""
        if self._suggestion_queue is not None:
            return
        try:
            from spaces.shuttles.swe_desgine.requirements_engineer.wizard.suggestion_queue import (
                WizardSuggestionQueue,
            )
            self._suggestion_queue = WizardSuggestionQueue(
                emitter=emitter, config=self._config
            )
        except ImportError:
            logger.debug("[WizardHandler] SuggestionQueue unavailable")

    def _get_state(self, shuttle_id: str) -> Dict[str, Any]:
        """Get or create wizard state for a shuttle."""
        if shuttle_id not in self._states:
            self._states[shuttle_id] = {
                "current_step": "mining",
                "project": {},
                "context": {},
                "stakeholders": [],
                "requirements": [],
                "constraints": {},
                "techstack": None,
                "work_division": "per_feature",
            }
        return self._states[shuttle_id]

    # ------------------------------------------------------------------
    # Step submissions (save user input)
    # ------------------------------------------------------------------

    def submit_step(self, shuttle_id: str, step: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save user input for a wizard step and advance stage."""
        state = self._get_state(shuttle_id)

        if step == "mining":
            state["project"] = {
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "domain": data.get("domain", ""),
                "target_users": data.get("target_users", ""),
            }
            if "context" in data:
                state["context"] = data["context"]
            state["current_step"] = "requirements"

        elif step == "requirements":
            if "stakeholders" in data:
                state["stakeholders"] = data["stakeholders"]
            if "requirements" in data:
                state["requirements"] = data["requirements"]
            state["current_step"] = "knowledge_graph"

        elif step == "knowledge_graph":
            if "constraints" in data:
                state["constraints"] = data["constraints"]
            state["current_step"] = "techstack"

        elif step == "techstack":
            if "techstack" in data:
                state["techstack"] = data["techstack"]
            if "work_division" in data:
                state["work_division"] = data["work_division"]

        # Persist step data to shuttle's stage_data in DB
        self._persist_state(shuttle_id, state)

        return {
            "success": True,
            "current_step": state["current_step"],
            "message": f"Step '{step}' saved",
        }

    # ------------------------------------------------------------------
    # Agent team execution
    # ------------------------------------------------------------------

    async def run_agent(
        self, shuttle_id: str, team_name: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run an agent team and return results."""
        self._ensure_teams()
        state = self._get_state(shuttle_id)
        start = time.time()

        try:
            if team_name == "context_enricher" and self._context_enricher:
                result = await self._context_enricher.run(
                    project_name=input_data.get("name", state["project"].get("name", "")),
                    description=input_data.get("description", state["project"].get("description", "")),
                    domain=input_data.get("domain", state["project"].get("domain", "")),
                )
                if result.success and result.suggestions:
                    # First suggestion is the context
                    state["context"] = result.suggestions[0] if result.suggestions else {}
                    self._persist_state(shuttle_id, state)
                return {
                    "success": result.success,
                    "team": team_name,
                    "suggestions": result.suggestions,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                }

            elif team_name == "stakeholder" and self._stakeholder_team:
                target_users = state["project"].get("target_users", "")
                users_list = [u.strip() for u in target_users.split(",") if u.strip()] if isinstance(target_users, str) else target_users
                result = await self._stakeholder_team.run(
                    project_name=state["project"].get("name", ""),
                    description=state["project"].get("description", ""),
                    domain=state["project"].get("domain", ""),
                    target_users=users_list or ["End User"],
                )
                if result.success:
                    state["stakeholders"] = result.suggestions
                    self._persist_state(shuttle_id, state)
                return {
                    "success": result.success,
                    "team": team_name,
                    "suggestions": result.suggestions,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                }

            elif team_name == "requirement_gap" and self._gap_team:
                result = await self._gap_team.run(
                    requirements=state.get("requirements", []),
                    stakeholders=state.get("stakeholders", []),
                    domain=state["project"].get("domain", ""),
                    description=state["project"].get("description", ""),
                )
                # Route through suggestion queue if available
                self._ensure_queue()
                routed = []
                if self._suggestion_queue and result.suggestions:
                    from spaces.shuttles.swe_desgine.requirements_engineer.wizard.suggestion_queue import (
                        WizardSuggestion, SuggestionType,
                    )
                    for sug in result.suggestions:
                        ws = WizardSuggestion.create(
                            suggestion_type=SuggestionType.REQUIREMENT,
                            content=sug,
                            confidence=sug.get("confidence", 0.7),
                            reasoning=sug.get("gap_area", ""),
                            source_team="requirement_gap",
                            wizard_step=2,
                        )
                        route_result = await self._suggestion_queue.submit(ws)
                        routed.append(route_result)
                return {
                    "success": result.success,
                    "team": team_name,
                    "suggestions": result.suggestions,
                    "routed": routed,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                }

            elif team_name == "constraint" and self._constraint_team:
                result = await self._constraint_team.run(
                    requirements=state.get("requirements", []),
                    existing_constraints=state.get("constraints", {}),
                    domain=state["project"].get("domain", ""),
                )
                if result.success:
                    state["constraints"] = _merge_constraints(
                        state.get("constraints", {}), result.suggestions
                    )
                    self._persist_state(shuttle_id, state)
                return {
                    "success": result.success,
                    "team": team_name,
                    "suggestions": result.suggestions,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                }

            else:
                return {
                    "success": False,
                    "team": team_name,
                    "error": f"Unknown team or team unavailable: {team_name}",
                }

        except Exception as e:
            logger.error(f"[WizardHandler] Agent {team_name} failed: {e}")
            return {
                "success": False,
                "team": team_name,
                "error": str(e),
                "duration_ms": int((time.time() - start) * 1000),
            }

    # ------------------------------------------------------------------
    # Suggestion approval/rejection
    # ------------------------------------------------------------------

    async def approve_suggestion(self, suggestion_id: str) -> Dict[str, Any]:
        """Approve a pending suggestion."""
        self._ensure_queue()
        if not self._suggestion_queue:
            return {"success": False, "error": "Suggestion queue unavailable"}
        result = await self._suggestion_queue.approve(suggestion_id)
        return {"success": result is not None, "suggestion": result.to_dict() if result else None}

    async def reject_suggestion(self, suggestion_id: str, reason: str = "") -> Dict[str, Any]:
        """Reject a pending suggestion."""
        self._ensure_queue()
        if not self._suggestion_queue:
            return {"success": False, "error": "Suggestion queue unavailable"}
        result = await self._suggestion_queue.reject(suggestion_id, reason)
        return {"success": result is not None, "suggestion": result.to_dict() if result else None}

    # ------------------------------------------------------------------
    # Finalize — package wizard data for SWE Design
    # ------------------------------------------------------------------

    def finalize(self, shuttle_id: str) -> Dict[str, Any]:
        """Package all wizard data and prepare for SWE Design.

        Returns the complete work package JSON that SWE Design
        can consume via its getWizardRequirements() format.
        """
        state = self._get_state(shuttle_id)

        work_package = {
            "project": state["project"],
            "context": state["context"],
            "stakeholders": state["stakeholders"],
            "requirements": state["requirements"],
            "constraints": state["constraints"],
            "work_division": state.get("work_division", "per_feature"),
            "source_shuttle_id": shuttle_id,
        }

        # Update shuttle in DB to arrived/complete
        self._complete_shuttle(shuttle_id, state)

        # Publish to Rowboat
        self._publish_to_rowboat(shuttle_id, state)

        # Clean up in-memory state
        self._states.pop(shuttle_id, None)

        return {
            "success": True,
            "work_package": work_package,
            "message": "Shuttle finalized and published to Rowboat",
        }

    # ------------------------------------------------------------------
    # Get wizard state (for frontend)
    # ------------------------------------------------------------------

    def get_state(self, shuttle_id: str) -> Dict[str, Any]:
        """Return current wizard state for a shuttle."""
        state = self._get_state(shuttle_id)
        return {
            "success": True,
            "current_step": state["current_step"],
            "project": state["project"],
            "context": state["context"],
            "stakeholders": state["stakeholders"],
            "requirements": state["requirements"],
            "constraints": state["constraints"],
            "techstack": state.get("techstack"),
            "work_division": state.get("work_division", "per_feature"),
        }

    # ------------------------------------------------------------------
    # Initialize wizard from bubble data
    # ------------------------------------------------------------------

    def init_from_bubble(self, shuttle_id: str, bubble_id: str) -> Dict[str, Any]:
        """Pre-populate wizard state with data from the source bubble.

        Collects bubble metadata, child ideas, canvas nodes, tags and
        concepts to provide smart defaults for all wizard fields.
        """
        try:
            from data import IdeasRepository, CanvasRepository
            from data.models import Idea

            ideas_repo = IdeasRepository()
            canvas_repo = CanvasRepository()
            bubble = ideas_repo.get(bubble_id)
            if not bubble:
                return {"success": False, "error": f"Bubble {bubble_id} not found"}

            state = self._get_state(shuttle_id)
            state["bubble_id"] = bubble_id

            # ----------------------------------------------------------
            # Collect all content from the bubble (ideas + canvas nodes)
            # ----------------------------------------------------------
            all_tags = set()
            all_concepts = set()
            all_node_types = set()
            content_texts = []
            req_index = 0

            # Child ideas (direct children in ideas table)
            child_rows = ideas_repo.db.fetch_all(
                "SELECT * FROM ideas WHERE parent_id = ?", (bubble_id,)
            )
            for r in child_rows:
                child = Idea.from_dict(dict(r))
                if child.title:
                    req_index += 1
                    state["requirements"].append({
                        "id": f"REQ-{req_index:03d}",
                        "title": child.title,
                        "description": child.description or "",
                        "acceptance_criteria": [],
                        "user_stories": [],
                        "priority": "medium",
                        "status": "pending",
                    })
                    content_texts.append(child.title)
                    if child.description:
                        content_texts.append(child.description)
                    if child.tags:
                        all_tags.update(child.tags)

            # Canvas nodes linked to this bubble
            try:
                all_nodes = canvas_repo.list_nodes(limit=2000)
                bubble_nodes = [n for n in all_nodes if n.linked_idea_id == bubble_id]
                for node in bubble_nodes:
                    if node.title:
                        req_index += 1
                        state["requirements"].append({
                            "id": f"REQ-{req_index:03d}",
                            "title": node.title,
                            "description": node.content or "",
                            "acceptance_criteria": [],
                            "user_stories": [],
                            "priority": "medium",
                            "status": "pending",
                        })
                        content_texts.append(node.title)
                        if node.content:
                            content_texts.append(node.content)
                    if node.node_type:
                        all_node_types.add(node.node_type)
            except Exception:
                pass  # Canvas nodes optional

            # ----------------------------------------------------------
            # Smart defaults: LLM infers domain, target users, description
            # ----------------------------------------------------------
            inferred = _infer_project_metadata(
                bubble.title or "",
                bubble.description or "",
                all_tags,
                content_texts,
            )

            state["project"] = {
                "name": bubble.title or "",
                "description": inferred.get("description") or bubble.description or "",
                "domain": inferred.get("domain", ""),
                "target_users": inferred.get("target_users", ""),
            }

            # Pre-populate tags as context hints
            if all_tags:
                state["context"]["tags"] = sorted(all_tags)

            # ----------------------------------------------------------
            # Optional: MiroFish readiness evaluation (30s timeout)
            # ----------------------------------------------------------
            mirofish_result = None
            try:
                from spaces.mirofish.tools.mirofish_tools import evaluate_bubble_readiness
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(evaluate_bubble_readiness, bubble.title or "")
                    mirofish_result = future.result(timeout=600)

                if mirofish_result and mirofish_result.get("success"):
                    state["mirofish_result"] = mirofish_result
                    # Missing items → pre-populate constraints
                    for item in mirofish_result.get("missing_items", []):
                        state["constraints"].setdefault("mirofish_gaps", []).append(item)
                    state["context"]["mirofish_readiness"] = {
                        "score": mirofish_result.get("total_score"),
                        "prediction": mirofish_result.get("prediction"),
                    }
                    logger.info(
                        f"[WizardHandler] MiroFish eval: {mirofish_result.get('total_score')}/100 "
                        f"({mirofish_result.get('prediction')})"
                    )
                else:
                    mirofish_result = None
            except Exception as e:
                logger.warning(f"[WizardHandler] MiroFish eval skipped: {e}")
                mirofish_result = None

            self._persist_state(shuttle_id, state)

            result = {
                "success": True,
                "project": state["project"],
                "requirements_count": len(state["requirements"]),
                "tags": sorted(all_tags) if all_tags else [],
            }
            if mirofish_result:
                result["mirofish_result"] = mirofish_result
            return result
        except Exception as e:
            logger.error(f"[WizardHandler] init_from_bubble failed: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _persist_state(self, shuttle_id: str, state: Dict[str, Any]):
        """Write wizard state to shuttle's stage_data in SQLite."""
        try:
            from data import ShuttlesRepository
            repo = ShuttlesRepository()
            shuttle = repo.get_by_shuttle_id(shuttle_id)
            if shuttle:
                wizard_data = {
                    "wizard_state": {
                        "current_step": state["current_step"],
                        "project": state["project"],
                        "context": state["context"],
                        "stakeholders": state["stakeholders"],
                        "requirements": state["requirements"],
                        "constraints": state["constraints"],
                        "techstack": state.get("techstack"),
                        "work_division": state.get("work_division", "per_feature"),
                    }
                }
                # Merge with existing stage_data
                existing = shuttle.stage_data or {}
                existing.update(wizard_data)
                repo.update_stage_data(shuttle.id, existing)
        except Exception as e:
            logger.debug(f"[WizardHandler] Persist failed: {e}")

    def _complete_shuttle(self, shuttle_id: str, state: Dict[str, Any]):
        """Mark shuttle as arrived in DB."""
        try:
            from data import ShuttlesRepository
            repo = ShuttlesRepository()
            shuttle = repo.get_by_shuttle_id(shuttle_id)
            if shuttle:
                reqs = state.get("requirements", [])
                repo.complete(
                    shuttle_db_id=shuttle.id,
                    final_score=1.0,
                    passed=len(reqs),
                    failed=0,
                    requirement_results={"requirements": reqs},
                )
        except Exception as e:
            logger.debug(f"[WizardHandler] Complete failed: {e}")

    def _publish_to_rowboat(self, shuttle_id: str, state: Dict[str, Any]):
        """Publish enriched wizard + MiroFish results to Rowboat knowledge folder."""
        try:
            bubble_id = state.get("bubble_id")
            if not bubble_id:
                from data import ShuttlesRepository
                shuttle = ShuttlesRepository().get_by_shuttle_id(shuttle_id)
                if shuttle:
                    bubble_id = shuttle.bubble_id

            if not bubble_id:
                logger.debug("[WizardHandler] No bubble_id for Rowboat publish")
                return

            from publishing import get_ideas_publisher
            publisher = get_ideas_publisher()
            mirofish_result = state.get("mirofish_result")

            # Write enriched .md files (_requirements, _stakeholders, etc.)
            if hasattr(publisher, "publish_wizard_results"):
                publisher.publish_wizard_results(bubble_id, state, mirofish_result)
                logger.info(
                    f"[WizardHandler] Published wizard results to Rowboat for bubble {bubble_id}"
                )
            # Fallback: MongoDB publisher path
            elif hasattr(publisher, "publish_shuttle_data"):
                publisher.publish_shuttle_data(bubble_id)
        except Exception as e:
            logger.warning(f"[WizardHandler] Rowboat publish failed: {e}")

    def load_state_from_shuttle(self, shuttle_id: str) -> Dict[str, Any]:
        """Restore wizard state from shuttle's stage_data (e.g. after restart)."""
        try:
            from data import ShuttlesRepository
            shuttle = ShuttlesRepository().get_by_shuttle_id(shuttle_id)
            if shuttle and shuttle.stage_data:
                wizard_data = shuttle.stage_data.get("wizard_state")
                if wizard_data:
                    self._states[shuttle_id] = wizard_data
                    return {"success": True, "state": wizard_data}
        except Exception as e:
            logger.debug(f"[WizardHandler] Load state failed: {e}")
        return {"success": False, "error": "No wizard state found"}


# ------------------------------------------------------------------
# LLM-based inference for domain + target users
# ------------------------------------------------------------------

_PREFILL_PROMPT = """\
Analyze the following project content and extract:
1. **domain**: The primary domain/industry (e.g. "E-Commerce", "FinTech", "SaaS", "AI / ML", "Marketing", "DevTools", "HealthTech", "EdTech", "IoT", "Social Media", "Automation", "Projektmanagement"). Pick 1-2 that fit best.
2. **target_users**: Who will use this product (e.g. "End Users", "Developers", "Admins", "Business Users", "Content Creators", "Teams"). Pick 1-3 that fit.
3. **description**: A concise 1-2 sentence project description (improve the existing one if vague).

Project title: {title}
Existing description: {description}
Tags: {tags}
Content samples (ideas/notes in this project):
{content_sample}

Respond in this exact JSON format, nothing else:
{{"domain": "...", "target_users": "...", "description": "..."}}"""

# Provider configs: try Ollama (free/local) first, then OpenRouter, then OpenAI
_LLM_PROVIDERS = [
    {
        "key_env": None,  # No key needed
        "api_key": "ollama",
        "base_url": "http://localhost:11434/v1",
        "model": get_model("wizard_ollama"),
        "timeout": 15,
    },
    {
        "key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "model": get_model("wizard_openrouter"),
    },
    {
        "key_env": "OPENAI_API_KEY",
        "base_url": None,  # Default OpenAI
        "model": get_model("wizard_openai"),
    },
]


def _infer_project_metadata(
    title: str,
    description: str,
    tags: set,
    content_texts: List[str],
) -> Dict[str, str]:
    """Use LLM to infer domain, target users, and improved description.

    Tries OpenRouter first, falls back to OpenAI, then to empty strings.
    """
    import json as _json

    # Build content sample (limit to keep prompt small)
    sample_lines = []
    for t in content_texts[:15]:
        line = t.strip()[:200]
        if line:
            sample_lines.append(f"- {line}")
    content_sample = "\n".join(sample_lines) if sample_lines else "(no content yet)"

    prompt = _PREFILL_PROMPT.format(
        title=title or "(untitled)",
        description=description or "(none)",
        tags=", ".join(sorted(tags)) if tags else "(none)",
        content_sample=content_sample,
    )

    from openai import OpenAI

    for provider in _LLM_PROVIDERS:
        # Resolve API key: fixed value or from env var
        if provider.get("api_key"):
            api_key = provider["api_key"]
        elif provider.get("key_env"):
            api_key = os.getenv(provider["key_env"])
            if not api_key:
                continue
        else:
            continue

        try:
            kwargs = {"api_key": api_key}
            if provider.get("base_url"):
                kwargs["base_url"] = provider["base_url"]
            if provider.get("timeout"):
                kwargs["timeout"] = provider["timeout"]

            client = OpenAI(**kwargs)
            response = client.chat.completions.create(
                model=provider["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200,
            )

            text = response.choices[0].message.content.strip()
            # Extract JSON from response (handle markdown code blocks)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = _json.loads(text)
            logger.debug(
                f"[WizardHandler] LLM prefill via {provider['key_env']}: {result}"
            )
            return {
                "domain": result.get("domain", ""),
                "target_users": result.get("target_users", ""),
                "description": result.get("description", description),
            }

        except Exception as e:
            logger.debug(
                f"[WizardHandler] LLM prefill via {provider['key_env']} failed: {e}"
            )
            continue  # Try next provider

    logger.warning("[WizardHandler] All LLM providers failed for prefill")
    return {"domain": "", "target_users": "", "description": description}


def _merge_constraints(
    existing: Dict[str, Any], new_suggestions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Merge auto-extracted constraints into existing constraints dict."""
    result = dict(existing)
    for sug in new_suggestions:
        category = sug.get("category", "technical")
        if category not in result:
            result[category] = []
        result[category].append({
            "constraint": sug.get("constraint", ""),
            "source": sug.get("source", "auto-extracted"),
            "confidence": sug.get("confidence", 0.0),
        })
    return result


# Singleton instance
_handler: Optional[ShuttleWizardHandler] = None


def get_wizard_handler() -> ShuttleWizardHandler:
    """Get or create the singleton wizard handler."""
    global _handler
    if _handler is None:
        _handler = ShuttleWizardHandler()
    return _handler
