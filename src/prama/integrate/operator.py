"""Reconciling a ``PramaEstate`` — the decision, without the cluster.

An operator is two things wearing one name: a control loop that talks to
Kubernetes, and a function that decides what to do. The loop needs a cluster to
develop against; the decision does not, and the decision is where an operator is
dangerous.

**This is the decision.** Given what a manifest declares and what the store
holds, it says what should happen — and every rule in it exists because the
obvious reconciler does something a bank would not accept:

* **Drift is reported, never resolved.** The Kubernetes instinct is that desired
  state wins, and applied here it would silently overwrite a declaration a
  business owner made in the console — the one place the product insists a human
  states meaning. A dataset that differs is a ``CONFLICT``, surfaced on the
  resource's status for somebody to settle.
* **Nothing is ever deleted.** Removing a dataset from a manifest means the
  manifest stopped mentioning it, which is not the same as the business retiring
  it. Deletion would take its controls and its evidence with it, and evidence is
  the thing this product exists to keep.
* **A declaration is not an approval.** Reconciling can create and amend
  declarations; it cannot activate a control, suppress one, or sign anything. A
  cluster admin with ``kubectl`` must not be able to make a control pass.
* **A partial reconcile is reported as partial.** Twelve of forty datasets
  applied leaves twenty-eight in a state nobody knows, and a status condition
  saying ``Ready`` over that is worse than one saying nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from typing import Any


class Verb(enum.Enum):
    """What reconciling one dataset should do."""

    CREATE = "create"
    AMEND = "amend"
    #: Declared identically in both places. Nothing to do, and worth counting.
    UNCHANGED = "unchanged"
    #: Declared in both and differently, where the store's version was not
    #: derived from this manifest. Surfaced, never overwritten.
    CONFLICT = "conflict"
    #: In the store and no longer in the manifest. Never deleted.
    ORPHANED = "orphaned"

    @property
    def writes(self) -> bool:
        return self in (Verb.CREATE, Verb.AMEND)

    @property
    def needs_a_human(self) -> bool:
        return self in (Verb.CONFLICT, Verb.ORPHANED)


@dataclasses.dataclass(frozen=True, slots=True)
class Step:
    """One dataset's decision, and why."""

    dataset: str
    verb: Verb
    why: str = ""
    #: Fields that differ, for a conflict. Named rather than counted: "this
    #: dataset conflicts" is not something anybody can settle.
    differing: tuple[str, ...] = ()

    def describe(self) -> str:
        head = f"{self.dataset}: {self.verb.value}"
        if self.differing:
            head += f" on {', '.join(self.differing)}"
        return f"{head} — {self.why}" if self.why else head

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "verb": self.verb.value,
            "why": self.why,
            "differing": list(self.differing),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Plan:
    """What a reconcile would do, before it does any of it."""

    tenant: str
    steps: tuple[Step, ...] = ()

    def of(self, verb: Verb) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if step.verb is verb)

    @property
    def writes(self) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if step.verb.writes)

    @property
    def needs_a_human(self) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if step.verb.needs_a_human)

    @property
    def is_settled(self) -> bool:
        """Whether this resource can be called Ready.

        A conflict or an orphan means somebody has to decide something, and a
        status of Ready over that is a lie the cluster will repeat every thirty
        seconds.
        """
        return not self.needs_a_human

    def describe(self) -> str:
        if not self.steps:
            return f"{self.tenant}: the manifest declares nothing, so there is nothing to do"
        parts = []
        # Conflicts first. They are the only part a human has to act on, and a
        # summary leading with "18 unchanged" buries them.
        conflicts = self.of(Verb.CONFLICT)
        orphans = self.of(Verb.ORPHANED)
        if conflicts:
            parts.append(
                f"{len(conflicts)} conflict(s) needing a decision: "
                + ", ".join(step.dataset for step in conflicts[:5])
            )
        if orphans:
            parts.append(
                f"{len(orphans)} dataset(s) are in the store and no longer in the "
                "manifest — left alone, because a manifest that stopped mentioning "
                "something is not the business retiring it"
            )
        for verb in (Verb.CREATE, Verb.AMEND, Verb.UNCHANGED):
            found = self.of(verb)
            if found:
                parts.append(
                    f"{len(found)} to {verb.value}" if verb.writes else f"{len(found)} unchanged"
                )
        return f"{self.tenant}: " + "; ".join(parts) + "."

    def conditions(self, *, generation: int, applied: int | None = None) -> list[dict[str, Any]]:
        """Status conditions for the resource.

        ``applied`` is how many writes actually landed. Passing ``None`` means
        the plan has not been applied, which is a different state from applying
        it and having everything succeed — and a condition that conflated them
        would report Ready on a reconcile that never ran.
        """
        ready = self.is_settled and applied is not None and applied == len(self.writes)
        reason = "Reconciled"
        message = self.describe()
        if applied is None:
            reason, message = "NotApplied", "planned but not applied"
        elif not self.is_settled:
            reason = "NeedsDecision"
        elif applied != len(self.writes):
            reason = "PartiallyApplied"
            message = (
                f"{applied} of {len(self.writes)} write(s) landed; the rest are in a "
                "state nobody knows, which is why this is not Ready"
            )
        return [
            {
                "type": "Ready",
                "status": "True" if ready else "False",
                "reason": reason,
                "message": message,
                "observedGeneration": generation,
            }
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant": self.tenant,
            "settled": self.is_settled,
            "steps": [step.to_dict() for step in self.steps],
            "creates": len(self.of(Verb.CREATE)),
            "amends": len(self.of(Verb.AMEND)),
            "unchanged": len(self.of(Verb.UNCHANGED)),
            "conflicts": len(self.of(Verb.CONFLICT)),
            "orphaned": len(self.of(Verb.ORPHANED)),
            "message": self.describe(),
        }


