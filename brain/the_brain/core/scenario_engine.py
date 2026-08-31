"""
Scenario Engine: Multi-bridge stress tests with named scenarios.

Runs N ticks of RadialAttentionNetwork with prescribed bridge state overrides,
recording the full trajectory of bridge states, modulation factors, and ring
activations. Used for integration testing and emergent behavior validation.

Each scenario:
  1. Sets initial bridge states (overriding bridge outputs)
  2. Optionally evolves overrides per-tick via a step function
  3. Records full trajectory for assertion / analysis
"""

import copy
import logging
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import torch

from core.brain_logger import get_logger

logger = get_logger('scenario_engine')


@dataclass
class TickSnapshot:
    """One tick's full state snapshot."""
    tick: int
    bridge_states: Dict[str, Any]         # bridge_name -> state dict
    modulation_factors: Dict[str, float]  # attention_gain, precision_boost, etc.
    prediction_errors: List[float]
    ring_norms: List[float]               # L2 norm of each ring activation


@dataclass
class ScenarioResult:
    """Full trajectory from a scenario run."""
    name: str
    ticks: int
    trajectory: List[TickSnapshot]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def bridge_series(self, bridge_name: str, field_name: str) -> List[float]:
        """Extract time series for a specific bridge field."""
        values = []
        for snap in self.trajectory:
            state = snap.bridge_states.get(bridge_name, {})
            values.append(state.get(field_name, 0.0))
        return values

    def modulation_series(self, factor_name: str) -> List[float]:
        """Extract time series for a modulation factor."""
        return [snap.modulation_factors.get(factor_name, 1.0)
                for snap in self.trajectory]

    def pe_series(self) -> List[List[float]]:
        """Extract prediction error series (list of lists)."""
        return [snap.prediction_errors for snap in self.trajectory]

    @property
    def final(self) -> TickSnapshot:
        """Last tick snapshot."""
        return self.trajectory[-1]


def _state_to_dict(state: Any) -> Dict[str, Any]:
    """Convert a bridge state (dataclass or dict) to a plain dict."""
    if state is None:
        return {}
    if is_dataclass(state) and not isinstance(state, type):
        result = {}
        for f in fields(state):
            val = getattr(state, f.name)
            # Skip numpy arrays and tensors — just record scalars/bools/strings
            if isinstance(val, (int, float, bool, str)):
                result[f.name] = val
        return result
    if isinstance(state, dict):
        return {k: v for k, v in state.items()
                if isinstance(v, (int, float, bool, str))}
    return {}


