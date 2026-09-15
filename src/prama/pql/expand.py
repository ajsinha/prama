"""Turning a selector into the controls it actually means.

``CHECK EVERY ATTRIBUTE WHERE is_cde AND domain = 'Credit Risk' IS NOT NULL``
is a sentence a Head of Data can approve. Two hundred hand-written controls
saying the same thing are not, and they will be out of date within a quarter.
Selectors are how a control estate is declared rather than typed.

The expansion is **materialised**, not resolved at run time, and that is the
whole design. A selector re-evaluated on every run silently starts covering a
new attribute the moment somebody tags one — which sounds like a feature and is
not: nobody approved the new control, nobody was told, and the first anybody
hears of it is an alert about a dataset they did not know was in scope. Worse
in the other direction: an attribute that stops matching quietly loses its
control, and the coverage report still says it is covered.

So an expansion is a recorded artefact with a hash. Re-expanding compares
against it, and the difference is shown to a person: *this selector now covers
four more attributes and no longer covers one.* Approving that is a decision
somebody makes, and it is on the record.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import difflib
import hashlib
from datetime import datetime
from typing import Any

from prama.core.clock import utc_now
from prama.core.errors import ValidationError
from prama.pql import ast


@dataclasses.dataclass(frozen=True, slots=True)
class Attribute:
    """A declared attribute, with the metadata a selector can match on."""

    dataset: str
    name: str
    concept: str = ""
    concept_property: str = ""
    domain: str = ""
    owner: str = ""
    criticality: str = ""
    semantic_type: str = ""
    is_cde: bool = False
    tags: tuple[str, ...] = ()

    @property
    def qualified(self) -> str:
        return f"{self.dataset}.{self.name}"

    def facts(self) -> dict[str, Any]:
        """The metadata a selector predicate is evaluated against.

        A flat mapping rather than the object, so the predicate language is the
        ordinary expression language and a selector reads like a WHERE clause —
        which is what it is.
        """
        return {
            "dataset": self.dataset,
            "name": self.name,
            "attribute": self.name,
            "concept": self.concept,
            "concept_property": self.concept_property,
            "domain": self.domain,
            "owner": self.owner,
            "criticality": self.criticality,
            "semantic_type": self.semantic_type,
            "is_cde": self.is_cde,
            "tags": list(self.tags),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class AttributeCatalogue:
    """Every declared attribute a selector may reach."""

    attributes: tuple[Attribute, ...] = ()

    def matching(self, selector: ast.Selector) -> list[Attribute]:
        if selector.kind == "concept":
            return [
                a
                for a in self.attributes
                if a.concept == selector.concept and a.concept_property == selector.concept_property
            ]
        if selector.where is None:
            return list(self.attributes)
        # Checked once against the fact names, before any attribute is tested.
        # `facts.get(name)` returns None for a typo, every comparison against
        # None is False, and the selector expands to nothing — so `WHERE
        # is_cdee` produced an estate that looked covered and covered nothing,
        # with no diagnostic anywhere. QA round 4, `PQL-366`.
        _check_fact_names(selector.where)
        return [a for a in self.attributes if _truth(selector.where, a.facts())]


@dataclasses.dataclass(frozen=True, slots=True)
class Expansion:
    """What a selector covered, at the moment somebody approved it."""

    selector: str
    attributes: tuple[str, ...]
    expanded_at: datetime
    #: A hash of the covered set, so drift is a comparison rather than a diff.
    digest: str = ""

    @classmethod
    def of(cls, selector: ast.Selector, attributes: list[Attribute]) -> Expansion:
        covered = tuple(sorted(a.qualified for a in attributes))
        return cls(
            selector=selector.render(),
            attributes=covered,
            expanded_at=utc_now(),
            digest=hashlib.sha256("\n".join(covered).encode("utf-8")).hexdigest()[:16],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "attributes": list(self.attributes),
            "count": len(self.attributes),
            "digest": self.digest,
            "expanded_at": self.expanded_at.isoformat(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Drift:
    """How a selector's coverage has changed since it was approved."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    @property
    def has_changed(self) -> bool:
        return bool(self.added or self.removed)

    def render(self) -> str:
        """What to put in front of the person who has to approve it."""
        if not self.has_changed:
            return "This selector covers exactly what it covered when it was approved."
        parts = []
        if self.added:
            parts.append(
                f"now covers {len(self.added)} more: {', '.join(self.added[:5])}"
                + (" …" if len(self.added) > 5 else "")
            )
        if self.removed:
            parts.append(
                f"no longer covers {len(self.removed)}: {', '.join(self.removed[:5])}"
                + (" …" if len(self.removed) > 5 else "")
            )
        return "This selector " + "; and ".join(parts) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.has_changed,
            "added": list(self.added),
            "removed": list(self.removed),
            "summary": self.render(),
        }


