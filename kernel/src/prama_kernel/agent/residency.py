"""What may leave the machine the data is on.

This is the decision that makes distributed execution possible in a bank, and
getting it wrong is not a bug — it is a regulatory incident. An agent runs
beside the data precisely so the data does not travel; a design in which
"findings" quietly include a hundred failing rows has moved the data and called
it something else.

So what crosses the boundary is declared, enforced at the agent, and recorded.
Three tiers, and the boundaries between them are not configurable:

* **Always crosses.** Counts, verdicts, plan identities, hashes, timings. These
  are facts *about* the data and contain none of it. Without them there is no
  central view at all, which is the point of the exercise.
* **Crosses by declaration.** Samples of failing rows, and only under a policy
  that says which columns may travel and how. This is the useful-but-dangerous
  tier and the one a data protection officer actually asks about.
* **Never crosses.** Credentials, connection strings, raw scans, anything not
  explicitly permitted. The agent holds the credential; the control plane holds
  a reference to it and nothing more.

**A withheld sample is not an absent sample.** If residency forbids samples, the
record says so, distinctly from a control that passed and had none to send.
Conflating them sends an investigator looking for rows that were never
collected, and — worse — lets a zone that is silently dropping everything look
identical to a zone that is clean.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from typing import Any

from prama_kernel.errors import ValidationError


class SampleDisposition(enum.Enum):
    """What happens to failing rows at the boundary."""

    #: Rows travel as they are. Only for a zone where the control plane is
    #: inside the same trust and residency boundary as the data.
    SEND = "send"
    #: Rows travel with the declared columns replaced. What most estates want:
    #: enough to investigate, nothing that identifies a person or an account.
    MASK = "mask"
    #: Only a hash of each row travels, so two occurrences of the same bad row
    #: can be recognised as the same without the row being known.
    FINGERPRINT = "fingerprint"
    #: Nothing travels. The record says samples were withheld and why, and an
    #: investigator is told where to look instead.
    WITHHOLD = "withhold"

    @property
    def carries_data(self) -> bool:
        return self in (SampleDisposition.SEND, SampleDisposition.MASK)


@dataclasses.dataclass(frozen=True, slots=True)
class ResidencyPolicy:
    """What this agent's zone permits to leave it."""

    #: A name a person recognises: 'eu-west', 'on-prem-frankfurt', 'pci-zone'.
    zone: str = "default"
    samples: SampleDisposition = SampleDisposition.MASK
    #: Columns that must never travel in clear, whatever the disposition.
    #: Applied on top of MASK; under SEND, naming any column here is refused
    #: at declaration rather than silently ignored.
    never_send: tuple[str, ...] = ()
    #: Columns permitted to travel in clear under MASK. Everything else is
    #: masked — an allow-list, because a deny-list is one new column away from
    #: leaking, and new columns appear without anybody telling the policy.
    may_send: tuple[str, ...] = ()
    max_sample_rows: int = 50
    #: Where an investigator should look when samples were withheld. Without
    #: it, "withheld" is a dead end rather than a redirection.
    investigate_at: str = ""

    def __post_init__(self) -> None:
        if self.samples is SampleDisposition.SEND and self.never_send:
            raise ValidationError(
                f"the {self.zone} policy sends samples in clear but also names columns "
                f"that must never be sent",
                remedy=(
                    "Use MASK, which sends what you permit and masks the rest. A policy "
                    "that says both would have to choose one silently, and the safe "
                    "choice is not the one anybody would notice being wrong."
                ),
                context={"zone": self.zone, "never_send": list(self.never_send)},
            )
        if self.samples is SampleDisposition.MASK and not self.may_send:
            raise ValidationError(
                f"the {self.zone} policy masks samples but permits no column to travel",
                remedy=(
                    "Name the columns an investigator needs — usually the key and the "
                    "offending value. A mask policy with an empty allow-list sends rows "
                    "of asterisks, which costs the same and helps nobody: use WITHHOLD "
                    "and say where to look instead."
                ),
                context={"zone": self.zone},
            )

    def describe(self) -> str:
        """The policy in the words a data protection officer would use."""
        if self.samples is SampleDisposition.WITHHOLD:
            where = f" Investigate at {self.investigate_at}." if self.investigate_at else ""
            return f"No row-level data leaves {self.zone}.{where}"
        if self.samples is SampleDisposition.FINGERPRINT:
            return (
                f"Only row fingerprints leave {self.zone}, so a repeated failure can be "
                f"recognised without the row being known."
            )
        if self.samples is SampleDisposition.SEND:
            return f"Failing rows leave {self.zone} in full, up to {self.max_sample_rows}."
        return (
            f"Failing rows leave {self.zone} with only {', '.join(self.may_send)} in "
            f"clear; everything else is masked."
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Redaction:
    """What a policy did to a batch of rows, said plainly."""

    disposition: SampleDisposition
    zone: str
    rows: tuple[dict[str, Any], ...] = ()
    #: Columns that were masked, so a reader knows what they are not seeing
    #: rather than assuming the row is complete.
    masked: tuple[str, ...] = ()
    #: Rows the policy dropped entirely, counted. A count of what is missing is
    #: not the same as no mention of it.
    withheld: int = 0
    reason: str = ""

    @property
    def carried_anything(self) -> bool:
        return bool(self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "zone": self.zone,
            "rows": [dict(r) for r in self.rows],
            "masked": list(self.masked),
            "withheld": self.withheld,
            "reason": self.reason,
        }


class Boundary:
    """Applies a residency policy to what an agent is about to send."""

    #: What a masked value becomes. Fixed rather than configurable: a mask
    #: that varied by deployment would make a redacted row from one zone
    #: indistinguishable from a real value in another.
    MASK = "***"

    def __init__(self, policy: ResidencyPolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> ResidencyPolicy:
        return self._policy

    def apply(self, rows: list[dict[str, Any]]) -> Redaction:
        """Turn failing rows into whatever this zone permits to travel."""
        policy = self._policy
        if not rows:
            return Redaction(
                disposition=policy.samples,
                zone=policy.zone,
                reason="the control had no failing rows to sample",
            )
        capped = rows[: policy.max_sample_rows]
        dropped = len(rows) - len(capped)

        if policy.samples is SampleDisposition.WITHHOLD:
            return Redaction(
                disposition=policy.samples,
                zone=policy.zone,
                withheld=len(rows),
                reason=(
                    f"{policy.zone} does not permit row-level data to leave"
                    + (f"; investigate at {policy.investigate_at}" if policy.investigate_at else "")
                ),
            )
        if policy.samples is SampleDisposition.FINGERPRINT:
            return Redaction(
                disposition=policy.samples,
                zone=policy.zone,
                rows=tuple({"fingerprint": _fingerprint(row)} for row in capped),
                withheld=dropped,
                reason=(
                    f"{policy.zone} permits only fingerprints, so a repeated failure is "
                    f"recognisable without the row being known"
                ),
            )
        if policy.samples is SampleDisposition.SEND:
            return Redaction(
                disposition=policy.samples,
                zone=policy.zone,
                rows=tuple(dict(row) for row in capped),
                withheld=dropped,
                reason=f"{policy.zone} permits failing rows to leave in full",
            )

        permitted = {c.lower() for c in policy.may_send}
        forbidden = {c.lower() for c in policy.never_send}
        masked: set[str] = set()
        out: list[dict[str, Any]] = []
        for row in capped:
            kept: dict[str, Any] = {}
            for column, value in row.items():
                lowered = column.lower()
                # An allow-list, checked first: a column nobody has classified
                # is masked rather than sent, because new columns appear and
                # policies do not update themselves.
                if lowered in permitted and lowered not in forbidden:
                    kept[column] = value
                else:
                    kept[column] = self.MASK
                    masked.add(column)
            out.append(kept)
        return Redaction(
            disposition=policy.samples,
            zone=policy.zone,
            rows=tuple(out),
            masked=tuple(sorted(masked)),
            withheld=dropped,
            reason=(
                f"{policy.zone} permits {', '.join(sorted(permitted)) or 'no column'} in "
                f"clear; {len(masked)} other column(s) were masked"
            ),
        )

    def permits(self, column: str) -> bool:
        """Whether one column's values may leave this zone in clear."""
        policy = self._policy
        if policy.samples is SampleDisposition.SEND:
            return True
        if policy.samples is not SampleDisposition.MASK:
            return False
        lowered = column.lower()
        return lowered in {c.lower() for c in policy.may_send} and lowered not in {
            c.lower() for c in policy.never_send
        }


def _fingerprint(row: dict[str, Any]) -> str:
    """A stable identity for a row, revealing nothing about it."""
    from prama_kernel.pjson import canonical

    return hashlib.blake2b(canonical(dict(sorted(row.items()))), digest_size=12).hexdigest()
