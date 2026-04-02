"""
Drumpad - 8×8 Learned Action Grid for Temporal Tool Control

A 64-cell action space where cell semantics are LEARNED, not hardcoded.
Each cell represents an abstract action ID that maps to concrete tools.

Grid Layout (8×8 = 64 cells):
    ┌───┬───┬───┬───┬───┬───┬───┬───┐
    │ 0 │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │
    ├───┼───┼───┼───┼───┼───┼───┼───┤
    │ 8 │ 9 │10 │11 │12 │13 │14 │15 │
    ├───┼───┼───┼───┼───┼───┼───┼───┤
    │16 │17 │18 │19 │20 │21 │22 │23 │
    ├───┼───┼───┼───┼───┼───┼───┼───┤
    │24 │25 │26 │27 │28 │29 │30 │31 │
    ├───┼───┼───┼───┼───┼───┼───┼───┤
    │32 │33 │34 │35 │36 │37 │38 │39 │
    ├───┼───┼───┼───┼───┼───┼───┼───┤
    │40 │41 │42 │43 │44 │45 │46 │47 │
    ├───┼───┼───┼───┼───┼───┼───┼───┤
    │48 │49 │50 │51 │52 │53 │54 │55 │
    ├───┼───┼───┼───┼───┼───┼───┼───┤
    │56 │57 │58 │59 │60 │61 │62 │63 │
    └───┴───┴───┴───┴───┴───┴───┴───┘

Key Principles:
- Cell meanings emerge from training data
- No hardcoded tool → cell mapping
- CTM learns which cells correspond to which temporal actions
- Cells can represent: tools, wait, retry, abort, verify, compound actions

Special Reserved Cells (by convention, not hardcoded):
- Cell 0: NOP (no operation) - often learned as "wait"
- Cell 63: ABORT - often learned as "stop/safety"
- Other cells: fully learned semantics
"""

import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum


class CellSemantics(Enum):
    """Possible semantic categories that cells can learn to represent"""
    UNKNOWN = "unknown"         # Not yet learned
    TOOL_CALL = "tool_call"     # Execute a specific tool
    WAIT = "wait"               # Wait for condition/time
    RETRY = "retry"             # Retry last action
    VERIFY = "verify"           # Verify last action succeeded
    ABORT = "abort"             # Abort current operation
    COMPOUND = "compound"       # Compound action (multiple tools)
    BACKOFF = "backoff"         # Backoff and reduce rate
    QUERY = "query"             # Query for information
    NOOP = "noop"               # No operation


@dataclass
class CellActivation:
    """Single cell activation from CTM"""
    cell_id: int
    activation: float           # Raw activation value
    probability: float          # After softmax normalization
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def row(self) -> int:
        """Grid row (0-7)"""
        return self.cell_id // 8

    @property
    def col(self) -> int:
        """Grid column (0-7)"""
        return self.cell_id % 8

    def to_dict(self) -> Dict:
        return {
            'cell_id': self.cell_id,
            'row': self.row,
            'col': self.col,
            'activation': self.activation,
            'probability': self.probability,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class CellMapping:
    """Learned mapping from cell to concrete action"""
    cell_id: int
    semantic: CellSemantics = CellSemantics.UNKNOWN
    tool_name: Optional[str] = None
    parameters_template: Dict[str, Any] = field(default_factory=dict)

    # Learning statistics
    activation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0.0

    # Confidence in mapping
    confidence: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def update_stats(self, success: bool, duration_ms: float):
        """Update learning statistics"""
        self.activation_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        # Running average for duration
        if self.avg_duration_ms == 0:
            self.avg_duration_ms = duration_ms
        else:
            self.avg_duration_ms = 0.9 * self.avg_duration_ms + 0.1 * duration_ms

        # Update confidence based on consistency
        if self.activation_count > 5:
            self.confidence = min(0.95, 0.5 + self.success_rate * 0.45)

    def to_dict(self) -> Dict:
        return {
            'cell_id': self.cell_id,
            'semantic': self.semantic.value,
            'tool_name': self.tool_name,
            'parameters_template': self.parameters_template,
            'activation_count': self.activation_count,
            'success_rate': self.success_rate,
            'confidence': self.confidence
        }


@dataclass
class DrumpadAction:
    """Action selected from drumpad"""
    cell_id: int
    semantic: CellSemantics
    tool_name: Optional[str]
    parameters: Dict[str, Any]
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)

    # Timing information
    should_wait_ms: float = 0.0  # Wait before executing
    timeout_ms: float = 30000.0  # Max execution time

    def to_dict(self) -> Dict:
        return {
            'cell_id': self.cell_id,
            'semantic': self.semantic.value,
            'tool_name': self.tool_name,
            'parameters': self.parameters,
            'confidence': self.confidence,
            'should_wait_ms': self.should_wait_ms,
            'timeout_ms': self.timeout_ms
        }


