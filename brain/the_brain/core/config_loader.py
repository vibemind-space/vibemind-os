"""
Configuration loader for ATM-R.

Loads YAML configs and instantiates ThalamoPC6 or ThalamoPC6Adaptive.
"""

import yaml
import os
from typing import Dict, Union
from core.thalamo_pc_live import ThalamoPC6
from core.thalamo_pc_adaptive import ThalamoPC6Adaptive


def load_config(config_path: str) -> Dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to YAML config file

    Returns:
        Dict with configuration parameters
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    return config


def create_model_from_config(
    config: Union[str, Dict],
    adaptive: bool = False
) -> Union[ThalamoPC6, ThalamoPC6Adaptive]:
    """
    Create ThalamoPC6 or ThalamoPC6Adaptive from config.

    Args:
        config: Either path to YAML config file or dict
        adaptive: If True, create ThalamoPC6Adaptive; else ThalamoPC6

    Returns:
        Instantiated model
    """
    if isinstance(config, str):
        cfg = load_config(config)
    else:
        cfg = config

    # Extract base parameters
    base_params = {
        'modalities': cfg.get('modalities', None),
        'dimensions': cfg.get('dimensions', None),
        'tau': cfg.get('tau', None),
        'priors': cfg.get('priors', None),
        'beta': cfg.get('beta', None),
        'trn_lambda': cfg.get('trn', {}).get('lambda', 0.5),
        'gate_temp': cfg.get('gating', {}).get('temperature', 0.5),
        'num_targets': cfg.get('routing', {}).get('num_targets', 3),
        'dt': cfg.get('simulation', {}).get('dt', 1.0),
        'seed': cfg.get('simulation', {}).get('seed', 42),
        'nonlinearity': cfg.get('simulation', {}).get('nonlinearity', 'tanh'),
        'use_phase': cfg.get('phase', {}).get('use_phase', False),
        'omega': cfg.get('phase', {}).get('omega', None),
        'K_coupling': cfg.get('phase', {}).get('coupling_strength', 0.05)
    }

    if adaptive:
        # Add adaptive-specific parameters
        learning = cfg.get('learning', {})
        bounds = cfg.get('bounds', {})

        adaptive_params = {
            'lr_input': learning.get('lr_input', 0.001),
            'lr_generative': learning.get('lr_generative', 0.01),
            'lr_trn': learning.get('lr_trn', 0.0005),
            'lr_prior': learning.get('lr_prior', 0.0001),
            'lr_tau': learning.get('lr_tau', 0.0001),
            'lr_gate_temp': learning.get('lr_gate_temp', 0.0001),
            'target_activity': learning.get('target_activity', 0.5),
            'target_entropy': learning.get('target_entropy', 1.5),
            'tau_min': bounds.get('tau_min', 10.0),
            'tau_max': bounds.get('tau_max', 200.0),
            'prior_min': bounds.get('prior_min', 0.01),
            'prior_max': bounds.get('prior_max', 2.0),
            'gate_temp_min': bounds.get('gate_temp_min', 0.1),
            'gate_temp_max': bounds.get('gate_temp_max', 2.0),
            'trn_max': bounds.get('trn_max', 5.0),
            'hazard_scale': learning.get('hazard_scale', 0.1),
            'reward_scale': learning.get('reward_scale', 0.05)
        }

        return ThalamoPC6Adaptive(**base_params, **adaptive_params)
    else:
        return ThalamoPC6(**base_params)


def save_config(config: Dict, save_path: str):
    """
    Save configuration to YAML file.

    Args:
        config: Configuration dict
        save_path: Path to save YAML file
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Config saved to {save_path}")


# Example usage
if __name__ == "__main__":
    # Load default config
    config = load_config("configs/default.yaml")
    print("Loaded config:")
    print(f"  Modalities: {config['modalities']}")
    print(f"  Gate temp: {config['gating']['temperature']}")

    # Create models
    print("\nCreating ThalamoPC6...")
    model = create_model_from_config(config, adaptive=False)
    print(f"  Model created with {model.M} modalities")

    print("\nCreating ThalamoPC6Adaptive...")
    model_adaptive = create_model_from_config(config, adaptive=True)
    print(f"  Adaptive model created")
    print(f"  Learning rates: input={model_adaptive.lr_input}, gen={model_adaptive.lr_generative}")
