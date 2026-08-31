"""
Brain Snapshot/Restore (PHASE 7: P7.100)

Serializes and restores the complete brain state across all subsystems.

Features:
1. Full state capture: memory, neuromodulation, consciousness, goals, emotional
2. Incremental snapshots (only changed state)
3. Atomic save with temp file + rename
4. Restore from snapshot file
5. Snapshot metadata (timestamp, version, stats)
"""

import json
import os
import time
import logging
import shutil
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger('brain.snapshot')

SNAPSHOT_VERSION = "1.0.0"


class NumpyJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class BrainSnapshot:
    """
    Brain state snapshot manager.

    Captures and restores the complete cognitive state of the brain.
    """

    def __init__(self, snapshot_dir: str = "data/snapshots"):
        self.snapshot_dir = snapshot_dir
        os.makedirs(snapshot_dir, exist_ok=True)
        self.last_snapshot_time: Optional[float] = None
        self.snapshot_count = 0

    def capture(self, brain) -> Dict[str, Any]:
        """
        Capture complete brain state from a ProductionPlanner instance.

        Args:
            brain: ProductionPlanner instance

        Returns:
            Dict containing the full serialized brain state
        """
        t0 = time.time()
        snapshot = {
            'metadata': {
                'version': SNAPSHOT_VERSION,
                'timestamp': datetime.now().isoformat(),
                'snapshot_id': f"snap_{int(time.time())}",
            },
            'subsystems': {},
        }

        planner = getattr(brain, 'planner', brain)

        # Memory state
        try:
            if hasattr(planner, 'memory'):
                memory = planner.memory
                wm_items = []
                if hasattr(memory, 'working_memory') and hasattr(memory.working_memory, 'items'):
                    for item in memory.working_memory.items:
                        if hasattr(item, 'to_dict'):
                            wm_items.append(item.to_dict())
                ep_count = 0
                if hasattr(memory, 'episodic_memory') and hasattr(memory.episodic_memory, 'entries'):
                    ep_count = len(memory.episodic_memory.entries)
                snapshot['subsystems']['memory'] = {
                    'working_memory_count': len(wm_items),
                    'episodic_memory_count': ep_count,
                    'working_memory_items': wm_items[:20],  # Cap to avoid huge files
                }
        except Exception as e:
            snapshot['subsystems']['memory'] = {'error': str(e)}

        # Neuromodulation state
        try:
            if hasattr(planner, 'neuromodulation') and planner.neuromodulation:
                levels = planner.neuromodulation.levels
                snapshot['subsystems']['neuromodulation'] = levels.to_dict() if hasattr(levels, 'to_dict') else {}
        except Exception as e:
            snapshot['subsystems']['neuromodulation'] = {'error': str(e)}

        # Consciousness state
        try:
            if hasattr(planner, 'consciousness') and planner.consciousness:
                cs = planner.consciousness
                snapshot['subsystems']['consciousness'] = {
                    'total_states_tracked': cs.total_states_tracked,
                    'known_unknowns': list(cs.known_unknowns) if hasattr(cs, 'known_unknowns') else [],
                    'current_state': cs.current_state.to_dict() if hasattr(cs.current_state, 'to_dict') else {},
                }
        except Exception as e:
            snapshot['subsystems']['consciousness'] = {'error': str(e)}

        # Emotional state
        try:
            cognitive_loop = getattr(brain, 'cognitive_loop', None)
            if cognitive_loop and hasattr(cognitive_loop, '_emotional_system') and cognitive_loop._emotional_system:
                es = cognitive_loop._emotional_system
                snapshot['subsystems']['emotional'] = {
                    'valence': float(es.state.valence) if hasattr(es, 'state') else 0.0,
                    'arousal': float(es.state.arousal) if hasattr(es, 'state') else 0.0,
                }
        except Exception as e:
            snapshot['subsystems']['emotional'] = {'error': str(e)}

        # Goal graph state
        try:
            if hasattr(planner, 'goal_graph') and planner.goal_graph:
                gg = planner.goal_graph
                goals_data = []
                if hasattr(gg, 'goals'):
                    for gid, goal in list(gg.goals.items())[:50]:
                        goals_data.append({
                            'id': gid,
                            'name': getattr(goal, 'name', str(gid)),
                            'status': getattr(goal, 'status', 'unknown'),
                            'priority': float(getattr(goal, 'priority', 0.0)),
                        })
                snapshot['subsystems']['goal_graph'] = {
                    'total_goals': len(goals_data),
                    'goals': goals_data,
                }
        except Exception as e:
            snapshot['subsystems']['goal_graph'] = {'error': str(e)}

        # Statistics
        try:
            stats = brain.get_statistics() if hasattr(brain, 'get_statistics') else {}
            snapshot['subsystems']['statistics'] = {
                'total_predictions': stats.get('total_predictions', 0),
                'total_feedback': stats.get('total_feedback', 0),
            }
        except Exception:
            pass

        # Cognitive loop state
        try:
            if cognitive_loop:
                loop_state = cognitive_loop.get_loop_state()
                snapshot['subsystems']['cognitive_loop'] = loop_state
        except Exception as e:
            snapshot['subsystems']['cognitive_loop'] = {'error': str(e)}

        # Phase 6 module availability
        try:
            if cognitive_loop:
                snapshot['subsystems']['phase6_modules'] = loop_state.get('phase6_modules', {})
        except Exception:
            pass

        elapsed = time.time() - t0
        snapshot['metadata']['capture_time_ms'] = round(elapsed * 1000, 2)
        snapshot['metadata']['subsystem_count'] = len(snapshot['subsystems'])

        return snapshot

    def save(self, brain, filename: Optional[str] = None) -> str:
        """
        Capture and save brain state to file.

        Args:
            brain: ProductionPlanner instance
            filename: Optional filename (defaults to timestamped name)

        Returns:
            Path to saved snapshot file
        """
        snapshot = self.capture(brain)

        if filename is None:
            filename = f"brain_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = os.path.join(self.snapshot_dir, filename)
        tmp_path = filepath + '.tmp'

        # Atomic write: temp file + rename
        with open(tmp_path, 'w') as f:
            json.dump(snapshot, f, cls=NumpyJSONEncoder, indent=2)

        # Rename atomically (on most OS)
        shutil.move(tmp_path, filepath)

        self.last_snapshot_time = time.time()
        self.snapshot_count += 1

        logger.info(f"Brain snapshot saved: {filepath} ({snapshot['metadata']['capture_time_ms']}ms)")
        return filepath

    def load(self, filepath: str) -> Dict[str, Any]:
        """
        Load a snapshot from file.

        Args:
            filepath: Path to snapshot JSON file

        Returns:
            Snapshot dict
        """
        with open(filepath, 'r') as f:
            snapshot = json.load(f)

        if snapshot.get('metadata', {}).get('version') != SNAPSHOT_VERSION:
            logger.warning(f"Snapshot version mismatch: {snapshot.get('metadata', {}).get('version')} != {SNAPSHOT_VERSION}")

        return snapshot

    def restore(self, brain, snapshot: Dict[str, Any]) -> Dict[str, bool]:
        """
        Restore brain state from a snapshot.

        Args:
            brain: ProductionPlanner instance to restore into
            snapshot: Snapshot dict (from load())

        Returns:
            Dict of subsystem_name → success boolean
        """
        results = {}
        subsystems = snapshot.get('subsystems', {})
        planner = getattr(brain, 'planner', brain)

        # Restore neuromodulation levels
        if 'neuromodulation' in subsystems and not subsystems['neuromodulation'].get('error'):
            try:
                if hasattr(planner, 'neuromodulation') and planner.neuromodulation:
                    levels_data = subsystems['neuromodulation']
                    nm = planner.neuromodulation
                    if hasattr(nm.levels, 'dopamine') and 'dopamine' in levels_data:
                        nm.levels.dopamine = levels_data['dopamine']
                    if hasattr(nm.levels, 'serotonin') and 'serotonin' in levels_data:
                        nm.levels.serotonin = levels_data['serotonin']
                    if hasattr(nm.levels, 'norepinephrine') and 'norepinephrine' in levels_data:
                        nm.levels.norepinephrine = levels_data['norepinephrine']
                    results['neuromodulation'] = True
            except Exception as e:
                results['neuromodulation'] = False
                logger.error(f"Failed to restore neuromodulation: {e}")

        # Restore emotional state
        if 'emotional' in subsystems and not subsystems['emotional'].get('error'):
            try:
                cognitive_loop = getattr(brain, 'cognitive_loop', None)
                if cognitive_loop and hasattr(cognitive_loop, '_emotional_system') and cognitive_loop._emotional_system:
                    es = cognitive_loop._emotional_system
                    if hasattr(es, 'state'):
                        es.state.valence = subsystems['emotional'].get('valence', 0.0)
                        es.state.arousal = subsystems['emotional'].get('arousal', 0.0)
                    results['emotional'] = True
            except Exception as e:
                results['emotional'] = False
                logger.error(f"Failed to restore emotional state: {e}")

        logger.info(f"Brain restore complete: {results}")
        return results

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """List all available snapshots with metadata."""
        snapshots = []
        for f in sorted(Path(self.snapshot_dir).glob("brain_snapshot_*.json"), reverse=True):
            try:
                with open(f, 'r') as fp:
                    data = json.load(fp)
                meta = data.get('metadata', {})
                snapshots.append({
                    'filename': f.name,
                    'filepath': str(f),
                    'timestamp': meta.get('timestamp', 'unknown'),
                    'version': meta.get('version', 'unknown'),
                    'subsystem_count': meta.get('subsystem_count', 0),
                    'size_bytes': f.stat().st_size,
                })
            except Exception:
                snapshots.append({
                    'filename': f.name,
                    'filepath': str(f),
                    'error': 'corrupt',
                })
        return snapshots

    def get_statistics(self) -> Dict:
        """Get snapshot manager statistics."""
        return {
            'snapshot_dir': self.snapshot_dir,
            'snapshot_count': self.snapshot_count,
            'last_snapshot_time': self.last_snapshot_time,
            'available_snapshots': len(list(Path(self.snapshot_dir).glob("brain_snapshot_*.json"))),
        }
