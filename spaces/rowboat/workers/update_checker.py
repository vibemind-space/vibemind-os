"""
Rowboat Update Checker + Auto-Pull

Periodically checks GitHub for new Rowboat releases. When a newer version
is found, automatically pulls it (stash → pull → stash pop) and notifies
the Electron UI.

Architecture:
  Python daemon thread  ──check──→  GitHub API (releases/latest)
        ↓ (if newer)
  auto-pull: git stash → git pull origin main → git stash pop
        ↓
  rowboat_update_applied  ──→  Electron main.js  ──→  Tab badge
"""

import os
import json
import time
import logging
import subprocess
import threading
import urllib.request
import urllib.error
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

# Default: check every 6 hours
DEFAULT_CHECK_INTERVAL = 6 * 60 * 60

# GitHub API endpoint (fetch all releases to include pre-releases)
GITHUB_RELEASES_URL = "https://api.github.com/repos/rowboatlabs/rowboat/releases?per_page=1"


class RowboatUpdateChecker:
    """
    Checks GitHub for new Rowboat releases and calls a callback
    when a newer version is found.

    Usage:
        checker = RowboatUpdateChecker(send_message_fn)
        checker.start()  # starts daemon thread
    """

    def __init__(self, send_message: Callable[[Dict[str, Any]], None]):
        self._send_message = send_message
        self._interval = int(os.getenv("ROWBOAT_UPDATE_CHECK_INTERVAL", str(DEFAULT_CHECK_INTERVAL)))
        self._auto_pull = os.getenv("ROWBOAT_AUTO_PULL", "true").lower() == "true"
        self._current_version: Optional[str] = None
        self._latest_version: Optional[str] = None
        self._submodule_path = self._find_submodule_path()
        self._running = False
        self._thread = None

    def _find_submodule_path(self) -> str:
        """Locate the Rowboat submodule directory."""
        # Standard location relative to this file
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # roarboot/
        submodule = os.path.join(base, "rowboat")
        if os.path.isdir(submodule):
            return submodule
        # Fallback: relative to project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(base)))
        return os.path.join(project_root, "python", "spaces", "roarboot", "rowboat")

    def _get_current_version(self) -> Optional[str]:
        """Get the current submodule version via git rev-parse or HEAD file."""
        if not os.path.isdir(self._submodule_path):
            logger.warning(f"[UpdateChecker] Submodule path does not exist: {self._submodule_path}")
            return None

        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": ""}

        # Fast path: rev-parse just reads .git/HEAD — should be instant
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=3,
                cwd=self._submodule_path,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and result.stdout.strip():
                version = result.stdout.strip()
                logger.debug(f"[UpdateChecker] Current version (commit): {version}")
                return version
        except subprocess.TimeoutExpired:
            logger.debug("[UpdateChecker] git rev-parse timed out, trying file read")
        except Exception:
            pass

        # Fallback: read the HEAD ref directly from the filesystem
        try:
            git_path = os.path.join(self._submodule_path, ".git")
            # Submodules have a .git file pointing to the real gitdir
            if os.path.isfile(git_path):
                with open(git_path, "r") as f:
                    content = f.read().strip()
                if content.startswith("gitdir:"):
                    gitdir = content[7:].strip()
                    if not os.path.isabs(gitdir):
                        gitdir = os.path.normpath(os.path.join(self._submodule_path, gitdir))
                    head_file = os.path.join(gitdir, "HEAD")
                else:
                    head_file = None
            elif os.path.isdir(git_path):
                head_file = os.path.join(git_path, "HEAD")
            else:
                head_file = None

            if head_file and os.path.isfile(head_file):
                with open(head_file, "r") as f:
                    head_content = f.read().strip()
                if head_content.startswith("ref:"):
                    # HEAD points to a branch — resolve it
                    ref_path = head_content[4:].strip()
                    ref_file = os.path.join(os.path.dirname(head_file), ref_path)
                    if os.path.isfile(ref_file):
                        with open(ref_file, "r") as f:
                            version = f.read().strip()[:10]
                            logger.debug(f"[UpdateChecker] Current version (file): {version}")
                            return version
                else:
                    # Detached HEAD — it's a commit hash
                    version = head_content[:10]
                    logger.debug(f"[UpdateChecker] Current version (detached): {version}")
                    return version
        except Exception as e:
            logger.warning(f"[UpdateChecker] Failed to read HEAD file: {e}")

        logger.warning(f"[UpdateChecker] Could not determine version for {self._submodule_path}")
        return None

    def _get_latest_release(self) -> Optional[Dict[str, Any]]:
        """Fetch the latest release from GitHub API."""
        try:
            req = urllib.request.Request(
                GITHUB_RELEASES_URL,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "VibeMind-UpdateChecker/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode())
                # API returns a list (all releases incl. pre-releases)
                data = raw[0] if isinstance(raw, list) and raw else raw
                return {
                    "tag_name": data.get("tag_name", ""),
                    "name": data.get("name", ""),
                    "html_url": data.get("html_url", ""),
                    "published_at": data.get("published_at", ""),
                    "body": data.get("body", "")[:500],  # Truncate changelog
                    "prerelease": data.get("prerelease", False),
                }
        except urllib.error.HTTPError as e:
            logger.warning(f"[UpdateChecker] GitHub API error: {e.code}")
        except Exception as e:
            logger.warning(f"[UpdateChecker] Failed to fetch latest release: {e}")
        return None

    def _is_newer(self, current: str, latest_tag: str) -> bool:
        """
        Compare versions. Simple check: if the latest tag is different
        from the current git describe output, an update is available.
        Handles tags like 'v0.1.57' and git describe like 'v0.1.57-3-gabcdef'.
        """
        if not current or not latest_tag:
            return False

        # Extract base version from git describe (strip commit suffix)
        current_base = current.split("-")[0] if "-" in current else current

        # Normalize: strip leading 'v'
        current_norm = current_base.lstrip("v")
        latest_norm = latest_tag.lstrip("v")

        if current_norm == latest_norm:
            return False

        # Try semver comparison
        try:
            current_parts = [int(x) for x in current_norm.split(".")]
            latest_parts = [int(x) for x in latest_norm.split(".")]
            return latest_parts > current_parts
        except (ValueError, AttributeError):
            # Fallback: string comparison
            return latest_norm != current_norm

    def _run_git(self, *args, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run a git command in the submodule directory (non-interactive, no window)."""
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": ""}
        return subprocess.run(
            ["git", *args],
            capture_output=True, text=True, timeout=timeout,
            cwd=self._submodule_path,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _auto_pull_update(self) -> Dict[str, Any]:
        """
        Auto-pull latest release: fetch tags, checkout the target tag.

        Submodules run in detached HEAD, so git pull doesn't work.
        Instead: fetch → checkout tag.

        Returns:
            Dict with keys: success, old_version, new_version, error
        """
        old_version = self._current_version or "unknown"
        target_tag = self._latest_version

        if not target_tag:
            return {"success": False, "old_version": old_version,
                    "new_version": old_version, "error": "No target version"}

        try:
            # 1. Fetch latest tags
            logger.info("[UpdateChecker] Fetching tags from origin...")
            fetch_result = self._run_git("fetch", "--tags", timeout=30)
            if fetch_result.returncode != 0:
                return {"success": False, "old_version": old_version,
                        "new_version": old_version, "error": f"Fetch failed: {fetch_result.stderr.strip()}"}

            # 2. Checkout the target tag (detached HEAD)
            logger.info(f"[UpdateChecker] Checking out {target_tag}...")
            checkout_result = self._run_git("checkout", target_tag, timeout=15)
            if checkout_result.returncode != 0:
                return {"success": False, "old_version": old_version,
                        "new_version": old_version, "error": f"Checkout failed: {checkout_result.stderr.strip()}"}

            # 3. Verify
            new_version = self._get_current_version() or target_tag
            logger.info(f"[UpdateChecker] Auto-update complete: {old_version} -> {new_version}")

            return {"success": True, "old_version": old_version, "new_version": new_version, "error": None}

        except subprocess.TimeoutExpired:
            return {"success": False, "old_version": old_version,
                    "new_version": old_version, "error": "Git operation timed out"}
        except Exception as e:
            return {"success": False, "old_version": old_version,
                    "new_version": old_version, "error": str(e)}

    def check_once(self) -> Optional[Dict[str, Any]]:
        """
        Perform a single update check.
        Returns release info if an update is available, None otherwise.
        """
        logger.info("[UpdateChecker] Running update check...")

        self._current_version = self._get_current_version()
        if not self._current_version:
            logger.warning("[UpdateChecker] Cannot determine current version — skipping check")
            return None

        logger.info(f"[UpdateChecker] Current local version: {self._current_version}")

        release = self._get_latest_release()
        if not release:
            logger.info("[UpdateChecker] GitHub API returned no releases")
            return None

        latest_tag = release["tag_name"]
        logger.info(f"[UpdateChecker] Latest GitHub release: {latest_tag} ({release.get('name', 'unnamed')})")

        if not latest_tag:
            logger.warning("[UpdateChecker] Release tag_name is empty — cannot compare versions")
            return None

        if self._is_newer(self._current_version, latest_tag):
            self._latest_version = latest_tag
            logger.info(f"[UpdateChecker] Update available: {self._current_version} -> {latest_tag}")
            return release

        logger.info(f"[UpdateChecker] Up to date (local={self._current_version}, remote={latest_tag})")
        return None

    def check_now(self) -> Optional[Dict[str, Any]]:
        """
        Trigger an immediate update check from outside the timer loop.
        Can be called from an IPC handler. Returns the check result.
        """
        logger.info("[UpdateChecker] Manual check triggered")
        try:
            release = self.check_once()
            if release:
                self._handle_release(release)
            else:
                self._send_message({
                    "type": "rowboat_update_check_result",
                    "up_to_date": True,
                    "current_version": self._current_version or "unknown",
                })
            return release
        except Exception as e:
            logger.error(f"[UpdateChecker] Manual check failed: {e}")
            self._send_message({
                "type": "rowboat_update_check_result",
                "up_to_date": False,
                "error": str(e),
            })
            return None

    def _handle_release(self, release: Dict[str, Any]):
        """Handle a detected release: auto-pull or notify."""
        if self._auto_pull:
            result = self._auto_pull_update()
            if result["success"]:
                self._send_message({
                    "type": "rowboat_update_applied",
                    "old_version": result["old_version"],
                    "new_version": result["new_version"],
                    "release_name": release.get("name", ""),
                    "changelog": release.get("body", ""),
                })
            else:
                logger.warning(f"[UpdateChecker] Auto-pull failed: {result['error']}")
                self._send_message({
                    "type": "rowboat_update_available",
                    "current_version": self._current_version,
                    "latest_version": release["tag_name"],
                    "release_name": release.get("name", ""),
                    "release_url": release.get("html_url", ""),
                    "changelog": release.get("body", ""),
                    "auto_pull_error": result["error"],
                })
        else:
            self._send_message({
                "type": "rowboat_update_available",
                "current_version": self._current_version,
                "latest_version": release["tag_name"],
                "release_name": release.get("name", ""),
                "release_url": release.get("html_url", ""),
                "changelog": release.get("body", ""),
            })

    def _run_loop(self):
        """Main loop: check periodically, auto-pull if enabled, and notify."""
        # Short delay to let the app stabilize
        time.sleep(10)

        # First check — log result clearly
        logger.info("[UpdateChecker] Running first update check after startup...")
        try:
            release = self.check_once()
            if release:
                logger.info(f"[UpdateChecker] First check: UPDATE AVAILABLE ({release['tag_name']})")
                self._handle_release(release)
            else:
                logger.info(f"[UpdateChecker] First check: no update available (current={self._current_version or 'unknown'})")
        except Exception as e:
            logger.error(f"[UpdateChecker] First check failed: {e}")

        # Wait for next interval, then loop
        time.sleep(self._interval)

        while self._running:
            try:
                release = self.check_once()
                if release:
                    self._handle_release(release)
            except Exception as e:
                logger.error(f"[UpdateChecker] Check failed: {e}")

            # Wait for next check
            time.sleep(self._interval)

    def start(self):
        """Start the update checker as a daemon thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="rowboat-update-checker",
        )
        self._thread.start()
        logger.info(f"[UpdateChecker] Started (interval={self._interval}s, auto_pull={self._auto_pull})")

    def stop(self):
        """Stop the update checker."""
        self._running = False
