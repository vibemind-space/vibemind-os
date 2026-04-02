"""
Runtime Validator - Tests Electron app runtime behavior.

Validates that:
- The app starts correctly in Electron context (not Node.js mode)
- process.type is 'browser' (main) or 'renderer'
- electron module exports are available
- No ELECTRON_RUN_AS_NODE interference
"""

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

from .base_validator import (
    BaseValidator,
    ValidationResult,
    ValidationFailure,
    ValidationSeverity,
)

logger = structlog.get_logger(__name__)


# Test script that runs inside Electron to diagnose runtime issues
RUNTIME_TEST_SCRIPT = '''
// Runtime diagnostic script for Electron apps
const fs = require('fs');
const path = require('path');

// Collect diagnostics
const diagnostics = {
    timestamp: new Date().toISOString(),
    processType: process.type,
    electronRunAsNode: process.env.ELECTRON_RUN_AS_NODE,
    nodeVersion: process.version,
    platform: process.platform,
    electronPath: null,
    electronType: null,
    appModule: null,
    errors: []
};

try {
    const electron = require('electron');
    diagnostics.electronType = typeof electron;

    if (typeof electron === 'string') {
        // electron module returned path string instead of module
        diagnostics.electronPath = electron;
        diagnostics.errors.push({
            code: 'ELECTRON_PATH_STRING',
            message: 'require("electron") returned a path string, not the electron module',
            detail: 'This typically happens when ELECTRON_RUN_AS_NODE=1 is set'
        });
    } else if (typeof electron === 'object') {
        // Check if app is available
        diagnostics.appModule = typeof electron.app;

        if (electron.app) {
            diagnostics.appName = electron.app.name || 'unknown';
            diagnostics.appVersion = electron.app.getVersion ? electron.app.getVersion() : 'unknown';
        }

        // Check other key exports
        diagnostics.hasApp = !!electron.app;
        diagnostics.hasBrowserWindow = !!electron.BrowserWindow;
        diagnostics.hasIpcMain = !!electron.ipcMain;
    }
} catch (err) {
    diagnostics.errors.push({
        code: 'ELECTRON_REQUIRE_ERROR',
        message: err.message,
        stack: err.stack
    });
}

// Check for common environment issues
if (process.env.ELECTRON_RUN_AS_NODE === '1') {
    diagnostics.errors.push({
        code: 'ELECTRON_RUN_AS_NODE_SET',
        message: 'ELECTRON_RUN_AS_NODE=1 is set, Electron runs in Node.js mode',
        detail: 'VSCode and other tools may set this. Create a helper script to unset it.'
    });
}

if (process.type === undefined) {
    diagnostics.errors.push({
        code: 'PROCESS_TYPE_UNDEFINED',
        message: 'process.type is undefined - not running in Electron context',
        detail: 'The app is running as plain Node.js, not Electron'
    });
}

// Output diagnostics as JSON
console.log('RUNTIME_DIAGNOSTICS_START');
console.log(JSON.stringify(diagnostics, null, 2));
console.log('RUNTIME_DIAGNOSTICS_END');

// Exit with appropriate code
if (diagnostics.errors.length > 0) {
    process.exit(1);
} else {
    // Signal success but exit quickly for diagnostic mode
    if (process.type === 'browser' && electron && electron.app) {
        electron.app.on('ready', () => {
            console.log('APP_READY');
            // Wait briefly to ensure app initialized
            setTimeout(() => {
                electron.app.quit();
            }, 500);
        });
    } else {
        process.exit(0);
    }
}
'''


