"""
Reasoning Modes Configuration for CTM-ATM-R Integration

Defines clear mappings between biological metaphors and actual reasoning functions.
"""

from typing import Dict, Any

# Reasoning mode definitions
REASONING_MODES: Dict[str, Dict[str, Any]] = {
    'vision': {
        'display_name': 'Visual Thinking',
        'short_name': 'Visual',
        'description': 'Mental imagery, scene understanding, visual pattern recognition',
        'icon': '👁️',
        'color': '#667eea',
        'dimension': 128,
        'prior': 0.20,
        'tau': 50.0,
        'examples': [
            'Imagine a 3D object',
            'Visualize spatial relationships',
            'Mental scene construction'
        ]
    },
    'audio': {
        'display_name': 'Verbal Logic',
        'short_name': 'Verbal',
        'description': 'Language-based reasoning, symbolic logic, linguistic processing',
        'icon': '💬',
        'color': '#f093fb',
        'dimension': 64,
        'prior': 0.15,
        'tau': 40.0,
        'examples': [
            'Logical deduction',
            'Symbolic manipulation',
            'Language-based inference'
        ]
    },
    'touch': {
        'display_name': 'Embodied Thinking',
        'short_name': 'Embodied',
        'description': 'Action simulation, affordance reasoning, interaction modeling',
        'icon': '🤲',
        'color': '#4facfe',
        'dimension': 32,
        'prior': 0.15,
        'tau': 35.0,
        'examples': [
            'Simulate physical interactions',
            'Reason about affordances',
            'Action sequence planning'
        ]
    },
    'taste': {
        'display_name': 'Value Reasoning',
        'short_name': 'Value',
        'description': 'Expected value estimation, reward prediction, decision making',
        'icon': '💎',
        'color': '#ffd700',
        'dimension': 16,
        'prior': 0.10,
        'tau': 45.0,
        'examples': [
            'Estimate expected value',
            'Compare alternatives',
            'Predict outcomes'
        ]
    },
    'vestibular': {
        'display_name': 'Spatial Thinking',
        'short_name': 'Spatial',
        'description': 'Mental rotation, navigation, spatial transformations',
        'icon': '🧭',
        'color': '#00f2fe',
        'dimension': 16,
        'prior': 0.15,
        'tau': 30.0,
        'examples': [
            'Mental rotation',
            'Path planning',
            'Spatial transformations'
        ]
    },
    'threat': {
        'display_name': 'Safety Monitoring',
        'short_name': 'Safety',
        'description': 'Anomaly detection, safety checks, interrupt signals',
        'icon': '🛡️',
        'color': '#ff6b6b',
        'dimension': 8,
        'prior': 0.25,
        'tau': 20.0,
        'examples': [
            'Detect anomalies',
            'Safety violations',
            'Interrupt reasoning'
        ]
    }
}


def get_display_name(modality: str) -> str:
    """Get display name for a modality."""
    return REASONING_MODES.get(modality, {}).get('display_name', modality)


def get_short_name(modality: str) -> str:
    """Get short name for a modality."""
    return REASONING_MODES.get(modality, {}).get('short_name', modality)


def get_icon(modality: str) -> str:
    """Get icon for a modality."""
    return REASONING_MODES.get(modality, {}).get('icon', '❓')


def get_color(modality: str) -> str:
    """Get color for a modality."""
    return REASONING_MODES.get(modality, {}).get('color', '#888888')


def get_description(modality: str) -> str:
    """Get description for a modality."""
    return REASONING_MODES.get(modality, {}).get('description', 'No description')


def format_reasoning_mode(modality: str, gate_value: float) -> str:
    """Format reasoning mode with icon and name."""
    icon = get_icon(modality)
    name = get_display_name(modality)
    return f"{icon} {name} ({gate_value:.1%})"


# Mapping for backwards compatibility
BIOLOGICAL_TO_REASONING = {
    'vision': 'visual_thinking',
    'audio': 'verbal_logic',
    'touch': 'embodied_thinking',
    'taste': 'value_reasoning',
    'vestibular': 'spatial_thinking',
    'threat': 'safety_monitoring'
}

REASONING_TO_BIOLOGICAL = {v: k for k, v in BIOLOGICAL_TO_REASONING.items()}


def explain_reasoning_mode(modality: str, verbose: bool = False) -> str:
    """Generate explanation of a reasoning mode."""
    mode = REASONING_MODES.get(modality)
    if not mode:
        return f"Unknown modality: {modality}"

    explanation = f"""
{mode['icon']} {mode['display_name']} ('{modality}')
{'-' * 60}
{mode['description']}

Configuration:
  • Dimension: {mode['dimension']}
  • Prior: {mode['prior']:.2f}
  • Time constant: {mode['tau']:.1f}

Examples:
"""

    for example in mode['examples']:
        explanation += f"  • {example}\n"

    if verbose:
        explanation += f"""
Technical Details:
  • Short name: {mode['short_name']}
  • Color code: {mode['color']}
  • Biological metaphor: {modality}
  • Reasoning function: {BIOLOGICAL_TO_REASONING[modality]}
"""

    return explanation


def print_all_modes():
    """Print overview of all reasoning modes."""
    print("=" * 80)
    print("REASONING MODES IN CTM-ATM-R")
    print("=" * 80)
    print("\nBiological metaphors -> Actual reasoning functions:\n")

    for bio_name, mode in REASONING_MODES.items():
        reasoning_name = BIOLOGICAL_TO_REASONING[bio_name]
        print(f"{mode['icon']} {bio_name:12s} -> {mode['display_name']:20s} ({reasoning_name})")
        print(f"   {mode['description']}")
        print()

    print("=" * 80)


if __name__ == "__main__":
    # Demo
    print_all_modes()

    print("\n\nDetailed explanation of 'taste' (the confusing one):")
    print(explain_reasoning_mode('taste', verbose=True))
