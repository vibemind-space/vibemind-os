"""
Drumpad 3×N - Phase-Synchronized Action Grid

A 3×N grid where:
    - Rows = Action-Potential channels (A=Advance, B=Explore, C=Correct)
    - Cols = Phase buckets (N=8 for 45° quantization)

Grid Layout (3×8 = 24 cells):

        Phase:  0°   45°   90°  135°  180°  225°  270°  315°
              ┌────┬────┬────┬────┬────┬────┬────┬────┐
   A (Adv)   │ A0 │ A1 │ A2 │ A3 │ A4 │ A5 │ A6 │ A7 │
              ├────┼────┼────┼────┼────┼────┼────┼────┤
   B (Exp)   │ B0 │ B1 │ B2 │ B3 │ B4 │ B5 │ B6 │ B7 │
              ├────┼────┼────┼────┼────┼────┼────┼────┤
   C (Cor)   │ C0 │ C1 │ C2 │ C3 │ C4 │ C5 │ C6 │ C7 │
              └────┴────┴────┴────┴────┴────┴────┴────┘

Mapping from Synchrony Vector:
    - Amplitude → Which row(s) to activate
    - Phase → Which column to hit
    - Synchrony → Multi-cell patterns (e.g., A2+B2 for locked advance-explore)

This creates a natural mapping between:
    - Time (phase in beat) → Column
    - Location (regime) → Row pattern
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.action_potential_oscillator import Channel
from core.synchrony_encoder import SynchronyVector
from core.regime_detector import Regime, RegimeClassification


@dataclass
class Cell3xN:
    """Single cell in 3×N drumpad"""
    channel: Channel              # Row: ADVANCE, EXPLORE, or CORRECT
    phase_bucket: int             # Column: 0-7 (for N=8)
    cell_id: int                  # Linear ID: channel_idx * N + phase_bucket

    # Learned semantics
    tool_name: Optional[str] = None
    tool_parameters: Dict[str, Any] = field(default_factory=dict)

    # Statistics
    activation_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    @property
    def row(self) -> int:
        """Row index (0=A, 1=B, 2=C)"""
        return {Channel.ADVANCE: 0, Channel.EXPLORE: 1, Channel.CORRECT: 2}[self.channel]

    @property
    def col(self) -> int:
        """Column index (0-7)"""
        return self.phase_bucket

    @property
    def phase_degrees(self) -> float:
        """Phase in degrees"""
        return self.phase_bucket * 45.0

    @property
    def success_rate(self) -> float:
        """Success rate of this cell"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    def to_dict(self) -> Dict:
        return {
            'cell_id': self.cell_id,
            'channel': self.channel.value,
            'phase_bucket': self.phase_bucket,
            'phase_degrees': self.phase_degrees,
            'tool_name': self.tool_name,
            'success_rate': self.success_rate,
            'activation_count': self.activation_count
        }


@dataclass
class DrumpadHit:
    """A single hit (activation) on the drumpad"""
    cell: Cell3xN
    intensity: float              # Activation strength [0, 1]
    sync_vector: np.ndarray       # Source synchrony vector
    regime: Regime                # Current regime
    timestamp: datetime = field(default_factory=datetime.now)
    beat_index: int = 0

    def to_dict(self) -> Dict:
        return {
            'cell': self.cell.to_dict(),
            'intensity': self.intensity,
            'regime': self.regime.value,
            'beat_index': self.beat_index
        }


@dataclass
class DrumpadPattern:
    """Multi-cell activation pattern"""
    hits: List[DrumpadHit]
    primary_hit: DrumpadHit       # Highest intensity hit
    regime: Regime
    beat_index: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def active_channels(self) -> Set[Channel]:
        """Channels that are active"""
        return {h.cell.channel for h in self.hits}

    @property
    def total_intensity(self) -> float:
        """Sum of all hit intensities"""
        return sum(h.intensity for h in self.hits)

    def to_dict(self) -> Dict:
        return {
            'hits': [h.to_dict() for h in self.hits],
            'primary_cell': self.primary_hit.cell.cell_id,
            'active_channels': [c.value for c in self.active_channels],
            'total_intensity': self.total_intensity,
            'regime': self.regime.value,
            'beat_index': self.beat_index
        }


