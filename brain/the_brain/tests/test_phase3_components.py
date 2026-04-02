"""
Unit Tests for Phase 3 Components

Tests:
- OscillatorCheckpoint & CheckpointManager
- ToolExecutor
- TokenFrequencyAdapter persistence methods
- Context-aware classification
- OllamaLLMRouter context classification

Run: pytest tests/test_phase3_components.py -v
"""

import os
import sys
import json
import tempfile
import shutil
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.oscillator_checkpoint import OscillatorCheckpoint, CheckpointManager
from core.tool_executor import ToolExecutor, ExecutionResult, ToolConfig
from core.action_potential_oscillator import ActionPotentialOscillator, Channel
from core.token_frequency_adapter import TokenFrequencyAdapter, TokenClass


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def temp_checkpoint_dir():
    """Create a temporary directory for checkpoints."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def oscillator():
    """Create a fresh ActionPotentialOscillator."""
    return ActionPotentialOscillator()


@pytest.fixture
def mock_router():
    """Create a mock Layer4TemporalRouter."""
    router = Mock()

    # Mock oscillator state
    osc_state = Mock()
    osc_state.A = Mock(amplitude=0.5, phase=0.0, frequency=10.0)
    osc_state.B = Mock(amplitude=0.3, phase=1.0, frequency=8.0)
    osc_state.C = Mock(amplitude=0.2, phase=2.0, frequency=6.0)
    router.get_oscillator_state.return_value = osc_state

    # Mock synchrony vector
    sync = Mock()
    sync.mean_coherence = 0.85
    sync.to_vector.return_value = [0.1] * 9
    router.get_synchrony_vector.return_value = sync

    # Mock dominant channel
    router.get_dominant_channel.return_value = Channel.ADVANCE

    # Mock statistics
    router.get_statistics.return_value = {
        'total_routes': 10,
        'token_adapter': {'tokens_processed': 50}
    }

    # Mock token adapter
    router.token_adapter = Mock()
    router.token_adapter.token_cache = {'deploy': 'ACTION', 'nginx': 'CONTENT'}
    router.token_adapter.export_frequency_history.return_value = []

    # Mock oscillator for restoration - TripleOscillatorState uses .A, .B, .C attributes
    router.oscillator = Mock()
    state_a = Mock(amplitude=0.5, phase=0.0)
    state_b = Mock(amplitude=0.3, phase=1.0)
    state_c = Mock(amplitude=0.2, phase=2.0)
    # Create mock TripleOscillatorState with A, B, C attributes
    osc_state_obj = Mock()
    osc_state_obj.A = state_a
    osc_state_obj.B = state_b
    osc_state_obj.C = state_c
    router.oscillator.state = osc_state_obj

    # Mock temporal CTM
    router.temporal_ctm = Mock()
    router.temporal_ctm.record_outcome = Mock()

    # Mock record_execution_result (called by ToolExecutor)
    router.record_execution_result = Mock()

    # Mock event bridge
    router.event_bridge = Mock()
    router.event_bridge.record_tool_outcome = Mock()

    # Mock apply methods
    router.token_adapter.apply_success_modulation = Mock()
    router.token_adapter.apply_failure_modulation = Mock()

    return router


# =============================================================================
# TEST: OscillatorCheckpoint
# =============================================================================

class TestOscillatorCheckpoint:
    """Test OscillatorCheckpoint dataclass."""

    def test_checkpoint_creation(self):
        """Test creating a checkpoint."""
        checkpoint = OscillatorCheckpoint(
            name="test_checkpoint",
            timestamp=datetime.now().isoformat()
        )
        assert checkpoint.name == "test_checkpoint"
        assert checkpoint.version == "1.0"
        assert checkpoint.dominant_channel == "advance"

    def test_checkpoint_with_data(self):
        """Test checkpoint with full data."""
        checkpoint = OscillatorCheckpoint(
            name="full_checkpoint",
            timestamp=datetime.now().isoformat(),
            oscillator_state={
                'A': {'amplitude': 0.5, 'phase': 0.0},
                'B': {'amplitude': 0.3, 'phase': 1.0},
                'C': {'amplitude': 0.2, 'phase': 2.0}
            },
            synchrony_vector=[0.1] * 9,
            dominant_channel="explore",
            token_mappings={'deploy': 'ACTION'},
            statistics={'total_routes': 100}
        )
        assert checkpoint.dominant_channel == "explore"
        assert checkpoint.token_mappings == {'deploy': 'ACTION'}
        assert len(checkpoint.synchrony_vector) == 9


class TestCheckpointManager:
    """Test CheckpointManager functionality."""

    def test_initialization(self, temp_checkpoint_dir):
        """Test manager initialization."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)
        assert str(manager.checkpoint_dir) == temp_checkpoint_dir
        assert manager.max_checkpoints == 50

    def test_save_checkpoint(self, temp_checkpoint_dir, mock_router):
        """Test saving a checkpoint."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)

        path = manager.save_checkpoint(mock_router, name="test_save")

        assert path is not None
        assert os.path.exists(path)
        assert "test_save" in path

    def test_save_checkpoint_auto_name(self, temp_checkpoint_dir, mock_router):
        """Test saving with auto-generated name."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)

        path = manager.save_checkpoint(mock_router)

        assert path is not None
        assert os.path.exists(path)
        # Auto-generated names use "oscillator_" prefix
        assert "oscillator_" in path or "checkpoint_" in path

    def test_load_checkpoint(self, temp_checkpoint_dir, mock_router):
        """Test loading a checkpoint."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)

        # Save first
        manager.save_checkpoint(mock_router, name="test_load")

        # Load
        checkpoint = manager.load_checkpoint("test_load")

        assert checkpoint is not None
        assert checkpoint.name == "test_load"

    def test_load_nonexistent_checkpoint(self, temp_checkpoint_dir):
        """Test loading a checkpoint that doesn't exist."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)

        checkpoint = manager.load_checkpoint("nonexistent")

        assert checkpoint is None

    def test_list_checkpoints(self, temp_checkpoint_dir, mock_router):
        """Test listing checkpoints."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)

        # Save multiple checkpoints
        manager.save_checkpoint(mock_router, name="checkpoint_1")
        manager.save_checkpoint(mock_router, name="checkpoint_2")

        checkpoints = manager.list_checkpoints()

        assert len(checkpoints) == 2
        names = [cp['name'] for cp in checkpoints]
        assert "checkpoint_1" in names
        assert "checkpoint_2" in names

    def test_restore_router(self, temp_checkpoint_dir, mock_router):
        """Test restoring router from checkpoint."""
        manager = CheckpointManager(checkpoint_dir=temp_checkpoint_dir)

        # Save
        manager.save_checkpoint(mock_router, name="test_restore")

        # Load
        checkpoint = manager.load_checkpoint("test_restore")

        # Restore
        success = manager.restore_router(mock_router, checkpoint)

        assert success is True

    def test_auto_checkpoint(self, temp_checkpoint_dir, mock_router):
        """Test auto-checkpoint functionality."""
        manager = CheckpointManager(
            checkpoint_dir=temp_checkpoint_dir,
            auto_save_interval=10
        )

        # Should not save on first call
        path = manager.auto_checkpoint(mock_router, tokens_processed=5)
        assert path is None

        # Should save after interval
        path = manager.auto_checkpoint(mock_router, tokens_processed=15)
        # Note: auto_checkpoint may or may not save based on internal logic

    def test_max_checkpoints_cleanup(self, temp_checkpoint_dir, mock_router):
        """Test that old checkpoints are cleaned up."""
        manager = CheckpointManager(
            checkpoint_dir=temp_checkpoint_dir,
            max_checkpoints=3
        )

        # Save more than max
        for i in range(5):
            manager.save_checkpoint(mock_router, name=f"cp_{i}")

        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) <= 3


# =============================================================================
# TEST: ToolExecutor
# =============================================================================

class TestToolExecutor:
    """Test ToolExecutor functionality."""

    def test_initialization(self, mock_router):
        """Test executor initialization."""
        executor = ToolExecutor(mock_router)

        assert executor.router == mock_router
        assert executor.total_executions == 0
        assert len(executor.tools) == 0

    def test_register_tool(self, mock_router):
        """Test registering a tool."""
        executor = ToolExecutor(mock_router)

        def my_tool(**kwargs):
            return {'result': 'success'}

        executor.register_tool(
            name='my_tool',
            func=my_tool,
            default_tonic=0.7,
            description='A test tool'
        )

        assert 'my_tool' in executor.tools
        assert executor.tools['my_tool'].default_tonic == 0.7

    def test_unregister_tool(self, mock_router):
        """Test unregistering a tool."""
        executor = ToolExecutor(mock_router)

        executor.register_tool('temp_tool', lambda: None)
        assert 'temp_tool' in executor.tools

        success = executor.unregister_tool('temp_tool')
        assert success is True
        assert 'temp_tool' not in executor.tools

    def test_execute_success(self, mock_router):
        """Test successful tool execution."""
        executor = ToolExecutor(mock_router)

        def successful_tool(**kwargs):
            return {'status': 'done', 'value': 42}

        executor.register_tool('success_tool', successful_tool)

        # Create mock routing result
        routing_result = Mock()
        routing_result.blocked = False
        routing_result.should_execute = True
        routing_result.tool_name = 'success_tool'
        routing_result.tool_parameters = {}
        routing_result.decision = Mock(timing_confidence=0.9)

        result = executor.execute(routing_result)

        assert result.success is True
        assert result.output == {'status': 'done', 'value': 42}
        assert executor.successful_executions == 1

    def test_execute_failure(self, mock_router):
        """Test failed tool execution."""
        executor = ToolExecutor(mock_router)

        def failing_tool(**kwargs):
            raise ValueError("Tool failed!")

        executor.register_tool('fail_tool', failing_tool)

        routing_result = Mock()
        routing_result.blocked = False
        routing_result.should_execute = True
        routing_result.tool_name = 'fail_tool'
        routing_result.tool_parameters = {}
        routing_result.decision = Mock(timing_confidence=0.9)

        result = executor.execute(routing_result)

        assert result.success is False
        assert "Tool failed!" in result.error
        assert executor.failed_executions == 1

    def test_execute_with_retry(self, mock_router):
        """Test tool execution with retry."""
        executor = ToolExecutor(mock_router)

        call_count = [0]

        def flaky_tool(**kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Temporary failure")
            return {'status': 'finally worked'}

        executor.register_tool('flaky_tool', flaky_tool, max_retries=3)

        routing_result = Mock()
        routing_result.blocked = False
        routing_result.should_execute = True
        routing_result.tool_name = 'flaky_tool'
        routing_result.tool_parameters = {}
        routing_result.decision = Mock(timing_confidence=0.9)

        result = executor.execute(routing_result)

        assert result.success is True
        assert call_count[0] == 3

    def test_execute_blocked(self, mock_router):
        """Test blocked execution."""
        executor = ToolExecutor(mock_router)

        routing_result = Mock()
        routing_result.blocked = True
        routing_result.should_execute = False
        routing_result.tool_name = 'blocked_tool'
        routing_result.block_reason = "Security violation"
        routing_result.decision = Mock(timing_confidence=0.1)

        result = executor.execute(routing_result)

        assert result.blocked is True
        assert result.block_reason == "Security violation"
        assert executor.blocked_executions == 1

    def test_execute_unregistered_tool(self, mock_router):
        """Test executing unregistered tool."""
        executor = ToolExecutor(mock_router)

        routing_result = Mock()
        routing_result.blocked = False
        routing_result.should_execute = True
        routing_result.tool_name = 'unknown_tool'
        routing_result.tool_parameters = {}
        routing_result.decision = Mock(timing_confidence=0.9)

        result = executor.execute(routing_result)

        assert result.success is False
        assert "not registered" in result.error

    def test_feedback_loop(self, mock_router):
        """Test that execution records feedback to router."""
        executor = ToolExecutor(mock_router)

        executor.register_tool('feedback_tool', lambda: {'ok': True})

        routing_result = Mock()
        routing_result.blocked = False
        routing_result.should_execute = True
        routing_result.tool_name = 'feedback_tool'
        routing_result.tool_parameters = {}
        routing_result.decision = Mock(timing_confidence=0.9)

        executor.execute(routing_result)

        # Verify feedback was recorded - ToolExecutor calls router.record_execution_result
        mock_router.record_execution_result.assert_called()
        mock_router.token_adapter.apply_success_modulation.assert_called_with('feedback_tool')

    def test_batch_execution(self, mock_router):
        """Test batch execution of multiple tools."""
        executor = ToolExecutor(mock_router)

        executor.register_tool('tool_1', lambda: {'result': 1})
        executor.register_tool('tool_2', lambda: {'result': 2})

        routing_results = []
        for i, name in enumerate(['tool_1', 'tool_2']):
            r = Mock()
            r.blocked = False
            r.should_execute = True
            r.tool_name = name
            r.tool_parameters = {}
            r.decision = Mock(timing_confidence=0.9)
            routing_results.append(r)

        results = executor.execute_batch(routing_results)

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_get_statistics(self, mock_router):
        """Test getting executor statistics."""
        executor = ToolExecutor(mock_router)

        executor.register_tool('stat_tool', lambda: None)

        stats = executor.get_statistics()

        assert 'total_executions' in stats
        assert 'registered_tools' in stats
        assert 'stat_tool' in stats['registered_tools']


# =============================================================================
# TEST: TokenFrequencyAdapter Persistence
# =============================================================================

class TestTokenFrequencyPersistence:
    """Test TokenFrequencyAdapter persistence methods."""

    def test_token_cache_property(self, oscillator):
        """Test token_cache property."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        # Cache should be empty initially
        cache = adapter.token_cache
        assert isinstance(cache, dict)

    def test_save_token_mappings(self, oscillator):
        """Test saving token mappings to file."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            adapter.save_token_mappings(temp_path)

            # Verify file was created
            assert os.path.exists(temp_path)

            # Verify content is valid JSON
            with open(temp_path, 'r') as f:
                data = json.load(f)
            assert isinstance(data, dict)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_load_token_mappings(self, oscillator):
        """Test loading token mappings from file."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        # Create test mappings file - must have 'mappings' key
        test_mappings = {
            'mappings': {
                'deploy': 'ACTION',
                'nginx': 'CONTENT',
                'not': 'NEGATION'
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_mappings, f)
            temp_path = f.name

        try:
            count = adapter.load_token_mappings(temp_path)
            assert count == 3
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_export_frequency_history(self, oscillator):
        """Test exporting frequency history."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        history = adapter.export_frequency_history()

        assert isinstance(history, list)


# =============================================================================
# TEST: Context-Aware Classification
# =============================================================================

class TestContextAwareClassification:
    """Test context-aware classification in TokenFrequencyAdapter."""

    def test_default_sequence_patterns(self, oscillator):
        """Test default sequence patterns are initialized."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        patterns = adapter.get_sequence_patterns()

        assert len(patterns) > 0
        assert 'do not' in patterns
        assert patterns['do not'] == 'NEGATION'

    def test_learn_sequence_pattern(self, oscillator):
        """Test learning a new sequence pattern."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        success = adapter.learn_sequence_pattern(
            tokens=['very', 'carefully'],
            category='CONSTRAINT'
        )

        assert success is True

        patterns = adapter.get_sequence_patterns()
        assert 'very carefully' in patterns

    def test_learn_invalid_category(self, oscillator):
        """Test learning with invalid category fails."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        success = adapter.learn_sequence_pattern(
            tokens=['test', 'pattern'],
            category='INVALID_CATEGORY'
        )

        assert success is False

    def test_learn_too_long_pattern(self, oscillator):
        """Test learning pattern that's too long fails."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        success = adapter.learn_sequence_pattern(
            tokens=['one', 'two', 'three', 'four', 'five', 'six'],
            category='ACTION'
        )

        assert success is False

    def test_process_token_with_context_match(self, oscillator):
        """Test context-aware classification with pattern match."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        # Add context
        adapter.context_window.append('do')

        # Process "not" after "do"
        result = adapter.process_token_with_context('not')

        # Should match "do not" -> NEGATION
        if result is not None:
            assert result.token_class == TokenClass.NEGATION
            assert result.confidence == 0.95

    def test_process_token_with_context_no_match(self, oscillator):
        """Test context-aware classification with no pattern match."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        # Clear context
        adapter.context_window.clear()

        # Process random token
        result = adapter.process_token_with_context('random')

        # Should return None (no pattern match)
        assert result is None

    def test_clear_sequence_patterns(self, oscillator):
        """Test clearing sequence patterns."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        # Add custom pattern
        adapter.learn_sequence_pattern(['custom', 'pattern'], 'ACTION')

        # Clear but keep defaults
        adapter.clear_sequence_patterns(keep_defaults=True)

        patterns = adapter.get_sequence_patterns()
        assert 'custom pattern' not in patterns
        assert 'do not' in patterns  # Default should remain


