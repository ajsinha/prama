"""Replacing a monitor without finding out the hard way.

`FR-MON-016` and `FR-LRN-006`. A better detector is worth having and swapping
one in is how a monitoring system loses its reputation: the new one is better
on average and worse on the case somebody depended on, and nobody discovers
that until the case arrives.

So a challenger runs in shadow — scored on every observation, alerting on
none — until it has earned promotion on evidence. The gates are deliberately
asymmetric, and the asymmetry is the design:

**A challenger must be better, not merely different.** Beating the champion on
one metric while losing on another is not an improvement, it is a trade, and a
trade needs a person rather than a threshold.

**Regression is disqualifying even when the average improves.** A challenger
that catches five new incidents and misses one the champion caught has, from
the desk that depended on that one, made things worse. It can still be promoted
— by somebody who reads what it would have missed and decides — but not
automatically.

**Promotion is reversible and rollback is automatic.** The shadow period ends
at promotion and the measurement does not: a promoted monitor whose precision
falls below what the champion was achieving is rolled back without waiting for
anybody to notice.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from typing import Any

#: Observations a challenger must be scored on before any promotion decision.
#: Fewer than this and the comparison is between two samples of noise.
MINIMUM_SHADOW = 200

#: A challenger must beat the champion by at least this much to be promoted.
#: Not zero: a coin-flip's worth of improvement is not an improvement, and
#: promoting on one would mean promoting whichever challenger was luckiest.
MATERIAL_MARGIN = 0.05


class Decision(enum.Enum):
    PROMOTE = "promote"
    HOLD = "hold"
    RETIRE = "retire"
    #: Better on balance and worse somewhere specific. Needs a person, and
    #: naming it is the point — the alternative is a threshold quietly making a
    #: trade nobody agreed to.
    REFER = "refer"


@dataclasses.dataclass(frozen=True, slots=True)
class Record:
    """What one candidate did over the shadow period."""

    name: str
    #: Observations it was scored on.
    observations: int = 0
    #: Alerts it would have raised.
    alerts: int = 0
    #: Alerts a steward confirmed, among those reviewed.
    confirmed: int = 0
    reviewed: int = 0
    #: Incidents the *other* candidate caught and this one did not. The number
    #: that disqualifies rather than the one that promotes.
    missed_that_other_caught: int = 0

    @property
    def precision(self) -> float | None:
        return self.confirmed / self.reviewed if self.reviewed else None

    @property
    def alert_rate(self) -> float:
        return self.alerts / self.observations if self.observations else 0.0

    def describe(self) -> str:
        precision = (
            f"{self.precision:.0%} precision on {self.reviewed} reviewed"
            if self.precision is not None
            else "no reviewed alerts"
        )
        return (
            f"{self.name}: {self.alerts} alerts over {self.observations} observations "
            f"({self.alert_rate:.1%}), {precision}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "observations": self.observations,
            "alerts": self.alerts,
            "confirmed": self.confirmed,
            "reviewed": self.reviewed,
            "missed_that_other_caught": self.missed_that_other_caught,
            "precision": round(self.precision, 4) if self.precision is not None else None,
            "alert_rate": round(self.alert_rate, 4),
            "summary": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Judgement:
    """Whether to promote, and why — in a sentence somebody can disagree with."""

    decision: Decision
    champion: Record
    challenger: Record
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "champion": self.champion.to_dict(),
            "challenger": self.challenger.to_dict(),
        }


class Tournament:
    """Runs a challenger in shadow and decides on evidence."""

    def __init__(
        self,
        *,
        minimum_shadow: int = MINIMUM_SHADOW,
        margin: float = MATERIAL_MARGIN,
    ) -> None:
        self._minimum = minimum_shadow
        self._margin = margin

    def judge(self, champion: Record, challenger: Record) -> Judgement:
        if challenger.observations < self._minimum:
            return Judgement(
                decision=Decision.HOLD,
                champion=champion,
                challenger=challenger,
                reason=(
                    f"{challenger.observations} shadow observations of "
                    f"{self._minimum}; below that the comparison is between two "
                    f"samples of noise"
                ),
            )
        if challenger.reviewed == 0:
            return Judgement(
                decision=Decision.HOLD,
                champion=champion,
                challenger=challenger,
                reason=(
                    "no alert from the challenger has been reviewed, so there is "
                    "nothing to compare its precision against"
                ),
            )

        if challenger.missed_that_other_caught > 0:
            # Disqualifying for an *automatic* promotion, not for promotion.
            # From the desk that depended on the missed incident, the challenger
            # has made things worse, and a person should read what it would have
            # missed before deciding that the average is what matters.
            return Judgement(
                decision=Decision.REFER,
                champion=champion,
                challenger=challenger,
                reason=(
                    f"the challenger missed {challenger.missed_that_other_caught} "
                    f"incident(s) the champion caught. It may still be the better "
                    f"monitor, and that is a judgement about which failures matter "
                    f"rather than an average somebody can compute"
                ),
            )

        champion_precision = champion.precision
        challenger_precision = challenger.precision
        if champion_precision is None:
            return Judgement(
                decision=Decision.PROMOTE,
                champion=champion,
                challenger=challenger,
                reason=(
                    f"the champion has no reviewed alerts to defend and the challenger "
                    f"is running at {challenger_precision:.0%} precision"
                ),
            )
        assert challenger_precision is not None
        improvement = challenger_precision - champion_precision
        if improvement >= self._margin:
            return Judgement(
                decision=Decision.PROMOTE,
                champion=champion,
                challenger=challenger,
                reason=(
                    f"precision {champion_precision:.0%} to {challenger_precision:.0%} "
                    f"with nothing lost that the champion caught"
                ),
            )
        if improvement <= -self._margin:
            return Judgement(
                decision=Decision.RETIRE,
                champion=champion,
                challenger=challenger,
                reason=(
                    f"the challenger is materially worse "
                    f"({challenger_precision:.0%} against {champion_precision:.0%})"
                ),
            )
        return Judgement(
            decision=Decision.HOLD,
            champion=champion,
            challenger=challenger,
            reason=(
                f"the difference ({improvement:+.0%}) is inside the margin that would "
                f"make it an improvement rather than luck; promoting on this would "
                f"mean promoting whichever challenger was luckiest"
            ),
        )

    def should_roll_back(
        self, promoted: Record, previous: Record, *, tolerance: float = 0.1
    ) -> str:
        """Whether a promoted monitor has fallen behind what it replaced.

        The shadow period ends at promotion and the measurement does not. A
        monitor that was better in shadow and is worse in production is the
        ordinary outcome of a small sample, and waiting for somebody to notice
        is how it stays that way for a quarter.
        """
        if promoted.reviewed < 20 or previous.precision is None:
            return ""
        current = promoted.precision
        if current is None:
            return ""
        if current < previous.precision - tolerance:
            return (
                f"{promoted.name} is running at {current:.0%} precision against the "
                f"{previous.precision:.0%} the monitor it replaced was achieving. "
                f"Rolling back; the promotion was decided on {promoted.reviewed} "
                f"reviewed alerts and production disagrees"
            )
        return ""


def shadow_record(
    name: str, alerts: Sequence[bool], confirmations: Sequence[bool | None]
) -> Record:
    """Build a record from a shadow run.

    ``confirmations`` carries None for an alert nobody has judged, which is
    counted as neither right nor wrong — treating unreviewed alerts as correct
    is how a challenger gets promoted on the strength of alerts nobody read.
    """
    reviewed = [c for c in confirmations if c is not None]
    return Record(
        name=name,
        observations=len(alerts),
        alerts=sum(alerts),
        confirmed=sum(1 for c in reviewed if c),
        reviewed=len(reviewed),
    )
