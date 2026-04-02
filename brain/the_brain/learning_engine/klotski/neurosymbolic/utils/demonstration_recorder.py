"""
Demonstration Recorder for Human Puzzle Solutions

Records human play sessions for imitation learning.
Captures state-action pairs and expert trajectories.
"""

import json
import pickle
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import numpy as np
import torch


class Demonstration:
    """Single demonstration trajectory"""

    def __init__(self, demo_id: Optional[str] = None):
        self.demo_id = demo_id or f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.states: List[np.ndarray] = []
        self.actions: List[int] = []
        self.rewards: List[float] = []
        self.metadata: Dict = {
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'total_moves': 0,
            'success': False,
            'difficulty': None
        }

    def add_step(self, state: np.ndarray, action: int, reward: float = 0.0):
        """Add a state-action pair"""
        self.states.append(state.copy())
        self.actions.append(action)
        self.rewards.append(reward)
        self.metadata['total_moves'] = len(self.actions)

    def finalize(self, success: bool = False):
        """Mark demonstration as complete"""
        self.metadata['end_time'] = datetime.now().isoformat()
        self.metadata['success'] = success
        self.metadata['total_reward'] = sum(self.rewards)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'demo_id': self.demo_id,
            'states': [s.tolist() for s in self.states],
            'actions': self.actions,
            'rewards': self.rewards,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Demonstration':
        """Load from dictionary"""
        demo = cls(demo_id=data['demo_id'])
        demo.states = [np.array(s) for s in data['states']]
        demo.actions = data['actions']
        demo.rewards = data['rewards']
        demo.metadata = data['metadata']
        return demo

    def __len__(self) -> int:
        return len(self.actions)


class DemonstrationRecorder:
    """Records and manages demonstration data"""

    def __init__(self, save_dir: str = "./demonstrations"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.current_demo: Optional[Demonstration] = None
        self.demonstrations: List[Demonstration] = []

        # Load existing demonstrations
        self._load_existing()

    def start_recording(self, demo_id: Optional[str] = None):
        """Start recording a new demonstration"""
        if self.current_demo is not None:
            print("Warning: Previous recording not finalized. Finalizing now.")
            self.stop_recording(success=False)

        self.current_demo = Demonstration(demo_id=demo_id)
        print(f"Started recording demonstration: {self.current_demo.demo_id}")

    def record_step(self, state: np.ndarray, action: int, reward: float = 0.0):
        """Record a single step"""
        if self.current_demo is None:
            raise ValueError("No active recording. Call start_recording() first.")

        self.current_demo.add_step(state, action, reward)

    def stop_recording(self, success: bool = False):
        """Stop recording and save demonstration"""
        if self.current_demo is None:
            print("No active recording to stop.")
            return

        self.current_demo.finalize(success=success)
        self.demonstrations.append(self.current_demo)

        # Save to disk
        self._save_demonstration(self.current_demo)

        print(f"Stopped recording: {self.current_demo.demo_id}")
        print(f"  Total steps: {len(self.current_demo)}")
        print(f"  Success: {success}")

        self.current_demo = None

    def _save_demonstration(self, demo: Demonstration):
        """Save demonstration to disk"""
        filepath = self.save_dir / f"{demo.demo_id}.json"
        with open(filepath, 'w') as f:
            json.dump(demo.to_dict(), f, indent=2)

    def _load_existing(self):
        """Load existing demonstrations from disk"""
        if not self.save_dir.exists():
            return

        for filepath in self.save_dir.glob("*.json"):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    demo = Demonstration.from_dict(data)
                    self.demonstrations.append(demo)
            except Exception as e:
                print(f"Failed to load {filepath}: {e}")

        if self.demonstrations:
            print(f"Loaded {len(self.demonstrations)} existing demonstrations")

    def get_all_demonstrations(self) -> List[Demonstration]:
        """Get all recorded demonstrations"""
        return self.demonstrations

    def get_successful_demonstrations(self) -> List[Demonstration]:
        """Get only successful demonstrations"""
        return [d for d in self.demonstrations if d.metadata['success']]

    def get_dataset(self, successful_only: bool = True) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get dataset for imitation learning

        Returns:
            states: (N, 4, 5) tensor of board states
            actions: (N,) tensor of action indices
        """
        demos = self.get_successful_demonstrations() if successful_only else self.demonstrations

        if not demos:
            return torch.empty(0, 4, 5), torch.empty(0, dtype=torch.long)

        all_states = []
        all_actions = []

        for demo in demos:
            all_states.extend(demo.states)
            all_actions.extend(demo.actions)

        states_tensor = torch.tensor(np.array(all_states), dtype=torch.float32)
        actions_tensor = torch.tensor(all_actions, dtype=torch.long)

        return states_tensor, actions_tensor

    def get_statistics(self) -> Dict:
        """Get statistics about demonstrations"""
        if not self.demonstrations:
            return {
                'total_demos': 0,
                'successful_demos': 0,
                'total_steps': 0,
                'avg_steps': 0,
                'success_rate': 0.0
            }

        successful = self.get_successful_demonstrations()
        total_steps = sum(len(d) for d in self.demonstrations)

        return {
            'total_demos': len(self.demonstrations),
            'successful_demos': len(successful),
            'total_steps': total_steps,
            'avg_steps': total_steps / len(self.demonstrations) if self.demonstrations else 0,
            'success_rate': len(successful) / len(self.demonstrations) if self.demonstrations else 0.0
        }

    def clear_all(self):
        """Clear all demonstrations (use with caution)"""
        import shutil
        if self.save_dir.exists():
            shutil.rmtree(self.save_dir)
            self.save_dir.mkdir(parents=True, exist_ok=True)
        self.demonstrations = []
        self.current_demo = None
        print("All demonstrations cleared")


# Convenience functions
_global_recorder: Optional[DemonstrationRecorder] = None

def get_recorder(save_dir: str = "./demonstrations") -> DemonstrationRecorder:
    """Get global demonstration recorder instance"""
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = DemonstrationRecorder(save_dir=save_dir)
    return _global_recorder


if __name__ == '__main__':
    # Test the recorder
    recorder = DemonstrationRecorder(save_dir="./test_demonstrations")

    # Simulate a demonstration
    recorder.start_recording()

    for i in range(10):
        state = np.random.randint(0, 10, size=(4, 5))
        action = np.random.randint(0, 20)
        reward = 1.0 if i == 9 else 0.0
        recorder.record_step(state, action, reward)

    recorder.stop_recording(success=True)

    # Get statistics
    stats = recorder.get_statistics()
    print(f"\nStatistics: {stats}")

    # Get dataset
    states, actions = recorder.get_dataset()
    print(f"\nDataset shape: states={states.shape}, actions={actions.shape}")
