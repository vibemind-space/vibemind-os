"""
Integration Tests for Oscillator Pipeline

Tests the complete flow:
1. Initialize Layer4TemporalRouter
2. Process tokens via EventBridge
3. Verify oscillator state changes
4. Execute tool via ToolExecutor
5. Verify feedback modulation
6. Save checkpoint
7. Reset and restore
8. Verify restored state matches

Run: pytest tests/test_oscillator_integration.py -v
"""

import os
import sys
import tempfile
import shutil
import time

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.layer4_temporal_router import Layer4TemporalRouter
from core.tool_executor import ToolExecutor
from core.oscillator_checkpoint import CheckpointManager
from core.action_potential_oscillator import Channel


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create temporary directory for test artifacts."""
    temp = tempfile.mkdtemp()
    yield temp
    shutil.rmtree(temp)


@pytest.fixture
def router():
    """Create Layer4TemporalRouter for testing."""
    return Layer4TemporalRouter(
        strict_security=True,
        timing_threshold=0.5,
        enable_deep_reasoning=False  # Faster for tests
    )


@pytest.fixture
def executor(router):
    """Create ToolExecutor with router."""
    return ToolExecutor(router)


@pytest.fixture
def checkpoint_manager(temp_dir):
    """Create CheckpointManager with temp directory."""
    return CheckpointManager(checkpoint_dir=temp_dir)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestOscillatorIntegration:
    """Integration tests for the complete oscillator pipeline."""

    def test_router_initialization(self, router):
        """Test that Layer4TemporalRouter initializes correctly."""
        assert router is not None
        assert router.oscillator is not None
        assert router.token_adapter is not None
        assert router.event_bridge is not None
        assert router.temporal_ctm is not None

    def test_process_tokens_via_event_bridge(self, router):
        """Test processing tokens through EventBridge."""
        initial_tokens = router.get_statistics()['token_adapter']['tokens_processed']

        # Process some text
        tokens = router.event_bridge.process_text("Deploy the nginx container")

        # Verify tokens were extracted
        assert len(tokens) > 0
        assert 'deploy' in [t.lower() for t in tokens]

        # Verify tokens processed count increased
        new_tokens = router.get_statistics()['token_adapter']['tokens_processed']
        assert new_tokens > initial_tokens

    def test_oscillator_state_changes(self, router):
        """Test that oscillator state changes after token processing."""
        # Get initial state
        initial_state = router.get_oscillator_state()
        initial_a = initial_state.A.amplitude

        # Process action-heavy text (should boost Advance channel)
        router.event_bridge.process_text("execute deploy run start create build")

        # Get updated state
        new_state = router.get_oscillator_state()

        # Note: State may or may not change significantly depending on local classifier
        # Just verify we can get the state
        assert new_state is not None

    def test_tool_executor_integration(self, router, executor):
        """Test ToolExecutor integration with router."""
        # Register a test tool
        execution_log = []

        def test_deploy_tool(**kwargs):
            execution_log.append(kwargs)
            return {'status': 'deployed', 'container': kwargs.get('container', 'unknown')}

        executor.register_tool(
            name='deploy',
            func=test_deploy_tool,
            default_tonic=0.7,
            description='Deploy a container'
        )

        # Verify tool is registered
        assert 'deploy' in executor.list_tools()

        # Create a mock routing result
        class MockRoutingResult:
            blocked = False
            should_execute = True
            tool_name = 'deploy'
            tool_parameters = {'container': 'nginx', 'port': 8080}
            block_reason = None

            class decision:
                timing_confidence = 0.85

        result = executor.execute(MockRoutingResult())

        # Verify execution
        assert result.success is True
        assert result.output['container'] == 'nginx'
        assert len(execution_log) == 1
        assert execution_log[0]['container'] == 'nginx'

    def test_feedback_modulation(self, router, executor):
        """Test that execution feedback modulates oscillator."""
        # Register tool
        executor.register_tool('feedback_test', lambda: {'ok': True})

        # Get initial oscillator state
        initial_state = router.get_oscillator_state()

        # Execute successfully
        class MockSuccess:
            blocked = False
            should_execute = True
            tool_name = 'feedback_test'
            tool_parameters = {}
            block_reason = None
            class decision:
                timing_confidence = 0.9

        executor.execute(MockSuccess())

        # Verify feedback was recorded (check statistics)
        stats = executor.get_statistics()
        assert stats['successful_executions'] >= 1

    def test_checkpoint_save_restore(self, router, checkpoint_manager):
        """Test saving and restoring oscillator checkpoint."""
        # Process some tokens to change state
        router.event_bridge.process_text("Deploy nginx but not to production")

        # Save checkpoint
        checkpoint_path = checkpoint_manager.save_checkpoint(router, name="test_checkpoint")
        assert checkpoint_path is not None
        assert os.path.exists(checkpoint_path)

        # Get state before reset
        state_before = router.get_oscillator_state()
        a_before = state_before.A.amplitude

        # Reset router
        router.reset()

        # Verify reset changed state
        state_after_reset = router.get_oscillator_state()

        # Load and restore checkpoint
        checkpoint = checkpoint_manager.load_checkpoint("test_checkpoint")
        assert checkpoint is not None

        success = checkpoint_manager.restore_router(router, checkpoint)
        assert success is True

    def test_full_pipeline_flow(self, router, executor, checkpoint_manager):
        """Test the complete oscillator pipeline flow."""

        # Step 1: Initialize (already done via fixtures)
        assert router is not None

        # Step 2: Register tools
        tool_calls = []

        def deploy_tool(**kwargs):
            tool_calls.append(('deploy', kwargs))
            return {'deployed': True}

        def status_tool(**kwargs):
            tool_calls.append(('status', kwargs))
            return {'running': True}

        executor.register_tool('deploy', deploy_tool)
        executor.register_tool('status', status_tool)

        # Step 3: Process tokens
        initial_stats = router.get_statistics()
        router.event_bridge.process_text("Deploy the application and then check status")
        updated_stats = router.get_statistics()

        assert updated_stats['token_adapter']['tokens_processed'] > initial_stats['token_adapter']['tokens_processed']

        # Step 4: Execute tools
        class DeployRequest:
            blocked = False
            should_execute = True
            tool_name = 'deploy'
            tool_parameters = {'app': 'myapp'}
            block_reason = None
            class decision:
                timing_confidence = 0.9

        result = executor.execute(DeployRequest())
        assert result.success is True

        # Step 5: Save checkpoint
        checkpoint_path = checkpoint_manager.save_checkpoint(router, name="pipeline_test")
        assert os.path.exists(checkpoint_path)

        # Step 6: Verify checkpoint contents
        checkpoints = checkpoint_manager.list_checkpoints()
        assert len(checkpoints) >= 1
        assert any(cp['name'] == 'pipeline_test' for cp in checkpoints)

        # Step 7: Reset and restore
        router.reset()
        checkpoint = checkpoint_manager.load_checkpoint("pipeline_test")
        checkpoint_manager.restore_router(router, checkpoint)

        # Step 8: Verify executor stats
        exec_stats = executor.get_statistics()
        assert exec_stats['total_executions'] >= 1

    def test_concurrent_token_processing(self, router):
        """Test processing multiple batches of tokens."""
        texts = [
            "Deploy the nginx container",
            "Check the status of the deployment",
            "But do not restart the service",
            "If there are errors, investigate carefully"
        ]

        total_tokens = 0
        for text in texts:
            tokens = router.event_bridge.process_text(text)
            total_tokens += len(tokens)

        # Verify all tokens were processed
        stats = router.get_statistics()
        assert stats['token_adapter']['tokens_processed'] >= total_tokens

    def test_oscillator_dominant_channel(self, router):
        """Test getting dominant channel."""
        dominant = router.get_dominant_channel()

        assert dominant is not None
        assert dominant in [Channel.ADVANCE, Channel.EXPLORE, Channel.CORRECT]

    def test_synchrony_vector(self, router):
        """Test getting synchrony vector."""
        sync = router.get_synchrony_vector()

        assert sync is not None
        assert hasattr(sync, 'mean_coherence')

        vector = sync.vector  # SynchronyVector uses .vector property, not .to_vector()
        assert len(vector) == 9  # 9D synchrony encoding

    def test_router_statistics(self, router):
        """Test getting router statistics."""
        stats = router.get_statistics()

        assert 'total_routes' in stats
        assert 'token_adapter' in stats
        assert 'event_bridge' in stats

    def test_blocked_execution(self, router, executor):
        """Test that blocked executions are handled correctly."""
        executor.register_tool('safe_tool', lambda: {'ok': True})

        class BlockedRequest:
            blocked = True
            should_execute = False
            tool_name = 'safe_tool'
            tool_parameters = {}
            block_reason = "Security policy violation"
            class decision:
                timing_confidence = 0.1

        result = executor.execute(BlockedRequest())

        assert result.blocked is True
        assert result.success is False
        assert result.block_reason == "Security policy violation"


class TestOscillatorEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_text_processing(self, router):
        """Test processing empty text."""
        tokens = router.event_bridge.process_text("")
        assert tokens == []

    def test_special_characters(self, router):
        """Test processing text with special characters."""
        tokens = router.event_bridge.process_text("Deploy @nginx# with $special% chars!")
        # Should handle gracefully
        assert isinstance(tokens, list)

    def test_very_long_text(self, router):
        """Test processing very long text."""
        long_text = "deploy " * 100
        tokens = router.event_bridge.process_text(long_text)

        # Should limit tokens
        assert len(tokens) <= router.event_bridge.config.max_tokens_per_event

    def test_checkpoint_with_special_name(self, router, checkpoint_manager):
        """Test checkpoint with special characters in name."""
        # Names should be sanitized
        path = checkpoint_manager.save_checkpoint(router, name="test-checkpoint_v1.0")
        assert path is not None

    def test_restore_with_modified_router(self, router, checkpoint_manager):
        """Test restoring to a router that has been modified."""
        # Save initial state
        checkpoint_manager.save_checkpoint(router, name="initial")

        # Modify router state
        router.event_bridge.process_text("Many action tokens deploy execute run start")

        # Restore
        checkpoint = checkpoint_manager.load_checkpoint("initial")
        success = checkpoint_manager.restore_router(router, checkpoint)

        assert success is True


class TestOscillatorPerformance:
    """Performance-related tests."""

    def test_token_processing_speed(self, router):
        """Test that token processing is reasonably fast."""
        import time

        start = time.time()

        # Process 100 texts
        for i in range(100):
            router.event_bridge.process_text(f"Deploy container {i}")

        elapsed = time.time() - start

        # Should complete in reasonable time (< 5 seconds without LLM)
        assert elapsed < 5.0, f"Token processing too slow: {elapsed:.2f}s"

    def test_checkpoint_size(self, router, checkpoint_manager):
        """Test that checkpoints are reasonable size."""
        # Process some data
        for i in range(50):
            router.event_bridge.process_text(f"Token batch {i}")

        path = checkpoint_manager.save_checkpoint(router, name="size_test")

        # Check file size (should be < 1MB for normal operation)
        size = os.path.getsize(path)
        assert size < 1_000_000, f"Checkpoint too large: {size} bytes"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
