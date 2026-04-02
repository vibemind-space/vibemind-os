"""
Dependency Manager Agent - Autonomous agent for dependency management.

Manages project dependencies:
- Checks for outdated packages
- Updates dependencies safely (patch/minor versions)
- Scans for license compliance issues
- Resolves peer dependency conflicts
- Responds to vulnerability reports from SecurityScannerAgent

Publishes:
- DEPENDENCY_CHECK_STARTED: Check began
- DEPENDENCY_CHECK_PASSED: No issues found
- DEPENDENCY_OUTDATED: Outdated packages found
- DEPENDENCY_UPDATED: Package updated successfully
- DEPENDENCY_CONFLICT: Peer dependency conflict
- LICENSE_ISSUE_FOUND: License compliance issue
"""

import json
import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    dependency_check_started_event,
    dependency_check_passed_event,
    dependency_outdated_event,
    dependency_conflict_event,
    dependency_updated_event,
    license_issue_found_event,
)
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin


logger = structlog.get_logger(__name__)


# Licenses that may have legal restrictions
RESTRICTIVE_LICENSES = {
    "GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.0", "LGPL-2.1", "LGPL-3.0",
    "GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only",
    "CC-BY-NC", "CC-BY-NC-SA", "CC-BY-NC-ND",
    "SSPL-1.0", "Elastic-2.0",
}

# Preferred permissive licenses
PERMISSIVE_LICENSES = {
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
    "0BSD", "Unlicense", "CC0-1.0", "WTFPL",
}


class DependencyManagerAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent that manages project dependencies.

    Subscribes to:
    - PROJECT_SCAFFOLDED: Check dependencies after initial setup
    - BUILD_FAILED: Check if failure is dependency-related
    - DEPENDENCY_VULNERABILITY: From SecurityScannerAgent
    - SECURITY_FIX_NEEDED: May require dependency update

    Publishes:
    - DEPENDENCY_CHECK_STARTED: Check began
    - DEPENDENCY_CHECK_PASSED: No issues found
    - DEPENDENCY_OUTDATED: Outdated packages found
    - DEPENDENCY_UPDATED: Package updated
    - DEPENDENCY_CONFLICT: Peer dependency conflict
    - LICENSE_ISSUE_FOUND: License compliance issue

    Workflow:
    1. Triggered after project scaffold or vulnerability report
    2. Checks for outdated dependencies
    3. Checks license compliance
    4. Updates packages (patch/minor only by default)
    5. Reports issues that require manual intervention
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        auto_update_patch: bool = True,
        auto_update_minor: bool = False,
        auto_update_major: bool = False,
        check_licenses: bool = True,
        restrictive_license_action: str = "warn",  # "warn", "block", "ignore"
        timeout: int = 300,
    ):
        """
        Initialize the DependencyManagerAgent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project working directory
            auto_update_patch: Auto-update patch versions (1.0.x)
            auto_update_minor: Auto-update minor versions (1.x.0)
            auto_update_major: Auto-update major versions (x.0.0)
            check_licenses: Check for license compliance
            restrictive_license_action: Action for restrictive licenses
            timeout: Timeout for npm/pip commands
        """
        super().__init__(name, event_bus, shared_state, working_dir)
        self.auto_update_patch = auto_update_patch
        self.auto_update_minor = auto_update_minor
        self.auto_update_major = auto_update_major
        self.check_licenses = check_licenses
        self.restrictive_license_action = restrictive_license_action
        self.timeout = timeout
        self._last_check_time: Optional[float] = None
        self._check_cooldown = 60.0  # Minimum seconds between checks
        self._outdated_packages: list[dict] = []
        self._license_issues: list[dict] = []
        self._conflicts: list[dict] = []

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.PROJECT_SCAFFOLDED,
            EventType.BUILD_FAILED,
            EventType.DEPENDENCY_VULNERABILITY,
            EventType.SECURITY_FIX_NEEDED,
            EventType.VALIDATION_ERROR,  # Handle dev server module errors
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide if we should run dependency check.

        Acts when:
        - PROJECT_SCAFFOLDED event received
        - BUILD_FAILED with dependency-related error
        - DEPENDENCY_VULNERABILITY from SecurityScanner
        - VALIDATION_ERROR with module_not_found error type
        - Not in cooldown period
        """
        import time

        # Check cooldown (skip for direct module installs)
        if self._last_check_time:
            elapsed = time.time() - self._last_check_time
            if elapsed < self._check_cooldown:
                # Still allow module_not_found events through
                for event in events:
                    if event.type == EventType.VALIDATION_ERROR:
                        error_data = event.data or {}
                        if error_data.get("error_type") == "module_not_found":
                            return True
                return False

        for event in events:
            # Always act on scaffold
            if event.type == EventType.PROJECT_SCAFFOLDED:
                return True

            # Act on dependency vulnerabilities
            if event.type == EventType.DEPENDENCY_VULNERABILITY:
                return True

            # Handle VALIDATION_ERROR with module_not_found (from dev server)
            if event.type == EventType.VALIDATION_ERROR:
                error_data = event.data or {}
                if error_data.get("error_type") == "module_not_found":
                    return True
                # Also check error message for dependency keywords
                error_msg = event.error_message or ""
                dependency_keywords = [
                    "cannot find module", "module not found",
                    "cannot find package", "missing module",
                ]
                if any(kw.lower() in error_msg.lower() for kw in dependency_keywords):
                    return True

            # Check if build failure is dependency-related
            if event.type == EventType.BUILD_FAILED:
                error_msg = event.error_message or ""
                error_data = event.data.get("error", "") if event.data else ""
                combined = f"{error_msg} {error_data}".lower()
                dependency_keywords = [
                    "cannot find module", "module not found",
                    "peer dep", "peerDependencies",
                    "ERESOLVE", "npm ERR!",
                    "ModuleNotFoundError", "ImportError",
                    "version conflict", "incompatible version",
                ]
                if any(kw.lower() in combined for kw in dependency_keywords):
                    return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Execute dependency management.

        Uses autogen team if available, falls back to direct tool execution.
        """
        # Fast path: Handle direct module installation for module_not_found errors
        for event in events:
            if event.type == EventType.VALIDATION_ERROR:
                error_data = event.data or {}
                if error_data.get("error_type") == "module_not_found":
                    module_name = error_data.get("module_name")
                    if module_name:
                        success = await self._install_missing_module(module_name)
                        if success:
                            return

        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> None:
        """Manage dependencies using autogen DependencyOperator + DependencyValidator team."""
        import time

        self._last_check_time = time.time()

        await self.event_bus.publish(dependency_check_started_event(
            source=self.name,
            working_dir=self.working_dir,
        ))

        try:
            task = self.build_task_prompt(events, extra_context=f"""
## Dependency Management Task

Check and manage dependencies for the project at {self.working_dir}:

1. Run `npm outdated` to find outdated packages
2. Check for peer dependency conflicts
3. Check license compliance (flag GPL, AGPL, SSPL licenses)
4. Auto-update patch versions if safe
5. Report any issues found

Auto-update settings: patch={self.auto_update_patch}, minor={self.auto_update_minor}, major={self.auto_update_major}
""")

            team = self.create_team(
                operator_name="DependencyOperator",
                operator_prompt="""You are a dependency management expert for Node.js and Python projects.

Your role is to check, update, and resolve dependency issues:
- Run npm outdated / pip list --outdated to find stale packages
- Resolve peer dependency conflicts intelligently
- Check for restrictive licenses (GPL, AGPL)
- Install missing modules
- Auto-update safe versions (patch/minor)

When done, say TASK_COMPLETE.""",
                validator_name="DependencyValidator",
                validator_prompt="""You are a dependency safety validator.

Review the dependency changes and verify:
1. No breaking changes from major version updates
2. Peer dependency conflicts are resolved
3. License compliance is maintained
4. All updates are safe (prefer patch over minor over major)

If the dependency state is healthy, say TASK_COMPLETE.
If issues remain, describe what needs attention.""",
                tool_categories=["npm", "pip"],
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                await self.event_bus.publish(dependency_check_passed_event(
                    source=self.name,
                    project_type="node",
                    message="Dependencies checked via autogen team",
                ))
                self.logger.info("dependency_check_passed", mode="autogen")
            else:
                self.logger.warning("dependency_check_issues", mode="autogen",
                                    result=result["result_text"][:500])

        except Exception as e:
            self.logger.error("dependency_check_autogen_error", error=str(e))

    async def _act_legacy(self, events: list[Event]) -> None:
        """Execute dependency management using direct tool calls (legacy)."""
        import time

        self._last_check_time = time.time()
        self._outdated_packages = []
        self._license_issues = []
        self._conflicts = []

        # Publish check started
        await self.event_bus.publish(dependency_check_started_event(
            source=self.name,
            working_dir=self.working_dir,
        ))

        self.logger.info("dependency_check_started", working_dir=self.working_dir)

        project_type = await self._detect_project_type()
        updates_made = 0
        issues_found = 0

        try:
            if project_type == "node":
                # Check outdated packages
                outdated = await self._check_npm_outdated()
                self._outdated_packages = outdated

                if outdated:
                    await self.event_bus.publish(dependency_outdated_event(
                        source=self.name,
                        packages=outdated,
                        count=len(outdated),
                    ))
                    issues_found += len(outdated)

                # Check for peer dependency issues
                conflicts = await self._check_peer_deps()
                self._conflicts = conflicts

                for conflict in conflicts:
                    await self.event_bus.publish(dependency_conflict_event(
                        source=self.name,
                        conflict_type=conflict.get("type"),
                        message=conflict.get("message"),
                    ))
                    issues_found += 1

                # Check licenses
                if self.check_licenses:
                    license_issues = await self._check_npm_licenses()
                    self._license_issues = license_issues

                    for issue in license_issues:
                        await self.event_bus.publish(license_issue_found_event(
                            source=self.name,
                            package=issue.get("package"),
                            license_type=issue.get("license"),
                            severity=issue.get("severity", "medium"),
                            message=issue.get("message"),
                        ))
                        issues_found += 1

                # Auto-update if configured
                if self.auto_update_patch or self.auto_update_minor:
                    updates = await self._auto_update_npm()
                    updates_made = len(updates)

                    for update in updates:
                        await self.event_bus.publish(dependency_updated_event(
                            source=self.name,
                            name=update.get("name"),
                            from_version=update.get("from"),
                            to_version=update.get("to"),
                            update_type=update.get("update_type"),
                        ))

            elif project_type == "python":
                # Check outdated packages
                outdated = await self._check_pip_outdated()
                self._outdated_packages = outdated

                if outdated:
                    await self.event_bus.publish(dependency_outdated_event(
                        source=self.name,
                        packages=outdated,
                        count=len(outdated),
                    ))
                    issues_found += len(outdated)

                # Auto-update if configured
                if self.auto_update_patch:
                    updates = await self._auto_update_pip()
                    updates_made = len(updates)

                    for update in updates:
                        await self.event_bus.publish(dependency_updated_event(
                            source=self.name,
                            name=update.get("name"),
                            from_version=update.get("from"),
                            to_version=update.get("to"),
                            update_type=update.get("update_type"),
                        ))

            # Publish final result
            if issues_found == 0 and updates_made == 0:
                await self.event_bus.publish(dependency_check_passed_event(
                    source=self.name,
                    project_type=project_type,
                    message="All dependencies are up-to-date",
                ))
                self.logger.info("dependency_check_passed")
            else:
                self.logger.info(
                    "dependency_check_complete",
                    issues=issues_found,
                    updates=updates_made,
                    outdated=len(self._outdated_packages),
                    conflicts=len(self._conflicts),
                    license_issues=len(self._license_issues),
                )

        except Exception as e:
            self.logger.error("dependency_check_error", error=str(e))

    async def _detect_project_type(self) -> str:
        """Detect project type (node, python, etc.)."""
        working_path = Path(self.working_dir)

        if (working_path / "package.json").exists():
            return "node"
        elif (working_path / "requirements.txt").exists():
            return "python"
        elif (working_path / "pyproject.toml").exists():
            return "python"
        elif (working_path / "Cargo.toml").exists():
            return "rust"
        elif (working_path / "go.mod").exists():
            return "go"
        else:
            return "unknown"

    async def _check_npm_outdated(self) -> list[dict]:
        """Check for outdated npm packages."""
        outdated = []

        try:
            result = await self.call_tool("npm.outdated", cwd=str(self.working_dir))

            # npm.outdated returns raw JSON; parse it
            raw = result.get("result", "") if isinstance(result, dict) else ""
            if raw:
                try:
                    data = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    data = result
            else:
                data = result

            if isinstance(data, dict) and "error" not in data:
                for pkg_name, info in data.items():
                    if not isinstance(info, dict):
                        continue
                    outdated.append({
                        "name": pkg_name,
                        "current": info.get("current"),
                        "wanted": info.get("wanted"),
                        "latest": info.get("latest"),
                        "type": info.get("type", "dependencies"),
                        "update_type": self._classify_update(
                            info.get("current", "0.0.0"),
                            info.get("latest", "0.0.0")
                        ),
                    })

        except Exception as e:
            self.logger.warning("npm_outdated_error", error=str(e))

        return outdated

    async def _check_peer_deps(self) -> list[dict]:
        """Check for peer dependency conflicts."""
        conflicts = []

        try:
            result = await self.call_tool("npm.list", depth=0, cwd=str(self.working_dir))
            # npm.list returns JSON; peer dep warnings appear in output
            output = result.get("result", "") if isinstance(result, dict) else str(result)
            if isinstance(output, str):
                peer_pattern = r"npm WARN.*peer dep.*"
                matches = re.findall(peer_pattern, output, re.IGNORECASE)
                for match in matches:
                    conflicts.append({
                        "type": "peer_dependency",
                        "message": match,
                    })

        except Exception as e:
            self.logger.warning("npm_ls_error", error=str(e))

        return conflicts

    async def _check_npm_licenses(self) -> list[dict]:
        """Check for restrictive licenses in dependencies."""
        issues = []

        try:
            result = await self.call_tool(
                "npm.npx", command="license-checker",
                args="--json --production", cwd=str(self.working_dir)
            )

            output = result.get("output", "") or result.get("result", "")
            if result.get("success") and output:
                try:
                    data = json.loads(output) if isinstance(output, str) else output
                    for pkg_name, info in data.items():
                        if not isinstance(info, dict):
                            continue
                        license_type = info.get("licenses", "UNKNOWN")

                        if isinstance(license_type, list):
                            licenses = license_type
                        else:
                            licenses = [license_type]

                        for lic in licenses:
                            if lic in RESTRICTIVE_LICENSES:
                                issues.append({
                                    "package": pkg_name,
                                    "license": lic,
                                    "severity": "high" if "GPL" in lic else "medium",
                                    "message": f"Package {pkg_name} uses {lic} license which may have restrictions",
                                })
                            elif lic == "UNKNOWN" or lic == "UNLICENSED":
                                issues.append({
                                    "package": pkg_name,
                                    "license": lic,
                                    "severity": "low",
                                    "message": f"Package {pkg_name} has unknown or no license",
                                })

                except json.JSONDecodeError:
                    pass

        except Exception as e:
            self.logger.debug("license_checker_not_available", error=str(e))

        return issues

    async def _check_pip_outdated(self) -> list[dict]:
        """Check for outdated pip packages."""
        outdated = []

        try:
            result = await self.call_tool("pip.list_outdated", cwd=str(self.working_dir))

            # Parse the result (may be raw JSON string in "result" key)
            raw = result.get("result", "") if isinstance(result, dict) else ""
            if raw and isinstance(raw, str):
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = []
            elif isinstance(result, list):
                data = result
            else:
                data = []

            for pkg in data:
                if not isinstance(pkg, dict):
                    continue
                outdated.append({
                    "name": pkg.get("name"),
                    "current": pkg.get("version"),
                    "latest": pkg.get("latest_version"),
                    "update_type": self._classify_update(
                        pkg.get("version", "0.0.0"),
                        pkg.get("latest_version", "0.0.0")
                    ),
                })

        except Exception as e:
            self.logger.warning("pip_outdated_error", error=str(e))

        return outdated

    async def _auto_update_npm(self) -> list[dict]:
        """Auto-update npm packages based on configuration."""
        updates = []

        for pkg in self._outdated_packages:
            update_type = pkg.get("update_type", "major")

            # Check if we should update based on configuration
            should_update = False
            if update_type == "patch" and self.auto_update_patch:
                should_update = True
            elif update_type == "minor" and self.auto_update_minor:
                should_update = True
            elif update_type == "major" and self.auto_update_major:
                should_update = True

            if should_update:
                try:
                    wanted = pkg.get("wanted", pkg.get("latest"))
                    result = await self.call_tool(
                        "npm.install",
                        package=f"{pkg['name']}@{wanted}",
                        cwd=str(self.working_dir),
                    )

                    if result.get("success"):
                        updates.append({
                            "name": pkg["name"],
                            "from": pkg.get("current"),
                            "to": wanted,
                            "update_type": update_type,
                        })
                        self.logger.info(
                            "package_updated",
                            package=pkg["name"],
                            from_version=pkg.get("current"),
                            to_version=wanted,
                        )

                except Exception as e:
                    self.logger.warning(
                        "package_update_failed",
                        package=pkg["name"],
                        error=str(e),
                    )

        return updates

    async def _auto_update_pip(self) -> list[dict]:
        """Auto-update pip packages based on configuration."""
        updates = []

        for pkg in self._outdated_packages:
            update_type = pkg.get("update_type", "major")

            # Only auto-update patch versions for Python (safer)
            if update_type == "patch" and self.auto_update_patch:
                try:
                    result = await self.call_tool(
                        "pip.install",
                        package=pkg["name"],
                        upgrade=True,
                        cwd=str(self.working_dir),
                    )

                    if result.get("success"):
                        updates.append({
                            "name": pkg["name"],
                            "from": pkg.get("current"),
                            "to": pkg.get("latest"),
                            "update_type": update_type,
                        })
                        self.logger.info(
                            "package_updated",
                            package=pkg["name"],
                            from_version=pkg.get("current"),
                            to_version=pkg.get("latest"),
                        )

                except Exception as e:
                    self.logger.warning(
                        "package_update_failed",
                        package=pkg["name"],
                        error=str(e),
                    )

        return updates

    async def _resolve_conflict_with_llm(self, conflict_error: str) -> Optional[dict]:
        """
        Use LLM to analyze and resolve dependency version conflicts.

        This provides intelligent resolution for complex peer dependency
        issues that simple pattern matching can't handle.

        Args:
            conflict_error: The full error output containing conflict details

        Returns:
            Dict with resolution strategy or None if analysis fails
        """
        from src.tools.claude_code_tool import ClaudeCodeTool

        # Load package.json for context
        package_json_content = ""
        try:
            package_json_path = Path(self.working_dir) / "package.json"
            if package_json_path.exists():
                package_json_content = package_json_path.read_text()
        except Exception:
            pass

        prompt = f"""Analyze and resolve this npm dependency version conflict.

## ERROR OUTPUT:
```
{conflict_error[:3000]}
```

## CURRENT package.json:
```json
{package_json_content[:2000]}
```

## ANALYSIS REQUIRED:

1. **Identify Conflict**: Which packages have incompatible versions?
2. **Root Cause**: What's the actual version mismatch?
3. **Resolution Options**:
   - Option A: Upgrade/downgrade to compatible versions
   - Option B: Use --legacy-peer-deps flag
   - Option C: Override with resolutions/overrides
   - Option D: Use alternative package

4. **Recommended Fix**: Which option is best and why?
5. **Commands to Run**: Exact npm commands to fix

## COMMON RESOLUTION PATTERNS:
- React peer deps: `npm i --legacy-peer-deps` (safe workaround)
- Major version conflict: Pin to older version
- Nested dep conflict: Use `overrides` in package.json
- Types mismatch: Install specific @types version

Respond with this JSON:
```json
{{
    "conflicting_packages": [
        {{"name": "react", "required": "^18.0.0", "installed": "17.0.2"}}
    ],
    "root_cause": "Package X requires React 18 but React 17 is installed",
    "recommended_resolution": "upgrade|downgrade|legacy-peer-deps|override|alternative",
    "commands": [
        "npm install react@18 react-dom@18"
    ],
    "package_json_changes": {{
        "overrides": {{"package": "version"}}
    }},
    "risk_level": "low|medium|high",
    "breaking_changes": ["List of potential breaks"],
    "explanation": "Why this resolution is recommended"
}}
```
"""

        try:
            claude_tool = ClaudeCodeTool(working_dir=self.working_dir)
            result = await claude_tool.execute(
                prompt=prompt,
                skill="environment-config",
                skill_tier="standard",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                resolution = json.loads(json_match.group(1))
                self.logger.info(
                    "llm_conflict_resolution",
                    resolution=resolution.get("recommended_resolution"),
                    risk=resolution.get("risk_level"),
                )
                return resolution

            return None

        except Exception as e:
            self.logger.warning("llm_conflict_resolution_failed", error=str(e))
            return None

    async def resolve_conflicts_intelligently(self, error_output: str) -> bool:
        """
        Attempt to automatically resolve dependency conflicts using LLM guidance.

        Args:
            error_output: The npm error output containing conflict info

        Returns:
            True if conflicts were resolved, False otherwise
        """
        # Get LLM resolution
        resolution = await self._resolve_conflict_with_llm(error_output)

        if not resolution:
            self.logger.warning("no_resolution_from_llm")
            return False

        # Only auto-apply low-risk resolutions
        risk_level = resolution.get("risk_level", "high")
        commands = resolution.get("commands", [])

        if risk_level == "high":
            self.logger.info(
                "high_risk_resolution_needs_manual_review",
                commands=commands,
                breaking_changes=resolution.get("breaking_changes", []),
            )
            # Publish event for manual review
            await self.event_bus.publish(dependency_conflict_event(
                source=self.name,
                conflict_type="version_conflict",
                message=resolution.get("explanation", "Complex version conflict"),
                data={
                    "suggested_resolution": resolution,
                    "requires_manual_review": True,
                },
            ))
            return False

        # Apply low/medium risk resolutions
        if commands:
            self.logger.info(
                "applying_llm_resolution",
                commands=commands,
                risk_level=risk_level,
            )

            for cmd in commands[:3]:  # Limit to 3 commands
                try:
                    if cmd.startswith("npm "):
                        # Strip "npm " prefix and pass rest to npm.run_cmd
                        npm_args = cmd[4:]
                        result = await self.call_tool(
                            "npm.run_cmd", cmd=npm_args, cwd=str(self.working_dir)
                        )

                        if result.get("success"):
                            self.logger.info("resolution_command_succeeded", command=cmd)
                        else:
                            self.logger.warning(
                                "resolution_command_failed",
                                command=cmd,
                                stderr=result.get("output", "")[:500],
                            )
                            return False

                except Exception as e:
                    self.logger.error("resolution_command_error", command=cmd, error=str(e))
                    return False

            return True

        # Apply package.json changes if needed
        package_json_changes = resolution.get("package_json_changes", {})
        if package_json_changes:
            try:
                package_json_path = Path(self.working_dir) / "package.json"
                if package_json_path.exists():
                    pkg = json.loads(package_json_path.read_text())

                    # Apply overrides
                    if "overrides" in package_json_changes:
                        pkg["overrides"] = {**pkg.get("overrides", {}), **package_json_changes["overrides"]}
                        package_json_path.write_text(json.dumps(pkg, indent=2))
                        self.logger.info("package_json_overrides_applied")

                        # Run npm install to apply
                        await self.call_tool("npm.install", cwd=str(self.working_dir))
                        return True

            except Exception as e:
                self.logger.error("package_json_modification_failed", error=str(e))
                return False

        return False

    def _classify_update(self, current: str, target: str) -> str:
        """Classify update type (major, minor, patch)."""
        try:
            current_parts = current.split(".")
            target_parts = target.split(".")

            # Pad with zeros if needed
            while len(current_parts) < 3:
                current_parts.append("0")
            while len(target_parts) < 3:
                target_parts.append("0")

            # Remove any non-numeric suffixes
            current_parts = [re.sub(r"[^0-9].*", "", p) or "0" for p in current_parts[:3]]
            target_parts = [re.sub(r"[^0-9].*", "", p) or "0" for p in target_parts[:3]]

            if int(target_parts[0]) > int(current_parts[0]):
                return "major"
            elif int(target_parts[1]) > int(current_parts[1]):
                return "minor"
            else:
                return "patch"

        except (ValueError, IndexError):
            return "unknown"

    def get_check_summary(self) -> dict:
        """Get summary of last dependency check."""
        return {
            "outdated": len(self._outdated_packages),
            "conflicts": len(self._conflicts),
            "license_issues": len(self._license_issues),
            "packages": [
                {
                    "name": p.get("name"),
                    "current": p.get("current"),
                    "latest": p.get("latest"),
                    "update_type": p.get("update_type"),
                }
                for p in self._outdated_packages
            ],
        }

    async def _install_missing_module(self, module_name: str) -> bool:
        """
        Install a specific missing module.

        This is a fast-path handler for module_not_found errors from the dev server.
        Attempts to install both the package and its TypeScript types.

        Args:
            module_name: Name of the missing module to install

        Returns:
            True if installation succeeded, False otherwise
        """
        self.logger.info("installing_missing_module", module=module_name)

        try:
            # Install the module and its types if TypeScript project
            packages_to_install = [module_name]

            if not module_name.startswith("@types/"):
                types_package = f"@types/{module_name}"
                packages_to_install.append(types_package)

            # Install all packages at once via npm.install
            pkg_str = " ".join(packages_to_install)
            result = await self.call_tool(
                "npm.install", package=pkg_str, cwd=str(self.working_dir)
            )

            if result.get("success"):
                self.logger.info(
                    "module_installed",
                    module=module_name,
                    packages=packages_to_install,
                )

                await self.event_bus.publish(dependency_updated_event(
                    source=self.name,
                    name=module_name,
                    from_version=None,
                    to_version="latest",
                    update_type="install",
                    data={
                        "module": module_name,
                        "action": "installed",
                    },
                ))
                return True
            else:
                self.logger.warning(
                    "module_install_partial_failure",
                    module=module_name,
                    stderr=result.get("output", ""),
                )

                # Try just the main package
                result2 = await self.call_tool(
                    "npm.install", package=module_name, cwd=str(self.working_dir)
                )

                if result2.get("success"):
                    self.logger.info("module_installed", module=module_name)
                    await self.event_bus.publish(dependency_updated_event(
                        source=self.name,
                        name=module_name,
                        from_version=None,
                        to_version="latest",
                        update_type="install",
                        data={
                            "module": module_name,
                            "action": "installed",
                        },
                    ))
                    return True

                self.logger.warning(
                    "module_install_failed",
                    module=module_name,
                    error=result2.get("output", ""),
                )
                return False

        except Exception as e:
            self.logger.error(
                "module_install_error",
                module=module_name,
                error=str(e),
            )
            return False
