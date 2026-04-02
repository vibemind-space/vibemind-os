"""
Electron-specific validation for generated Electron projects.

Checks for:
- Electron module resolution (the bug we encountered)
- Main process startup
- Preload script validity
- IPC handler registration
- Build output configuration
"""

import json
import re
import tempfile
from pathlib import Path
from typing import Optional

from .base_validator import (
    BaseValidator,
    ValidationResult,
    ValidationFailure,
    ValidationSeverity,
)


# Test script that validates Electron can start properly
ELECTRON_STARTUP_TEST = '''
// Auto-generated Electron startup validation test
const startTime = Date.now();

try {
    const electron = require('electron');

    // Check if electron module resolved correctly (not a path string)
    if (typeof electron === 'string') {
        console.log('VALIDATION:FAIL:electron_module:' + JSON.stringify({
            error: 'electron module resolved to path string instead of module object',
            value: electron.substring(0, 100),
            suggestion: 'Check bundler externals config and electron package installation'
        }));
        process.exit(1);
    }

    // Check for required APIs
    const requiredAPIs = ['app', 'BrowserWindow', 'ipcMain'];
    const missingAPIs = requiredAPIs.filter(api => !electron[api]);

    if (missingAPIs.length > 0) {
        console.log('VALIDATION:FAIL:electron_apis:' + JSON.stringify({
            error: 'Missing required Electron APIs',
            missing: missingAPIs,
            available: Object.keys(electron).slice(0, 20)
        }));
        process.exit(1);
    }

    // Check process.type
    if (typeof process.type === 'undefined') {
        console.log('VALIDATION:WARN:process_type:' + JSON.stringify({
            warning: 'process.type is undefined - may indicate improper Electron initialization',
            expected: 'browser'
        }));
    }

    // Try to initialize app
    const { app } = electron;

    if (typeof app.whenReady !== 'function') {
        console.log('VALIDATION:FAIL:app_whenReady:' + JSON.stringify({
            error: 'app.whenReady is not a function',
            appType: typeof app,
            appKeys: Object.keys(app || {}).slice(0, 10)
        }));
        process.exit(1);
    }

    // Quick startup test with timeout
    const timeout = setTimeout(() => {
        console.log('VALIDATION:FAIL:startup_timeout:' + JSON.stringify({
            error: 'Electron app.whenReady() timed out after 10 seconds'
        }));
        process.exit(1);
    }, 10000);

    app.whenReady().then(() => {
        clearTimeout(timeout);
        const elapsed = Date.now() - startTime;
        console.log('VALIDATION:PASS:electron_startup:' + JSON.stringify({
            message: 'Electron started successfully',
            elapsed_ms: elapsed,
            electron_version: process.versions.electron,
            chrome_version: process.versions.chrome,
            node_version: process.versions.node
        }));
        app.quit();
    }).catch((err) => {
        clearTimeout(timeout);
        console.log('VALIDATION:FAIL:app_ready:' + JSON.stringify({
            error: 'app.whenReady() rejected',
            message: err.message
        }));
        process.exit(1);
    });

} catch (err) {
    console.log('VALIDATION:FAIL:startup_error:' + JSON.stringify({
        error: 'Exception during Electron startup test',
        message: err.message,
        stack: err.stack
    }));
    process.exit(1);
}
'''


