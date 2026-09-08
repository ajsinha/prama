"""Asking a model for a control, and not believing the answer.

`FR-IND-003`…`006`: retrieval from the semantic layer, grammar-constrained
decoding, parse/type-check/sandbox-execute, empirical validation. The pipeline
is short and the shape of it is the point — **nothing reaches a person except
through** :class:`~prama.induce.validate.Validated`, which cannot be built
without passing every gate.

**Retrieval is what makes the output specific.** A model asked "write a data
quality control" produces a generic one. A model given the dataset's declared
grain, the attribute's definition and *interpretation*, the semantic types
already established by checksum, and three real values from the column produces
one about this business. The interpretation field earns its place here more
than anywhere: "positions are reported gross of collateral" is the sentence
that decides whether a sign control is right or backwards, and it exists in no
schema.

**Constrained where possible, validated always.** A provider that can enforce a
grammar during decoding gets one; one that cannot is retried against the same
validator. Both paths end at the same gate, and the response records which one
ran — because a grammar-constrained provider emitting unparseable PQL is a
provider bug worth reporting, and an unconstrained one doing so is Tuesday.

**The failure rate is measured and published.** The wave's acceptance criterion
asks for it, and the reason is practical: a prompt whose output fails the gate
half the time is a prompt somebody should fix, and without the number nobody
knows. It also makes a model regression visible — the same prompts, the same
schema, and a rate that moved.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any

from prama.core.provenance import Origin, Provenance, identity
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.induce.validate import Gate, Rejection, Validated, Validator
from prama.llm.providers import PQL_CONTROL_GRAMMAR
from prama.llm.spi import ModelProvider, Request
from prama.semantic.values import Sensitivity

#: How many times a candidate is regenerated after failing the gate. Two,
#: because a third attempt from the same prompt on the same schema has, in
#: practice, the same defect as the second — and each retry is a paid call.
DEFAULT_ATTEMPTS = 3

SYSTEM = """\
You write controls in PQL, a small language for data quality assertions.

Reply with the control and nothing else: no explanation, no markdown fence, no
apology. If the request cannot be expressed as a control over the columns you
have been given, reply with exactly NONE.

A control looks like:

  CHECK dataset.column IS NOT NULL
    SEVERITY major
    DIMENSION completeness
    BECAUSE 'the reason a person would give'

Available assertions: IS NOT NULL, IS NULL, IN (...), IN CODELIST '...',
BETWEEN a AND b, MATCHES /regex/, IS VALID 'semantic_type', comparisons
(=, <>, <, <=, >, >=), HAS UNIQUE KEY (...), HAS ROW COUNT BETWEEN a AND b,
REFERENCES other.column, SATISFIES <expression>.

Rules that matter:
- Only use columns you have been given. Inventing one makes the control fail
  on its first run.
- A control must be able to fail. A condition that every row satisfies is
  rejected before anybody sees it.
- BECAUSE is read at three in the morning by somebody deciding whether an
  alert matters. Write it for them, in the business's words, not the schema's.
