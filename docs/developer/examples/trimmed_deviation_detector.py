"""A monitor detector, ``trimmed_deviation``.

The worked example of docs/developer/monitors-and-notifiers.md.

Distance from a trimmed mean, in units of the trimmed standard deviation. The
trim discards the most extreme tenth at each end of the history before either
statistic is computed, so a handful of bad days in the window do not widen the
band the next bad day is measured against.

A detector produces a **nonconformity score**, never a verdict: how unusual the
score is, and whether that is unusual enough to alert, is the conformal
calibrator's question. So the only contract is that a stranger point scores
higher, computed the same way for the calibration points and the observation.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar

from prama.monitor.detect import MINIMUM_HISTORY, Detector, Score

#: The share of the history dropped at each end before the statistics.
TRIM = 0.10


class TrimmedDeviation(Detector):
    """|observation - trimmed mean| / trimmed standard deviation."""

    name: ClassVar[str] = "trimmed_deviation"
    good_at: ClassVar[str] = (
        "a level that has shifted, on a roughly symmetric series with occasional outliers"
    )
    blind_to: ClassVar[str] = (
        "a trend, and a bounded or skewed quantity such as a null rate, where a "
        "symmetric band spends half its width on the impossible side"
    )

    def compute(self, observation: float, history: Sequence[float]) -> Score | None:
        if len(history) < MINIMUM_HISTORY:
            return None
        ordered = sorted(history)
        cut = int(len(ordered) * TRIM)
        kept = ordered[cut : len(ordered) - cut] or ordered
        centre = sum(kept) / len(kept)
        spread = math.sqrt(sum((v - centre) ** 2 for v in kept) / len(kept))
        if spread <= 0:
            # A constant history: the raw distance, and the calibrator's floor
            # handles the rest, as the shipped detectors do.
            spread = 1.0
        deviation = abs(observation - centre) / spread
        return Score(
            value=deviation,
            detector=self.name,
            expected=centre,
            observed=observation,
            explanation=(
                f"{observation:,.0f} against a trimmed mean of {centre:,.0f}, "
                f"{deviation:.1f} trimmed deviations away"
            ),
        )
