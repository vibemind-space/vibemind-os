"""
Configuration Validation, Hot-Reload, and Diff Logging (PHASE 5: P5.73-75)

P5.73: Config Schema Validation
  - Validates all sections of default.yaml against expected schema
  - Type checking, range validation, required fields
  - Returns structured errors/warnings

P5.74: Config Hot-Reload
  - File watcher for YAML config changes
  - Reloads and re-validates on file modification
  - Callbacks to notify subsystems of config changes

P5.75: Config Diff Logging
  - Logs non-default values at startup
  - Compares running config to defaults
  - Structured diff output for debugging
"""

import os
import yaml
import time
import logging
import threading
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from copy import deepcopy

logger = logging.getLogger('brain.config')


# ─────────────────────────────────────────────────────────
# P5.73: Config Schema Validation
# ─────────────────────────────────────────────────────────

@dataclass
class ConfigValidationError:
    """A single validation error or warning."""
    section: str        # e.g. 'neuromodulation'
    field: str          # e.g. 'baseline_dopamine'
    message: str        # e.g. 'Must be between 0 and 1'
    severity: str       # 'error' or 'warning'

    def to_dict(self) -> Dict:
        return {
            'section': self.section,
            'field': self.field,
            'message': self.message,
            'severity': self.severity,
        }