#: Fields a manifest may state about a dataset. Anything else in the store is
#: not compared: the console holds facts a manifest never carries — an owner, a
#: rhythm — and treating their absence as a difference would make every dataset
#: conflict forever.
COMPARED = ("description", "criticality", "grain", "grainStatement")

#: Marks a stored declaration as having come from this operator. A stored
#: dataset without it was declared by a person, and overwriting a person's
#: declaration from a manifest is the thing this module most exists to refuse.
MANAGED_BY = "prama-operator"


def _normalise(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value


def plan(
    spec: Mapping[str, Any],
    stored: Sequence[Mapping[str, Any]],
) -> Plan:
    """What reconciling this manifest against the store should do.

    ``stored`` is what the estate already holds, each entry carrying at least a
    ``name`` and optionally ``managedBy``. Nothing here writes: the caller
    applies the plan, and separating the two is what lets a `--dry-run` be
    exactly the same decision as a real reconcile.
    """
    tenant = str(spec.get("tenant", ""))
    declared = {str(item.get("name", "")): item for item in spec.get("datasets", [])}
    held = {str(item.get("name", "")): item for item in stored}

    steps: list[Step] = []
    for name, wanted in sorted(declared.items()):
        current = held.get(name)
        if current is None:
            steps.append(Step(dataset=name, verb=Verb.CREATE, why="not in the store"))
            continue

        differing = tuple(
            field
            for field in COMPARED
            if field in wanted and _normalise(wanted.get(field)) != _normalise(current.get(field))
        )
        if not differing:
            steps.append(Step(dataset=name, verb=Verb.UNCHANGED))
        elif current.get("managedBy") == MANAGED_BY:
            steps.append(
                Step(
                    dataset=name,
                    verb=Verb.AMEND,
                    why="this operator declared it, so the manifest is its source",
                    differing=differing,
                )
            )
        else:
            steps.append(
                Step(
                    dataset=name,
                    verb=Verb.CONFLICT,
                    why=(
                        "a person declared this in the console and the manifest "
                        "disagrees; overwriting would erase a statement somebody made"
                    ),
                    differing=differing,
                )
            )

    for name in sorted(set(held) - set(declared)):
        steps.append(
            Step(
                dataset=name,
                verb=Verb.ORPHANED,
                why=(
                    "no longer in the manifest, and left alone — deleting would take "
                    "its controls and its evidence with it"
                ),
            )
        )

    return Plan(tenant=tenant, steps=tuple(steps))


__all__ = ["COMPARED", "MANAGED_BY", "Plan", "Step", "Verb", "plan"]
