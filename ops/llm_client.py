"""Compatibility shim — actual implementation lives in vibemind_shared.

Historically each subsystem (business/, devops/, ops/, security/, system/)
had its own byte-identical copy of llm_client.py (~204 LOC x 5 = 1020 LOC).
The shared/ package now hosts the canonical, more-feature-rich version
(~283 LOC) — this shim keeps `from .llm_client import X` working in this
subsystem while removing the dead duplicate.

To migrate a caller off this shim:
    from vibemind_shared import llm_client    # preferred
    # instead of
    from .llm_client import get_client        # via this shim
"""
from vibemind_shared.llm_client import *  # noqa: F401,F403
from vibemind_shared.llm_client import (  # noqa: F401
    get_client,
    get_config,
    get_model,
    get_temperature,
)