# Schema definition: section → field → {type, required, min, max, default, choices}
CONFIG_SCHEMA: Dict[str, Dict[str, Dict]] = {
    'cognitive_loop': {
        'enabled': {'type': bool, 'required': False, 'default': False},
        'memory_routing_bias_strength': {'type': float, 'required': False, 'default': 0.25, 'min': 0.0, 'max': 1.0},
        'attention_gating_strength': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
        'attention_ctm_threshold': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'neuro_temperature_sensitivity': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 2.0},
        'low_dopamine_threshold': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'high_norepinephrine_threshold': {'type': float, 'required': False, 'default': 0.7, 'min': 0.0, 'max': 1.0},
        'base_ctm_threshold': {'type': float, 'required': False, 'default': 0.4, 'min': 0.0, 'max': 1.0},
        'uncertainty_ctm_reduction': {'type': float, 'required': False, 'default': 0.2, 'min': 0.0, 'max': 1.0},
        'reconsider_confidence_threshold': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'reconsider_pe_threshold': {'type': float, 'required': False, 'default': 0.7, 'min': 0.0, 'max': 1.0},
        'max_loop_iterations': {'type': int, 'required': False, 'default': 2, 'min': 1, 'max': 10},
        'enable_memory_bias': {'type': bool, 'required': False, 'default': True},
        'enable_attention_driving': {'type': bool, 'required': False, 'default': True},
        'enable_neuro_modulation': {'type': bool, 'required': False, 'default': True},
        'enable_dynamic_ctm': {'type': bool, 'required': False, 'default': True},
        'enable_reflection_loop': {'type': bool, 'required': False, 'default': True},
        'enable_inline_consolidation': {'type': bool, 'required': False, 'default': True},
        'ctm_timeout_seconds': {'type': float, 'required': False, 'default': 30.0, 'min': 1.0, 'max': 300.0},
        # Phase 6 enable flags
        'enable_safety_layer': {'type': bool, 'required': False, 'default': True},
        'enable_explanation_gen': {'type': bool, 'required': False, 'default': True},
        'enable_theory_of_mind': {'type': bool, 'required': False, 'default': True},
        'enable_causal_reasoning': {'type': bool, 'required': False, 'default': True},
        'enable_intrinsic_curiosity': {'type': bool, 'required': False, 'default': True},
        'enable_temporal_patterns': {'type': bool, 'required': False, 'default': True},
        'enable_autonomous_goals': {'type': bool, 'required': False, 'default': True},
        'enable_self_improvement': {'type': bool, 'required': False, 'default': True},
        'enable_multimodal_fusion': {'type': bool, 'required': False, 'default': True},
        'enable_formal_verifier': {'type': bool, 'required': False, 'default': True},
        'enable_thought_decoder': {'type': bool, 'required': False, 'default': True},
    },
    'neuromodulation': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'baseline_dopamine': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
        'baseline_serotonin': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
        'baseline_norepinephrine': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
        'decay_rate': {'type': float, 'required': False, 'default': 0.05, 'min': 0.0, 'max': 1.0},
        'sensitivity': {'type': float, 'required': False, 'default': 1.0, 'min': 0.0, 'max': 10.0},
        'history_size': {'type': int, 'required': False, 'default': 50, 'min': 1, 'max': 10000},
    },
    'consciousness': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'state_history_size': {'type': int, 'required': False, 'default': 100, 'min': 1, 'max': 10000},
        'calibration_window': {'type': int, 'required': False, 'default': 50, 'min': 1, 'max': 10000},
        'awareness_threshold': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
        'uncertainty_sensitivity': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
    },
    'memory': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'working_memory_capacity': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 1000},
        'episodic_max_size': {'type': int, 'required': False, 'default': 1000, 'min': 1, 'max': 1000000},
        'similarity_threshold': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'gate_weight': {'type': float, 'required': False, 'default': 0.7, 'min': 0.0, 'max': 1.0},
        'context_cache_ttl': {'type': float, 'required': False, 'default': 5.0, 'min': 0.0, 'max': 3600.0},
        'persistence_dir': {'type': str, 'required': False, 'default': 'data/episodic_memory'},
    },
    'ctm_ensemble': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'enable_logic_ctm': {'type': bool, 'required': False, 'default': True},
        'enable_temporal_ctm': {'type': bool, 'required': False, 'default': True},
        'enable_value_ctm': {'type': bool, 'required': False, 'default': True},
        'enable_evolution': {'type': bool, 'required': False, 'default': True},
        'consciousness_threshold': {'type': float, 'required': False, 'default': 0.85, 'min': 0.0, 'max': 1.0},
        'max_reasoning_steps': {'type': int, 'required': False, 'default': 50, 'min': 1, 'max': 10000},
        'max_concurrent_per_ctm': {'type': int, 'required': False, 'default': 2, 'min': 1, 'max': 100},
        'mixed_domain_threshold': {'type': float, 'required': False, 'default': 0.70, 'min': 0.0, 'max': 1.0},
        'evolution_population_size': {'type': int, 'required': False, 'default': 20, 'min': 2, 'max': 1000},
        'evolution_trigger_count': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 10000},
        'feature_dim': {'type': int, 'required': False, 'default': 256, 'min': 8, 'max': 4096},
        'fallback_strategy': {'type': str, 'required': False, 'default': 'primary_only', 'choices': ['primary_only', 'ensemble_vote', 'abstain']},
    },
    'goal_graph': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'max_goals': {'type': int, 'required': False, 'default': 50, 'min': 1, 'max': 10000},
        'priority_decay_rate': {'type': float, 'required': False, 'default': 0.01, 'min': 0.0, 'max': 1.0},
        'critical_path_algorithm': {'type': str, 'required': False, 'default': 'longest', 'choices': ['longest', 'shortest']},
        'auto_cleanup_completed': {'type': bool, 'required': False, 'default': True},
    },
    'predictive_coding': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'prediction_history_size': {'type': int, 'required': False, 'default': 100, 'min': 1, 'max': 100000},
        'error_threshold': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 10.0},
        'curiosity_weight': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'learning_rate_generative': {'type': float, 'required': False, 'default': 0.01, 'min': 0.0, 'max': 1.0},
        'surprise_history_min': {'type': int, 'required': False, 'default': 5, 'min': 1, 'max': 10000},
    },
    'dream_mode': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'replay_rate': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'counterfactual_rate': {'type': float, 'required': False, 'default': 0.2, 'min': 0.0, 'max': 1.0},
        'consolidation_threshold': {'type': float, 'required': False, 'default': 0.7, 'min': 0.0, 'max': 1.0},
        'pattern_min_support': {'type': int, 'required': False, 'default': 3, 'min': 1, 'max': 10000},
        'max_dreams_per_cycle': {'type': int, 'required': False, 'default': 5, 'min': 1, 'max': 1000},
    },
    'emotional_system': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'valence_decay_rate': {'type': float, 'required': False, 'default': 0.05, 'min': 0.0, 'max': 1.0},
        'arousal_decay_rate': {'type': float, 'required': False, 'default': 0.1, 'min': 0.0, 'max': 1.0},
        'emotional_memory_weight': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'fear_threshold': {'type': float, 'required': False, 'default': 0.7, 'min': 0.0, 'max': 1.0},
        'reward_threshold': {'type': float, 'required': False, 'default': 0.7, 'min': 0.0, 'max': 1.0},
    },
    'homeostatic': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'energy_per_task': {'type': float, 'required': False, 'default': 0.02, 'min': 0.0, 'max': 1.0},
        'energy_recovery_rate': {'type': float, 'required': False, 'default': 0.01, 'min': 0.0, 'max': 1.0},
        'energy_rest_recovery': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'fatigue_per_task': {'type': float, 'required': False, 'default': 0.015, 'min': 0.0, 'max': 1.0},
        'fatigue_decay_rate': {'type': float, 'required': False, 'default': 0.005, 'min': 0.0, 'max': 1.0},
        'fatigue_complexity_multiplier': {'type': float, 'required': False, 'default': 1.5, 'min': 0.0, 'max': 10.0},
        'sleep_accumulation_rate': {'type': float, 'required': False, 'default': 0.001, 'min': 0.0, 'max': 1.0},
        'sleep_dream_reduction': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
        'sleep_threshold': {'type': float, 'required': False, 'default': 0.8, 'min': 0.0, 'max': 1.0},
        'stress_threshold': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
        'low_energy_threshold': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'high_fatigue_threshold': {'type': float, 'required': False, 'default': 0.7, 'min': 0.0, 'max': 1.0},
    },
    'heartbeat': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'interval_seconds': {'type': float, 'required': False, 'default': 30.0, 'min': 1.0, 'max': 3600.0},
        'enable_dream_mode': {'type': bool, 'required': False, 'default': True},
        'dream_idle_threshold_seconds': {'type': float, 'required': False, 'default': 300.0, 'min': 1.0, 'max': 86400.0},
        'enable_temporal_updates': {'type': bool, 'required': False, 'default': True},
        'enable_neuromodulation_decay': {'type': bool, 'required': False, 'default': True},
        'enable_meta_learning_checks': {'type': bool, 'required': False, 'default': True},
        'enable_health_monitoring': {'type': bool, 'required': False, 'default': True},
        'meta_learning_check_interval': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 10000},
    },
    'subsystem_registry': {
        'circuit_breaker_threshold': {'type': int, 'required': False, 'default': 3, 'min': 1, 'max': 100},
        'circuit_breaker_reset_seconds': {'type': float, 'required': False, 'default': 60.0, 'min': 1.0, 'max': 86400.0},
    },
    'layer4': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'strict_security': {'type': bool, 'required': False, 'default': True},
        'timing_threshold': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
    },
    # Phase 6: Advanced cognitive capabilities
    'theory_of_mind': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'state_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 1024},
        'action_dim': {'type': int, 'required': False, 'default': 16, 'min': 4, 'max': 256},
        'belief_dim': {'type': int, 'required': False, 'default': 32, 'min': 4, 'max': 512},
        'goal_dim': {'type': int, 'required': False, 'default': 16, 'min': 4, 'max': 256},
        'hidden_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 1024},
    },
    'causal_reasoning': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'max_nodes': {'type': int, 'required': False, 'default': 100, 'min': 1, 'max': 10000},
        'intervention_threshold': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
    },
    'intrinsic_curiosity': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'state_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 1024},
        'action_dim': {'type': int, 'required': False, 'default': 16, 'min': 4, 'max': 256},
        'feature_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 1024},
        'hidden_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 1024},
        'curiosity_scale': {'type': float, 'required': False, 'default': 1.0, 'min': 0.0, 'max': 10.0},
    },
    'safety_layer': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'action_dim': {'type': int, 'required': False, 'default': 16, 'min': 4, 'max': 256},
        'block_threshold': {'type': float, 'required': False, 'default': 0.8, 'min': 0.0, 'max': 1.0},
    },
    'explanation_generator': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'max_feature_contributions': {'type': int, 'required': False, 'default': 5, 'min': 1, 'max': 50},
    },
    'self_improvement': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'window_size': {'type': int, 'required': False, 'default': 100, 'min': 10, 'max': 10000},
        'degradation_threshold': {'type': float, 'required': False, 'default': 0.1, 'min': 0.0, 'max': 1.0},
    },
    'autonomous_goals': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'max_concurrent_goals': {'type': int, 'required': False, 'default': 5, 'min': 1, 'max': 50},
    },
    'multimodal_fusion': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'unified_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 4096},
        'fusion_type': {'type': str, 'required': False, 'default': 'gated', 'choices': ['attention', 'gated', 'concat']},
        'use_modality_dropout': {'type': bool, 'required': False, 'default': True},
        'dropout_prob': {'type': float, 'required': False, 'default': 0.2, 'min': 0.0, 'max': 1.0},
    },
    'sensorimotor': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'sensory_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 1024},
        'motor_dim': {'type': int, 'required': False, 'default': 16, 'min': 4, 'max': 256},
        'hidden_dim': {'type': int, 'required': False, 'default': 32, 'min': 8, 'max': 1024},
        'learning_rate': {'type': float, 'required': False, 'default': 0.01, 'min': 0.0, 'max': 1.0},
    },
    'formal_verifier': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'state_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 1024},
        'action_dim': {'type': int, 'required': False, 'default': 16, 'min': 4, 'max': 256},
        'timeout_ms': {'type': int, 'required': False, 'default': 5000, 'min': 100, 'max': 60000},
    },
    'thought_decoder': {
        'enabled': {'type': bool, 'required': False, 'default': True},
        'thought_dim': {'type': int, 'required': False, 'default': 64, 'min': 8, 'max': 4096},
        'num_prefix_tokens': {'type': int, 'required': False, 'default': 4, 'min': 1, 'max': 64},
        'max_length': {'type': int, 'required': False, 'default': 32, 'min': 1, 'max': 1024},
        'device': {'type': str, 'required': False, 'default': 'cpu', 'choices': ['cpu', 'cuda']},
    },
    'production': {
        'session_log_dir': {'type': str, 'required': False, 'default': 'data/logs'},
        'matrix_dir': {'type': str, 'required': False, 'default': 'production/trained_matrices'},
        'feedback_dir': {'type': str, 'required': False, 'default': 'production/feedback'},
        'learning_rate': {'type': float, 'required': False, 'default': 0.005, 'min': 0.0, 'max': 1.0},
        'enable_continuous_learning': {'type': bool, 'required': False, 'default': True},
        'enable_semantic_coherence': {'type': bool, 'required': False, 'default': True},
        'embedding_type': {'type': str, 'required': False, 'default': 'hash', 'choices': ['hash', 'neural']},
        'k_min': {'type': float, 'required': False, 'default': 0.55, 'min': 0.0, 'max': 1.0},
        'green_threshold': {'type': float, 'required': False, 'default': 0.75, 'min': 0.0, 'max': 1.0},
        'alpha': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
    },
    # Phase 4: Language & Communication (P4.46-60)
    'language_center': {
        'max_context_tokens': {'type': int, 'required': False, 'default': 2000, 'min': 100, 'max': 32000},
        'default_abstraction': {'type': str, 'required': False, 'default': 'standard',
                                'choices': ['brief', 'standard', 'technical', 'conversational']},
        'enable_llm': {'type': bool, 'required': False, 'default': False},
        'llm_timeout_ms': {'type': int, 'required': False, 'default': 5000, 'min': 100, 'max': 60000},
        'template_fallback': {'type': bool, 'required': False, 'default': True},
    },
    'personality': {
        'traits': {'type': dict, 'required': False, 'default': {}},
    },
    'communication_style': {
        'default_mode': {'type': str, 'required': False, 'default': 'technical',
                         'choices': ['technical', 'chat', 'report', 'alarm']},
        'user_preference': {'type': str, 'required': False, 'default': None},
        'feedback_learning_rate': {'type': float, 'required': False, 'default': 0.05, 'min': 0.0, 'max': 1.0},
    },
    'status_updater': {
        'verbosity': {'type': str, 'required': False, 'default': 'important',
                      'choices': ['silent', 'important', 'all']},
        'max_queue_size': {'type': int, 'required': False, 'default': 50, 'min': 1, 'max': 1000},
    },
    'suggestion_engine': {
        'confidence_threshold': {'type': float, 'required': False, 'default': 0.7, 'min': 0.0, 'max': 1.0},
        'cooldown_seconds': {'type': float, 'required': False, 'default': 300.0, 'min': 0.0, 'max': 86400.0},
        'max_suggestions': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 100},
    },
    'dialogue_manager': {
        'max_context_depth': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 100},
    },

    # ── Phase 1: Sensor Systems (P1.3-6, P1.9-15) ──
    'system_vitals_sensor': {
        'poll_interval_seconds': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 3600},
        'anomaly_window': {'type': int, 'required': False, 'default': 30, 'min': 5, 'max': 1000},
        'sigma_threshold': {'type': float, 'required': False, 'default': 2.0, 'min': 0.5, 'max': 5.0},
    },
    'file_system_sensor': {
        'watch_paths': {'type': list, 'required': False, 'default': []},
        'poll_interval': {'type': int, 'required': False, 'default': 5, 'min': 1, 'max': 3600},
        'max_events': {'type': int, 'required': False, 'default': 1000, 'min': 10, 'max': 100000},
    },
    'process_sensor': {
        'monitored_ports': {'type': dict, 'required': False, 'default': {}},
        'check_interval': {'type': int, 'required': False, 'default': 15, 'min': 1, 'max': 3600},
    },
    'log_sensor': {
        'log_paths': {'type': list, 'required': False, 'default': []},
        'tail_lines': {'type': int, 'required': False, 'default': 100, 'min': 10, 'max': 10000},
    },
    'git_activity_sensor': {
        'repo_paths': {'type': list, 'required': False, 'default': []},
        'check_interval': {'type': int, 'required': False, 'default': 300, 'min': 10, 'max': 86400},
        'since_minutes': {'type': int, 'required': False, 'default': 60, 'min': 1, 'max': 10080},
    },
    'sensor_registry': {
        'max_events_per_second': {'type': int, 'required': False, 'default': 100, 'min': 1, 'max': 10000},
        'event_buffer_size': {'type': int, 'required': False, 'default': 10000, 'min': 100, 'max': 1000000},
    },
    'sensor_fusion': {
        'correlation_window_seconds': {'type': float, 'required': False, 'default': 5.0, 'min': 0.1, 'max': 60.0},
        'min_events_for_fusion': {'type': int, 'required': False, 'default': 2, 'min': 2, 'max': 20},
    },
    'perception_pipeline': {
        'pipeline_enabled': {'type': bool, 'required': False, 'default': True},
        'batch_size': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 1000},
    },
    'attention_sampling': {
        'base_multiplier': {'type': float, 'required': False, 'default': 1.0, 'min': 0.01, 'max': 10.0},
        'max_multiplier': {'type': float, 'required': False, 'default': 5.0, 'min': 1.0, 'max': 100.0},
        'min_multiplier': {'type': float, 'required': False, 'default': 0.2, 'min': 0.01, 'max': 1.0},
    },
    'novelty_filter': {
        'novelty_threshold': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'history_window': {'type': int, 'required': False, 'default': 100, 'min': 10, 'max': 10000},
    },
    'sensory_memory': {
        'buffer_size': {'type': int, 'required': False, 'default': 1000, 'min': 10, 'max': 100000},
        'retention_seconds': {'type': float, 'required': False, 'default': 60.0, 'min': 1.0, 'max': 3600.0},
    },

    # ── Phase 2: Action Systems (P2.18, P2.25-30) ──
    'approval_gate': {
        'default_timeout': {'type': int, 'required': False, 'default': 60, 'min': 5, 'max': 3600},
        'auto_reject_on_timeout': {'type': bool, 'required': False, 'default': True},
        'risk_threshold': {'type': str, 'required': False, 'default': 'high', 'choices': ['low', 'medium', 'high', 'critical']},
    },
    'action_planner': {
        'max_plan_depth': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 100},
        'max_actions_per_plan': {'type': int, 'required': False, 'default': 50, 'min': 1, 'max': 1000},
        'default_risk': {'type': str, 'required': False, 'default': 'low', 'choices': ['low', 'medium', 'high', 'critical']},
    },
    'action_validator': {
        'blocked_patterns': {'type': list, 'required': False, 'default': []},
        'max_resource_cost': {'type': int, 'required': False, 'default': 100, 'min': 1, 'max': 10000},
    },
    'action_monitor': {
        'default_timeout_seconds': {'type': int, 'required': False, 'default': 300, 'min': 10, 'max': 86400},
        'max_retries': {'type': int, 'required': False, 'default': 3, 'min': 0, 'max': 20},
        'escalation_threshold': {'type': float, 'required': False, 'default': 0.9, 'min': 0.0, 'max': 1.0},
    },
    'action_outcome_detector': {
        'unknown_timeout': {'type': int, 'required': False, 'default': 60, 'min': 5, 'max': 3600},
    },
    'action_replay_memory': {
        'max_memories': {'type': int, 'required': False, 'default': 5000, 'min': 100, 'max': 100000},
        'priority_boost_on_failure': {'type': float, 'required': False, 'default': 2.0, 'min': 1.0, 'max': 10.0},
        'replay_batch_size': {'type': int, 'required': False, 'default': 32, 'min': 1, 'max': 1000},
    },
    'action_learning': {
        'learning_rate': {'type': float, 'required': False, 'default': 0.1, 'min': 0.001, 'max': 1.0},
        'min_samples': {'type': int, 'required': False, 'default': 5, 'min': 1, 'max': 100},
        'decay_factor': {'type': float, 'required': False, 'default': 0.95, 'min': 0.0, 'max': 1.0},
    },

    # ── Phase 5: Learning Systems (P5.61-75) ──
    'experience_replay': {
        'max_buffer_size': {'type': int, 'required': False, 'default': 5000, 'min': 100, 'max': 100000},
        'sample_batch_size': {'type': int, 'required': False, 'default': 32, 'min': 1, 'max': 1000},
        'min_priority': {'type': float, 'required': False, 'default': 0.1, 'min': 0.0, 'max': 1.0},
    },
    'transfer_learning': {
        'min_similarity': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 1.0},
        'max_transfers': {'type': int, 'required': False, 'default': 200, 'min': 10, 'max': 10000},
    },
    'skill_library': {
        'max_skills': {'type': int, 'required': False, 'default': 500, 'min': 10, 'max': 10000},
        'deprecation_threshold': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'min_executions_to_evaluate': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 1000},
    },
    'world_model': {
        'max_entities': {'type': int, 'required': False, 'default': 500, 'min': 10, 'max': 10000},
        'max_anomalies': {'type': int, 'required': False, 'default': 1000, 'min': 10, 'max': 50000},
        'baseline_alpha': {'type': float, 'required': False, 'default': 0.1, 'min': 0.01, 'max': 1.0},
    },
    'causal_world_model': {
        'min_observations': {'type': int, 'required': False, 'default': 3, 'min': 1, 'max': 100},
        'min_strength': {'type': float, 'required': False, 'default': 0.4, 'min': 0.0, 'max': 1.0},
        'max_links': {'type': int, 'required': False, 'default': 1000, 'min': 10, 'max': 50000},
    },
    'predictive_world_model': {
        'min_confidence': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'max_predictions': {'type': int, 'required': False, 'default': 500, 'min': 10, 'max': 50000},
    },
    'knowledge_gaps': {
        'failure_threshold': {'type': int, 'required': False, 'default': 3, 'min': 1, 'max': 100},
        'decay_days': {'type': int, 'required': False, 'default': 7, 'min': 1, 'max': 365},
        'max_gaps': {'type': int, 'required': False, 'default': 200, 'min': 10, 'max': 10000},
    },
    'collaborative_learning': {
        'max_strategies': {'type': int, 'required': False, 'default': 500, 'min': 10, 'max': 10000},
        'min_confidence': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
    },

    # ── Phase 6: Identity Systems (P6.76-85) ──
    'self_model': {
        'max_capabilities': {'type': int, 'required': False, 'default': 200, 'min': 10, 'max': 10000},
        'max_strategies': {'type': int, 'required': False, 'default': 100, 'min': 10, 'max': 10000},
        'max_tools': {'type': int, 'required': False, 'default': 50, 'min': 5, 'max': 1000},
        'max_weaknesses': {'type': int, 'required': False, 'default': 100, 'min': 10, 'max': 10000},
        'weakness_auto_resolve_threshold': {'type': int, 'required': False, 'default': 5, 'min': 1, 'max': 100},
    },
    'value_system': {
        'values': {'type': dict, 'required': False, 'default': {}},
        'min_value': {'type': float, 'required': False, 'default': 0.0, 'min': 0.0, 'max': 1.0},
        'max_value': {'type': float, 'required': False, 'default': 1.0, 'min': 0.0, 'max': 1.0},
    },
    'emotional_memory_system': {
        'max_memories': {'type': int, 'required': False, 'default': 500, 'min': 10, 'max': 100000},
        'similarity_threshold': {'type': float, 'required': False, 'default': 0.3, 'min': 0.0, 'max': 1.0},
        'caution_decay_hours': {'type': float, 'required': False, 'default': 24.0, 'min': 0.1, 'max': 720.0},
    },
    'mood_system': {
        'inertia': {'type': float, 'required': False, 'default': 0.85, 'min': 0.0, 'max': 1.0},
        'valence_sensitivity': {'type': float, 'required': False, 'default': 0.5, 'min': 0.0, 'max': 2.0},
        'arousal_sensitivity': {'type': float, 'required': False, 'default': 0.4, 'min': 0.0, 'max': 2.0},
        'history_window': {'type': int, 'required': False, 'default': 100, 'min': 10, 'max': 10000},
    },
    'stress_response': {
        'max_concurrent_tasks': {'type': int, 'required': False, 'default': 10, 'min': 1, 'max': 100},
        'error_window_minutes': {'type': float, 'required': False, 'default': 30.0, 'min': 1.0, 'max': 1440.0},
        'chronic_threshold_hours': {'type': float, 'required': False, 'default': 2.0, 'min': 0.1, 'max': 48.0},
        'recovery_threshold': {'type': float, 'required': False, 'default': 0.85, 'min': 0.0, 'max': 1.0},
        'event_buffer_size': {'type': int, 'required': False, 'default': 1000, 'min': 100, 'max': 100000},
    },
    'user_model': {
        'max_interactions': {'type': int, 'required': False, 'default': 1000, 'min': 10, 'max': 100000},
        'expertise_window': {'type': int, 'required': False, 'default': 50, 'min': 5, 'max': 10000},
        'activity_smoothing': {'type': float, 'required': False, 'default': 0.1, 'min': 0.0, 'max': 1.0},
        'default_preferences': {'type': dict, 'required': False, 'default': {}},
    },

    # ── Phase 7: Resilience Systems (P7.86-92) ──
    'graceful_degradation': {
        'fallback_chains': {'type': dict, 'required': False, 'default': {}},
    },
    'resource_awareness': {
        'tokens_per_minute': {'type': int, 'required': False, 'default': 1000, 'min': 1, 'max': 1000000},
        'tokens_per_hour': {'type': int, 'required': False, 'default': 50000, 'min': 100, 'max': 10000000},
        'cpu_high_threshold': {'type': float, 'required': False, 'default': 80.0, 'min': 0.0, 'max': 100.0},
        'ram_high_threshold': {'type': float, 'required': False, 'default': 85.0, 'min': 0.0, 'max': 100.0},
        'max_concurrent_base': {'type': int, 'required': False, 'default': 4, 'min': 1, 'max': 100},
        'history_size': {'type': int, 'required': False, 'default': 120, 'min': 10, 'max': 10000},
    },

    # ── Phase 8: Ecosystem Intelligence (P8.96-100) ──
    'ecosystem_intelligence': {
        'orchestrator_of_orchestrators': {'type': dict, 'required': False, 'default': {}},
    },
}


