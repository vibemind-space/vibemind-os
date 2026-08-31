"""Marketing-side Mirofish wrapper.

Separate from spaces/mirofish/ (which is a submodule). Purpose: provide
a thin Marketing-specific API (predict_post_reception, drilldown_persona)
that wraps Mirofish's multi-step HTTP pipeline.

Why a separate wrapper:
- Mirofish-submodule has no `predict_post_reception()` function — its
  yml registry lists tools that don't exist on disk (refactoring drift).
- A separate wrapper lets us iterate without committing into the submodule.
- Keeps marketing domain language (post / channel / reception / persona)
  out of mirofish's code (which is platform-agnostic by design).
"""