class ScenarioEngine:
    """Runs multi-tick scenarios with bridge state overrides.

    Parameters
    ----------
    network : RadialAttentionNetwork
        The network to run forward passes on.
    seed_dim : int
        Dimension of seed embeddings (default 384).
    """

    def __init__(self, network, seed_dim: int = 384):
        self.network = network
        self.seed_dim = seed_dim
        self._results: Dict[str, ScenarioResult] = {}

    def run(
        self,
        name: str,
        ticks: int,
        initial_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        step_fn: Optional[Callable[[int, 'ScenarioEngine'], None]] = None,
        seed_fn: Optional[Callable[[int], torch.Tensor]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScenarioResult:
        """Run a named scenario.

        Parameters
        ----------
        name : str
            Human-readable scenario name.
        ticks : int
            Number of forward ticks to simulate.
        initial_overrides : dict, optional
            {bridge_name: {field: value}} to apply before tick 0.
        step_fn : callable, optional
            Called as step_fn(tick, engine) before each forward pass.
            Can modify bridge states via engine.set_bridge_field().
        seed_fn : callable, optional
            Called as seed_fn(tick) to produce seed embedding for each tick.
            If None, uses random normal seeds.
        metadata : dict, optional
            Extra metadata to attach to the result.

        Returns
        -------
        ScenarioResult
            Full trajectory with all bridge states and modulation factors.
        """
        trajectory: List[TickSnapshot] = []

        # Apply initial overrides
        if initial_overrides:
            self._apply_overrides(initial_overrides)

        for tick in range(ticks):
            # Per-tick modifications
            if step_fn is not None:
                step_fn(tick, self)

            # Generate seed
            if seed_fn is not None:
                seed = seed_fn(tick)
            else:
                seed = torch.randn(1, self.seed_dim)

            # Forward pass
            result = self.network.forward(seed)

            # Snapshot
            snapshot = self._capture_snapshot(tick, result)
            trajectory.append(snapshot)

        scenario_result = ScenarioResult(
            name=name,
            ticks=ticks,
            trajectory=trajectory,
            metadata=metadata or {},
        )
        self._results[name] = scenario_result
        logger.info(f"Scenario '{name}' completed: {ticks} ticks")
        return scenario_result

    def set_bridge_field(
        self, bridge_name: str, field_name: str, value: Any
    ) -> bool:
        """Set a field on a bridge's current state.

        Works with the 3 legacy bridges (neuromod, cortex, limbic) and
        generic bridges (sleep_wake, motor, defense, memory, integration,
        visceral, social).

        Returns True if the field was set.
        """
        # Legacy bridges
        if bridge_name == 'neuromod':
            state = self.network._neuromod_state
            if state is not None:
                try:
                    setattr(state, field_name, value)
                    return True
                except (AttributeError, TypeError):
                    return False
        elif bridge_name == 'cortex':
            state = self.network._cortex_state
            if state is not None:
                try:
                    setattr(state, field_name, value)
                    return True
                except (AttributeError, TypeError):
                    return False
        elif bridge_name == 'limbic':
            state = self.network._limbic_state
            if state is not None:
                try:
                    setattr(state, field_name, value)
                    return True
                except (AttributeError, TypeError):
                    return False
        else:
            # Generic bridges
            state = self.network._bridge_states.get(bridge_name)
            if state is not None:
                try:
                    setattr(state, field_name, value)
                    return True
                except (AttributeError, TypeError):
                    return False
        return False

    def get_bridge_state(self, bridge_name: str) -> Any:
        """Get the current state object for a bridge."""
        if bridge_name == 'neuromod':
            return self.network._neuromod_state
        elif bridge_name == 'cortex':
            return self.network._cortex_state
        elif bridge_name == 'limbic':
            return self.network._limbic_state
        else:
            return self.network._bridge_states.get(bridge_name)

    def get_results(self, name: str) -> Optional[ScenarioResult]:
        """Retrieve results from a previously run scenario."""
        return self._results.get(name)

    def list_results(self) -> List[str]:
        """List names of completed scenarios."""
        return list(self._results.keys())

    # ── Private helpers ──────────────────────────────────────────────────

    def _apply_overrides(self, overrides: Dict[str, Dict[str, Any]]) -> None:
        """Apply field overrides to bridge states."""
        for bridge_name, field_overrides in overrides.items():
            for field_name, value in field_overrides.items():
                success = self.set_bridge_field(bridge_name, field_name, value)
                if success:
                    logger.debug(
                        f"Override: {bridge_name}.{field_name} = {value}")
                else:
                    logger.warning(
                        f"Override failed: {bridge_name}.{field_name}")

    def _capture_snapshot(
        self, tick: int, forward_result: Dict[str, Any]
    ) -> TickSnapshot:
        """Capture full state after a forward pass."""
        # Collect bridge states
        bridge_states = {}

        # Legacy bridges
        if self.network._neuromod_state is not None:
            bridge_states['neuromod'] = _state_to_dict(
                self.network._neuromod_state)
        if self.network._cortex_state is not None:
            bridge_states['cortex'] = _state_to_dict(
                self.network._cortex_state)
        if self.network._limbic_state is not None:
            bridge_states['limbic'] = _state_to_dict(
                self.network._limbic_state)

        # Generic bridges
        for name, state in self.network._bridge_states.items():
            if state is not None:
                bridge_states[name] = _state_to_dict(state)

        # Modulation factors
        mod_ctx = forward_result.get('modulation_context')
        modulation_factors = {}
        if mod_ctx is not None:
            modulation_factors = {
                'attention_gain': mod_ctx.attention_gain,
                'precision_boost': mod_ctx.precision_boost,
                'ffn_throughput': mod_ctx.ffn_throughput,
                'threshold_mod': mod_ctx.threshold_mod,
            }

        # Prediction errors
        prediction_errors = forward_result.get('prediction_errors', [])

        # Ring activation norms
        ring_norms = []
        for activation in forward_result.get('ring_activations', []):
            if isinstance(activation, torch.Tensor):
                ring_norms.append(activation.detach().norm().item())
            else:
                ring_norms.append(0.0)

        return TickSnapshot(
            tick=tick,
            bridge_states=bridge_states,
            modulation_factors=modulation_factors,
            prediction_errors=prediction_errors,
            ring_norms=ring_norms,
        )


# ─── Built-in Scenarios ──────────────────────────────────────────────────────

def scenario_threat_while_sleepy(engine: ScenarioEngine, ticks: int = 30) -> ScenarioResult:
    """High threat + low arousal (sleep pressure).

    Expected: defense activates but motor is suppressed by sleep, creating
    approach-avoidance conflict visible in ACC conflict signal.

    Biological basis: Waking from sleep to a threat — PAG defense activates
    but reticular formation arousal hasn't caught up, creating a brief window
    of high threat perception with suppressed motor output.
    """
    def step(tick, eng):
        # Sustained high threat throughout
        eng.set_bridge_field('defense', 'defense_intensity', 0.85)
        eng.set_bridge_field('defense', 'alarm_level', 0.8)
        eng.set_bridge_field('defense', 'anxiety_level', 0.6)

        # Low sleep-wake arousal (sleepy state)
        # Gradually increase arousal as "waking up"
        arousal = min(0.2 + tick * 0.015, 0.8)
        eng.set_bridge_field('sleep_wake', 'arousal', arousal)
        eng.set_bridge_field('sleep_wake', 'sleep_pressure', max(0.7 - tick * 0.02, 0.1))
        eng.set_bridge_field('sleep_wake', 'melatonin', max(0.6 - tick * 0.02, 0.05))
        eng.set_bridge_field('sleep_wake', 'histamine', min(0.2 + tick * 0.01, 0.7))

    return engine.run(
        name='threat_while_sleepy',
        ticks=ticks,
        step_fn=step,
        metadata={
            'description': 'High threat + low arousal → defense/motor conflict',
            'expected': 'Defense active, motor suppressed by sleep, ACC conflict elevated',
        },
    )


def scenario_novel_social_under_load(engine: ScenarioEngine, ticks: int = 30) -> ScenarioResult:
    """Novel social input + high cognitive load.

    Expected: SocialPerception bridge activates (identity, theory-of-mind),
    but attention is constrained by high cognitive load, limiting engagement.

    Biological basis: Meeting someone new while multitasking — TPJ engagement
    limited by prefrontal resource competition.
    """
    def step(tick, eng):
        # Novel social stimulus appears at tick 5
        if tick >= 5:
            eng.set_bridge_field('social', 'social_salience', 0.8)
            eng.set_bridge_field('social', 'familiarity', 0.1)  # novel
            eng.set_bridge_field('social', 'identity_score', 0.7)
            eng.set_bridge_field('social', 'social_inference', 0.6)

        # High cognitive load throughout
        eng.set_bridge_field('cortex', 'conflict', 0.7)
        eng.set_bridge_field('cortex', 'choice_difficulty', 0.8)
        eng.set_bridge_field('cortex', 'control_signal', 0.9)

        # Memory under load — high theta for encoding effort
        eng.set_bridge_field('memory', 'theta_power', 0.8)
        eng.set_bridge_field('memory', 'memory_gateway', 0.7)

    return engine.run(
        name='novel_social_under_load',
        ticks=ticks,
        step_fn=step,
        metadata={
            'description': 'Novel social signal during high cognitive load',
            'expected': 'Social activates, attention constrained, limited TPJ',
        },
    )


def scenario_reward_prediction_error(engine: ScenarioEngine, ticks: int = 30) -> ScenarioResult:
    """Unexpected positive outcome (positive RPE).

    Expected: VTA DA spike, NAcc approach drive increase, learning rate boost
    via ACh, positive valence shift.

    Biological basis: Better-than-expected reward → DA burst → enhanced
    plasticity and approach motivation.
    """
    def step(tick, eng):
        # Baseline expectation for first 10 ticks
        if tick < 10:
            eng.set_bridge_field('neuromod', 'dopamine', 0.4)
            eng.set_bridge_field('neuromod', 'acetylcholine', 0.5)
            eng.set_bridge_field('limbic', 'valence', 0.0)
            eng.set_bridge_field('limbic', 'approach_drive', 0.3)
            eng.set_bridge_field('visceral', 'liking', 0.5)
            eng.set_bridge_field('visceral', 'wanting', 0.4)

        # Positive RPE at tick 10 — unexpected reward
        elif tick == 10:
            eng.set_bridge_field('neuromod', 'dopamine', 0.95)  # DA burst
            eng.set_bridge_field('neuromod', 'acetylcholine', 0.85)  # learning boost
            eng.set_bridge_field('neuromod', 'anti_reward', 0.0)
            eng.set_bridge_field('limbic', 'valence', 0.7)
            eng.set_bridge_field('limbic', 'approach_drive', 0.8)
            eng.set_bridge_field('limbic', 'salience', 0.8)
            eng.set_bridge_field('visceral', 'liking', 0.9)
            eng.set_bridge_field('visceral', 'wanting', 0.85)

        # Post-RPE: gradual decay back toward baseline
        elif tick > 10:
            decay = 0.92 ** (tick - 10)
            eng.set_bridge_field('neuromod', 'dopamine', 0.4 + 0.55 * decay)
            eng.set_bridge_field('neuromod', 'acetylcholine', 0.5 + 0.35 * decay)
            eng.set_bridge_field('limbic', 'valence', 0.7 * decay)
            eng.set_bridge_field('limbic', 'approach_drive', 0.3 + 0.5 * decay)
            eng.set_bridge_field('visceral', 'liking', 0.5 + 0.4 * decay)

    return engine.run(
        name='reward_prediction_error',
        ticks=ticks,
        step_fn=step,
        metadata={
            'description': 'Unexpected positive outcome → DA burst',
            'expected': 'DA spike, approach increase, ACh learning boost, positive valence',
        },
    )


def scenario_sustained_stress(engine: ScenarioEngine, ticks: int = 60) -> ScenarioResult:
    """Prolonged mild threat over 50+ ticks.

    Expected: BNST sustained anxiety, cortisol (HPA) elevation, hippocampal
    encoding suppression, vigilance increase.

    Biological basis: Chronic low-grade threat → BNST anxiety response
    replaces acute PAG defense, sustained HPA cortisol impairs memory
    encoding, NE keeps vigilance elevated.
    """
    def step(tick, eng):
        # Mild persistent threat
        eng.set_bridge_field('defense', 'defense_intensity', 0.4)
        eng.set_bridge_field('defense', 'anxiety_level', min(0.3 + tick * 0.008, 0.85))
        eng.set_bridge_field('defense', 'vigilance', min(0.4 + tick * 0.005, 0.8))

        # Sustained stress builds
        eng.set_bridge_field('limbic', 'stress', min(0.1 + tick * 0.012, 0.9))
        eng.set_bridge_field('limbic', 'arousal', min(0.4 + tick * 0.005, 0.75))
        eng.set_bridge_field('limbic', 'valence', max(-0.1 - tick * 0.005, -0.5))

        # NE stays elevated (vigilance)
        eng.set_bridge_field('neuromod', 'norepinephrine', min(0.5 + tick * 0.006, 0.85))
        eng.set_bridge_field('neuromod', 'ne_gain', min(1.0 + tick * 0.01, 1.8))

        # Memory encoding suppressed by chronic stress
        eng.set_bridge_field('memory', 'consolidation_strength',
                             max(0.6 - tick * 0.008, 0.15))
        eng.set_bridge_field('memory', 'theta_power',
                             max(0.5 - tick * 0.005, 0.2))

        # Serotonin dips under sustained stress
        eng.set_bridge_field('neuromod', 'serotonin',
                             max(0.5 - tick * 0.004, 0.2))

    return engine.run(
        name='sustained_stress',
        ticks=ticks,
        step_fn=step,
        metadata={
            'description': 'Prolonged mild threat → chronic stress response',
            'expected': 'Rising anxiety, suppressed encoding, elevated vigilance, negative valence',
        },
    )


def scenario_creative_exploration(engine: ScenarioEngine, ticks: int = 40) -> ScenarioResult:
    """Low threat, moderate novelty, idle state.

    Expected: DMN activation, LC explore mode (high explore_ratio), high ACh
    for plasticity, rich pattern formation in rings 3-4.

    Biological basis: Safe, unstimulated state → DMN mind-wandering,
    LC tonic mode (broad attention), basal forebrain ACh release for
    pattern exploration.
    """
    def step(tick, eng):
        # No threat — safe environment
        eng.set_bridge_field('defense', 'defense_intensity', 0.0)
        eng.set_bridge_field('defense', 'anxiety_level', 0.0)
        eng.set_bridge_field('defense', 'vigilance', 0.2)

        # Low arousal, relaxed
        eng.set_bridge_field('sleep_wake', 'arousal', 0.45)
        eng.set_bridge_field('sleep_wake', 'histamine', 0.4)
        eng.set_bridge_field('limbic', 'arousal', 0.35)
        eng.set_bridge_field('limbic', 'stress', 0.0)
        eng.set_bridge_field('limbic', 'valence', 0.2)  # mildly positive

        # Exploration mode
        eng.set_bridge_field('neuromod', 'explore_ratio', 0.8)
        eng.set_bridge_field('neuromod', 'acetylcholine', 0.8)  # high plasticity
        eng.set_bridge_field('neuromod', 'dopamine', 0.55)  # moderate DA
        eng.set_bridge_field('neuromod', 'norepinephrine', 0.3)  # low NE = tonic LC

        # DMN active — mind-wandering
        eng.set_bridge_field('integration', 'dmn_activation', 0.7)
        eng.set_bridge_field('integration', 'binding_strength', 0.6)

        # Low conflict — not effortful
        eng.set_bridge_field('cortex', 'conflict', 0.1)
        eng.set_bridge_field('cortex', 'choice_difficulty', 0.2)

    return engine.run(
        name='creative_exploration',
        ticks=ticks,
        step_fn=step,
        metadata={
            'description': 'Safe idle state → creative exploration',
            'expected': 'DMN active, explore mode, high ACh, low NE, positive valence',
        },
    )


def scenario_minibook_collaboration_burst(engine: ScenarioEngine, ticks: int = 30) -> ScenarioResult:
    """Burst of social signals simulating Minibook @mentions from multiple agents.

    Expected: SocialPerception activates (TPJ theory-of-mind, FusiformGyrus
    identity), Social→Limbic coupling raises valence, attention reorients
    to social stimuli, integration binding increases for multi-agent tracking.

    Biological basis: Sudden social engagement burst → amygdala social
    evaluation, TPJ mentalizing, prefrontal social resource allocation.
    """
    def step(tick, eng):
        # Social burst starts at tick 3, peaks at tick 10, fades
        if tick < 3:
            # Pre-burst baseline
            eng.set_bridge_field('social', 'social_salience', 0.1)
            eng.set_bridge_field('social', 'familiarity', 0.3)
            eng.set_bridge_field('social', 'social_inference', 0.1)
        elif tick < 15:
            # Burst phase — multiple agents interacting
            burst_intensity = min(0.3 + (tick - 3) * 0.06, 0.9)
            eng.set_bridge_field('social', 'social_salience', burst_intensity)
            eng.set_bridge_field('social', 'identity_score', 0.7)
            eng.set_bridge_field('social', 'word_score', 0.6)
            eng.set_bridge_field('social', 'agency_score', 0.8)
            eng.set_bridge_field('social', 'social_inference', 0.75)
            # Multiple agents → moderate familiarity (some known, some new)
            eng.set_bridge_field('social', 'familiarity', 0.5)
        else:
            # Post-burst decay
            decay = 0.9 ** (tick - 15)
            eng.set_bridge_field('social', 'social_salience', 0.9 * decay)
            eng.set_bridge_field('social', 'social_inference', 0.75 * decay)

        # Integration needs to bind multi-agent representations
        if 3 <= tick < 20:
            eng.set_bridge_field('integration', 'binding_strength',
                                 min(0.5 + (tick - 3) * 0.03, 0.85))
            eng.set_bridge_field('integration', 'orienting_saliency', 0.7)
        # Moderate cognitive demand for social reasoning
        if tick >= 3:
            eng.set_bridge_field('cortex', 'control_signal', 0.7)

    return engine.run(
        name='minibook_collaboration_burst',
        ticks=ticks,
        step_fn=step,
        metadata={
            'description': 'Burst of Minibook @mentions from multiple agents',
            'expected': 'Social activation, positive valence shift, attention reorienting, binding increase',
        },
    )


# ─── Scenario Registry ───────────────────────────────────────────────────────

SCENARIOS: Dict[str, Callable[[ScenarioEngine, int], ScenarioResult]] = {
    'threat_while_sleepy': scenario_threat_while_sleepy,
    'novel_social_under_load': scenario_novel_social_under_load,
    'reward_prediction_error': scenario_reward_prediction_error,
    'sustained_stress': scenario_sustained_stress,
    'creative_exploration': scenario_creative_exploration,
    'minibook_collaboration_burst': scenario_minibook_collaboration_burst,
}


def run_scenario(
    network,
    name: str,
    ticks: Optional[int] = None,
    seed_dim: int = 384,
) -> ScenarioResult:
    """Convenience function to run a named scenario.

    Parameters
    ----------
    network : RadialAttentionNetwork
        Network with bridges attached.
    name : str
        Scenario name (must be in SCENARIOS).
    ticks : int, optional
        Override default tick count for the scenario.
    seed_dim : int
        Seed embedding dimension.

    Returns
    -------
    ScenarioResult
    """
    if name not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{name}'. Available: {list(SCENARIOS.keys())}")

    engine = ScenarioEngine(network, seed_dim=seed_dim)
    fn = SCENARIOS[name]
    if ticks is not None:
        return fn(engine, ticks=ticks)
    return fn(engine)