def validate_config(config: Dict) -> List[ConfigValidationError]:
    """
    Validate a full configuration dict against the schema.

    Args:
        config: The loaded YAML config dict

    Returns:
        List of ConfigValidationError (empty means valid)
    """
    errors: List[ConfigValidationError] = []

    for section_name, field_defs in CONFIG_SCHEMA.items():
        section = config.get(section_name)
        if section is None:
            # Missing section is OK — subsystem will use defaults
            continue

        if not isinstance(section, dict):
            errors.append(ConfigValidationError(
                section=section_name,
                field='',
                message=f'Section must be a dict, got {type(section).__name__}',
                severity='error',
            ))
            continue

        for field_name, rules in field_defs.items():
            value = section.get(field_name)
            if value is None:
                if rules.get('required', False):
                    errors.append(ConfigValidationError(
                        section=section_name,
                        field=field_name,
                        message='Required field missing',
                        severity='error',
                    ))
                continue

            # Type check (allow int where float is expected)
            expected_type = rules['type']
            if expected_type == float and isinstance(value, int):
                value = float(value)  # int is OK for float fields
            elif not isinstance(value, expected_type):
                errors.append(ConfigValidationError(
                    section=section_name,
                    field=field_name,
                    message=f'Expected {expected_type.__name__}, got {type(value).__name__}',
                    severity='error',
                ))
                continue

            # Range check
            if 'min' in rules and isinstance(value, (int, float)):
                if value < rules['min']:
                    errors.append(ConfigValidationError(
                        section=section_name,
                        field=field_name,
                        message=f'Value {value} below minimum {rules["min"]}',
                        severity='error',
                    ))

            if 'max' in rules and isinstance(value, (int, float)):
                if value > rules['max']:
                    errors.append(ConfigValidationError(
                        section=section_name,
                        field=field_name,
                        message=f'Value {value} above maximum {rules["max"]}',
                        severity='error',
                    ))

            # Choices check
            if 'choices' in rules and value not in rules['choices']:
                errors.append(ConfigValidationError(
                    section=section_name,
                    field=field_name,
                    message=f'Value "{value}" not in allowed choices: {rules["choices"]}',
                    severity='error',
                ))

        # Warn about unknown fields in section
        known_fields = set(field_defs.keys())
        actual_fields = set(section.keys())
        unknown = actual_fields - known_fields
        for uf in unknown:
            errors.append(ConfigValidationError(
                section=section_name,
                field=uf,
                message=f'Unknown field "{uf}" in section "{section_name}"',
                severity='warning',
            ))

    return errors