class Drumpad3xN:
    """
    3×N Phase-Synchronized Drumpad

    Maps synchrony vectors to action patterns:
    - Row (channel) from dominant amplitude
    - Column (phase bucket) from oscillator phase
    - Pattern from synchrony relationships

    Can produce:
    - Single hits (one cell)
    - Multi-hits (multiple cells in same beat)
    - Patterns (sequence of hits)
    """

    N_CHANNELS = 3   # A, B, C
    N_PHASES = 8     # 8 phase buckets (45° each)
    N_CELLS = 24     # 3 × 8

    CHANNEL_ORDER = [Channel.ADVANCE, Channel.EXPLORE, Channel.CORRECT]

    def __init__(
        self,
        amplitude_threshold: float = 0.3,   # Min amplitude to activate row
        multi_hit_enabled: bool = True,     # Allow multiple hits per beat
        temperature: float = 1.0            # Softmax temperature
    ):
        """
        Initialize 3×N drumpad

        Args:
            amplitude_threshold: Minimum amplitude to activate a channel
            multi_hit_enabled: Allow multiple channels to fire
            temperature: Softmax temperature for selection
        """
        self.amplitude_threshold = amplitude_threshold
        self.multi_hit_enabled = multi_hit_enabled
        self.temperature = temperature

        # Initialize cells
        self.cells: Dict[int, Cell3xN] = {}
        for ch_idx, channel in enumerate(self.CHANNEL_ORDER):
            for phase in range(self.N_PHASES):
                cell_id = ch_idx * self.N_PHASES + phase
                self.cells[cell_id] = Cell3xN(
                    channel=channel,
                    phase_bucket=phase,
                    cell_id=cell_id
                )

        # Current grid state
        self.grid = np.zeros((self.N_CHANNELS, self.N_PHASES))

        # History
        self.pattern_history: List[DrumpadPattern] = []

    def phase_to_bucket(self, phase_radians: float) -> int:
        """Convert phase in radians to bucket index"""
        # Normalize to [0, 2π)
        phase_norm = phase_radians % (2 * np.pi)
        # Convert to bucket
        bucket = int(phase_norm / (2 * np.pi) * self.N_PHASES)
        return min(bucket, self.N_PHASES - 1)

    def activate(
        self,
        sync: SynchronyVector,
        regime: Regime
    ) -> DrumpadPattern:
        """
        Activate drumpad from synchrony vector

        Args:
            sync: 9-D synchrony vector
            regime: Current regime classification

        Returns:
            DrumpadPattern with hits
        """
        hits = []

        # Get amplitudes and determine active channels
        amplitudes = [sync.amp_A, sync.amp_B, sync.amp_C]

        # Get phases (compute from sync vector)
        # We need original phases, but sync only has differences
        # Use amplitude-weighted average as reference
        # For simplicity, use a fixed reference and compute from differences
        phases = self._estimate_phases(sync)

        # Activate channels above threshold
        for ch_idx, (channel, amp, phase) in enumerate(
            zip(self.CHANNEL_ORDER, amplitudes, phases)
        ):
            if amp >= self.amplitude_threshold:
                # Determine phase bucket
                bucket = self.phase_to_bucket(phase)

                # Get cell
                cell_id = ch_idx * self.N_PHASES + bucket
                cell = self.cells[cell_id]

                # Create hit
                hit = DrumpadHit(
                    cell=cell,
                    intensity=amp,
                    sync_vector=sync.vector,
                    regime=regime,
                    beat_index=sync.beat_index
                )
                hits.append(hit)

                # Update grid
                self.grid[ch_idx, bucket] = amp

                # Update cell stats
                cell.activation_count += 1

                if not self.multi_hit_enabled:
                    break  # Only one hit per beat

        # If no hits, create a default (lowest active or center)
        if not hits:
            # Default to ADVANCE channel, middle phase
            default_cell = self.cells[3]  # A3 (middle)
            hit = DrumpadHit(
                cell=default_cell,
                intensity=0.1,
                sync_vector=sync.vector,
                regime=regime,
                beat_index=sync.beat_index
            )
            hits.append(hit)

        # Find primary hit (highest intensity)
        primary = max(hits, key=lambda h: h.intensity)

        # Create pattern
        pattern = DrumpadPattern(
            hits=hits,
            primary_hit=primary,
            regime=regime,
            beat_index=sync.beat_index
        )

        # Add to history
        self.pattern_history.append(pattern)
        if len(self.pattern_history) > 100:
            self.pattern_history = self.pattern_history[-100:]

        return pattern

    def _estimate_phases(self, sync: SynchronyVector) -> Tuple[float, float, float]:
        """
        Estimate individual phases from synchrony vector

        Since sync only contains phase differences, we need to recover
        individual phases. We use A's phase as reference (0) and
        compute B and C relative to A.
        """
        # Phase A is reference (0)
        phase_A = 0.0

        # Phase B from delta_AB
        # delta_AB = phase_A - phase_B, so phase_B = phase_A - delta_AB
        delta_AB = np.arctan2(sync.sin_AB, sync.cos_AB)
        phase_B = (phase_A - delta_AB) % (2 * np.pi)

        # Phase C from delta_AC
        delta_AC = np.arctan2(sync.sin_AC, sync.cos_AC)
        phase_C = (phase_A - delta_AC) % (2 * np.pi)

        return (phase_A, phase_B, phase_C)

    def get_cell(self, channel: Channel, phase_bucket: int) -> Cell3xN:
        """Get cell by channel and phase bucket"""
        ch_idx = self.CHANNEL_ORDER.index(channel)
        cell_id = ch_idx * self.N_PHASES + phase_bucket
        return self.cells[cell_id]

    def get_cell_by_id(self, cell_id: int) -> Cell3xN:
        """Get cell by linear ID"""
        return self.cells[cell_id]

    def learn_mapping(
        self,
        cell_id: int,
        tool_name: str,
        parameters: Optional[Dict] = None
    ):
        """Learn tool mapping for a cell"""
        if cell_id in self.cells:
            self.cells[cell_id].tool_name = tool_name
            if parameters:
                self.cells[cell_id].tool_parameters = parameters

    def record_outcome(self, cell_id: int, success: bool):
        """Record outcome for learning"""
        if cell_id in self.cells:
            if success:
                self.cells[cell_id].success_count += 1
            else:
                self.cells[cell_id].failure_count += 1

    def get_grid_visualization(self) -> str:
        """ASCII visualization of current grid"""
        lines = []

        # Header with phase labels
        header = "      " + "".join(f" {i*45:3d}°" for i in range(self.N_PHASES))
        lines.append(header)
        lines.append("     ┌" + "────┬" * (self.N_PHASES - 1) + "────┐")

        channel_labels = ['A', 'B', 'C']
        for ch_idx, label in enumerate(channel_labels):
            row_str = f"  {label}  │"
            for phase in range(self.N_PHASES):
                val = self.grid[ch_idx, phase]
                if val > 0.7:
                    char = "█"
                elif val > 0.5:
                    char = "▓"
                elif val > 0.3:
                    char = "▒"
                elif val > 0.1:
                    char = "░"
                else:
                    char = " "
                row_str += f" {char}  │"
            lines.append(row_str)

            if ch_idx < 2:
                lines.append("     ├" + "────┼" * (self.N_PHASES - 1) + "────┤")

        lines.append("     └" + "────┴" * (self.N_PHASES - 1) + "────┘")

        return "\n".join(lines)

    def get_active_cells(self) -> List[Tuple[int, float]]:
        """Get list of (cell_id, activation) for active cells"""
        active = []
        for ch_idx in range(self.N_CHANNELS):
            for phase in range(self.N_PHASES):
                if self.grid[ch_idx, phase] > 0:
                    cell_id = ch_idx * self.N_PHASES + phase
                    active.append((cell_id, self.grid[ch_idx, phase]))
        return sorted(active, key=lambda x: x[1], reverse=True)

    def reset_grid(self):
        """Reset current grid state"""
        self.grid = np.zeros((self.N_CHANNELS, self.N_PHASES))

    def get_statistics(self) -> Dict:
        """Get drumpad statistics"""
        # Cell statistics
        total_activations = sum(c.activation_count for c in self.cells.values())
        mapped_cells = sum(1 for c in self.cells.values() if c.tool_name)

        # Channel distribution
        channel_activations = {
            'advance': sum(
                c.activation_count for c in self.cells.values()
                if c.channel == Channel.ADVANCE
            ),
            'explore': sum(
                c.activation_count for c in self.cells.values()
                if c.channel == Channel.EXPLORE
            ),
            'correct': sum(
                c.activation_count for c in self.cells.values()
                if c.channel == Channel.CORRECT
            )
        }

        return {
            'n_channels': self.N_CHANNELS,
            'n_phases': self.N_PHASES,
            'n_cells': self.N_CELLS,
            'amplitude_threshold': self.amplitude_threshold,
            'multi_hit_enabled': self.multi_hit_enabled,
            'total_activations': total_activations,
            'mapped_cells': mapped_cells,
            'channel_distribution': channel_activations,
            'history_length': len(self.pattern_history)
        }

    def save_mappings(self) -> Dict:
        """Export cell mappings"""
        return {
            str(cell_id): {
                'channel': cell.channel.value,
                'phase_bucket': cell.phase_bucket,
                'tool_name': cell.tool_name,
                'tool_parameters': cell.tool_parameters,
                'success_rate': cell.success_rate,
                'activation_count': cell.activation_count
            }
            for cell_id, cell in self.cells.items()
        }

    def load_mappings(self, data: Dict):
        """Load cell mappings"""
        for cell_id_str, mapping in data.items():
            cell_id = int(cell_id_str)
            if cell_id in self.cells:
                self.cells[cell_id].tool_name = mapping.get('tool_name')
                self.cells[cell_id].tool_parameters = mapping.get('tool_parameters', {})
                self.cells[cell_id].activation_count = mapping.get('activation_count', 0)
                self.cells[cell_id].success_count = mapping.get('success_count', 0)
                self.cells[cell_id].failure_count = mapping.get('failure_count', 0)