class Expander:
    """Expands selector controls, and reports when an expansion has moved."""

    def __init__(self, catalogue: AttributeCatalogue) -> None:
        self._catalogue = catalogue

    def preview(self, control: ast.Control) -> Expansion:
        """What this selector covers now. Shown before anything is approved."""
        selector = self._selector_of(control)
        return Expansion.of(selector, self._catalogue.matching(selector))

    def expand(self, control: ast.Control) -> list[ast.Control]:
        """One concrete control per matched attribute.

        Each keeps the selector that produced it, so an expanded control can
        always say which declaration it came from — which is the difference
        between a generated estate somebody owns and one nobody recognises.
        """
        selector = self._selector_of(control)
        matched = self._catalogue.matching(selector)
        if not matched:
            # Not an error: a domain may genuinely have no CDEs yet. But an
            # empty expansion that looked like a covered estate would be a
            # coverage report built on nothing.
            return []
        return [self._bind(control, attribute) for attribute in matched]

    def expand_all(self, controls: list[ast.Control]) -> list[ast.Control]:
        out: list[ast.Control] = []
        for control in controls:
            out.extend(self.expand(control) if control.is_template else [control])
        return out

    def drift(self, control: ast.Control, approved: Expansion) -> Drift:
        """What has changed since the expansion on the record."""
        now = set(self.preview(control).attributes)
        then = set(approved.attributes)
        return Drift(added=tuple(sorted(now - then)), removed=tuple(sorted(then - now)))

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _selector_of(control: ast.Control) -> ast.Selector:
        if control.selector is None:
            raise ValidationError(
                "this control names a dataset, so there is nothing to expand",
                remedy="Only controls written against a selector are expanded.",
                context={"control": control.render().splitlines()[0]},
            )
        return control.selector

    @staticmethod
    def _bind(control: ast.Control, attribute: Attribute) -> ast.Control:
        column = ast.ColumnRef(name=attribute.name, dataset=attribute.dataset)
        origin = control.selector.render() if control.selector else ""
        return dataclasses.replace(
            control,
            target=attribute.dataset,
            assertion=_rebind(control.assertion, column),
            # Cleared, so the expanded control renders and re-parses as the
            # ordinary control it now is; kept as provenance beside it.
            selector=None,
            derived_from=origin,
            because=control.because or f"Selected by {origin}",
        )


def _rebind(assertion: ast.Assertion, column: ast.ColumnRef) -> ast.Assertion:
    """Replace the placeholder with the attribute the selector matched."""
    if isinstance(assertion, ast.PredicateAssertion) and isinstance(
        assertion.subject, ast.SelectedAttribute
    ):
        return dataclasses.replace(assertion, subject=column)
    return assertion


#: Every name a selector may mention, derived from the mapping the predicate is
#: actually evaluated against rather than restated here — a second list would
#: drift the first time a fact is added.
def _known_facts() -> frozenset[str]:
    return frozenset(Attribute(dataset="", name="").facts())


def _check_fact_names(expression: ast.Expression) -> None:
    """Refuse a selector that mentions metadata no attribute carries."""
    unknown = sorted(_mentioned(expression) - _known_facts())
    if not unknown:
        return
    known = sorted(_known_facts())
    suggestions = {
        name: close[0]
        for name in unknown
        if (close := difflib.get_close_matches(name, known, n=1, cutoff=0.7))
    }
    hint = (
        " Did you mean " + ", ".join(f"{bad} -> {good}" for bad, good in suggestions.items()) + "?"
        if suggestions
        else ""
    )
    raise ValidationError(
        f"the selector mentions {', '.join(repr(n) for n in unknown)}, which is not "
        "attribute metadata",
        remedy=f"Available: {', '.join(known)}.{hint}",
        context={"unknown": unknown},
    )


