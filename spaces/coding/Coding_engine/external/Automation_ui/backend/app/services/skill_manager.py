"""
Skill Manager - Local Skill Installation & Execution

Manages locally installed skills: install, uninstall, update, execute.
Skills are stored in backend/skills/{skill_id}/ with metadata.json.

Usage:
    manager = get_skill_manager()
    await manager.install_skill(skill_detail)
    result = await manager.execute_skill("browser-automation", {"url": "..."})
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.skill import (
    InstalledSkill,
    SkillDetail,
    SkillExecuteResponse,
    SkillStatus,
)

logger = logging.getLogger(__name__)

# Default skills directory
SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


class SkillManager:
    """
    Manages locally installed skills.

    Skills are stored in:
        backend/skills/{skill_id}/
        ├── metadata.json   (InstalledSkill as JSON)
        ├── skill.py        (executable code, optional)
        └── README.md       (documentation, optional)
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, InstalledSkill] = {}
        self._loaded = False

    def _load_cache(self):
        """Load all installed skills into memory."""
        if self._loaded:
            return

        self._cache.clear()
        if not self.skills_dir.exists():
            self._loaded = True
            return

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            meta_path = skill_dir / "metadata.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    skill = InstalledSkill(**data)
                    self._cache[skill.id] = skill
                except Exception as e:
                    logger.warning(f"Failed to load skill {skill_dir.name}: {e}")

        self._loaded = True
        logger.info(f"Loaded {len(self._cache)} installed skills")

    def _save_skill_metadata(self, skill: InstalledSkill):
        """Save skill metadata to disk."""
        skill_dir = self.skills_dir / skill.id
        skill_dir.mkdir(parents=True, exist_ok=True)

        meta_path = skill_dir / "metadata.json"
        meta_path.write_text(
            skill.model_dump_json(indent=2),
            encoding="utf-8",
        )

    # ========================================================================
    # Public API
    # ========================================================================

    def list_installed(self) -> List[InstalledSkill]:
        """List all installed skills."""
        self._load_cache()
        return list(self._cache.values())

    def get_installed(self, skill_id: str) -> Optional[InstalledSkill]:
        """Get a specific installed skill."""
        self._load_cache()
        return self._cache.get(skill_id)

    def is_installed(self, skill_id: str) -> bool:
        """Check if a skill is installed."""
        self._load_cache()
        return skill_id in self._cache

    async def install_skill(self, skill: SkillDetail) -> InstalledSkill:
        """
        Install a skill from ClawHub.

        Creates the skill directory and saves metadata.
        In a real implementation, this would also download the code bundle.
        """
        self._load_cache()

        # Create InstalledSkill from detail
        installed = InstalledSkill(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            author=skill.author,
            category=skill.category,
            tags=skill.tags,
            permissions=skill.permissions,
            parameters=skill.parameters,
            status=SkillStatus.INSTALLED,
            enabled=True,
            installed_at=datetime.utcnow(),
            local_path=str(self.skills_dir / skill.id),
        )

        # Save to disk
        self._save_skill_metadata(installed)

        # Create a placeholder skill.py
        skill_dir = self.skills_dir / skill.id
        skill_py = skill_dir / "skill.py"
        if not skill_py.exists():
            skill_py.write_text(
                f'"""\n{skill.name}\n\n{skill.description}\n"""\n\n'
                f'async def execute(params: dict) -> dict:\n'
                f'    """Execute the {skill.name} skill."""\n'
                f'    return {{\n'
                f'        "success": True,\n'
                f'        "message": "{skill.name} executed successfully",\n'
                f'        "params": params,\n'
                f'    }}\n',
                encoding="utf-8",
            )

        # Update cache
        self._cache[installed.id] = installed

        logger.info(f"Installed skill: {skill.id} v{skill.version}")
        return installed

    async def uninstall_skill(self, skill_id: str) -> bool:
        """Uninstall a skill by removing its directory."""
        self._load_cache()

        if skill_id not in self._cache:
            return False

        skill_dir = self.skills_dir / skill_id

        # Remove directory
        if skill_dir.exists():
            import shutil
            shutil.rmtree(skill_dir, ignore_errors=True)

        # Remove from cache
        del self._cache[skill_id]

        logger.info(f"Uninstalled skill: {skill_id}")
        return True

    async def toggle_skill(self, skill_id: str, enabled: bool) -> Optional[InstalledSkill]:
        """Enable or disable a skill."""
        self._load_cache()

        skill = self._cache.get(skill_id)
        if not skill:
            return None

        skill.enabled = enabled
        self._save_skill_metadata(skill)
        return skill

    async def execute_skill(
        self,
        skill_id: str,
        params: Dict[str, Any],
    ) -> SkillExecuteResponse:
        """
        Execute an installed skill.

        Loads and runs the skill's execute() function.
        """
        self._load_cache()
        start_time = time.time()

        skill = self._cache.get(skill_id)
        if not skill:
            return SkillExecuteResponse(
                success=False,
                skill_id=skill_id,
                message=f"Skill '{skill_id}' not installed",
                error="not_installed",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        if not skill.enabled:
            return SkillExecuteResponse(
                success=False,
                skill_id=skill_id,
                message=f"Skill '{skill.name}' is disabled",
                error="disabled",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        try:
            # Try to load and execute the skill module
            skill_py = self.skills_dir / skill_id / "skill.py"

            if skill_py.exists():
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    f"skill_{skill_id}", str(skill_py)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "execute"):
                    if asyncio.iscoroutinefunction(module.execute):
                        result = await module.execute(params)
                    else:
                        result = module.execute(params)
                else:
                    result = {
                        "success": True,
                        "message": f"Skill '{skill.name}' loaded (no execute function)",
                    }
            else:
                # No skill.py - return metadata-based response
                result = {
                    "success": True,
                    "message": f"Skill '{skill.name}' v{skill.version} ready",
                    "params": params,
                    "note": "Skill code not yet downloaded from ClawHub",
                }

            # Update execution stats
            skill.last_executed = datetime.utcnow()
            skill.execution_count += 1
            self._save_skill_metadata(skill)

            return SkillExecuteResponse(
                success=result.get("success", True),
                skill_id=skill_id,
                message=result.get("message", "Executed"),
                data=result,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Skill execution failed ({skill_id}): {e}")
            return SkillExecuteResponse(
                success=False,
                skill_id=skill_id,
                message=f"Execution failed: {str(e)}",
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get skill manager statistics."""
        self._load_cache()
        installed = list(self._cache.values())
        return {
            "total_installed": len(installed),
            "enabled": sum(1 for s in installed if s.enabled),
            "disabled": sum(1 for s in installed if not s.enabled),
            "total_executions": sum(s.execution_count for s in installed),
            "skills_dir": str(self.skills_dir),
        }


# ============================================================================
# Singleton
# ============================================================================

_manager: Optional[SkillManager] = None


def get_skill_manager() -> SkillManager:
    """Get the SkillManager singleton."""
    global _manager
    if _manager is None:
        _manager = SkillManager()
    return _manager