@dataclass
class RuntimeDiagnostics:
    """Parsed runtime diagnostics from test script."""
    process_type: Optional[str] = None
    electron_run_as_node: Optional[str] = None
    electron_type: Optional[str] = None
    electron_path: Optional[str] = None
    has_app: bool = False
    has_browser_window: bool = False
    has_ipc_main: bool = False
    errors: list[dict] = field(default_factory=list)
    raw_output: str = ""
    exit_code: int = -1

    @property
    def is_healthy(self) -> bool:
        """Check if runtime is healthy."""
        return (
            self.process_type in ('browser', 'renderer') and
            self.electron_type == 'object' and
            len(self.errors) == 0
        )

    @classmethod
    def from_output(cls, output: str, exit_code: int) -> "RuntimeDiagnostics":
        """Parse diagnostics from script output."""
        diagnostics = cls(raw_output=output, exit_code=exit_code)

        # Extract JSON from output
        match = re.search(
            r'RUNTIME_DIAGNOSTICS_START\s*(.*?)\s*RUNTIME_DIAGNOSTICS_END',
            output,
            re.DOTALL
        )

        if match:
            try:
                data = json.loads(match.group(1))
                diagnostics.process_type = data.get('processType')
                diagnostics.electron_run_as_node = data.get('electronRunAsNode')
                diagnostics.electron_type = data.get('electronType')
                diagnostics.electron_path = data.get('electronPath')
                diagnostics.has_app = data.get('hasApp', False)
                diagnostics.has_browser_window = data.get('hasBrowserWindow', False)
                diagnostics.has_ipc_main = data.get('hasIpcMain', False)
                diagnostics.errors = data.get('errors', [])
            except json.JSONDecodeError as e:
                diagnostics.errors.append({
                    'code': 'JSON_PARSE_ERROR',
                    'message': f'Failed to parse diagnostics: {e}'
                })

        return diagnostics


# Known error patterns and their fixes
KNOWN_ERROR_PATTERNS = [
    {
        'pattern': r"Cannot read properties of undefined \(reading '(whenReady|on|quit)'\)",
        'code': 'APP_UNDEFINED',
        'message': 'electron.app is undefined',
        'cause': 'ELECTRON_RUN_AS_NODE=1 or running as Node.js instead of Electron',
        'fix_type': 'helper_script',
        'fix_description': 'Create a helper script that removes ELECTRON_RUN_AS_NODE before spawning Electron',
    },
    {
        'pattern': r'Electron failed to install correctly',
        'code': 'ELECTRON_INSTALL_FAILED',
        'message': 'Electron binary not found',
        'cause': 'npm install did not download Electron binary',
        'fix_type': 'reinstall',
        'fix_description': 'Delete node_modules/electron and run npm install again',
    },
    {
        'pattern': r'Module not found.*electron',
        'code': 'ELECTRON_MODULE_NOT_FOUND',
        'message': 'Cannot find electron module',
        'cause': 'electron not installed or path issue',
        'fix_type': 'reinstall',
        'fix_description': 'Run npm install electron',
    },
    {
        'pattern': r'ENOENT.*electron',
        'code': 'ELECTRON_BINARY_NOT_FOUND',
        'message': 'Electron executable not found',
        'cause': 'Electron binary not downloaded',
        'fix_type': 'postinstall',
        'fix_description': 'Run node node_modules/electron/install.js',
    },
]


