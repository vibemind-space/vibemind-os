"""
Oscillator Checkpoint Manager

Provides save/load functionality for oscillator state persistence.
Follows existing checkpoint patterns (JSON + metadata).

Usage:
    from core.oscillator_checkpoint import CheckpointManager
    from core.layer4_temporal_router import Layer4TemporalRouter

    router = Layer4TemporalRouter()
    router.process_tokens(['deploy', 'nginx', 'container'])

    manager = CheckpointManager()
    checkpoint_path = manager.save_checkpoint(router, 'my_checkpoint')

    # Later...
    checkpoint = manager.load_checkpoint('my_checkpoint')
    manager.restore_router(router, checkpoint)
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class OscillatorCheckpoint:
    """Checkpoint data for oscillator state"""
    # Metadata
    name: str
    timestamp: str
    version: str = "1.0"

    # Oscillator state
    oscillator_state: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # {'A': {'amplitude': 0.5, 'phase': 0.0}, 'B': {...}, 'C': {...}}

    synchrony_vector: List[float] = field(default_factory=list)
    dominant_channel: str = "advance"

    # Token mappings (learned cache)
    token_mappings: Dict[str, str] = field(default_factory=dict)
    # {'deploy': 'ACTION', 'not': 'NEGATION', ...}

    # Frequency history (recent modulations)
    frequency_history: List[Dict] = field(default_factory=list)
    # [{'token': 'deploy', 'category': 'ACTION', 'timestamp': '...'}]

    # Statistics
    statistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'OscillatorCheckpoint':
        """Create from dictionary"""
        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'OscillatorCheckpoint':
        """Deserialize from JSON string"""
        return cls.from_dict(json.loads(json_str))


class CheckpointManager:
    """
    Manages oscillator checkpoints

    Features:
    - Save/load oscillator state
    - Persist learned token mappings
    - Store frequency modulation history
    - Auto-checkpoint at intervals
    """

    def __init__(
        self,
        checkpoint_dir: str = "data/oscillator_checkpoints",
        max_checkpoints: int = 50,
        auto_save_interval: int = 100  # Tokens between auto-saves
    ):
        """
        Initialize CheckpointManager

        Args:
            checkpoint_dir: Directory for checkpoint files
            max_checkpoints: Maximum checkpoints to keep
            auto_save_interval: Tokens between auto-checkpoints
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.max_checkpoints = max_checkpoints
        self.auto_save_interval = auto_save_interval

        # Create directory if needed
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Auto-checkpoint tracking
        self._tokens_since_checkpoint = 0

        print(f"[CheckpointManager] Initialized at {self.checkpoint_dir}")

    def save_checkpoint(
        self,
        router: Any,  # Layer4TemporalRouter
        name: Optional[str] = None
    ) -> str:
        """
        Save current router state to checkpoint

        Args:
            router: Layer4TemporalRouter instance
            name: Checkpoint name (auto-generated if None)

        Returns:
            Path to saved checkpoint file
        """
        if name is None:
            name = f"oscillator_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Extract oscillator state
        try:
            osc = router.get_oscillator_state()
            oscillator_state = {
                'A': {'amplitude': float(osc.A.amplitude), 'phase': float(osc.A.phase)},
                'B': {'amplitude': float(osc.B.amplitude), 'phase': float(osc.B.phase)},
                'C': {'amplitude': float(osc.C.amplitude), 'phase': float(osc.C.phase)}
            }
        except Exception as e:
            print(f"[CheckpointManager] Error extracting oscillator state: {e}")
            oscillator_state = {}

        # Extract synchrony vector
        try:
            sync = router.get_synchrony_vector()
            # SynchronyVector has .vector property, not .to_vector() method
            synchrony_vector = list(sync.vector)
        except Exception as e:
            print(f"[CheckpointManager] Error extracting synchrony: {e}")
            synchrony_vector = []

        # Get dominant channel
        try:
            dominant = router.get_dominant_channel()
            dominant_channel = dominant.value
        except Exception:
            dominant_channel = "advance"

        # Extract token mappings from adapter
        try:
            token_mappings = dict(router.token_adapter.token_cache)
        except Exception:
            token_mappings = {}

        # Extract frequency history
        try:
            frequency_history = list(router.token_adapter.recent_tokens)[-50:]
            frequency_history = [{'token': t} for t in frequency_history]
        except Exception:
            frequency_history = []

        # Get statistics
        try:
            stats = router.get_statistics()
            statistics = {
                'token_adapter': stats.get('token_adapter', {}),
                'event_bridge': stats.get('event_bridge', {}),
                'total_routes': stats.get('total_routes', 0)
            }
        except Exception:
            statistics = {}

        # Create checkpoint
        checkpoint = OscillatorCheckpoint(
            name=name,
            timestamp=datetime.now().isoformat(),
            oscillator_state=oscillator_state,
            synchrony_vector=synchrony_vector,
            dominant_channel=dominant_channel,
            token_mappings=token_mappings,
            frequency_history=frequency_history,
            statistics=statistics
        )

        # Save to file
        filepath = self.checkpoint_dir / f"{name}.json"
        with open(filepath, 'w') as f:
            f.write(checkpoint.to_json())

        # Cleanup old checkpoints
        self._cleanup_old_checkpoints()

        print(f"[CheckpointManager] Saved checkpoint: {filepath}")
        return str(filepath)

    def load_checkpoint(self, name: str) -> Optional[OscillatorCheckpoint]:
        """
        Load checkpoint by name

        Args:
            name: Checkpoint name (without .json extension)

        Returns:
            OscillatorCheckpoint or None if not found
        """
        filepath = self.checkpoint_dir / f"{name}.json"

        if not filepath.exists():
            print(f"[CheckpointManager] Checkpoint not found: {filepath}")
            return None

        try:
            with open(filepath, 'r') as f:
                checkpoint = OscillatorCheckpoint.from_json(f.read())
            print(f"[CheckpointManager] Loaded checkpoint: {name}")
            return checkpoint
        except Exception as e:
            print(f"[CheckpointManager] Error loading checkpoint: {e}")
            return None

    def restore_router(
        self,
        router: Any,  # Layer4TemporalRouter
        checkpoint: OscillatorCheckpoint
    ) -> bool:
        """
        Restore router state from checkpoint

        Args:
            router: Layer4TemporalRouter instance
            checkpoint: OscillatorCheckpoint to restore

        Returns:
            True if successful
        """
        try:
            # Restore oscillator amplitudes
            osc_state = checkpoint.oscillator_state
            if osc_state:
                oscillator = router.oscillator

                # TripleOscillatorState has .A, .B, .C attributes (not subscriptable)
                if 'A' in osc_state:
                    oscillator.state.A.amplitude = osc_state['A']['amplitude']
                    oscillator.state.A.phase = osc_state['A']['phase']
                if 'B' in osc_state:
                    oscillator.state.B.amplitude = osc_state['B']['amplitude']
                    oscillator.state.B.phase = osc_state['B']['phase']
                if 'C' in osc_state:
                    oscillator.state.C.amplitude = osc_state['C']['amplitude']
                    oscillator.state.C.phase = osc_state['C']['phase']

            # Restore token cache
            if checkpoint.token_mappings:
                router.token_adapter.token_cache.update(checkpoint.token_mappings)

            print(f"[CheckpointManager] Restored router from: {checkpoint.name}")
            return True

        except Exception as e:
            print(f"[CheckpointManager] Error restoring: {e}")
            return False

    def list_checkpoints(self) -> List[Dict[str, str]]:
        """
        List available checkpoints

        Returns:
            List of checkpoint info dicts
        """
        checkpoints = []

        for filepath in sorted(self.checkpoint_dir.glob("*.json"), reverse=True):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                checkpoints.append({
                    'name': data.get('name', filepath.stem),
                    'timestamp': data.get('timestamp', ''),
                    'path': str(filepath)
                })
            except Exception:
                continue

        return checkpoints

    def get_latest_checkpoint(self) -> Optional[OscillatorCheckpoint]:
        """Get the most recent checkpoint"""
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None
        return self.load_checkpoint(checkpoints[0]['name'])

    def auto_checkpoint(self, router: Any, tokens_processed: int = 1) -> Optional[str]:
        """
        Auto-checkpoint if interval reached

        Args:
            router: Layer4TemporalRouter instance
            tokens_processed: Number of tokens just processed

        Returns:
            Checkpoint path if saved, None otherwise
        """
        self._tokens_since_checkpoint += tokens_processed

        if self._tokens_since_checkpoint >= self.auto_save_interval:
            self._tokens_since_checkpoint = 0
            return self.save_checkpoint(router, f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        return None

    def _cleanup_old_checkpoints(self):
        """Remove old checkpoints beyond max_checkpoints"""
        checkpoints = list(self.checkpoint_dir.glob("*.json"))

        if len(checkpoints) <= self.max_checkpoints:
            return

        # Sort by modification time, oldest first
        checkpoints.sort(key=lambda p: p.stat().st_mtime)

        # Remove oldest
        to_remove = len(checkpoints) - self.max_checkpoints
        for filepath in checkpoints[:to_remove]:
            try:
                filepath.unlink()
                print(f"[CheckpointManager] Removed old checkpoint: {filepath.name}")
            except Exception:
                pass

    def delete_checkpoint(self, name: str) -> bool:
        """Delete a checkpoint by name"""
        filepath = self.checkpoint_dir / f"{name}.json"

        if filepath.exists():
            try:
                filepath.unlink()
                print(f"[CheckpointManager] Deleted: {name}")
                return True
            except Exception as e:
                print(f"[CheckpointManager] Error deleting: {e}")
                return False
        return False


# Quick test
if __name__ == "__main__":
    print("=" * 60)
    print("  CHECKPOINT MANAGER TEST")
    print("=" * 60)

    try:
        from core.layer4_temporal_router import Layer4TemporalRouter

        # Create router
        router = Layer4TemporalRouter(
            strict_security=True,
            timing_threshold=0.5,
            enable_deep_reasoning=False
        )

        # Process some tokens
        router.process_tokens(['deploy', 'nginx', 'container', 'but', 'not', 'production'])

        # Show initial state
        osc = router.get_oscillator_state()
        print(f"\nInitial State:")
        print(f"  A: {osc.A.amplitude:.3f}  B: {osc.B.amplitude:.3f}  C: {osc.C.amplitude:.3f}")

        # Create checkpoint manager
        manager = CheckpointManager()

        # Save checkpoint
        path = manager.save_checkpoint(router, 'test_checkpoint')
        print(f"\nSaved to: {path}")

        # List checkpoints
        print(f"\nAvailable checkpoints:")
        for cp in manager.list_checkpoints():
            print(f"  - {cp['name']} ({cp['timestamp']})")

        # Reset router
        router.reset()
        osc = router.get_oscillator_state()
        print(f"\nAfter Reset:")
        print(f"  A: {osc.A.amplitude:.3f}  B: {osc.B.amplitude:.3f}  C: {osc.C.amplitude:.3f}")

        # Restore checkpoint
        checkpoint = manager.load_checkpoint('test_checkpoint')
        if checkpoint:
            manager.restore_router(router, checkpoint)
            osc = router.get_oscillator_state()
            print(f"\nAfter Restore:")
            print(f"  A: {osc.A.amplitude:.3f}  B: {osc.B.amplitude:.3f}  C: {osc.C.amplitude:.3f}")

        print(f"\n{'=' * 60}")
        print("  TEST PASSED")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
