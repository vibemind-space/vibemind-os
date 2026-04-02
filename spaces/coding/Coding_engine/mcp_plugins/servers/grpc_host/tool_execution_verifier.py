"""
ToolExecutionVerifier - Verifiziert Tool-Ausführungen und bietet Fallbacks

Dieser Modul stellt sicher, dass MCP Tool-Ausführungen:
1. Erfolgreich waren (nicht nur aufgerufen)
2. Das erwartete Ergebnis produzierten
3. Bei Fehlern automatisch wiederholt oder Fallback genutzt wird
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from difflib import SequenceMatcher

# Ensure agents directory is in path
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

# Local imports - direct import to avoid __init__.py issues
try:
    from agents.file_write_agent import FileWriteAgent
except ImportError:
    # Fallback: Direct file import
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "file_write_agent",
        _current_dir / "agents" / "file_write_agent.py"
    )
    file_write_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(file_write_module)
    FileWriteAgent = file_write_module.FileWriteAgent

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ToolExecutionResult:
    """Strukturiertes Ergebnis einer Tool-Ausführung mit Verifikation"""
    tool_name: str
    success: bool
    verified: bool = False  # Wurde die Operation verifiziert?
    content: str = ""  # VOLLER Content (nicht truncated)
    error: Optional[str] = None
    retry_count: int = 0
    fallback_used: bool = False
    verification_method: str = "none"  # "mcp", "filesystem", "none"
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class VerificationResult:
    """Ergebnis einer Verifikations-Prüfung"""
    verified: bool
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    content_match: Optional[bool] = None
    similarity: Optional[float] = None
    error: Optional[str] = None


@dataclass
class RetryConfig:
    """Konfiguration für Retry-Logik"""
    max_retries: int = 3
    base_delay: float = 1.0  # Sekunden
    max_delay: float = 10.0
    exponential_base: float = 2.0


# ============================================================================
# File Operation Verifier
# ============================================================================

class FileOperationVerifier:
    """Verifiziert Datei-Operationen"""

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)

    def _resolve_path(self, path: str) -> Path:
        """Löst relativen Pfad auf"""
        p = Path(path)
        if p.is_absolute():
            return p
        return self.base_path / p

    async def verify_exists(self, file_path: str) -> bool:
        """Prüft ob Datei existiert"""
        path = self._resolve_path(file_path)
        return path.exists() and path.is_file()

    async def verify_not_empty(self, file_path: str) -> bool:
        """Prüft ob Datei nicht leer ist"""
        path = self._resolve_path(file_path)
        if not path.exists():
            return False
        return path.stat().st_size > 0

    async def verify_content(self, file_path: str, expected_content: str) -> VerificationResult:
        """Prüft ob Datei-Inhalt korrekt ist"""
        path = self._resolve_path(file_path)

        if not path.exists():
            return VerificationResult(
                verified=False,
                error=f"Datei existiert nicht: {file_path}"
            )

        try:
            actual_content = path.read_text(encoding='utf-8')

            if actual_content == expected_content:
                return VerificationResult(
                    verified=True,
                    file_path=str(path),
                    file_size=len(actual_content),
                    content_match=True,
                    similarity=1.0
                )

            # Berechne Ähnlichkeit für Debugging
            similarity = SequenceMatcher(None, actual_content, expected_content).ratio()

            return VerificationResult(
                verified=False,
                file_path=str(path),
                file_size=len(actual_content),
                content_match=False,
                similarity=similarity,
                error=f"Content mismatch (Ähnlichkeit: {similarity:.1%})"
            )

        except Exception as e:
            return VerificationResult(
                verified=False,
                error=f"Fehler beim Lesen: {str(e)}"
            )

    async def verify_write(
        self,
        file_path: str,
        expected_content: Optional[str] = None,
        expected_min_size: Optional[int] = None
    ) -> VerificationResult:
        """Vollständige Verifikation einer Write-Operation"""
        path = self._resolve_path(file_path)

        # Step 1: Existenz prüfen
        if not path.exists():
            return VerificationResult(
                verified=False,
                error=f"Datei existiert nicht nach Write: {file_path}"
            )

        # Step 2: Nicht leer prüfen
        file_size = path.stat().st_size
        if file_size == 0:
            return VerificationResult(
                verified=False,
                error=f"Datei ist leer nach Write: {file_path}"
            )

        # Step 3: Mindestgröße prüfen
        if expected_min_size and file_size < expected_min_size:
            return VerificationResult(
                verified=False,
                error=f"Datei kleiner als erwartet: {file_size} < {expected_min_size}"
            )

        # Step 4: Content prüfen (optional)
        if expected_content:
            return await self.verify_content(file_path, expected_content)

        return VerificationResult(
            verified=True,
            file_path=str(path.absolute()),
            file_size=file_size
        )


# ============================================================================
# Tool Execution Verifier
# ============================================================================

class ToolExecutionVerifier:
    """
    Hauptklasse für Tool-Ausführungs-Verifikation.

    Bietet:
    - Verifikation nach Tool-Ausführung
    - Retry mit exponential backoff
    - Fallback zu direkter Python I/O
    """

    # Tools die Dateien schreiben
    WRITE_TOOLS = {
        "write_file", "create_file", "edit_file",
        "filesystem_write", "mcp_write_file"
    }

    def __init__(
        self,
        base_path: str = ".",
        max_retries: int = 3,
        use_fallback: bool = True
    ):
        """
        Initialisiert den Verifier.

        Args:
            base_path: Basis-Pfad für Datei-Operationen
            max_retries: Maximale Retry-Versuche
            use_fallback: Fallback zu direkter Python I/O erlauben
        """
        self.base_path = Path(base_path)
        self.max_retries = max_retries
        self.use_fallback = use_fallback

        # FileWriteAgent als Fallback
        self._file_agent = FileWriteAgent(str(self.base_path))

        # Verifier für Datei-Operationen
        self._file_verifier = FileOperationVerifier(str(self.base_path))

        # Statistiken
        self._stats = {
            "total_verifications": 0,
            "successful_verifications": 0,
            "failed_verifications": 0,
            "retries": 0,
            "fallbacks_used": 0
        }

        logger.info(f"ToolExecutionVerifier initialisiert: {self.base_path}")

    def is_write_operation(self, tool_name: str) -> bool:
        """Prüft ob Tool eine Write-Operation ist"""
        tool_lower = tool_name.lower()
        return any(write_tool in tool_lower for write_tool in self.WRITE_TOOLS)

    async def verify_file_write(
        self,
        file_path: str,
        expected_content: Optional[str] = None
    ) -> VerificationResult:
        """
        Verifiziert eine Datei-Write-Operation.

        Args:
            file_path: Pfad zur geschriebenen Datei
            expected_content: Erwarteter Inhalt (optional)

        Returns:
            VerificationResult mit Details
        """
        self._stats["total_verifications"] += 1

        result = await self._file_verifier.verify_write(
            file_path,
            expected_content=expected_content
        )

        if result.verified:
            self._stats["successful_verifications"] += 1
        else:
            self._stats["failed_verifications"] += 1

        return result

    async def fallback_write(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8"
    ) -> ToolExecutionResult:
        """
        Schreibt Datei direkt via Python I/O (Fallback).

        Args:
            file_path: Ziel-Pfad
            content: Inhalt
            encoding: Encoding

        Returns:
            ToolExecutionResult
        """
        self._stats["fallbacks_used"] += 1
        logger.info(f"Fallback Write: {file_path}")

        try:
            # Nutze FileWriteAgent
            result = self._file_agent.write_file(file_path, content, encoding)

            if result.get("status") == "success":
                # Verifiziere nach Write
                verification = await self.verify_file_write(file_path, content)

                return ToolExecutionResult(
                    tool_name="fallback_write",
                    success=verification.verified,
                    verified=verification.verified,
                    content=f"Datei geschrieben: {file_path}",
                    fallback_used=True,
                    verification_method="filesystem",
                    file_path=str(result.get("path")),
                    file_size=result.get("size")
                )

            return ToolExecutionResult(
                tool_name="fallback_write",
                success=False,
                verified=False,
                error=result.get("error", "Unknown error"),
                fallback_used=True
            )

        except Exception as e:
            logger.error(f"Fallback Write fehlgeschlagen: {e}")
            return ToolExecutionResult(
                tool_name="fallback_write",
                success=False,
                verified=False,
                error=str(e),
                fallback_used=True
            )

    async def retry_with_fallback(
        self,
        tool_name: str,
        args: Dict[str, Any],
        original_error: Optional[str] = None
    ) -> ToolExecutionResult:
        """
        Versucht Operation mit Retry und Fallback.

        Args:
            tool_name: Name des fehlgeschlagenen Tools
            args: Tool-Argumente
            original_error: Ursprünglicher Fehler

        Returns:
            ToolExecutionResult
        """
        if not self.use_fallback:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                verified=False,
                error=original_error or "Operation fehlgeschlagen, kein Fallback erlaubt"
            )

        # Extrahiere Pfad und Content aus Args
        file_path = args.get("path") or args.get("file_path")
        content = args.get("content") or args.get("text")

        if not file_path or not content:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                verified=False,
                error="Kann Fallback nicht ausführen: path oder content fehlt"
            )

        # Retry mit exponential backoff
        config = RetryConfig(max_retries=self.max_retries)

        for attempt in range(config.max_retries):
            self._stats["retries"] += 1

            result = await self.fallback_write(file_path, content)

            if result.success:
                result.retry_count = attempt + 1
                return result

            # Exponential backoff
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay
            )
            logger.warning(
                f"Fallback Versuch {attempt + 1}/{config.max_retries} fehlgeschlagen, "
                f"warte {delay}s: {result.error}"
            )
            await asyncio.sleep(delay)

        return ToolExecutionResult(
            tool_name=tool_name,
            success=False,
            verified=False,
            error=f"Alle {config.max_retries} Fallback-Versuche fehlgeschlagen",
            retry_count=config.max_retries,
            fallback_used=True
        )

    async def execute_with_verification(
        self,
        operation: Callable,
        tool_name: str,
        args: Dict[str, Any]
    ) -> ToolExecutionResult:
        """
        Führt Operation aus und verifiziert das Ergebnis.

        Args:
            operation: Async Funktion die ausgeführt werden soll
            tool_name: Name des Tools
            args: Argumente für das Tool

        Returns:
            ToolExecutionResult mit Verifikation
        """
        try:
            # Operation ausführen
            result = await operation()

            # Für Write-Operationen: Verifizieren
            if self.is_write_operation(tool_name):
                file_path = args.get("path") or args.get("file_path")
                content = args.get("content") or args.get("text")

                if file_path:
                    verification = await self.verify_file_write(file_path, content)

                    if verification.verified:
                        return ToolExecutionResult(
                            tool_name=tool_name,
                            success=True,
                            verified=True,
                            content=str(result),
                            verification_method="filesystem",
                            file_path=verification.file_path,
                            file_size=verification.file_size
                        )
                    else:
                        # Verifikation fehlgeschlagen - Fallback
                        logger.warning(f"Verifikation fehlgeschlagen: {verification.error}")
                        return await self.retry_with_fallback(
                            tool_name, args, verification.error
                        )

            # Nicht-Write-Operationen: Direkt zurückgeben
            return ToolExecutionResult(
                tool_name=tool_name,
                success=True,
                verified=False,  # Keine Verifikation für Nicht-Write
                content=str(result),
                verification_method="none"
            )

        except Exception as e:
            logger.error(f"Tool-Ausführung fehlgeschlagen: {e}")

            # Bei Write-Operationen: Fallback versuchen
            if self.is_write_operation(tool_name) and self.use_fallback:
                return await self.retry_with_fallback(tool_name, args, str(e))

            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                verified=False,
                error=str(e)
            )

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        return {
            **self._stats,
            "fallback_rate": (
                self._stats["fallbacks_used"] / max(1, self._stats["total_verifications"])
            ),
            "success_rate": (
                self._stats["successful_verifications"] / max(1, self._stats["total_verifications"])
            )
        }


# ============================================================================
# Test
# ============================================================================

async def test_verifier():
    """Test-Funktion"""
    import tempfile

    print("=== ToolExecutionVerifier Test ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        verifier = ToolExecutionVerifier(base_path=tmpdir)

        # Test 1: Fallback Write
        print("Test 1: Fallback Write")
        result = await verifier.fallback_write(
            "test.txt",
            "Hello, World!"
        )
        print(f"  Success: {result.success}")
        print(f"  Verified: {result.verified}")
        print(f"  Fallback used: {result.fallback_used}")
        print()

        # Test 2: Verify Write
        print("Test 2: Verify Write")
        verification = await verifier.verify_file_write(
            "test.txt",
            "Hello, World!"
        )
        print(f"  Verified: {verification.verified}")
        print(f"  File size: {verification.file_size}")
        print()

        # Test 3: Content Mismatch
        print("Test 3: Content Mismatch")
        verification = await verifier.verify_file_write(
            "test.txt",
            "Different content"
        )
        print(f"  Verified: {verification.verified}")
        print(f"  Error: {verification.error}")
        print(f"  Similarity: {verification.similarity}")
        print()

        # Test 4: Non-existent file
        print("Test 4: Non-existent file")
        verification = await verifier.verify_file_write("nonexistent.txt")
        print(f"  Verified: {verification.verified}")
        print(f"  Error: {verification.error}")
        print()

        # Stats
        print("Stats:")
        stats = verifier.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(test_verifier())
