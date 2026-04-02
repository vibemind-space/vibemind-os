"""
Inter-Bridge Coupling: Direct signaling pathways between bridges.

Provides 6 biologically-motivated coupling pathways that propagate signals
between bridge states BEFORE ModulationContext hooks fire. This allows
bridge states to influence each other beyond shared ring activations.

Coupling order (per tick):
  1. All bridges compute their states from module outputs
  2. InterBridgeCouplingRegistry.propagate() modifies states in-place
  3. ModulationContext hooks read (now-coupled) states
  4. Composite factors are clamped

All modifications are additive/multiplicative with clamping to valid ranges,
so couplings never produce out-of-range values.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.brain_logger import get_logger

logger = get_logger('inter_bridge_coupling')


@dataclass
class CouplingPathway:
    """A directed coupling pathway between two bridges.

    Parameters
    ----------
    name : str
        Human-readable pathway name (e.g. 'defense_to_motor').
    source_bridge : str
        Name of the source bridge (e.g. 'defense').
    target_bridge : str
        Name of the target bridge (e.g. 'motor').
    transform : callable
        Function (source_state, target_state) -> None that modifies
        target_state in-place based on source_state.
    description : str
        Biological rationale for the coupling.
    enabled : bool
        Whether this pathway is active.
    """
    name: str
    source_bridge: str
    target_bridge: str
    transform: Callable[[Any, Any], None]
    description: str = ''
    enabled: bool = True


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ─── Default coupling transforms ──────────────────────────────────────────────

def _defense_to_motor(defense, motor) -> None:
    """PAG→motor: threat activates motor readiness for fight/flight.

    When defense_intensity > 0.5, increase action_tendency and
    decrease inhibition_level proportionally.
    """
    intensity = getattr(defense, 'defense_intensity', 0.0)
    if intensity > 0.5:
        excess = intensity - 0.5  # [0, 0.5]
        # Boost action tendency (approach/flee)
        current_at = getattr(motor, 'action_tendency', 0.5)
        new_at = _clamp(current_at + 0.4 * excess, 0.0, 1.0)
        try:
            motor.action_tendency = new_at
        except AttributeError:
            pass
        # Reduce inhibition (disinhibit motor for escape)
        current_inh = getattr(motor, 'inhibition_level', 0.5)
        new_inh = _clamp(current_inh - 0.3 * excess, 0.0, 1.0)
        try:
            motor.inhibition_level = new_inh
        except AttributeError:
            pass


def _limbic_to_visceral(limbic, visceral) -> None:
    """Amygdala→NTS: high emotional arousal triggers autonomic response.

    When limbic arousal > 0.6, elevate visceral afferent_strength.
    """
    arousal = getattr(limbic, 'arousal', 0.3)
    if arousal > 0.6:
        excess = arousal - 0.6  # [0, 0.4]
        current = getattr(visceral, 'afferent_strength', 0.3)
        new_val = _clamp(current + 0.5 * excess, 0.0, 1.0)
        try:
            visceral.afferent_strength = new_val
        except AttributeError:
            pass


def _sleep_to_neuromod(sleep_wake, neuromod) -> None:
    """Sleep→catecholamines: low arousal suppresses DA and NE release.

    When sleep arousal < 0.3, scale down dopamine and norepinephrine.
    Biologically: sleep reduces catecholamine release.
    """
    arousal = getattr(sleep_wake, 'arousal', 0.5)
    if arousal < 0.3:
        suppress = arousal / 0.3  # [0, 1) — 0 means full suppression
        current_da = getattr(neuromod, 'dopamine', 0.5)
        current_ne = getattr(neuromod, 'norepinephrine', 0.5)
        try:
            neuromod.dopamine = current_da * suppress
        except AttributeError:
            pass
        try:
            neuromod.norepinephrine = current_ne * suppress
        except AttributeError:
            pass


def _motor_to_integration(motor, integration) -> None:
    """Motor efference copy: action tendency feeds forward to integration.

    High action_tendency increases binding_strength (Claustrum integrates
    motor intent with perceptual state).
    """
    action = getattr(motor, 'action_tendency', 0.5)
    current = getattr(integration, 'binding_strength', 0.5)
    new_val = _clamp(current + 0.15 * action, 0.0, 1.0)
    try:
        integration.binding_strength = new_val
    except AttributeError:
        pass


def _integration_to_limbic(integration, limbic) -> None:
    """Claustrum→Amygdala: integration score gates salience.

    High binding_strength increases limbic salience (integrated percepts
    are more salient).
    """
    binding = getattr(integration, 'binding_strength', 0.5)
    current = getattr(limbic, 'salience', 0.3)
    new_val = _clamp(current + 0.15 * binding, 0.0, 1.0)
    try:
        limbic.salience = new_val
    except AttributeError:
        pass


def _social_to_limbic(social, limbic) -> None:
    """Social→Amygdala: social signals modulate emotional state.

    High social_salience nudges valence positive and raises arousal.
    Biologically: social stimuli trigger amygdala social evaluation.
    """
    salience = getattr(social, 'social_salience', 0.0)
    if salience > 0.2:
        excess = salience - 0.2  # [0, 0.8]
        # Positive valence shift from social engagement
        current_val = getattr(limbic, 'valence', 0.0)
        new_val = _clamp(current_val + 0.15 * excess, -1.0, 1.0)
        try:
            limbic.valence = new_val
        except AttributeError:
            pass
        # Moderate arousal increase
        current_ar = getattr(limbic, 'arousal', 0.3)
        new_ar = _clamp(current_ar + 0.1 * excess, 0.0, 1.0)
        try:
            limbic.arousal = new_ar
        except AttributeError:
            pass


# ─── Registry ─────────────────────────────────────────────────────────────────

class InterBridgeCouplingRegistry:
    """Central registry for inter-bridge coupling pathways.

    Manages directed coupling pathways and propagates signals between
    bridge states in a single pass per tick.

    Parameters
    ----------
    register_defaults : bool
        Whether to register the 6 default pathways on init (default True).
    """

    def __init__(self, register_defaults: bool = True):
        self._pathways: List[CouplingPathway] = []
        self._propagation_count: int = 0
        if register_defaults:
            self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the 6 biologically-motivated coupling pathways.

        Order matters: pathways are topologically sorted so cascades
        propagate within a single pass. Incoming couplings to a bridge
        fire before that bridge's outgoing couplings.

        Dependency chain:
            sleep → neuromod  (independent)
            defense → motor → integration → limbic → visceral
            social → limbic → visceral
        """
        # --- Independent pathways first ---
        self.register(CouplingPathway(
            name='sleep_to_neuromod',
            source_bridge='sleep_wake',
            target_bridge='neuromod',
            transform=_sleep_to_neuromod,
            description='Sleep→catecholamines: low arousal suppresses DA/NE',
        ))
        # --- Defense→Motor chain ---
        self.register(CouplingPathway(
            name='defense_to_motor',
            source_bridge='defense',
            target_bridge='motor',
            transform=_defense_to_motor,
            description='PAG→motor: threat activates fight/flight readiness',
        ))
        # --- Social→Limbic (before limbic outgoing) ---
        self.register(CouplingPathway(
            name='social_to_limbic',
            source_bridge='social',
            target_bridge='limbic',
            transform=_social_to_limbic,
            description='Social signals→Amygdala emotional response',
        ))
        # --- Motor→Integration (after defense→motor) ---
        self.register(CouplingPathway(
            name='motor_to_integration',
            source_bridge='motor',
            target_bridge='integration',
            transform=_motor_to_integration,
            description='Motor efference copy→Claustrum integration',
        ))
        # --- Integration→Limbic (after motor→integration) ---
        self.register(CouplingPathway(
            name='integration_to_limbic',
            source_bridge='integration',
            target_bridge='limbic',
            transform=_integration_to_limbic,
            description='Claustrum binding→Amygdala salience gating',
        ))
        # --- Limbic→Visceral (last: after all limbic inputs) ---
        self.register(CouplingPathway(
            name='limbic_to_visceral',
            source_bridge='limbic',
            target_bridge='visceral',
            transform=_limbic_to_visceral,
            description='Amygdala→NTS: emotional arousal triggers autonomic response',
        ))

    def register(self, pathway: CouplingPathway) -> None:
        """Register a new coupling pathway."""
        self._pathways.append(pathway)

    def unregister(self, name: str) -> bool:
        """Remove a pathway by name. Returns True if found."""
        before = len(self._pathways)
        self._pathways = [p for p in self._pathways if p.name != name]
        return len(self._pathways) < before

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a pathway by name. Returns True if found."""
        for p in self._pathways:
            if p.name == name:
                p.enabled = enabled
                return True
        return False

    def propagate(self, bridge_states: Dict[str, Any]) -> int:
        """Apply all enabled coupling pathways.

        Parameters
        ----------
        bridge_states : dict
            Maps bridge name to state object (dataclass or dict).
            Keys: 'neuromod', 'cortex', 'limbic', 'sleep_wake', 'motor',
                  'defense', 'memory', 'integration', 'visceral', 'social'.

        Returns
        -------
        int
            Number of pathways that fired (had both source and target present).
        """
        fired = 0
        for pathway in self._pathways:
            if not pathway.enabled:
                continue
            source = bridge_states.get(pathway.source_bridge)
            target = bridge_states.get(pathway.target_bridge)
            if source is None or target is None:
                continue
            try:
                pathway.transform(source, target)
                fired += 1
            except Exception as e:
                logger.warning(
                    f"Coupling {pathway.name} failed: {e}",
                    exc_info=False,
                )
        self._propagation_count += 1
        return fired

    @property
    def pathways(self) -> List[CouplingPathway]:
        return list(self._pathways)

    @property
    def propagation_count(self) -> int:
        return self._propagation_count

    def get_pathway(self, name: str) -> Optional[CouplingPathway]:
        """Get a pathway by name."""
        for p in self._pathways:
            if p.name == name:
                return p
        return None

    def list_pathways(self) -> List[Dict[str, Any]]:
        """Return summary of all pathways."""
        return [
            {
                'name': p.name,
                'source': p.source_bridge,
                'target': p.target_bridge,
                'enabled': p.enabled,
                'description': p.description,
            }
            for p in self._pathways
        ]