class ElectronValidator(BaseValidator):
    """
    Validates Electron project configuration and startup.

    Checks:
    1. electron-vite or similar config has correct externals
    2. Bundled output doesn't inline electron
    3. Electron can actually start
    4. Preload script exists and has IPC bridge
    """

    @property
    def name(self) -> str:
        return "Electron Validator"

    @property
    def check_type(self) -> str:
        return "electron"

    def is_applicable(self) -> bool:
        """Check if this is an Electron project."""
        package_json = self.project_dir / "package.json"
        if not package_json.exists():
            return False

        try:
            with open(package_json) as f:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                return "electron" in deps
        except Exception:
            return False

    async def validate(self) -> ValidationResult:
        """Run all Electron validation checks."""
        result = self._create_result()
        start_time = __import__("time").time()

        # Check 1: Validate bundler configuration
        config_failures = await self._check_bundler_config()
        for failure in config_failures:
            result.add_failure(failure)

        # Check 2: Validate bundled output doesn't inline electron
        output_failures = await self._check_bundled_output()
        for failure in output_failures:
            result.add_failure(failure)

        # Check 3: Check preload script
        preload_failures = await self._check_preload_script()
        for failure in preload_failures:
            result.add_failure(failure)

        # Check 4: Run startup test (only if no blocking errors so far)
        if result.error_count == 0:
            startup_failures = await self._check_electron_startup()
            for failure in startup_failures:
                result.add_failure(failure)

        result.execution_time_ms = (__import__("time").time() - start_time) * 1000

        if result.passed:
            result.checks_passed.append(self.check_type)

        return result

    async def _check_bundler_config(self) -> list[ValidationFailure]:
        """Check that bundler config has electron as external."""
        failures = []

        # Look for common config files
        config_files = [
            "electron.vite.config.ts",
            "electron.vite.config.js",
            "vite.config.ts",
            "vite.config.js",
            "webpack.config.js",
            "rollup.config.js",
        ]

        for config_name in config_files:
            config_path = self.project_dir / config_name
            if config_path.exists():
                content = config_path.read_text(encoding="utf-8", errors="replace")

                # Check for electron in externals
                if "electron" not in content.lower():
                    failures.append(self._create_failure(
                        f"Config file {config_name} may not have 'electron' in externals",
                        severity=ValidationSeverity.WARNING,
                        file_path=str(config_path),
                        suggested_fix="Add 'electron' to the rollupOptions.external array in your bundler config",
                    ))

                # Check for proper main process config
                if "electron.vite" in config_name:
                    if "external:" not in content and "external :" not in content:
                        failures.append(self._create_failure(
                            f"electron-vite config missing external configuration",
                            severity=ValidationSeverity.ERROR,
                            file_path=str(config_path),
                            suggested_fix="Add external: ['electron', 'electron-store'] to main.build.rollupOptions",
                            raw_output=content[:500],
                        ))

        return failures

    async def _check_bundled_output(self) -> list[ValidationFailure]:
        """Check that bundled main.js doesn't have electron inlined incorrectly."""
        failures = []

        # Find main entry point
        package_json = self.project_dir / "package.json"
        main_entry = "dist/main/main.js"

        if package_json.exists():
            try:
                pkg = json.load(open(package_json))
                main_entry = pkg.get("main", main_entry)
            except Exception:
                pass

        main_path = self.project_dir / main_entry
        if not main_path.exists():
            failures.append(self._create_failure(
                f"Main entry point not found: {main_entry}",
                severity=ValidationSeverity.ERROR,
                file_path=str(main_path),
                suggested_fix="Run 'npm run build' to generate the main entry point",
            ))
            return failures

        content = main_path.read_text(encoding="utf-8", errors="replace")

        # Check for proper electron require pattern
        if 'require("electron")' not in content and "require('electron')" not in content:
            failures.append(self._create_failure(
                "Bundled main.js doesn't contain require('electron')",
                severity=ValidationSeverity.WARNING,
                file_path=str(main_path),
                suggested_fix="Check bundler externals - electron should not be bundled",
            ))

        # Check for signs of electron being bundled (bad patterns)
        bad_patterns = [
            (r'module\.exports\s*=\s*require\("electron"\)', "electron re-exported"),
            (r'getElectronPath', "electron npm package code bundled"),
            (r'ELECTRON_OVERRIDE_DIST_PATH', "electron npm package code bundled"),
        ]

        for pattern, description in bad_patterns:
            if re.search(pattern, content):
                failures.append(self._create_failure(
                    f"Bundled code contains '{description}' - electron npm package may be inlined",
                    severity=ValidationSeverity.ERROR,
                    file_path=str(main_path),
                    suggested_fix="Add 'electron' to external in bundler config to prevent inlining",
                    raw_output=content[:200],
                ))
                break

        return failures

    async def _check_preload_script(self) -> list[ValidationFailure]:
        """Check preload script exists and has IPC bridge."""
        failures = []

        # Common preload locations
        preload_paths = [
            "dist/preload/preload.js",
            "preload/preload.js",
            "src/preload/preload.js",
            "src/preload/preload.ts",
        ]

        preload_found = None
        for path in preload_paths:
            full_path = self.project_dir / path
            if full_path.exists():
                preload_found = full_path
                break

        if not preload_found:
            failures.append(self._create_failure(
                "No preload script found",
                severity=ValidationSeverity.WARNING,
                suggested_fix="Create a preload script at src/preload/preload.ts with contextBridge.exposeInMainWorld",
            ))
            return failures

        content = preload_found.read_text(encoding="utf-8", errors="replace")

        # Check for contextBridge usage
        if "contextBridge" not in content:
            failures.append(self._create_failure(
                "Preload script doesn't use contextBridge",
                severity=ValidationSeverity.WARNING,
                file_path=str(preload_found),
                suggested_fix="Use contextBridge.exposeInMainWorld to expose IPC methods",
            ))

        # Check for ipcRenderer
        if "ipcRenderer" not in content:
            failures.append(self._create_failure(
                "Preload script doesn't import ipcRenderer",
                severity=ValidationSeverity.WARNING,
                file_path=str(preload_found),
                suggested_fix="Import ipcRenderer from 'electron' to enable IPC communication",
            ))

        return failures

    async def _check_electron_startup(self) -> list[ValidationFailure]:
        """Run actual Electron startup test."""
        failures = []

        # Create temp test file
        test_file = self.project_dir / "_electron_validation_test.js"

        try:
            test_file.write_text(ELECTRON_STARTUP_TEST, encoding="utf-8")

            # Find electron binary
            electron_bin = self._find_electron_binary()
            if not electron_bin:
                failures.append(self._create_failure(
                    "Could not find electron binary",
                    severity=ValidationSeverity.ERROR,
                    suggested_fix="Run 'npm install' to install electron",
                ))
                return failures

            # Run test
            exit_code, stdout, stderr = await self._run_command(
                [str(electron_bin), str(test_file)],
                timeout=30.0
            )

            # Parse output
            for line in stdout.split('\n'):
                if line.startswith('VALIDATION:'):
                    parts = line.split(':', 3)
                    if len(parts) >= 4:
                        status = parts[1]
                        check_name = parts[2]
                        try:
                            data = json.loads(parts[3])
                        except json.JSONDecodeError:
                            data = {"raw": parts[3]}

                        if status == "FAIL":
                            failures.append(self._create_failure(
                                data.get("error", f"Electron check {check_name} failed"),
                                severity=ValidationSeverity.ERROR,
                                error_code=f"ELECTRON_{check_name.upper()}",
                                raw_output=json.dumps(data, indent=2),
                                suggested_fix=data.get("suggestion"),
                            ))
                        elif status == "WARN":
                            failures.append(self._create_failure(
                                data.get("warning", f"Electron check {check_name} warning"),
                                severity=ValidationSeverity.WARNING,
                                error_code=f"ELECTRON_{check_name.upper()}",
                            ))

            # Check for crash/error
            if exit_code != 0 and not any(f.error_code for f in failures):
                failures.append(self._create_failure(
                    f"Electron startup test failed with exit code {exit_code}",
                    severity=ValidationSeverity.ERROR,
                    raw_output=f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                    suggested_fix="Check the raw output for error details",
                ))

        finally:
            # Cleanup
            if test_file.exists():
                test_file.unlink()

        return failures

    def _find_electron_binary(self) -> Optional[Path]:
        """Find the electron binary in node_modules."""
        import platform

        electron_dir = self.project_dir / "node_modules" / "electron" / "dist"

        if platform.system() == "Windows":
            binary = electron_dir / "electron.exe"
        elif platform.system() == "Darwin":
            binary = electron_dir / "Electron.app" / "Contents" / "MacOS" / "Electron"
        else:
            binary = electron_dir / "electron"

        if binary.exists():
            return binary

        return None
