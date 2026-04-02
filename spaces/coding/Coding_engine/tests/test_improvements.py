"""
Unit Tests für die neuen Verbesserungen:
1. Generator-Koordination (pending state)
2. Deadlock-Erkennung (error hash tracking)
3. Missing File Detection (FixerAgent)
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import re


class TestSharedStateGeneratorPending:
    """Tests für Generator-Koordination via pending state."""

    @pytest.fixture
    def shared_state(self):
        """Create a fresh SharedState instance."""
        from src.mind.shared_state import SharedState
        return SharedState()

    @pytest.mark.asyncio
    async def test_set_generator_pending_true(self, shared_state):
        """Test dass generator_pending auf True gesetzt werden kann."""
        await shared_state.set_generator_pending(True)
        
        assert shared_state.metrics.generator_pending is True
        assert shared_state.metrics.generator_started_at is not None
        assert isinstance(shared_state.metrics.generator_started_at, datetime)

    @pytest.mark.asyncio
    async def test_set_generator_pending_false(self, shared_state):
        """Test dass generator_pending auf False gesetzt und Timestamp gelöscht wird."""
        await shared_state.set_generator_pending(True)
        await shared_state.set_generator_pending(False)
        
        assert shared_state.metrics.generator_pending is False
        assert shared_state.metrics.generator_started_at is None

    @pytest.mark.asyncio
    async def test_generator_pending_in_to_dict(self, shared_state):
        """Test dass generator_pending korrekt in to_dict() exportiert wird."""
        await shared_state.set_generator_pending(True)
        
        data = shared_state.metrics.to_dict()
        
        assert "generator" in data
        assert data["generator"]["pending"] is True
        assert data["generator"]["started_at"] is not None


class TestSharedStateDeadlockDetection:
    """Tests für Deadlock-Erkennung via Error Hash Tracking."""

    @pytest.fixture
    def shared_state(self):
        """Create a fresh SharedState instance."""
        from src.mind.shared_state import SharedState
        return SharedState()

    @pytest.mark.asyncio
    async def test_record_error_increments_counter(self, shared_state):
        """Test dass consecutive_same_errors bei gleichem Fehler erhöht wird."""
        error = "Error: Cannot find module './missing.ts'"
        
        await shared_state.record_error(error)
        assert shared_state.metrics.consecutive_same_errors == 1
        
        await shared_state.record_error(error)
        assert shared_state.metrics.consecutive_same_errors == 2
        
        await shared_state.record_error(error)
        assert shared_state.metrics.consecutive_same_errors == 3

    @pytest.mark.asyncio
    async def test_record_error_resets_on_different_error(self, shared_state):
        """Test dass counter bei unterschiedlichem Fehler zurückgesetzt wird."""
        await shared_state.record_error("Error A")
        await shared_state.record_error("Error A")
        assert shared_state.metrics.consecutive_same_errors == 2
        
        await shared_state.record_error("Error B")
        assert shared_state.metrics.consecutive_same_errors == 1

    @pytest.mark.asyncio
    async def test_is_stuck_triggered_at_threshold(self, shared_state):
        """Test dass is_stuck bei 3+ gleichen Fehlern ausgelöst wird."""
        error = "Error: Build failed"
        
        await shared_state.record_error(error)
        await shared_state.record_error(error)
        assert shared_state.metrics.is_stuck is False
        
        await shared_state.record_error(error)
        assert shared_state.metrics.is_stuck is True

    @pytest.mark.asyncio
    async def test_clear_stuck_state(self, shared_state):
        """Test dass clear_stuck_state() den Zustand zurücksetzt."""
        error = "Error: Build failed"
        
        # Trigger stuck state
        for _ in range(3):
            await shared_state.record_error(error)
        assert shared_state.metrics.is_stuck is True
        
        await shared_state.clear_stuck_state()
        
        assert shared_state.metrics.is_stuck is False
        assert shared_state.metrics.consecutive_same_errors == 0
        assert shared_state.metrics.recent_error_hashes == []

    @pytest.mark.asyncio
    async def test_error_hash_is_consistent(self, shared_state):
        """Test dass derselbe Fehler-Text denselben Hash erzeugt."""
        error1 = "Error: Cannot find module './test.ts'"
        error2 = "Error: Cannot find module './test.ts'"
        
        await shared_state.record_error(error1)
        hash1 = shared_state.metrics.recent_error_hashes[-1]
        
        await shared_state.record_error(error2)
        hash2 = shared_state.metrics.recent_error_hashes[-1]
        
        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_deadlock_in_to_dict(self, shared_state):
        """Test dass deadlock-info korrekt in to_dict() exportiert wird."""
        await shared_state.record_error("Error A")
        
        data = shared_state.metrics.to_dict()
        
        assert "deadlock" in data
        assert data["deadlock"]["consecutive_same_errors"] == 1
        assert data["deadlock"]["is_stuck"] is False


class TestConvergenceWithDeadlock:
    """Tests für Convergence Criteria mit Deadlock-Erkennung."""

    @pytest.fixture
    def metrics(self):
        """Create metrics with stuck state."""
        from src.mind.shared_state import ConvergenceMetrics
        metrics = ConvergenceMetrics()
        metrics.is_stuck = True
        metrics.consecutive_same_errors = 3
        metrics.iteration = 1  # Must be >= min_iterations
        return metrics

    @pytest.fixture
    def criteria_with_deadlock(self):
        """Create criteria with deadlock detection enabled."""
        from src.mind.convergence import ConvergenceCriteria
        return ConvergenceCriteria(
            enable_deadlock_detection=True,
            stuck_threshold=3,
            force_converge_on_stuck=True,
        )

    @pytest.fixture
    def criteria_without_deadlock(self):
        """Create criteria with deadlock detection disabled."""
        from src.mind.convergence import ConvergenceCriteria
        return ConvergenceCriteria(
            enable_deadlock_detection=False,
        )

    def test_convergence_forced_when_stuck(self, metrics, criteria_with_deadlock):
        """Test dass Konvergenz erzwungen wird wenn stuck."""
        from src.mind.convergence import is_converged
        
        converged, reasons = is_converged(metrics, criteria_with_deadlock, elapsed_seconds=10.0)
        
        assert converged is True
        assert any("Deadlock" in r or "deadlock" in r for r in reasons)

    def test_convergence_not_forced_when_disabled(self, metrics, criteria_without_deadlock):
        """Test dass Konvergenz nicht erzwungen wird wenn disabled."""
        from src.mind.convergence import is_converged
        
        # Set stuck state
        metrics.is_stuck = True
        
        converged, reasons = is_converged(metrics, criteria_without_deadlock, elapsed_seconds=10.0)
        
        # Should not converge just because of stuck (deadlock detection disabled)
        assert converged is False


class TestFixerAgentMissingFileDetection:
    """Tests für Missing File Detection im FixerAgent."""

    def test_missing_file_patterns_match(self):
        """Test dass MISSING_FILE_PATTERNS die erwarteten Fehler erkennen."""
        from src.agents.autonomous_base import FixerAgent
        
        test_errors = [
            "Error: Cannot find module './components/Header'",
            "ModuleNotFoundError: No module named 'utils.helpers'",
            "Error: ENOENT: no such file or directory, open './src/config.ts'",
            "TS2307: Cannot find module './styles.css' or its corresponding type declarations.",
            "ImportError: cannot import name 'process_data' from 'data_processor'",
            "FileNotFoundError: [Errno 2] No such file or directory: 'config.json'",
        ]
        
        for error in test_errors:
            matched = False
            for pattern in FixerAgent.MISSING_FILE_PATTERNS:
                if re.search(pattern, error, re.IGNORECASE):
                    matched = True
                    break
            assert matched, f"Pattern should match: {error}"

    def test_non_missing_file_errors_dont_match(self):
        """Test dass andere Fehler nicht als Missing File erkannt werden."""
        from src.agents.autonomous_base import FixerAgent
        
        test_errors = [
            "TypeError: Cannot read property 'length' of undefined",
            "SyntaxError: Unexpected token '}' at line 10",
            "Error: Build failed with exit code 1",
            "Warning: React does not recognize the `onClick` prop",
        ]
        
        for error in test_errors:
            matched = False
            for pattern in FixerAgent.MISSING_FILE_PATTERNS:
                if re.search(pattern, error, re.IGNORECASE):
                    matched = True
                    break
            assert not matched, f"Pattern should NOT match: {error}"


class TestFixerAgentDetectMissingFile:
    """Tests für die _detect_missing_file Methode."""

    @pytest.fixture
    def fixer_agent(self):
        """Create a FixerAgent instance with mocks."""
        from src.agents.autonomous_base import FixerAgent
        from src.mind.event_bus import EventBus
        from src.mind.shared_state import SharedState
        
        return FixerAgent(
            name="Fixer",
            event_bus=EventBus(),
            shared_state=SharedState(),
            working_dir="/tmp/test",
        )

    def test_detect_missing_ts_module(self, fixer_agent):
        """Test Erkennung von fehlenden TypeScript Modulen."""
        error = "Error: Cannot find module './components/Header'"
        
        result = fixer_agent._detect_missing_file(error)
        
        assert result is not None
        assert "./components/Header" in result or "Header" in result

    def test_detect_missing_python_module(self, fixer_agent):
        """Test Erkennung von fehlenden Python Modulen."""
        error = "ModuleNotFoundError: No module named 'utils.helpers'"
        
        result = fixer_agent._detect_missing_file(error)
        
        assert result is not None
        assert "utils" in result or "helpers" in result

    def test_detect_missing_file_enoent(self, fixer_agent):
        """Test Erkennung von ENOENT Fehlern."""
        error = "Error: ENOENT: no such file or directory, open './src/config.ts'"
        
        result = fixer_agent._detect_missing_file(error)
        
        assert result is not None
        assert "config" in result

    def test_no_missing_file_returns_none(self, fixer_agent):
        """Test dass None zurückgegeben wird wenn kein File fehlt."""
        error = "TypeError: Cannot read property 'length' of undefined"
        
        result = fixer_agent._detect_missing_file(error)
        
        assert result is None


class TestIntegration:
    """Integration Tests für das Zusammenspiel der Komponenten."""

    @pytest.mark.asyncio
    async def test_generator_blocks_orchestrator_iteration(self):
        """Test dass Orchestrator wartet wenn Generator pending ist."""
        from src.mind.shared_state import SharedState
        
        shared_state = SharedState()
        
        # Generator starts work
        await shared_state.set_generator_pending(True)
        
        # Simulate orchestrator check
        if shared_state.metrics.generator_pending:
            # Orchestrator should wait
            waited = True
        else:
            waited = False
        
        assert waited is True
        
        # Generator finishes
        await shared_state.set_generator_pending(False)
        
        assert shared_state.metrics.generator_pending is False

    @pytest.mark.asyncio
    async def test_stuck_detection_workflow(self):
        """Test kompletter Workflow der Stuck-Erkennung."""
        from src.mind.shared_state import SharedState
        from src.mind.convergence import ConvergenceCriteria, is_converged
        
        shared_state = SharedState()
        criteria = ConvergenceCriteria(
            enable_deadlock_detection=True,
            stuck_threshold=3,
            force_converge_on_stuck=True,
        )

        # Simulate at least 1 iteration
        await shared_state.increment_iteration()

        # Same error 3 times
        error = "Error: Cannot find module './missing.css'"
        await shared_state.record_error(error)
        await shared_state.record_error(error)
        await shared_state.record_error(error)
        
        # Check stuck state
        assert shared_state.metrics.is_stuck is True
        
        # Check convergence
        converged, reasons = is_converged(shared_state.metrics, criteria, elapsed_seconds=10.0)
        
        assert converged is True
        assert len(reasons) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])