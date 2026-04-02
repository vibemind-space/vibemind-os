"""AccuracyGate — controls cursor activation based on measured prediction accuracy.

Three phases:
- learning  : startup phase, collecting click data, cursor OFF
- ready     : accuracy >= threshold_on, cursor ON
- degraded  : accuracy dropped below threshold_off (drift detected), cursor OFF

Resolution-independent: thresholds are expressed as fractions of the screen diagonal,
so the same accuracy_radius_frac works correctly on 1080p, 1440p, and 4K displays.
"""

import math
import logging
from typing import List

logger = logging.getLogger("eyeterm.accuracy_gate")

# Phase constants
PHASE_LEARNING = "learning"
PHASE_READY = "ready"
PHASE_DEGRADED = "degraded"

_DRIFT_WINDOW = 10  # number of recent clicks used for drift detection


class AccuracyGate:
    """Controls cursor activation based on measured click-prediction accuracy.

    Args:
        screen_w: Screen width in pixels.
        screen_h: Screen height in pixels.
        threshold_on: Accuracy fraction required to enter 'ready' phase (default 0.75).
        threshold_off: Accuracy fraction below which the gate enters 'degraded' (default 0.50).
        accuracy_radius_frac: Hit-radius as fraction of screen diagonal (default 0.05 → ~110px
            at 1080p, ~220px at 4K).
        drift_threshold_frac: Drift detection threshold as fraction of diagonal (default 0.07).
        min_clicks: Minimum number of clicks required before phase can advance (default 20).
    """

    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        threshold_on: float = 0.75,
        threshold_off: float = 0.50,
        accuracy_radius_frac: float = 0.05,
        drift_threshold_frac: float = 0.07,
        min_clicks: int = 20,
    ) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._threshold_on = threshold_on
        self._threshold_off = threshold_off
        self._min_clicks = min_clicks

        # Compute resolution-dependent pixel thresholds from diagonal fractions
        diagonal = math.hypot(screen_w, screen_h)
        self._accuracy_radius_px = accuracy_radius_frac * diagonal
        self._drift_threshold_px = drift_threshold_frac * diagonal

        self._phase = PHASE_LEARNING
        logger.info(
            "AccuracyGate init: %dx%d, diagonal=%.0fpx, "
            "accuracy_radius=%.1fpx, drift_threshold=%.1fpx",
            screen_w,
            screen_h,
            diagonal,
            self._accuracy_radius_px,
            self._drift_threshold_px,
        )

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def phase(self) -> str:
        """Current phase string: 'learning', 'ready', or 'degraded'."""
        return self._phase

    @property
    def cursor_enabled(self) -> bool:
        """True only when phase is 'ready'."""
        return self._phase == PHASE_READY

    @property
    def accuracy_radius_px(self) -> float:
        """Hit-radius in pixels for the current resolution."""
        return self._accuracy_radius_px

    @property
    def drift_threshold_px(self) -> float:
        """Drift detection threshold in pixels for the current resolution."""
        return self._drift_threshold_px

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def update(self, recent_clicks: List) -> str:
        """Evaluate accuracy over recent_clicks and transition phase if needed.

        Each click object must expose a ``residual_px`` attribute (float) — the
        Euclidean distance between the predicted gaze point and the actual click.

        Args:
            recent_clicks: Sequence of click samples with ``.residual_px``.

        Returns:
            Current phase string after evaluation.
        """
        n = len(recent_clicks)

        if n < self._min_clicks:
            # Not enough data to advance from learning
            if self._phase == PHASE_LEARNING:
                logger.debug("AccuracyGate: only %d/%d clicks, staying learning", n, self._min_clicks)
            # If already ready/degraded, still re-evaluate with what we have
            # but we cannot promote from learning without min_clicks
            if self._phase == PHASE_LEARNING:
                return self._phase

        # Compute fraction of clicks within accuracy radius
        hits = sum(1 for c in recent_clicks if c.residual_px <= self._accuracy_radius_px)
        accuracy = hits / n if n > 0 else 0.0

        logger.debug(
            "AccuracyGate.update: n=%d, hits=%d, accuracy=%.2f, phase=%s",
            n,
            hits,
            accuracy,
            self._phase,
        )

        if self._phase == PHASE_LEARNING:
            if accuracy >= self._threshold_on:
                self._phase = PHASE_READY
                logger.info("AccuracyGate: learning → ready (accuracy=%.2f)", accuracy)

        elif self._phase == PHASE_READY:
            if accuracy < self._threshold_off:
                self._phase = PHASE_DEGRADED
                logger.warning("AccuracyGate: ready → degraded (accuracy=%.2f)", accuracy)
            # Drift check only with enough data (prevents false positives)
            elif n >= _DRIFT_WINDOW and self.check_drift(recent_clicks):
                self._phase = PHASE_DEGRADED
                logger.warning("AccuracyGate: ready → degraded (drift detected)")

        elif self._phase == PHASE_DEGRADED:
            if accuracy >= self._threshold_on:
                self._phase = PHASE_READY
                logger.info("AccuracyGate: degraded → ready (accuracy=%.2f)", accuracy)

        return self._phase

    def check_drift(self, recent_clicks: List) -> bool:
        """Return True if the last ``_DRIFT_WINDOW`` clicks show mean residual above drift threshold.

        This detects gradual accuracy degradation (e.g., user moved laptop) even
        when the overall accuracy fraction is still above ``threshold_off``.

        Args:
            recent_clicks: All available recent click samples.

        Returns:
            True if drift is detected, False otherwise.
        """
        window = recent_clicks[-_DRIFT_WINDOW:]
        if not window:
            return False
        mean_residual = sum(c.residual_px for c in window) / len(window)
        drifting = mean_residual > self._drift_threshold_px
        if drifting:
            logger.debug(
                "AccuracyGate.check_drift: mean_residual=%.1fpx > threshold=%.1fpx",
                mean_residual,
                self._drift_threshold_px,
            )
        return drifting