"""


@dataclasses.dataclass(frozen=True, slots=True)
class Retrieved:
    """What the model is told about the thing it is writing a control for.

    Assembled from the semantic layer rather than from the schema, which is the
    difference between a control about this business and a control about a
    table that happens to have these column names.
    """

    dataset: str
    columns: tuple[tuple[str, str], ...]
    grain: str = ""
    purpose: str = ""
    #: (name, definition, interpretation) for the attribute in question.
    attribute: tuple[str, str, str] | None = None
    semantic_type: str = ""
    #: Values from the column, already cleared for the provider's residency
    #: class. Never assembled here — see :meth:`Inducer._sample_values`.
    examples: tuple[str, ...] = ()
    #: Rules already in force, so the model does not propose them again.
    existing: tuple[str, ...] = ()

    def render(self) -> str:
        parts = [f"Dataset: {self.dataset}"]
        if self.purpose:
            parts.append(f"Purpose: {self.purpose}")
        if self.grain:
            parts.append(f"One row is: {self.grain}")
        parts.append("Columns: " + ", ".join(f"{name} ({kind})" for name, kind in self.columns))
        if self.attribute is not None:
            name, definition, interpretation = self.attribute
            parts.append(f"The attribute in question is {name}.")
            if definition:
                parts.append(f"It means: {definition}")
            if interpretation:
                # The field that decides whether a sign control is right or
                # backwards, and which exists in no schema anywhere.
                parts.append(f"How to read it: {interpretation}")
        if self.semantic_type:
            parts.append(
                f"Its values have been established by checksum to be {self.semantic_type}."
            )
        if self.examples:
            parts.append("Example values: " + ", ".join(repr(v) for v in self.examples))
        if self.existing:
            parts.append(
                "Controls already in force (do not repeat these):\n"
                + "\n".join(f"  {rule}" for rule in self.existing)
            )
        return "\n".join(parts)


@dataclasses.dataclass(frozen=True, slots=True)
class Induced:
    """A control a model wrote, having survived every gate."""

    validated: Validated
    provenance: Provenance
    identity: str
    #: How many generations it took. Worth keeping per candidate: a rule that
    #: only ever appears on the third attempt is a rule the prompt is bad at.
    attempts: int = 1
    #: What the earlier attempts got wrong, for diagnosing the prompt.
    rejected: tuple[Rejection, ...] = ()

    @property
    def content(self) -> str:
        return self.validated.content

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "attempts": self.attempts,
            "validated": self.validated.to_dict(),
            "provenance": self.provenance.to_dict(),
            "rejected": [r.to_dict() for r in self.rejected],
        }


@dataclasses.dataclass(frozen=True, slots=True)
class InductionReport:
    """What a run of the inducer produced, and what it failed to.

    Published rather than logged. A prompt whose output fails the gate half the
    time is a prompt somebody should fix, and without the number nobody knows
    it is happening.
    """

    induced: tuple[Induced, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    #: Requests that produced nothing at all — the model declined, or was
    #: unreachable. Counted separately from a rejected candidate, because one
    #: is a model saying no and the other is a model being wrong.
    declined: int = 0
    requested: int = 0

    @property
    def generation_failure_rate(self) -> float:
        """Fraction of requests that yielded no usable control."""
        if not self.requested:
            return 0.0
        return 1.0 - len(self.induced) / self.requested

    def failures_by_gate(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rejection in self.rejections:
            counts[rejection.gate.value] = counts.get(rejection.gate.value, 0) + 1
        return counts

    def describe(self) -> str:
        gates = self.failures_by_gate()
        detail = ", ".join(f"{count} at {gate}" for gate, count in sorted(gates.items()))
        return (
            f"{len(self.induced)} of {self.requested} requests produced a control that "
            f"passed every gate ({self.generation_failure_rate:.0%} failure rate)"
            + (f"; rejections: {detail}" if detail else "")
            + (f"; {self.declined} declined or unreachable" if self.declined else "")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "induced": [i.to_dict() for i in self.induced],
            "rejections": [r.to_dict() for r in self.rejections],
            "declined": self.declined,
            "generation_failure_rate": round(self.generation_failure_rate, 4),
            "failures_by_gate": self.failures_by_gate(),
            "summary": self.describe(),
        }


class Inducer:
    """Asks a model for controls and lets almost none of them through."""

    def __init__(
        self,
        provider: ModelProvider,
        validator: Validator,
        *,
        attempts: int = DEFAULT_ATTEMPTS,
        system: str = SYSTEM,
    ) -> None:
        self._provider = provider
        self._validator = validator
        self._attempts = max(1, attempts)
        self._system = system

    def induce(
        self,
        retrieved: Retrieved,
        instruction: str,
        rows: Sequence[dict[str, Any]] = (),
        *,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> Induced | Rejection | None:
        """One control, or the reason there is not one.

        Returns ``None`` when the model declined or could not be reached, which
        is an ordinary outcome and not an error: every feature that uses this
        has a deterministic path that does not need it.
        """
        rejections: list[Rejection] = []
        prompt = f"{retrieved.render()}\n\nWrite a control that: {instruction}"

        for attempt in range(1, self._attempts + 1):
            request = Request(
                system=self._system,
                prompt=prompt if attempt == 1 else _with_feedback(prompt, rejections[-1]),
                sensitivity=sensitivity,
                # Supplied whether or not the provider can use it. One that can
                # constrains decoding; one that cannot ignores the field, and
                # the response says which happened.
                grammar=PQL_CONTROL_GRAMMAR,
                context={"dataset": retrieved.dataset, "attempt": str(attempt)},
            )
            response = self._provider.ask(request)
            if not response.ok or response.text.strip().upper() == "NONE":
                return None

            outcome = self._validator.validate(response.text, rows)
            if isinstance(outcome, Validated):
                return Induced(
                    validated=outcome,
                    identity=identity(
                        retrieved.dataset, "induce.llm", retrieved.dataset, outcome.content
                    ),
                    attempts=attempt,
                    rejected=tuple(rejections),
                    provenance=Provenance(
                        origin=Origin.INDUCTION,
                        rule="induce.llm",
                        source_ref=f"{retrieved.dataset}#{response.request_fingerprint}",
                        statement=outcome.control.describe(),
                        observations=(
                            f"generated by {response.provider}/{response.model}"
                            + (
                                " with the grammar enforced during decoding"
                                if response.grammar_enforced
                                else " and validated afterwards; the provider cannot "
                                "constrain decoding"
                            ),
                            f"passed {len(outcome.passed)} gates; "
                            f"{outcome.sandbox.value_probes_caught} of "
                            f"{outcome.sandbox.value_probes} rows built to break it were "
                            f"caught",
                            f"attempt {attempt} of {self._attempts}",
                        ),
                    ),
                )
            rejections.append(outcome)

        if not rejections:
            return None
        return dataclasses.replace(rejections[-1], earlier=tuple(rejections[:-1]))

    def induce_all(
        self,
        requests: Sequence[tuple[Retrieved, str]],
        rows: Sequence[dict[str, Any]] = (),
        *,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> InductionReport:
        induced: list[Induced] = []
        rejections: list[Rejection] = []
        declined = 0
        for retrieved, instruction in requests:
            outcome = self.induce(retrieved, instruction, rows, sensitivity=sensitivity)
            if outcome is None:
                declined += 1
            elif isinstance(outcome, Induced):
                induced.append(outcome)
                rejections.extend(outcome.rejected)
            else:
                # Every attempt, not just the last. Counting three parse errors
                # as one understates the failure rate in the flattering
                # direction, which is the direction it must never be wrong in.
                rejections.extend(outcome.attempts)
        return InductionReport(
            induced=tuple(induced),
            rejections=tuple(rejections),
            declined=declined,
            requested=len(requests),
        )


def retrieve(
    declaration: DatasetDeclaration,
    attribute: AttributeDeclaration | None = None,
    *,
    examples: Sequence[str] = (),
    existing: Sequence[str] = (),
    semantic_type: str = "",
) -> Retrieved:
    """Assemble what the model should be told, from the semantic layer.

    Values are passed in rather than read here, because whether a value may
    leave the building is a residency decision and this module is the wrong
    place to make it — see :meth:`prama.llm.spi.ModelProvider.permit`.
    """
    return Retrieved(
        dataset=declaration.name,
        columns=tuple(
            (a.name, a.semantic_type or a.unit or "value") for a in declaration.attributes
        ),
        grain=declaration.grain.render() if declaration.grain else "",
        purpose=declaration.purpose or declaration.description,
        attribute=(
            (attribute.name, attribute.definition, attribute.interpretation)
            if attribute is not None
            else None
        ),
        semantic_type=semantic_type or (attribute.semantic_type if attribute else ""),
        examples=tuple(examples),
        existing=tuple(existing),
    )


def _with_feedback(prompt: str, rejection: Rejection) -> str:
    """Tell the model what went wrong, precisely.

    A retry with the identical prompt is a retry with the identical answer, at
    the same price. The rejection is quoted rather than summarised — the
    parser's message names the position, and a model given the position
    generally fixes it, where a model told "that was invalid" generally does
    not.
    """
    return (
        f"{prompt}\n\n"
        f"Your previous answer was rejected at the {rejection.gate.value} stage: "
        f"{rejection.detail}\n"
        f"That means {rejection.gate.explains}. Correct it and reply with the control "
        f"alone."
    )


__all__ = [
    "DEFAULT_ATTEMPTS",
    "SYSTEM",
    "Gate",
    "Induced",
    "Inducer",
    "InductionReport",
    "Retrieved",
    "retrieve",
]