class RuntimeValidator(BaseValidator):
    """
    Validates Electron app runtime behavior.

    Runs a diagnostic script inside the Electron process to verify:
    - Electron is running in proper mode (not Node.js mode)
    - All required Electron modules are available
    - No environment variable interference
    """

    def __init__(
        self,
        project_dir: str,
        timeout: float = 10.0,
        clean_env: bool = True,
    ):
        """
        Initialize runtime validator.

        Args:
            project_dir: Path to the Electron project
            timeout: Timeout for runtime test in seconds
            clean_env: Whether to clean problematic env vars
        """
        super().__init__(project_dir)
        self.timeout = timeout
        self.clean_env = clean_env
        self.logger = logger.bind(component="runtime_validator")

    @property
    def name(self) -> str:
        return "Runtime Validator"

    @property
    def check_type(self) -> str:
        return "runtime"

    def is_applicable(self) -> bool:
        """Check if this is an Electron project."""
        package_json = self.project_dir / "package.json"
        if not package_json.exists():
            return False

        try:
            with open(package_json) as f:
                data = json.load(f)
            deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
            return 'electron' in deps
        except Exception:
            return False

    async def validate(self) -> ValidationResult:
        """
        Run runtime validation.

        Returns:
            ValidationResult with any runtime failures
        """
        import time
        start_time = time.time()
        result = self._create_result()

        # Check if Electron is installed
        electron_path = self._find_electron_binary()
        if not electron_path:
            result.add_failure(self._create_failure(
                "Electron binary not found",
                severity=ValidationSeverity.ERROR,
                error_code="ELECTRON_NOT_FOUND",
                suggested_fix="Run 'npm install' to install Electron",
            ))
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result

        # Create diagnostic test script
        test_script_path = self.project_dir / "_runtime_test.js"
        try:
            with open(test_script_path, 'w') as f:
                f.write(RUNTIME_TEST_SCRIPT)

            # Run the test
            diagnostics = await self._run_runtime_test(electron_path, test_script_path)

            # Analyze results
            self._analyze_diagnostics(diagnostics, result)

        finally:
            # Clean up test script
            if test_script_path.exists():
                test_script_path.unlink()

        result.execution_time_ms = (time.time() - start_time) * 1000

        if result.passed:
            result.checks_passed.append(self.check_type)
            self.logger.info("runtime_validation_passed")
        else:
            self.logger.warning(
                "runtime_validation_failed",
                error_count=result.error_count,
            )

        return result

    def _find_electron_binary(self) -> Optional[Path]:
        """Find the Electron binary path."""
        # Check node_modules/electron
        electron_module = self.project_dir / "node_modules" / "electron"
        if not electron_module.exists():
            return None

        # Read path from electron module
        path_file = electron_module / "path.txt"
        if path_file.exists():
            rel_path = path_file.read_text().strip()
            electron_binary = electron_module / "dist" / rel_path
            if electron_binary.exists():
                return electron_binary

        # Fallback: try common locations
        if sys.platform == 'win32':
            candidates = [
                electron_module / "dist" / "electron.exe",
            ]
        elif sys.platform == 'darwin':
            candidates = [
                electron_module / "dist" / "Electron.app" / "Contents" / "MacOS" / "Electron",
            ]
        else:
            candidates = [
                electron_module / "dist" / "electron",
            ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    async def _run_runtime_test(
        self,
        electron_path: Path,
        test_script: Path,
    ) -> RuntimeDiagnostics:
        """
        Run the diagnostic script in Electron.

        Args:
            electron_path: Path to Electron binary
            test_script: Path to test script

        Returns:
            RuntimeDiagnostics from the test
        """
        # Prepare clean environment
        env = os.environ.copy()

        if self.clean_env:
            # Remove variables that interfere with Electron
            for var in ['ELECTRON_RUN_AS_NODE', 'ELECTRON_NO_ATTACH_CONSOLE']:
                env.pop(var, None)

        try:
            process = await asyncio.create_subprocess_exec(
                str(electron_path),
                str(test_script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_dir),
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            output = stdout.decode('utf-8', errors='replace')
            error_output = stderr.decode('utf-8', errors='replace')

            # Combine outputs for analysis
            full_output = output + "\n" + error_output

            return RuntimeDiagnostics.from_output(full_output, process.returncode or 0)

        except asyncio.TimeoutError:
            return RuntimeDiagnostics(
                raw_output=f"Timeout after {self.timeout}s",
                exit_code=-1,
                errors=[{
                    'code': 'TIMEOUT',
                    'message': f'Runtime test timed out after {self.timeout}s',
                }]
            )
        except Exception as e:
            return RuntimeDiagnostics(
                raw_output=str(e),
                exit_code=-1,
                errors=[{
                    'code': 'EXECUTION_ERROR',
                    'message': str(e),
                }]
            )

    def _analyze_diagnostics(
        self,
        diagnostics: RuntimeDiagnostics,
        result: ValidationResult,
    ) -> None:
        """
        Analyze diagnostics and add failures to result.

        Args:
            diagnostics: Parsed runtime diagnostics
            result: ValidationResult to add failures to
        """
        # Check for known error patterns in raw output
        for pattern_info in KNOWN_ERROR_PATTERNS:
            if re.search(pattern_info['pattern'], diagnostics.raw_output, re.IGNORECASE):
                result.add_failure(self._create_failure(
                    pattern_info['message'],
                    severity=ValidationSeverity.ERROR,
                    error_code=pattern_info['code'],
                    raw_output=diagnostics.raw_output[:2000],
                    suggested_fix=pattern_info['fix_description'],
                ))

        # Analyze specific diagnostic errors
        for error in diagnostics.errors:
            code = error.get('code', 'UNKNOWN')
            message = error.get('message', 'Unknown error')
            detail = error.get('detail', '')

            suggested_fix = self._get_fix_suggestion(code)

            result.add_failure(self._create_failure(
                f"{message}. {detail}".strip(),
                severity=ValidationSeverity.ERROR,
                error_code=code,
                suggested_fix=suggested_fix,
            ))

        # Check process type
        if diagnostics.process_type is None and not diagnostics.errors:
            result.add_failure(self._create_failure(
                "process.type is undefined - app not running in Electron context",
                severity=ValidationSeverity.ERROR,
                error_code="PROCESS_TYPE_UNDEFINED",
                suggested_fix="Ensure ELECTRON_RUN_AS_NODE is not set. Create a helper script.",
            ))

        # Check electron type
        if diagnostics.electron_type == 'string':
            result.add_failure(self._create_failure(
                f"require('electron') returned path string: {diagnostics.electron_path}",
                severity=ValidationSeverity.ERROR,
                error_code="ELECTRON_RETURNS_PATH",
                suggested_fix="This happens when ELECTRON_RUN_AS_NODE=1. Create helper script to unset it.",
            ))

    def _get_fix_suggestion(self, error_code: str) -> str:
        """Get fix suggestion for an error code."""
        fixes = {
            'ELECTRON_RUN_AS_NODE_SET': (
                "Create scripts/run-electron.js that removes ELECTRON_RUN_AS_NODE "
                "before spawning electron-vite. Update package.json scripts to use it."
            ),
            'PROCESS_TYPE_UNDEFINED': (
                "The app is running as Node.js instead of Electron. "
                "Check that ELECTRON_RUN_AS_NODE is not set in the environment."
            ),
            'ELECTRON_PATH_STRING': (
                "require('electron') returned a path instead of the module. "
                "This means Electron is running in Node.js mode. "
                "Create a helper script that unsets ELECTRON_RUN_AS_NODE."
            ),
            'ELECTRON_REQUIRE_ERROR': (
                "Failed to require electron module. "
                "Ensure electron is properly installed and the binary exists."
            ),
            'APP_UNDEFINED': (
                "electron.app is undefined. Create a helper script that removes "
                "ELECTRON_RUN_AS_NODE before spawning the app."
            ),
        }
        return fixes.get(error_code, "Check the error details and fix accordingly.")

    def get_helper_script_fix(self) -> dict:
        """
        Generate the helper script fix for ELECTRON_RUN_AS_NODE issue.

        Returns:
            Dict with file paths and contents for the fix
        """
        helper_script = '''#!/usr/bin/env node
/**
 * Helper script to run electron-vite with ELECTRON_RUN_AS_NODE unset.
 * This is needed when running from VSCode (which sets ELECTRON_RUN_AS_NODE=1).
 */
const { spawn } = require('child_process');
const path = require('path');

// Remove the environment variable that prevents Electron from working
delete process.env.ELECTRON_RUN_AS_NODE;

const args = process.argv.slice(2);
const command = args[0] || 'dev';

const child = spawn('npx', ['electron-vite', command], {
  stdio: 'inherit',
  shell: true,
  env: process.env,
  cwd: path.join(__dirname, '..')
});

child.on('error', (err) => {
  console.error('Failed to start:', err);
  process.exit(1);
});

child.on('close', (code) => {
  process.exit(code || 0);
});
'''

        return {
            'scripts/run-electron.js': helper_script,
            'package.json_updates': {
                'scripts': {
                    'dev': 'node scripts/run-electron.js dev',
                    'start': 'node scripts/run-electron.js start',
                    'preview': 'node scripts/run-electron.js preview',
                }
            }
        }