def _mentioned(expression: ast.Expression) -> set[str]:
    """Every metadata name a selector predicate reads."""
    if isinstance(expression, ast.ColumnRef):
        return {expression.name}
    if isinstance(expression, ast.ListExpression):
        return set().union(*(_mentioned(item) for item in expression.items), set())
    if isinstance(expression, ast.UnaryOp):
        return _mentioned(expression.operand)
    if isinstance(expression, ast.BinaryOp):
        return _mentioned(expression.left) | _mentioned(expression.right)
    return set()


def _truth(expression: ast.Expression, facts: dict[str, Any]) -> bool:
    """Evaluate a selector predicate against one attribute's metadata.

    Two-valued deliberately, unlike the row predicates: an attribute either
    matches a selector or it does not. There is no third state, because an
    attribute whose metadata is missing is simply an attribute that has not
    been declared that way — and quietly including it would put a control on
    something nobody classified.
    """
    # `_is_true`, not `is True`. The two disagreed: this required the literal
    # `True` and `_is_true` — used by the NOT branch — also accepted the string
    # "true". So for a value that arrived from a warehouse as text, `WHERE
    # is_cde` and `WHERE NOT is_cde` **both** excluded the attribute, putting it
    # in neither half of a partition. QA round 4, `PQL-372`, `PQL-373`.
    return _is_true(_value(expression, facts))


def _value(expression: ast.Expression, facts: dict[str, Any]) -> Any:
    if isinstance(expression, ast.ColumnRef):
        return facts.get(expression.name)
    if isinstance(expression, ast.Literal):
        return expression.value
    if isinstance(expression, ast.ListExpression):
        return [_value(item, facts) for item in expression.items]
    if isinstance(expression, ast.UnaryOp):
        inner = _value(expression.operand, facts)
        if expression.operator == "NOT":
            return not _is_true(inner)
        if expression.operator == "IS NULL":
            return inner in (None, "")
        if expression.operator == "IS NOT NULL":
            return inner not in (None, "")
        return inner
    if isinstance(expression, ast.BinaryOp):
        return _binary(expression, facts)
    return None


def _binary(expression: ast.BinaryOp, facts: dict[str, Any]) -> Any:
    operator = expression.operator
    if operator == "AND":
        return _truth(expression.left, facts) and _truth(expression.right, facts)
    if operator == "OR":
        return _truth(expression.left, facts) or _truth(expression.right, facts)
    left = _value(expression.left, facts)
    right = _value(expression.right, facts)
    if operator in ("IN", "NOT IN"):
        members = right if isinstance(right, list) else [right]
        found = left in members
        # A tag list matches if the selector's value is among the tags, so
        # `tags IN ('pii')` reads the way somebody expects it to.
        if not found and isinstance(left, list):
            found = any(m in left for m in members)
        return found if operator == "IN" else not found
    if left is None or right is None:
        return False
    if isinstance(left, list) and operator in ("=", "<>"):
        # `tags = 'pii'` compares a list with a string: never equal, so the
        # selector silently matched nothing while `tags IN ('pii')` — the same
        # intent, spelled differently — matched. Refused rather than quietly
        # answered, with the spelling that works. QA round 4, `PQL-369`.
        raise ValidationError(
            f"{expression.left.render()} holds a list, so it cannot be compared with {operator!r}",
            remedy=(
                f"Write {expression.left.render()} IN (…) to ask whether a value is "
                "among them. An equality against a list is never true, so the "
                "selector would match nothing and say nothing."
            ),
            context={"operator": operator},
        )
    try:
        return {
            "=": left == right,
            "<>": left != right,
            ">": left > right,
            ">=": left >= right,
            "<": left < right,
            "<=": left <= right,
        }.get(operator, False)
    except TypeError as exc:
        # Swallowed into `False` before, so `criticality > 3` — a string against
        # an integer — expanded to nothing and looked like "no attribute is that
        # critical". QA round 4, `PQL-369`.
        raise ValidationError(
            f"{expression.render()} compares {type(left).__name__} with "
            f"{type(right).__name__}, which cannot be ordered",
            remedy=(
                "Compare like with like. Selector metadata is text unless it was "
                "declared otherwise, so quote the value or fix the declaration."
            ),
            context={"left": type(left).__name__, "right": type(right).__name__},
        ) from exc


def _is_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")