def validate_config_file(config_path: str) -> Tuple[Dict, List[ConfigValidationError]]:
    """
    Load and validate a config file.

    Args:
        config_path: Path to YAML config file

    Returns:
        (config_dict, list_of_errors)
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    errors = validate_config(config)
    return config, errors


# ─────────────────────────────────────────────────────────
# P5.74: Config Hot-Reload
# ─────────────────────────────────────────────────────────

class ConfigHotReloader:
    """
    Watches a YAML config file for changes and notifies subscribers.

    Usage:
        reloader = ConfigHotReloader('configs/default.yaml')
        reloader.on_reload(my_callback)   # Register callback
        reloader.start()                  # Start watching (background thread)
        ...
        reloader.stop()                   # Stop watching
    """

    def __init__(
        self,
        config_path: str,
        poll_interval: float = 2.0,
        validate_on_reload: bool = True,
    ):
        """
        Args:
            config_path: Path to the YAML config file
            poll_interval: Seconds between file modification checks
            validate_on_reload: Whether to validate config on reload
        """
        self.config_path = os.path.abspath(config_path)
        self.poll_interval = poll_interval
        self.validate_on_reload = validate_on_reload

        self._callbacks: List[Callable[[Dict, Dict], None]] = []
        self._error_callbacks: List[Callable[[List[ConfigValidationError]], None]] = []
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_mtime: float = 0.0
        self._current_config: Optional[Dict] = None
        self._lock = threading.Lock()
        self.reload_count = 0

    def on_reload(self, callback: Callable[[Dict, Dict], None]):
        """
        Register a callback for config changes.

        Callback signature: (new_config: Dict, old_config: Dict) -> None
        """
        self._callbacks.append(callback)

    def on_validation_error(self, callback: Callable[[List[ConfigValidationError]], None]):
        """Register a callback for validation errors on reload."""
        self._error_callbacks.append(callback)

    def load_current(self) -> Dict:
        """Load the current config (without starting the watcher)."""
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        self._current_config = config
        self._last_mtime = os.path.getmtime(self.config_path)
        return config

    def start(self):
        """Start the file watcher background thread."""
        if self._thread is not None and self._thread.is_alive():
            return  # Already running

        # Load initial config
        self.load_current()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop,
            name='ConfigHotReloader',
            daemon=True,
        )
        self._thread.start()
        logger.info(f"ConfigHotReloader started watching: {self.config_path}")

    def stop(self):
        """Stop the file watcher."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval * 2)
            self._thread = None
        logger.info("ConfigHotReloader stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def current_config(self) -> Optional[Dict]:
        with self._lock:
            return deepcopy(self._current_config) if self._current_config else None

    def _watch_loop(self):
        """Background loop that polls for file changes."""
        while not self._stop_event.is_set():
            try:
                mtime = os.path.getmtime(self.config_path)
                if mtime > self._last_mtime:
                    self._handle_change(mtime)
            except FileNotFoundError:
                logger.warning(f"Config file not found: {self.config_path}")
            except Exception as e:
                logger.error(f"ConfigHotReloader error: {e}")

            self._stop_event.wait(self.poll_interval)

    def _handle_change(self, new_mtime: float):
        """Handle a detected file change."""
        try:
            with open(self.config_path, 'r') as f:
                new_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error on reload: {e}")
            return

        # Validate if enabled
        if self.validate_on_reload:
            errors = validate_config(new_config)
            real_errors = [e for e in errors if e.severity == 'error']
            if real_errors:
                logger.warning(f"Config reload has {len(real_errors)} validation errors - notifying error callbacks")
                for cb in self._error_callbacks:
                    try:
                        cb(real_errors)
                    except Exception as e:
                        logger.error(f"Error in validation error callback: {e}")
                return  # Don't apply invalid config

        with self._lock:
            old_config = self._current_config
            self._current_config = new_config
            self._last_mtime = new_mtime
            self.reload_count += 1

        logger.info(f"Config reloaded (reload #{self.reload_count})")

        # Notify callbacks
        for cb in self._callbacks:
            try:
                cb(new_config, old_config)
            except Exception as e:
                logger.error(f"Error in reload callback: {e}")

    def to_dict(self) -> Dict:
        """Get reloader status."""
        return {
            'config_path': self.config_path,
            'is_running': self.is_running,
            'reload_count': self.reload_count,
            'poll_interval': self.poll_interval,
        }


# ─────────────────────────────────────────────────────────
# P5.75: Config Diff Logging
# ─────────────────────────────────────────────────────────

@dataclass
class ConfigDiffEntry:
    """A single diff between running config and defaults."""
    section: str
    field: str
    default_value: Any
    running_value: Any

    def to_dict(self) -> Dict:
        return {
            'section': self.section,
            'field': self.field,
            'default': self.default_value,
            'running': self.running_value,
        }


def compute_config_diff(config: Dict) -> List[ConfigDiffEntry]:
    """
    Compare running config against schema defaults.

    Args:
        config: The loaded YAML config

    Returns:
        List of diffs where running value differs from default
    """
    diffs: List[ConfigDiffEntry] = []

    for section_name, field_defs in CONFIG_SCHEMA.items():
        section = config.get(section_name)
        if section is None:
            continue

        if not isinstance(section, dict):
            continue

        for field_name, rules in field_defs.items():
            if 'default' not in rules:
                continue

            default_val = rules['default']
            running_val = section.get(field_name)

            if running_val is None:
                continue  # Not set, will use default anyway

            # Compare (handle float vs int)
            if isinstance(default_val, float) and isinstance(running_val, int):
                running_val = float(running_val)

            if running_val != default_val:
                diffs.append(ConfigDiffEntry(
                    section=section_name,
                    field=field_name,
                    default_value=default_val,
                    running_value=running_val,
                ))

    return diffs


def log_config_diff(config: Dict, log_level: int = logging.INFO):
    """
    Log all non-default config values at startup.

    Args:
        config: The loaded YAML config
        log_level: Logging level to use
    """
    diffs = compute_config_diff(config)

    if not diffs:
        logger.log(log_level, "Config: all values match defaults")
        return

    logger.log(log_level, f"Config: {len(diffs)} non-default value(s):")
    for d in diffs:
        logger.log(
            log_level,
            f"  [{d.section}] {d.field}: {d.default_value} → {d.running_value}"
        )

    return diffs


def compute_config_diff_between(old_config: Dict, new_config: Dict) -> List[ConfigDiffEntry]:
    """
    Compare two configs and find differences.

    Args:
        old_config: Previous config
        new_config: New config

    Returns:
        List of diffs
    """
    diffs: List[ConfigDiffEntry] = []

    # Get all section names from both
    all_sections = set()
    for section_name in CONFIG_SCHEMA:
        all_sections.add(section_name)

    for section_name in all_sections:
        old_section = (old_config or {}).get(section_name, {})
        new_section = (new_config or {}).get(section_name, {})

        if not isinstance(old_section, dict):
            old_section = {}
        if not isinstance(new_section, dict):
            new_section = {}

        # Get all keys from both
        all_keys = set(old_section.keys()) | set(new_section.keys())
        for key in all_keys:
            old_val = old_section.get(key)
            new_val = new_section.get(key)
            if old_val != new_val:
                diffs.append(ConfigDiffEntry(
                    section=section_name,
                    field=key,
                    default_value=old_val,  # "default" here means "old"
                    running_value=new_val,
                ))

    return diffs


# ─────────────────────────────────────────────────────────
# Convenience: startup validation + diff logging
# ─────────────────────────────────────────────────────────

def startup_config_check(config_path: str) -> Tuple[Dict, List[ConfigValidationError], List[ConfigDiffEntry]]:
    """
    Run full startup config check: load, validate, log diffs.

    Args:
        config_path: Path to YAML config

    Returns:
        (config, validation_errors, diffs_from_defaults)
    """
    config, errors = validate_config_file(config_path)

    # Log validation results
    real_errors = [e for e in errors if e.severity == 'error']
    warnings = [e for e in errors if e.severity == 'warning']

    if real_errors:
        logger.warning(f"Config validation: {len(real_errors)} error(s)")
        for e in real_errors:
            logger.warning(f"  [{e.section}] {e.field}: {e.message}")

    if warnings:
        logger.info(f"Config validation: {len(warnings)} warning(s)")
        for w in warnings:
            logger.info(f"  [{w.section}] {w.field}: {w.message}")

    if not real_errors and not warnings:
        logger.info("Config validation: OK (no errors or warnings)")

    # Log diffs
    diffs = compute_config_diff(config)
    if diffs:
        logger.info(f"Config: {len(diffs)} non-default value(s):")
        for d in diffs:
            logger.info(f"  [{d.section}] {d.field}: {d.default_value} → {d.running_value}")
    else:
        logger.info("Config: all values match defaults")

    return config, errors, diffs