if __name__ == "__main__":
    print("=" * 70)
    print("DRUMPAD 3×N - Phase-Synchronized Action Grid")
    print("=" * 70)
    print()
    print("Grid Layout (3×8 = 24 cells):")
    print("  Rows: A=Advance, B=Explore, C=Correct")
    print("  Cols: Phase buckets (0°, 45°, ..., 315°)")
    print()

    # Create drumpad
    drumpad = Drumpad3xN(
        amplitude_threshold=0.3,
        multi_hit_enabled=True
    )

    # Set up some example tool mappings
    drumpad.learn_mapping(0, 'docker_run', {'image': '$container'})     # A0
    drumpad.learn_mapping(3, 'kubectl_apply', {'file': '$config'})      # A3
    drumpad.learn_mapping(8, 'file_list', {'path': '$dir'})             # B0
    drumpad.learn_mapping(11, 'search_logs', {'query': '$pattern'})     # B3
    drumpad.learn_mapping(16, 'validate_config', {'file': '$config'})   # C0
    drumpad.learn_mapping(19, 'rollback', {'version': '$prev'})         # C3

    print("Tool mappings:")
    for cell_id in [0, 3, 8, 11, 16, 19]:
        cell = drumpad.cells[cell_id]
        print(f"  {cell.channel.value[0].upper()}{cell.phase_bucket}: {cell.tool_name}")
    print()

    # Test with synchrony vectors
    from core.action_potential_oscillator import ActionPotentialOscillator
    from core.synchrony_encoder import SynchronyEncoder
    from core.regime_detector import RegimeDetector

    osc = ActionPotentialOscillator(use_neural_coupling=False)
    encoder = SynchronyEncoder()
    detector = RegimeDetector()

    print("Testing drumpad activation:")
    print("-" * 70)

    scenarios = [
        ("Exploit", {'advance': 0.9, 'explore': 0.1, 'correct': 0.1}),
        ("Explore", {'advance': 0.2, 'explore': 0.8, 'correct': 0.1}),
        ("Repair", {'advance': 0.1, 'explore': 0.1, 'correct': 0.9}),
        ("Balanced", {'advance': 0.5, 'explore': 0.5, 'correct': 0.4}),
    ]

    for name, scenario in scenarios:
        # Step oscillator
        osc_state = osc.step(external_input=scenario)

        # Encode synchrony
        sync = encoder.encode(osc_state)

        # Detect regime
        regime_result = detector.detect(sync)

        # Activate drumpad
        drumpad.reset_grid()
        pattern = drumpad.activate(sync, regime_result.regime)

        print(f"\n{name} mode:")
        print(f"  Input: A={scenario['advance']:.1f}, B={scenario['explore']:.1f}, C={scenario['correct']:.1f}")
        print(f"  Regime: {regime_result.regime.value}")
        print(f"  Hits: {len(pattern.hits)}")
        for hit in pattern.hits:
            print(f"    - {hit.cell.channel.value[0].upper()}{hit.cell.phase_bucket} "
                  f"(intensity={hit.intensity:.3f}, tool={hit.cell.tool_name})")
        print()
        print(drumpad.get_grid_visualization())

    print()
    print("-" * 70)
    print("Statistics:", drumpad.get_statistics())
    print()
    print("=" * 70)