class Drumpad:
    """
    8×8 Learned Action Grid

    The drumpad receives activation patterns from the Temporal CTM and
    selects actions based on learned cell-to-tool mappings.

    Key features:
    - 64 cells with learned semantics
    - Softmax selection over activations
    - Action confidence based on learning history
    - Support for compound actions
    """

    GRID_SIZE = 8
    NUM_CELLS = 64

    # Reserved cells (by convention)
    CELL_NOOP = 0
    CELL_ABORT = 63

    def __init__(
        self,
        temperature: float = 1.0,
        min_confidence_threshold: float = 0.3,
        known_tools: Optional[Set[str]] = None
    ):
        """
        Initialize drumpad

        Args:
            temperature: Softmax temperature (higher = more exploration)
            min_confidence_threshold: Minimum confidence to execute action
            known_tools: Set of known tool names for validation
        """
        self.temperature = temperature
        self.min_confidence_threshold = min_confidence_threshold
        self.known_tools = known_tools or set()

        # Initialize cell mappings (all unknown)
        self.cell_mappings: Dict[int, CellMapping] = {
            i: CellMapping(cell_id=i) for i in range(self.NUM_CELLS)
        }

        # Set reserved cell semantics
        self.cell_mappings[self.CELL_NOOP].semantic = CellSemantics.NOOP
        self.cell_mappings[self.CELL_ABORT].semantic = CellSemantics.ABORT

        # Activation history for analysis
        self.activation_history: List[CellActivation] = []
        self.action_history: List[DrumpadAction] = []

        # Grid state (current activations)
        self.current_activations = np.zeros(self.NUM_CELLS)
        self.current_probabilities = np.zeros(self.NUM_CELLS)

    def activate(
        self,
        activation_vector: np.ndarray,
        state_context: Optional[Dict] = None
    ) -> DrumpadAction:
        """
        Process activation vector and select action

        Args:
            activation_vector: Raw activations from CTM (shape: 64)
            state_context: Optional context for parameter filling

        Returns:
            Selected DrumpadAction
        """
        # Ensure correct shape
        if len(activation_vector) != self.NUM_CELLS:
            activation_vector = self._reshape_activations(activation_vector)

        self.current_activations = activation_vector

        # Apply softmax with temperature
        probabilities = self._softmax(activation_vector)
        self.current_probabilities = probabilities

        # Select cell (can use sampling or argmax)
        selected_cell = self._select_cell(probabilities)

        # Record activation
        activation = CellActivation(
            cell_id=selected_cell,
            activation=activation_vector[selected_cell],
            probability=probabilities[selected_cell]
        )
        self.activation_history.append(activation)

        # Build action from cell mapping
        action = self._build_action(selected_cell, probabilities[selected_cell], state_context)
        self.action_history.append(action)

        return action

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Apply temperature-scaled softmax"""
        x_scaled = x / self.temperature
        x_max = np.max(x_scaled)
        exp_x = np.exp(x_scaled - x_max)  # Numerical stability
        return exp_x / np.sum(exp_x)

    def _select_cell(self, probabilities: np.ndarray) -> int:
        """Select cell from probability distribution"""
        # For now, use argmax (deterministic)
        # Could switch to sampling for exploration: np.random.choice(64, p=probabilities)
        return int(np.argmax(probabilities))

    def _reshape_activations(self, activation_vector: np.ndarray) -> np.ndarray:
        """Reshape activation vector to 64 dimensions"""
        if len(activation_vector) < self.NUM_CELLS:
            # Pad with zeros
            padded = np.zeros(self.NUM_CELLS)
            padded[:len(activation_vector)] = activation_vector
            return padded
        else:
            # Truncate or project
            return activation_vector[:self.NUM_CELLS]

    def _build_action(
        self,
        cell_id: int,
        probability: float,
        state_context: Optional[Dict]
    ) -> DrumpadAction:
        """Build action from cell mapping and context"""
        mapping = self.cell_mappings[cell_id]

        # Fill parameters from context if available
        parameters = dict(mapping.parameters_template)
        if state_context:
            parameters = self._fill_parameters(parameters, state_context)

        # Calculate confidence
        confidence = min(probability, mapping.confidence) if mapping.confidence > 0 else probability

        # Determine timing
        should_wait = 0.0
        if mapping.semantic == CellSemantics.BACKOFF:
            should_wait = 1000.0  # Default backoff
        elif mapping.semantic == CellSemantics.WAIT:
            should_wait = 500.0  # Short wait

        return DrumpadAction(
            cell_id=cell_id,
            semantic=mapping.semantic,
            tool_name=mapping.tool_name,
            parameters=parameters,
            confidence=confidence,
            should_wait_ms=should_wait
        )

    def _fill_parameters(
        self,
        template: Dict[str, Any],
        context: Dict
    ) -> Dict[str, Any]:
        """Fill parameter template from context"""
        filled = {}
        for key, value in template.items():
            if isinstance(value, str) and value.startswith('$'):
                # Variable reference
                var_name = value[1:]
                if var_name in context:
                    filled[key] = context[var_name]
                else:
                    filled[key] = value  # Keep placeholder
            else:
                filled[key] = value
        return filled

    def learn_mapping(
        self,
        cell_id: int,
        semantic: CellSemantics,
        tool_name: Optional[str] = None,
        parameters_template: Optional[Dict] = None
    ):
        """
        Update cell mapping (called during training)

        Args:
            cell_id: Cell to update
            semantic: Learned semantic category
            tool_name: Associated tool (if TOOL_CALL)
            parameters_template: Parameter template with $variables
        """
        if cell_id < 0 or cell_id >= self.NUM_CELLS:
            return

        mapping = self.cell_mappings[cell_id]
        mapping.semantic = semantic
        mapping.tool_name = tool_name
        if parameters_template:
            mapping.parameters_template = parameters_template

        # Validate tool name
        if tool_name and self.known_tools and tool_name not in self.known_tools:
            # Unknown tool - mark with lower confidence
            mapping.confidence = 0.3

    def record_outcome(
        self,
        cell_id: int,
        success: bool,
        duration_ms: float
    ):
        """Record outcome of action for learning"""
        if cell_id in self.cell_mappings:
            self.cell_mappings[cell_id].update_stats(success, duration_ms)

    def get_grid_visualization(self) -> str:
        """Get ASCII visualization of current grid state"""
        lines = []
        lines.append("┌" + "───┬" * 7 + "───┐")

        for row in range(self.GRID_SIZE):
            cells = []
            for col in range(self.GRID_SIZE):
                cell_id = row * self.GRID_SIZE + col
                prob = self.current_probabilities[cell_id]

                # Visualize probability with characters
                if prob > 0.5:
                    char = "█"
                elif prob > 0.2:
                    char = "▓"
                elif prob > 0.1:
                    char = "▒"
                elif prob > 0.05:
                    char = "░"
                else:
                    char = " "

                cells.append(f" {char} ")

            lines.append("│" + "│".join(cells) + "│")

            if row < self.GRID_SIZE - 1:
                lines.append("├" + "───┼" * 7 + "───┤")

        lines.append("└" + "───┴" * 7 + "───┘")
        return "\n".join(lines)

    def get_cell_info(self, cell_id: int) -> Dict:
        """Get detailed information about a cell"""
        if cell_id not in self.cell_mappings:
            return {}

        mapping = self.cell_mappings[cell_id]
        return {
            'cell_id': cell_id,
            'row': cell_id // self.GRID_SIZE,
            'col': cell_id % self.GRID_SIZE,
            'mapping': mapping.to_dict(),
            'current_activation': float(self.current_activations[cell_id]),
            'current_probability': float(self.current_probabilities[cell_id])
        }

    def get_top_k_cells(self, k: int = 5) -> List[Dict]:
        """Get top k cells by current probability"""
        indices = np.argsort(self.current_probabilities)[-k:][::-1]
        return [self.get_cell_info(int(i)) for i in indices]

    def get_tool_cells(self) -> Dict[str, int]:
        """Get mapping of tool names to cell IDs"""
        tool_cells = {}
        for cell_id, mapping in self.cell_mappings.items():
            if mapping.tool_name:
                tool_cells[mapping.tool_name] = cell_id
        return tool_cells

    def reset_activations(self):
        """Reset current activation state"""
        self.current_activations = np.zeros(self.NUM_CELLS)
        self.current_probabilities = np.zeros(self.NUM_CELLS)

    def get_statistics(self) -> Dict:
        """Get drumpad statistics"""
        # Count by semantic type
        semantic_counts = {}
        for mapping in self.cell_mappings.values():
            semantic = mapping.semantic.value
            semantic_counts[semantic] = semantic_counts.get(semantic, 0) + 1

        # Calculate average confidence
        confidences = [m.confidence for m in self.cell_mappings.values() if m.confidence > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            'grid_size': self.GRID_SIZE,
            'num_cells': self.NUM_CELLS,
            'temperature': self.temperature,
            'min_confidence_threshold': self.min_confidence_threshold,
            'semantic_distribution': semantic_counts,
            'avg_mapping_confidence': avg_confidence,
            'activation_history_size': len(self.activation_history),
            'action_history_size': len(self.action_history)
        }

    def save_mappings(self) -> Dict:
        """Export mappings for persistence"""
        return {
            str(cell_id): mapping.to_dict()
            for cell_id, mapping in self.cell_mappings.items()
        }

    def load_mappings(self, data: Dict):
        """Load mappings from persisted data"""
        for cell_id_str, mapping_data in data.items():
            cell_id = int(cell_id_str)
            if cell_id in self.cell_mappings:
                mapping = self.cell_mappings[cell_id]
                mapping.semantic = CellSemantics(mapping_data.get('semantic', 'unknown'))
                mapping.tool_name = mapping_data.get('tool_name')
                mapping.parameters_template = mapping_data.get('parameters_template', {})
                mapping.activation_count = mapping_data.get('activation_count', 0)
                mapping.success_count = mapping_data.get('success_count', 0)
                mapping.failure_count = mapping_data.get('failure_count', 0)
                mapping.confidence = mapping_data.get('confidence', 0.0)


if __name__ == "__main__":
    print("=" * 70)
    print("DRUMPAD - 8×8 Learned Action Grid for Temporal Tool Control")
    print("=" * 70)
    print()

    # Create drumpad
    drumpad = Drumpad(temperature=0.5)

    # Set up some example mappings
    drumpad.learn_mapping(0, CellSemantics.NOOP)
    drumpad.learn_mapping(1, CellSemantics.TOOL_CALL, 'docker_run', {'image': '$container_id'})
    drumpad.learn_mapping(2, CellSemantics.TOOL_CALL, 'docker_ps', {})
    drumpad.learn_mapping(3, CellSemantics.WAIT)
    drumpad.learn_mapping(8, CellSemantics.TOOL_CALL, 'file_read', {'path': '$file_path'})
    drumpad.learn_mapping(9, CellSemantics.RETRY)
    drumpad.learn_mapping(63, CellSemantics.ABORT)

    print("Cell Mappings:")
    print("-" * 70)
    for cell_id in [0, 1, 2, 3, 8, 9, 63]:
        info = drumpad.get_cell_info(cell_id)
        print(f"  Cell {cell_id}: {info['mapping']['semantic']} "
              f"→ {info['mapping']['tool_name'] or 'N/A'}")

    print()

    # Simulate CTM activation
    print("Simulating CTM Activation:")
    print("-" * 70)

    # Create fake activation (high on cell 1 = docker_run)
    activation = np.random.randn(64) * 0.1
    activation[1] = 2.0  # Boost docker_run cell
    activation[0] = 0.5  # Some activation for NOOP

    # Process activation
    action = drumpad.activate(activation, state_context={
        'container_id': 'nginx:latest',
        'file_path': '/var/log/app.log'
    })

    print(f"Selected Action:")
    print(f"  Cell: {action.cell_id}")
    print(f"  Semantic: {action.semantic.value}")
    print(f"  Tool: {action.tool_name}")
    print(f"  Parameters: {action.parameters}")
    print(f"  Confidence: {action.confidence:.3f}")
    print()

    # Show grid visualization
    print("Grid Visualization (probability heatmap):")
    print(drumpad.get_grid_visualization())
    print()

    # Show top cells
    print("Top 5 Cells by Probability:")
    for info in drumpad.get_top_k_cells(5):
        print(f"  Cell {info['cell_id']}: {info['current_probability']:.3f} "
              f"({info['mapping']['semantic']})")

    print()
    print("Statistics:", drumpad.get_statistics())
    print()
    print("=" * 70)
