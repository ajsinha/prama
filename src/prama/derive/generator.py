"""Γ — the mapping from a business declaration to running controls.

The claim that makes Prama a business tool rather than an engineer's tool: a
person answers "what does one row represent?" and eight controls appear, each
carrying the sentence that justifies it. No SQL is written by anyone.

The mapping is docs/03 §5, and it is deliberately *explicit*. A user can always
ask "why does this control exist?" and get "because you declared X on 4 March",
because the provenance is attached at generation and cannot be absent.

Three properties this generator is built around, each of which was easy to get
wrong:

**It refuses to invent.** If the grain names ``account_id`` and the dataset has
no such column, emitting the control anyway produces something that compiles,
deploys, and fails at three in the morning with a message about a missing
column. Silently skipping is no better: the user declared a grain and got
nothing, with no explanation. So the declaration is checked against the schema
and an unsatisfiable one is *reported back to the declarer* — see
:class:`Unsatisfiable`, which is as much a product of Γ as a control is.

**It is stable under regeneration.** Identity derives from what a control is
about — the declaration, the rule, the subject — never from its text. Editing a
threshold updates the existing control; deriving identity from the text would
orphan one and create another, so re-running Γ after any edit would produce an
estate of duplicates nobody recognises and a review queue full of controls that
already exist.

**Nothing it emits is active.** Every control here is a proposal, whatever its
origin. `docs/03 §5` says "proposed, never silently activated", and the reason
is not caution: an estate that appeared without anybody agreeing to it is an
estate nobody owns, and unowned alerts get muted rather than fixed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.classify.codelists import REGISTRY as CODELISTS
from prama.classify.codelists import CodeListRegistry
from prama.classify.validators import REGISTRY as VALIDATORS
from prama.classify.validators import ValidatorRegistry
from prama.core.provenance import Origin, Provenance, content_hash, identity
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.pql import ast
from prama.pql.types import Catalogue
from prama.semantic.values import (
    Criticality,
    Frequency,
    Optionality,
    Temporality,
    ValueDomainKind,
)

# ---------------------------------------------------------------------------
# What Γ produces
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class DerivedControl:
    """A control that a declaration produced, and the reason it did."""

    #: Stable across regeneration. See :func:`prama.core.provenance.identity`.
    identity: str
    control: ast.Control
    provenance: Provenance
    #: The Γ rule that produced it, so a systematically bad rule can be found
    #: and fixed once rather than control by control.
    rule: str

    @property
    def content(self) -> str:
        return self.control.render()

    @property
    def content_hash(self) -> str:
        """Changes when the control changes. What a review diff is computed on."""
        return content_hash(self.content)

    def describe(self) -> str:
        """The control and its justification, as two sentences."""
        return f"{self.control.describe()} {self.provenance.sentence()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "rule": self.rule,
            "pql": self.content,
            "content_hash": self.content_hash,
            "description": self.control.describe(),
            "provenance": self.provenance.to_dict(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Unsatisfiable:
    """A declaration that should have generated a control and could not.

    As much an output of Γ as a control is. The alternative to reporting these
    is a generator that either emits controls it knows will fail or drops them
    without saying so, and both leave the declarer believing something is being
    checked that is not.
    """

    rule: str
    #: What was declared, in the declarer's terms.
    declared: str
    reason: str
    remedy: str
    dataset: str = ""

    def render(self) -> str:
        return f"{self.dataset}: {self.reason}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "declared": self.declared,
            "reason": self.reason,
            "remedy": self.remedy,
            "dataset": self.dataset,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Deferred:
    """Something declared that Γ deliberately does not turn into a control.

    Distinct from unsatisfiable: nothing is wrong. A volume driver of
    "month_end" is real, useful, and belongs to a *monitor* with a seasonal
    baseline rather than to a control with a fixed threshold. Recording it here
    means the declarer can see their declaration was understood and where it
    went, instead of wondering why it produced nothing.
    """

    rule: str
    declared: str
    destination: str

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "declared": self.declared, "destination": self.destination}


@dataclasses.dataclass(frozen=True, slots=True)
class Generation:
    """Everything Γ concluded about one declaration."""

    controls: tuple[DerivedControl, ...] = ()
    unsatisfiable: tuple[Unsatisfiable, ...] = ()
    deferred: tuple[Deferred, ...] = ()

    def __len__(self) -> int:
        return len(self.controls)

    @property
    def is_complete(self) -> bool:
        """Whether every declaration became something."""
        return not self.unsatisfiable

    def by_rule(self, rule: str) -> tuple[DerivedControl, ...]:
        return tuple(c for c in self.controls if c.rule == rule)

    def rules(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for control in self.controls:
            seen.setdefault(control.rule, None)
        return tuple(seen)

    def merge(self, other: Generation) -> Generation:
        return Generation(
            controls=(*self.controls, *other.controls),
            unsatisfiable=(*self.unsatisfiable, *other.unsatisfiable),
            deferred=(*self.deferred, *other.deferred),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "controls": [c.to_dict() for c in self.controls],
            "unsatisfiable": [u.to_dict() for u in self.unsatisfiable],
            "deferred": [d.to_dict() for d in self.deferred],
        }


# ---------------------------------------------------------------------------
# Severity and evidence, derived from what was declared
# ---------------------------------------------------------------------------

#: Criticality to the severity floor. Tier 1 is regulatory: a defect there is
#: reportable, so the control that finds it cannot be a warning.
_SEVERITY_FLOOR: dict[Criticality, ast.Severity] = {
    Criticality.TIER_1: ast.Severity.CRITICAL,
    Criticality.TIER_2: ast.Severity.MAJOR,
    Criticality.TIER_3: ast.Severity.MINOR,
    Criticality.TIER_4: ast.Severity.INFO,
}


def severity_for(
    dataset: DatasetDeclaration, attribute: AttributeDeclaration | None = None
) -> ast.Severity:
    """The severity a declaration implies.

    Derived rather than defaulted, so a Tier 1 dataset cannot end up with a
    suite of warnings that nobody pages on. A CDE raises the floor of its
    dataset by one rank, because the declaration "this attribute is critical"
    is a statement about the attribute and not about the table it sits in.
    """
    floor = _SEVERITY_FLOOR[dataset.criticality]
    if attribute is not None and attribute.is_cde:
        ranks = list(ast.Severity)
        floor = ranks[min(len(ranks) - 1, floor.rank + 1)]
    return floor


def evidence_for(attribute: AttributeDeclaration | None) -> ast.EvidenceSpec:
    """How much evidence to retain.

    A CDE tied to a regulatory obligation gets full evidence, because the
    question asked about it later is "show me every row", and a sample cannot
    answer that. A sensitive attribute gets counts only: samples of it would
    have to be masked to be stored, and a masked sample of a PII column tells
    the reader nothing they could act on anyway.
    """
    if attribute is None:
        return ast.EvidenceSpec()
    if attribute.sensitivity.masked_by_default:
        return ast.EvidenceSpec(level=ast.EvidenceLevel.COUNTS)
    if attribute.is_cde and attribute.obligations:
        return ast.EvidenceSpec(level=ast.EvidenceLevel.FULL)
    return ast.EvidenceSpec()


def fail_action_for(attribute: AttributeDeclaration | None) -> ast.FailAction:
    """What a failure does.

    A CDE feeding a regulatory return blocks: the declaration "this attribute
    goes into FR Y-14Q" means submitting it wrong is worse than submitting it
    late, and an alert nobody reads before the deadline is not a control.
    """
    if attribute is not None and attribute.is_cde and attribute.obligations:
        return ast.FailAction.BLOCK
    return ast.FailAction.ALERT


# ---------------------------------------------------------------------------
# The generator
# ---------------------------------------------------------------------------


class ControlGenerator:
    """Γ. A declaration in, proposed controls out."""

    def __init__(
        self,
        *,
        catalogue: Catalogue | None = None,
        validators: ValidatorRegistry | None = None,
        codelists: CodeListRegistry | None = None,
    ) -> None:
        #: When present, every generated control is checked against the real
        #: schema before it is offered. A generator with no catalogue still
        #: works — it just cannot promise the controls will compile, and says so
        #: by not claiming to have checked.
        self._catalogue = catalogue
        self._validators = VALIDATORS if validators is None else validators
        self._codelists = CODELISTS if codelists is None else codelists

    def generate(self, declaration: DatasetDeclaration) -> Generation:
        """Every control this declaration implies, each of them once."""
        result = Generation()
        for rule in (
            self._from_grain,
            self._from_business_key,
            self._from_rhythm,
            self._from_temporality,
            self._from_attributes,
            self._from_authoritativeness,
        ):
            result = result.merge(rule(declaration))
        return dataclasses.replace(result, controls=_coalesce(result.controls))

    # -- grain: the most valuable sentence a business owner can write ------

    def _from_grain(self, declaration: DatasetDeclaration) -> Generation:
        grain = declaration.grain
        if grain is None:
            return Generation()
        missing = self._missing(declaration, grain.attributes)
        if missing:
            return Generation(
                unsatisfiable=(
                    Unsatisfiable(
                        rule="grain.uniqueness",
                        declared=grain.render(),
                        reason=(
                            f"the grain names {_and(missing)}, which "
                            f"{'is' if len(missing) == 1 else 'are'} not in "
                            f"{declaration.name}"
                        ),
                        remedy=(
                            "Correct the grain, or map the business attribute to the "
                            "column that holds it. A uniqueness control cannot be "
                            "written against a column that does not exist, and writing "
                            "one anyway would fail on its first run rather than here."
                        ),
                        dataset=declaration.name,
                    ),
                )
            )
        provenance = self._provenance(declaration, "grain.uniqueness", grain.render())
        controls = [
            self._control(
                declaration,
                rule="grain.uniqueness",
                subject=",".join(grain.attributes),
                control=ast.Control(
                    target=declaration.name,
                    assertion=ast.UniqueKeyAssertion(
                        columns=tuple(ast.ColumnRef(name=a) for a in grain.attributes)
                    ),
                    name=f"{declaration.slug or declaration.name}_grain",
                    severity=severity_for(declaration),
                    dimensions=(ast.Dimension.UNIQUENESS,),
                    because=grain.render(),
                    owner=declaration.owner_id,
                    evidence=ast.EvidenceSpec(level=ast.EvidenceLevel.SAMPLES),
                ),
                provenance=provenance,
            )
        ]
        # A unique key over a nullable column does not enforce what the
        # declarer meant. SQL's COUNT(DISTINCT) ignores nulls, so a thousand
        # rows with a null account_id are one distinct value or none depending
        # on the engine, and the grain control passes over data that has no
        # grain at all. The completeness control is not a nicety here; without
        # it the uniqueness control is unsound.
        for attribute_name in grain.attributes:
            controls.append(
                self._control(
                    declaration,
                    rule="grain.completeness",
                    subject=attribute_name,
                    control=ast.Control(
                        target=declaration.name,
                        assertion=ast.PredicateAssertion(
                            subject=ast.ColumnRef(name=attribute_name),
                            operator="is_not_null",
                        ),
                        name=f"{declaration.slug or declaration.name}_{attribute_name}_present",
                        severity=severity_for(declaration, declaration.attribute(attribute_name)),
                        dimensions=(ast.Dimension.COMPLETENESS,),
                        because=(
                            f"{attribute_name} is part of the declared grain "
                            f"({grain.render()}). A missing value here means the row "
                            f"identifies nothing, and would slip past the uniqueness "
                            f"control because SQL does not count nulls as duplicates"
                        ),
                        owner=declaration.owner_id,
                    ),
                    provenance=self._provenance(declaration, "grain.completeness", grain.render()),
                )
            )
        return self._checked(declaration, controls)

    def _from_business_key(self, declaration: DatasetDeclaration) -> Generation:
        key = declaration.business_key
        grain = declaration.grain
        if not key or (grain is not None and set(key) == set(grain.attributes)):
            # The common case: the business key *is* the grain. Generating both
            # would put two identical controls on the same table, and a second
            # alert saying the same thing is how people learn to ignore the
            # first.
            return Generation()
        missing = self._missing(declaration, key)
        if missing:
            return Generation(
                unsatisfiable=(
                    Unsatisfiable(
                        rule="business_key.uniqueness",
                        declared=", ".join(key),
                        reason=f"the business key names {_and(missing)}, which is not present",
                        remedy="Correct the key, or map the attribute to its column.",
                        dataset=declaration.name,
                    ),
                )
            )
        return self._checked(
            declaration,
            [
                self._control(
                    declaration,
                    rule="business_key.uniqueness",
                    subject=",".join(key),
                    control=ast.Control(
                        target=declaration.name,
                        assertion=ast.UniqueKeyAssertion(
                            columns=tuple(ast.ColumnRef(name=a) for a in key)
                        ),
                        name=f"{declaration.slug or declaration.name}_business_key",
                        severity=severity_for(declaration),
                        dimensions=(ast.Dimension.UNIQUENESS,),
                        because=(
                            f"{_and(key)} is the declared business key — the identifier "
                            f"the business uses, as distinct from the grain the table "
                            f"is stored at"
                        ),
                        owner=declaration.owner_id,
                    ),
                    provenance=self._provenance(
                        declaration, "business_key.uniqueness", ", ".join(key)
                    ),
                )
            ],
        )

    # -- rhythm: when data is expected, and how much ------------------------

    def _from_rhythm(self, declaration: DatasetDeclaration) -> Generation:
        rhythm = declaration.rhythm
        if rhythm is None:
            return Generation()
        controls: list[DerivedControl] = []
        deferred: list[Deferred] = []
        unmeasurable: list[Unsatisfiable] = []
        absent: tuple[str, ...] = (
            self._missing(declaration, (rhythm.arrival_column,)) if rhythm.arrival_column else ()
        )
        if rhythm.has_arrival_expectation and absent:
            unmeasurable.append(
                Unsatisfiable(
                    rule="rhythm.freshness",
                    declared=_arrival(rhythm),
                    reason=(f"the arrival column {_and(absent)} is not in {declaration.name}"),
                    remedy="Correct the arrival column, or declare the attribute.",
                    dataset=declaration.name,
                )
            )
        elif rhythm.has_arrival_expectation and not rhythm.arrival_column:
            # A table records its rows, not when they were loaded. With no
            # column saying when a row arrived there is nothing to measure, and
            # a freshness control that can never reach a verdict is worse than
            # none: it sits on the scorecard, never red (Q-64).
            unmeasurable.append(
                Unsatisfiable(
                    rule="rhythm.freshness",
                    declared=_arrival(rhythm),
                    reason=(
                        f"{declaration.name} declares when it arrives but not which column "
                        "records the arrival, so there is nothing to measure freshness on"
                    ),
                    remedy=(
                        "Declare the rhythm's arrival column: the load or ingestion "
                        "timestamp each row carries. For a feed of files, the arrival "
                        "checks on the feed judge timeliness instead."
                    ),
                    dataset=declaration.name,
                )
            )
        elif rhythm.has_arrival_expectation:
            controls.append(
                self._control(
                    declaration,
                    rule="rhythm.freshness",
                    subject="arrival",
                    control=ast.Control(
                        target=declaration.name,
                        assertion=ast.FreshnessAssertion(
                            tolerance_minutes=int(rhythm.lateness_tolerance_seconds // 60),
                            due_time=rhythm.arrival_by or "",
                            calendar=rhythm.calendar or "",
                            column=ast.ColumnRef(
                                name=str(rhythm.arrival_column), dataset=declaration.name
                            ),
                        ),
                        name=f"{declaration.slug or declaration.name}_freshness",
                        severity=severity_for(declaration),
                        dimensions=(ast.Dimension.TIMELINESS,),
                        # The arrival clause only. Quoting the whole rhythm puts
                        # the expected record count in the reason for a
                        # timeliness alert, and a reason that includes an
                        # irrelevant number reads as boilerplate.
                        because=_arrival(rhythm),
                        owner=declaration.owner_id,
                    ),
                    provenance=self._provenance(declaration, "rhythm.freshness", rhythm.render()),
                )
            )
        if rhythm.expected_volume_min is not None or rhythm.expected_volume_max is not None:
            controls.append(
                self._control(
                    declaration,
                    rule="rhythm.volume",
                    subject="row_count",
                    control=ast.Control(
                        target=declaration.name,
                        assertion=ast.RowCountAssertion(
                            minimum=rhythm.expected_volume_min,
                            maximum=rhythm.expected_volume_max,
                        ),
                        name=f"{declaration.slug or declaration.name}_volume",
                        severity=_one_below(severity_for(declaration)),
                        dimensions=(ast.Dimension.COMPLETENESS,),
                        because=(
                            f"the declared volume for a {rhythm.frequency.value} feed is "
                            f"{_volume(rhythm.expected_volume_min, rhythm.expected_volume_max)}"
                        ),
                        owner=declaration.owner_id,
                    ),
                    provenance=self._provenance(declaration, "rhythm.volume", rhythm.render()),
                )
            )
        if rhythm.volume_drivers:
            # Real, useful, and not a control. "Three times normal at month-end"
            # is a *baseline*, and a fixed threshold that accommodates it is
            # loose enough to miss a genuine collapse on an ordinary Tuesday.
            deferred.append(
                Deferred(
                    rule="rhythm.seasonality",
                    declared=", ".join(rhythm.volume_drivers),
                    destination=(
                        "a seasonality-aware volume monitor. A fixed threshold wide "
                        "enough for a month-end spike cannot detect an ordinary day "
                        "collapsing to half its usual size, so this belongs to a "
                        "baseline model rather than to a control"
                    ),
                )
            )
        if rhythm.frequency is Frequency.CONTINUOUS and not rhythm.has_arrival_expectation:
            deferred.append(
                Deferred(
                    rule="rhythm.freshness",
                    declared="continuous",
                    destination=(
                        "a streaming lag monitor. A continuous feed has no cut-off to be "
                        "late against; what matters is how far behind it is running"
                    ),
                )
            )
        checked = self._checked(declaration, controls)
        return Generation(
            controls=checked.controls,
            unsatisfiable=(*checked.unsatisfiable, *unmeasurable),
            deferred=tuple(deferred),
        )

    # -- temporality --------------------------------------------------------

    def _from_temporality(self, declaration: DatasetDeclaration) -> Generation:
        """What a record's relationship to time implies.

        Mostly deferred rather than generated, and honestly so: an append-only
        table's real control is "no row that existed yesterday has changed",
        which compares two points in time and is not a single-scan control at
        all. Emitting a within-scan approximation of it would report green on a
        table being silently rewritten, and that is worse than emitting nothing.
        """
        deferred = {
            Temporality.APPEND_ONLY: (
                "a roll-forward control comparing consecutive snapshots. Whether a row "
                "changed cannot be seen within one scan, and a single-scan approximation "
                "would report green on a table being quietly rewritten"
            ),
            Temporality.EVENT_STREAM: (
                "an ordering and late-arrival monitor, with the watermark carried into "
                "evidence so a verdict says how much of the stream it had seen"
            ),
            Temporality.SLOWLY_CHANGING: (
                "validity-period controls: no overlapping periods, no gaps, exactly one "
                "current row per key"
            ),
            Temporality.AS_OF_DATED: (
                "bitemporal controls: opening plus movements equals closing, and a "
                "restatement is distinguishable from a correction"
            ),
            Temporality.MUTABLE: (
                "no control at all until an as-at column exists. A table overwritten in "
                "place has no history to check against, which is worth saying plainly "
                "rather than generating something that looks like coverage"
            ),
        }
        destination = deferred.get(declaration.temporality)
        if destination is None:
            return Generation()
        return Generation(
            deferred=(
                Deferred(
                    rule="temporality",
                    declared=declaration.temporality.value,
                    destination=destination,
                ),
            )
        )

    # -- attributes ---------------------------------------------------------

    def _from_attributes(self, declaration: DatasetDeclaration) -> Generation:
        result = Generation()
        for attribute in declaration.attributes:
            result = result.merge(self._from_attribute(declaration, attribute))
        return result

    def _from_attribute(
        self, declaration: DatasetDeclaration, attribute: AttributeDeclaration
    ) -> Generation:
        controls: list[DerivedControl] = []
        unsatisfiable: list[Unsatisfiable] = []

        completeness = self._completeness(declaration, attribute)
        if isinstance(completeness, Unsatisfiable):
            unsatisfiable.append(completeness)
        elif completeness is not None:
            controls.append(completeness)

        if attribute.semantic_type:
            outcome = self._semantic_type(declaration, attribute)
            if isinstance(outcome, Unsatisfiable):
                unsatisfiable.append(outcome)
            elif outcome is not None:
                controls.append(outcome)

        domain = self._value_domain(declaration, attribute)
        if isinstance(domain, Unsatisfiable):
            unsatisfiable.append(domain)
        elif domain is not None:
            controls.append(domain)

        currency = self._currency(declaration, attribute)
        if isinstance(currency, Unsatisfiable):
            unsatisfiable.append(currency)
        elif currency is not None:
            controls.append(currency)

        checked = self._checked(declaration, controls)
        return Generation(
            controls=checked.controls,
            unsatisfiable=(*unsatisfiable, *checked.unsatisfiable),
        )

    def _completeness(
        self, declaration: DatasetDeclaration, attribute: AttributeDeclaration
    ) -> DerivedControl | Unsatisfiable | None:
        if attribute.optionality is Optionality.OPTIONAL:
            return None
        conditional = attribute.optionality is Optionality.CONDITIONAL
        where = None
        if conditional:
            problem = self._condition_problem(declaration, attribute)
            if problem is not None:
                return problem
            where = _parse_condition(attribute.optionality_condition)
        because = (
            f"{attribute.name} is mandatory"
            if not conditional
            else f"{attribute.name} is mandatory when {attribute.optionality_condition}"
        )
        if attribute.definition:
            because += f". {attribute.definition}"
        return self._control(
            declaration,
            rule="attribute.completeness",
            subject=attribute.name,
            control=ast.Control(
                target=declaration.name,
                assertion=ast.PredicateAssertion(
                    subject=ast.ColumnRef(name=attribute.name), operator="is_not_null"
                ),
                where=where,
                name=f"{declaration.slug or declaration.name}_{attribute.name}_present",
                severity=severity_for(declaration, attribute),
                dimensions=(ast.Dimension.COMPLETENESS,),
                because=because,
                evidence=evidence_for(attribute),
                on_fail=fail_action_for(attribute),
                owner=attribute.owner_id or declaration.owner_id,
            ),
            provenance=self._provenance(declaration, "attribute.completeness", because, attribute),
        )

    @staticmethod
    def _condition_problem(
        declaration: DatasetDeclaration, attribute: AttributeDeclaration
    ) -> Unsatisfiable | None:
        """Why a conditional attribute cannot become a filtered control.

        Both failures here land in the same place, and it is not the obvious
        one. Falling through with no filter produces an *unconditional*
        control: stricter than declared, alerting on rows the business
        explicitly said were fine, and switched off within a week — taking the
        real coverage with it. A control the declarer did not ask for is worse
        than no control, because it looks like the one they did.
        """
        if not attribute.optionality_condition:
            return Unsatisfiable(
                rule="attribute.completeness",
                declared=f"{attribute.name} is conditionally mandatory",
                reason="no condition was given for when it is mandatory",
                remedy=(
                    "State the condition. The only control that could be generated "
                    "without one is the unconditional version, which is stricter than "
                    "you declared."
                ),
                dataset=declaration.name,
            )
        if _parse_condition(attribute.optionality_condition) is None:
            return Unsatisfiable(
                rule="attribute.completeness",
                declared=(f"{attribute.name} is mandatory when {attribute.optionality_condition}"),
                reason=(
                    f"the condition {attribute.optionality_condition!r} is not a PQL "
                    f"expression, so the rows it applies to cannot be identified"
                ),
                remedy=(
                    "Write the condition as an expression over this dataset's columns, "
                    "for example product_type = 'BOND'. Without one the only control "
                    "that could be generated is the unconditional version, which is "
                    "stricter than you declared."
                ),
                dataset=declaration.name,
            )
        return None

    def _semantic_type(
        self, declaration: DatasetDeclaration, attribute: AttributeDeclaration
    ) -> DerivedControl | Unsatisfiable | None:
        name = attribute.semantic_type
        validator = self._validators.find(name)
        if validator is None:
            code_list = self._codelists.find(name)
            if code_list is not None:
                return self._control(
                    declaration,
                    rule="attribute.semantic_type",
                    subject=attribute.name,
                    control=self._membership(declaration, attribute, name, code_list.label),
                    provenance=self._provenance(
                        declaration,
                        "attribute.semantic_type",
                        f"{attribute.name} is a {code_list.label}",
                        attribute,
                    ),
                )
            return Unsatisfiable(
                rule="attribute.semantic_type",
                declared=f"{attribute.name} is a {name}",
                reason=f"Prama has no validator or code list called {name!r}",
                # Every known type, not the first handful. An alphabetical
                # truncation hides isin and lei — the two anybody hitting this
                # message is most likely to have meant — and a remedy that
                # omits the answer is not a remedy.
                remedy=(
                    "Choose a known type — "
                    + ", ".join((*self._validators.names(), *self._codelists.names()))
                    + " — or register a validator for it. An unknown type would "
                    "compile to a check that passes everything, which is worse than "
                    "no control because it looks like coverage."
                ),
                dataset=declaration.name,
            )
        return self._control(
            declaration,
            rule="attribute.semantic_type",
            subject=attribute.name,
            control=ast.Control(
                target=declaration.name,
                assertion=ast.PredicateAssertion(
                    subject=ast.ColumnRef(name=attribute.name),
                    operator="is_valid",
                    argument=ast.Literal(value=name),
                ),
                name=f"{declaration.slug or declaration.name}_{attribute.name}_valid",
                severity=severity_for(declaration, attribute),
                dimensions=(ast.Dimension.VALIDITY,),
                because=(
                    f"{attribute.name} is declared to be {validator.describe()}"
                    + (
                        f". {validator.beyond_shape.capitalize()}"
                        if not validator.screen_is_complete
                        else ""
                    )
                ),
                evidence=evidence_for(attribute),
                on_fail=fail_action_for(attribute),
                owner=attribute.owner_id or declaration.owner_id,
            ),
            provenance=self._provenance(
                declaration,
                "attribute.semantic_type",
                f"{attribute.name} is {validator.describe()}",
                attribute,
            ),
        )

    def _value_domain(
        self, declaration: DatasetDeclaration, attribute: AttributeDeclaration
    ) -> DerivedControl | Unsatisfiable | None:
        domain = attribute.value_domain
        if not domain.is_constrained:
            return None
        if domain.kind is ValueDomainKind.CODELIST:
            if domain.codelist_ref:
                code_list = self._codelists.find(domain.codelist_ref)
                if code_list is None:
                    return Unsatisfiable(
                        rule="attribute.value_domain",
                        declared=f"{attribute.name} is drawn from {domain.codelist_ref}",
                        reason=f"the code list {domain.codelist_ref!r} is not registered",
                        remedy=(
                            "Register the list, so the control can be replayed against "
                            "the list as it stood on the day it ran."
                        ),
                        dataset=declaration.name,
                    )
                control = self._membership(
                    declaration, attribute, domain.codelist_ref, code_list.label
                )
            else:
                control = ast.Control(
                    target=declaration.name,
                    assertion=ast.PredicateAssertion(
                        subject=ast.ColumnRef(name=attribute.name),
                        operator="in",
                        argument=ast.ListExpression(
                            items=tuple(ast.Literal(value=v) for v in domain.allowed_values)
                        ),
                    ),
                    name=f"{declaration.slug or declaration.name}_{attribute.name}_domain",
                    severity=severity_for(declaration, attribute),
                    dimensions=(ast.Dimension.VALIDITY,),
                    because=(f"{attribute.name} may only be {_and(domain.allowed_values)}"),
                    evidence=evidence_for(attribute),
                    on_fail=fail_action_for(attribute),
                    owner=attribute.owner_id or declaration.owner_id,
                )
        elif domain.kind is ValueDomainKind.RANGE:
            control = ast.Control(
                target=declaration.name,
                assertion=self._range(attribute, domain.minimum, domain.maximum),
                name=f"{declaration.slug or declaration.name}_{attribute.name}_range",
                severity=severity_for(declaration, attribute),
                dimensions=(ast.Dimension.VALIDITY,),
                because=(
                    f"{attribute.name} is declared to lie "
                    f"{_range_words(domain.minimum, domain.maximum)}"
                ),
                evidence=evidence_for(attribute),
                on_fail=fail_action_for(attribute),
                owner=attribute.owner_id or declaration.owner_id,
            )
        elif not domain.pattern:
            # A pattern domain with no pattern. Generating one anyway produces
            # ``MATCHES /None/`` — a control that parses, compiles, runs and
            # fails every row, which is the exact class of artefact this
            # codebase exists to refuse. It is a gap in the declaration, and it
            # is reported as one.
            return Unsatisfiable(
                rule="attribute.value_domain",
                declared=f"{attribute.name} has a pattern domain",
                reason=(
                    f"{attribute.name} is declared to be constrained by a pattern and "
                    "no pattern was given, so there is nothing to check against"
                ),
                remedy=(
                    "Give the pattern, choose a semantic type that carries one "
                    "(isin, lei, iban), or leave the domain free text."
                ),
            )
        else:  # PATTERN
            control = ast.Control(
                target=declaration.name,
                assertion=ast.PredicateAssertion(
                    subject=ast.ColumnRef(name=attribute.name),
                    operator="matches",
                    # A pattern literal, not text. PQL writes patterns between
                    # slashes, and a text literal here renders to something the
                    # parser refuses — which a round-trip test found and no
                    # amount of reading the generator would have.
                    argument=ast.Literal(value=domain.pattern, literal_type="pattern"),
                ),
                name=f"{declaration.slug or declaration.name}_{attribute.name}_pattern",
                severity=severity_for(declaration, attribute),
                dimensions=(ast.Dimension.CONFORMITY,),
                because=f"{attribute.name} is declared to match {domain.pattern}",
                evidence=evidence_for(attribute),
                on_fail=fail_action_for(attribute),
                owner=attribute.owner_id or declaration.owner_id,
            )
        return self._control(
            declaration,
            rule="attribute.value_domain",
            subject=attribute.name,
            control=control,
            provenance=self._provenance(
                declaration, "attribute.value_domain", control.because, attribute
            ),
        )

    def _currency(
        self, declaration: DatasetDeclaration, attribute: AttributeDeclaration
    ) -> DerivedControl | Unsatisfiable | None:
        """A monetary amount implies a control on the column beside it.

        Declaring an amount is denominated in ``settlement_ccy`` is a statement
        about *that* column, and it is the one that makes the amount summable.
        An invalid currency code does not make one row wrong; it makes every
        aggregate over the column meaningless, which is why it is generated
        here rather than left to whoever remembers to declare the code column
        separately.
        """
        if not attribute.currency_attribute:
            return None
        currency_column = attribute.currency_attribute
        if not self._present(declaration, currency_column):
            return Unsatisfiable(
                rule="attribute.currency",
                declared=f"{attribute.name} is denominated in {currency_column}",
                reason=f"{declaration.name} has no column {currency_column!r}",
                remedy=(
                    "Name the column that holds the currency code. Without one, the "
                    "amounts cannot be summed — an aggregate over them would be adding "
                    "euros to yen — and no control can establish otherwise."
                ),
                dataset=declaration.name,
            )
        return self._control(
            declaration,
            rule="attribute.currency",
            subject=currency_column,
            control=self._membership(
                declaration,
                dataclasses.replace(attribute, name=currency_column),
                "iso4217",
                "ISO 4217 currency code",
                because=(
                    f"{attribute.name} is denominated in {currency_column}. An invalid "
                    f"code there does not make one row wrong — it makes every total over "
                    f"{attribute.name} meaningless, because the amounts cannot be added"
                ),
            ),
            provenance=self._provenance(
                declaration,
                "attribute.currency",
                f"{attribute.name} is a monetary amount denominated in {currency_column}",
                attribute,
            ),
        )

    # -- authoritativeness --------------------------------------------------

    def _from_authoritativeness(self, declaration: DatasetDeclaration) -> Generation:
        """A replica's controls are parity and staleness, not quality.

        A replica scoring well on its own content says nothing: it is only ever
        as good as its origin, and a perfect copy of wrong data is a perfect
        copy. So the declaration "this is a replica of X" produces controls
        about the *relationship* and demotes the independent score, rather than
        generating another suite of column checks that would flatter it.
        """
        if not declaration.is_replica:
            return Generation()
        if not declaration.source_of_truth:
            return Generation(
                unsatisfiable=(
                    Unsatisfiable(
                        rule="authoritativeness.parity",
                        declared=f"{declaration.name} is a {declaration.authoritativeness.value}",
                        reason="no source of truth was named",
                        remedy=(
                            "Name the dataset this one copies. A replica whose origin is "
                            "unknown cannot be checked for parity or staleness, and its "
                            "own quality score would flatter it: a perfect copy of wrong "
                            "data is a perfect copy."
                        ),
                        dataset=declaration.name,
                    ),
                )
            )
        return Generation(
            deferred=(
                Deferred(
                    rule="authoritativeness.parity",
                    declared=(
                        f"{declaration.name} is a {declaration.authoritativeness.value} "
                        f"of {declaration.source_of_truth}"
                    ),
                    destination=(
                        "a MIRRORS relationship, which generates row-count parity, "
                        "content parity and staleness across the two datasets. Those are "
                        "cross-dataset controls and belong to the relationship rather "
                        "than to either side of it"
                    ),
                ),
            )
        )

    # -- construction and checking -----------------------------------------

    def _membership(
        self,
        declaration: DatasetDeclaration,
        attribute: AttributeDeclaration,
        codelist: str,
        label: str,
        *,
        because: str = "",
    ) -> ast.Control:
        return ast.Control(
            target=declaration.name,
            assertion=ast.PredicateAssertion(
                subject=ast.ColumnRef(name=attribute.name),
                operator="in_codelist",
                argument=ast.Literal(value=codelist),
            ),
            name=f"{declaration.slug or declaration.name}_{attribute.name}_codelist",
            severity=severity_for(declaration, attribute),
            # Consistency as well as validity when this control exists because
            # an amount is denominated in it: an invalid code does not make one
            # row invalid, it makes the amount and its currency disagree, and
            # every total over the amount meaningless.
            dimensions=(
                (ast.Dimension.VALIDITY, ast.Dimension.CONSISTENCY)
                if because
                else (ast.Dimension.VALIDITY,)
            ),
            because=because or f"{attribute.name} is declared to be a {label}",
            evidence=evidence_for(attribute),
            on_fail=fail_action_for(attribute),
            owner=attribute.owner_id or declaration.owner_id,
        )

    @staticmethod
    def _range(
        attribute: AttributeDeclaration, minimum: float | None, maximum: float | None
    ) -> ast.Assertion:
        column = ast.ColumnRef(name=attribute.name)
        if minimum is not None and maximum is not None:
            return ast.PredicateAssertion(
                subject=column,
                operator="between",
                argument=_number(minimum),
                upper=_number(maximum),
            )
        if minimum is not None:
            return ast.PredicateAssertion(subject=column, operator=">=", argument=_number(minimum))
        return ast.PredicateAssertion(subject=column, operator="<=", argument=_number(maximum))

    def _control(
        self,
        declaration: DatasetDeclaration,
        *,
        rule: str,
        subject: str,
        control: ast.Control,
        provenance: Provenance,
    ) -> DerivedControl:
        return DerivedControl(
            identity=identity(
                declaration.reference or declaration.name, rule, declaration.name, subject
            ),
            control=dataclasses.replace(
                control,
                derived_from=provenance.source_ref or declaration.name,
            ),
            provenance=provenance,
            rule=rule,
        )

    @staticmethod
    def _provenance(
        declaration: DatasetDeclaration,
        rule: str,
        statement: str,
        attribute: AttributeDeclaration | None = None,
    ) -> Provenance:
        # The reference points at the *attribute* declaration when one produced
        # the control. "Why does this exist?" should land on the sentence
        # somebody wrote about this field, not on the table it happens to live
        # in — otherwise the answer to a question about counterparty_lei is a
        # page describing exposures, and the reader has to hunt for the line
        # that matters.
        base = declaration.reference or declaration.name
        return Provenance(
            origin=Origin.DECLARATION,
            rule=rule,
            source_ref=f"{base}#{attribute.name}" if attribute is not None else base,
            statement=statement,
            declared_by=declaration.declared_by,
            declared_at=declaration.declared_at,
        )

    def _checked(
        self, declaration: DatasetDeclaration, controls: list[DerivedControl]
    ) -> Generation:
        """Type-check what was generated, before anybody is offered it.

        Doctrine, not belt and braces: assert the rendered artefact, not the
        intent. A generator that emits plausible PQL and is never asked to
        compile it is a generator whose bugs are found in production.
        """
        if self._catalogue is None:
            return Generation(controls=tuple(controls))
        from prama.pql.types import TypeChecker

        checker = TypeChecker(self._catalogue)
        kept: list[DerivedControl] = []
        rejected: list[Unsatisfiable] = []
        for derived in controls:
            findings = checker.check(derived.control)
            errors = [f for f in findings if f.level == "error"]
            if errors:
                rejected.append(
                    Unsatisfiable(
                        rule=derived.rule,
                        declared=derived.provenance.statement,
                        reason="; ".join(f.message for f in errors),
                        remedy=(
                            "The declaration produced a control that does not type-check "
                            "against the live schema. Correct the declaration, or the "
                            "mapping from business attribute to column."
                        ),
                        dataset=declaration.name,
                    )
                )
            else:
                kept.append(derived)
        return Generation(controls=tuple(kept), unsatisfiable=tuple(rejected))

    def _missing(self, declaration: DatasetDeclaration, names: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(n for n in names if not self._present(declaration, n))

    def _present(self, declaration: DatasetDeclaration, name: str) -> bool:
        """Whether a column exists, according to whichever source knows.

        The catalogue is the authority when there is one, because it reflects
        the database. The declaration's own attribute list is the fallback, and
        a declaration with no attributes at all is taken at its word — refusing
        to generate anything for a dataset whose columns have not been profiled
        yet would make Γ useless at exactly the moment it is most wanted.
        """
        if self._catalogue is not None:
            schema = self._catalogue.get(declaration.name)
            if schema is not None:
                return schema.column(name) is not None
        if declaration.attributes:
            return declaration.has_attribute(name)
        return True


# ---------------------------------------------------------------------------
# Sentence helpers. Generated prose is read by people; it has to scan.
# ---------------------------------------------------------------------------


def _coalesce(controls: tuple[DerivedControl, ...]) -> tuple[DerivedControl, ...]:
    """Fold controls that check the same thing into one that says why twice.

    Two rules reaching the same check is normal and correct. A grain of
    ``(account_id, business_date)`` implies ``account_id IS NOT NULL`` because a
    null key member would slip past the uniqueness control; declaring the same
    attribute mandatory implies it too. Both are real reasons.

    Emitting both produces two identical alerts on the same rows, and a second
    alert saying exactly what the first one said is how people learn to ignore
    the first. Dropping one loses a reason the owner declared. So they merge:
    the strictest severity, evidence and failure action of the group, and *both*
    justifications in the BECAUSE clause — which is the honest answer to "why
    does this exist?" when there are two answers.

    Merging is on what the control *does* — target, rendered assertion, filter —
    and never on its name or reason, because that is what determines whether two
    alerts would land on the same rows.
    """
    groups: dict[tuple[str, str, str], list[DerivedControl]] = {}
    for derived in controls:
        control = derived.control
        key = (
            control.target,
            control.assertion.render(),
            control.where.render() if control.where is not None else "",
        )
        groups.setdefault(key, []).append(derived)
    folded: list[DerivedControl] = []
    for members in groups.values():
        folded.append(members[0] if len(members) == 1 else _fold(members))
    return tuple(folded)


def _fold(members: list[DerivedControl]) -> DerivedControl:
    """Combine a group of identical checks into the strictest of them."""
    strongest = max(members, key=lambda m: m.control.severity.rank)
    reasons: list[str] = []
    for member in members:
        reason = member.control.because.strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    evidence = max(
        (m.control.evidence for m in members),
        key=lambda e: list(ast.EvidenceLevel).index(e.level),
    )
    blocks = any(m.control.on_fail is ast.FailAction.BLOCK for m in members)
    provenance = strongest.provenance
    control = dataclasses.replace(
        strongest.control,
        because=" ".join(_terminated(r) for r in reasons),
        evidence=evidence,
        on_fail=ast.FailAction.BLOCK if blocks else strongest.control.on_fail,
    )
    return dataclasses.replace(
        strongest,
        control=control,
        # The rule becomes the set that produced it. A control attributed to
        # one rule when two made it would mislead anybody trying to find out
        # why a whole class of controls looks wrong.
        rule="+".join(sorted({m.rule for m in members})),
        provenance=provenance,
    )


def _terminated(sentence: str) -> str:
    return sentence if sentence.endswith((".", "!", "?")) else sentence + "."


def _number(value: float | None) -> ast.Literal:
    """A numeric literal, typed as one.

    ``Literal`` defaults to text, so a bound built without this renders as
    ``market_value >= '0'`` — a numeric column compared against a string. The
    engines mostly coerce it, which is worse than failing: the control runs, and
    on a dialect that compares lexically it reports that -5 is above zero.
    """
    return ast.Literal(value=value, literal_type="number")


def _and(items: tuple[str, ...] | list[str]) -> str:
    values = list(items)
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f" and {values[-1]}"


def _arrival(rhythm: Any) -> str:
    parts = [f"{rhythm.frequency.value.replace('_', ' ')} data is due by {rhythm.arrival_by}"]
    if rhythm.calendar:
        parts.append(f"on {rhythm.calendar} business days")
    if rhythm.lateness_tolerance_seconds:
        parts.append(f"with {int(rhythm.lateness_tolerance_seconds // 60)} minutes of grace")
    return ", ".join(parts)


def _volume(minimum: int | None, maximum: int | None) -> str:
    if minimum is not None and maximum is not None:
        return f"between {minimum:,} and {maximum:,} records"
    if minimum is not None:
        return f"at least {minimum:,} records"
    return f"at most {maximum or 0:,} records"


def _range_words(minimum: float | None, maximum: float | None) -> str:
    if minimum is not None and maximum is not None:
        return f"between {minimum:g} and {maximum:g}"
    if minimum is not None:
        return f"at or above {minimum:g}"
    return f"at or below {maximum:g}" if maximum is not None else "within bounds"


def _one_below(severity: ast.Severity) -> ast.Severity:
    """A volume miss is real but rarely as urgent as a broken key."""
    ranks = list(ast.Severity)
    return ranks[max(0, severity.rank - 1)]


def _parse_condition(condition: str) -> ast.Expression | None:
    """Parse a declared condition into a WHERE clause.

    Returns None when it will not parse. A conditional-completeness control
    with an unparseable condition would silently become an unconditional one —
    stricter than declared, alerting on rows the business said were fine, and
    switched off within the week.
    """
    from prama.pql.errors import PqlError
    from prama.pql.parser import parse_control

    try:
        parsed = parse_control(f"CHECK x SATISFIES {condition}")
    except PqlError:
        return None
    assertion = parsed.assertion
    if isinstance(assertion, ast.ExpressionAssertion):
        return assertion.condition
    return None