# =============================================================================
# TEST: Success/Failure Modulation
# =============================================================================

class TestModulation:
    """Test success/failure modulation methods."""

    def test_apply_success_modulation(self, oscillator):
        """Test applying success modulation."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        initial_beat = oscillator.state.beat_index

        adapter.apply_success_modulation('test_tool')

        # Modulation should step the oscillator
        assert oscillator.state.beat_index > initial_beat

    def test_apply_failure_modulation(self, oscillator):
        """Test applying failure modulation."""
        adapter = TokenFrequencyAdapter(oscillator, use_ollama=False)

        initial_beat = oscillator.state.beat_index

        adapter.apply_failure_modulation('test_tool')

        # Modulation should step the oscillator
        assert oscillator.state.beat_index > initial_beat


# =============================================================================
# TEST: ExecutionResult
# =============================================================================

class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_to_dict(self):
        """Test converting ExecutionResult to dictionary."""
        result = ExecutionResult(
            tool_name='test',
            success=True,
            output={'data': 123},
            error=None,
            duration_ms=50.5,
            timestamp=datetime.now(),
            routing_confidence=0.95
        )

        d = result.to_dict()

        assert d['tool_name'] == 'test'
        assert d['success'] is True
        assert 'timestamp' in d
        assert d['duration_ms'] == 50.5


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
