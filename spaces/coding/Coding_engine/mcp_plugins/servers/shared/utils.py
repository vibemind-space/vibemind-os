# -*- coding: utf-8 -*-
"""
Shared utility functions for MCP server plugins.
"""
import os
from typing import Optional


def load_prompt_from_module(module_name: str, base_dir: str, default: str) -> str:
    """Load prompt from a Python module's PROMPT variable.
    
    Args:
        module_name: Name of the module to load (e.g., "github_operator_prompt")
        base_dir: Base directory where the module is located
        default: Default prompt to return if module not found or fails to load
        
    Returns:
        Prompt string from module.PROMPT or default
        
    Example:
        >>> prompt = load_prompt_from_module(
        ...     "github_operator_prompt",
        ...     "/path/to/github",
        ...     "Default prompt"
        ... )
    """
    try:
        import importlib.util
        module_path = os.path.join(base_dir, f"{module_name}.py")
        
        if os.path.exists(module_path):
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'PROMPT'):
                    return module.PROMPT
        return default
    except Exception as e:
        # Log warning but don't fail - return default
        print(f"Warning: Failed to load prompt from {module_name}: {e}")
        return default