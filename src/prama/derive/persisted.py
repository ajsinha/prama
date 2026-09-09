"""Reading a stored declaration back into the form Γ generates from.

Γ takes a :class:`DatasetDeclaration` — a plain value with no database in it,
which is what makes the generator testable and the same in every caller. The
declarations, though, live in the semantic tables. This module is the one
place that crosses between them.

One place, deliberately. The alternative is each caller — the console, the CLI,
the scheduler — assembling its own, and then the console generating a control
the CLI does not, for a reason nobody can find. If the mapping is wrong it is
wrong everywhere at once, which is the failure mode you can actually fix.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.semantic.values import (
    Authoritativeness,
    Criticality,
    Grain,
    Optionality,
    Rhythm,
    Sensitivity,
    Temporality,
    ValueDomain,
    ValueDomainKind,
)


def _enum(cls: Any, value: Any, fallback: Any) -> Any:
    """Coerce a stored string, falling back rather than raising.

    A row whose ``temporality`` is a value this build does not know about is a
    reason to generate fewer controls, not a reason to fail the whole page.
    The CHECK constraints make it nearly impossible; nearly is not never, and
    a console that 500s on one bad row hides the other nine hundred.
    """
    try:
        return cls(value)
    except (ValueError, KeyError):
        return fallback


def _value_domain(payload: dict[str, Any]) -> ValueDomain:
    """A stored value domain as the value object.

    ``ValueDomain(**payload)`` looks right and is wrong: ``kind`` comes back
    from JSON as a string, and ``ValueDomain.kind`` is an enum. The dataclass
    accepts it without complaint, and then ``is_constrained`` — which asks
    ``self.kind is not ValueDomainKind.FREE_TEXT`` — is True for *every*
    attribute, because a string is never that enum member.

    The result was a control on every free-text column asserting it matches the
    literal pattern ``None``, which failed every row of every dataset. It
    parsed, it compiled, it ran, and it was nonsense.
    """
    if not payload:
        return ValueDomain()
    fields = dict(payload)
    fields["kind"] = _enum(ValueDomainKind, fields.get("kind"), ValueDomainKind.FREE_TEXT)
    fields["allowed_values"] = tuple(fields.get("allowed_values") or ())
    return ValueDomain(**fields)


def attribute_declaration_of(version: Any) -> AttributeDeclaration:
    return AttributeDeclaration(
        name=version.name,
        definition=version.definition or "",
        interpretation=version.interpretation or "",
        semantic_type=version.semantic_type or "",
        unit=version.unit or "",
        currency_attribute=version.currency_attribute or "",
        numeric_scale=version.numeric_scale,
        numeric_precision=version.numeric_precision,
        value_domain=_value_domain(version.value_domain_json or {}),
        optionality=_enum(Optionality, version.optionality, Optionality.OPTIONAL),
        optionality_condition=version.optionality_condition or "",
        is_cde=bool(version.is_cde),
        obligations=tuple(version.obligations_json or ()),
        sensitivity=_enum(Sensitivity, version.sensitivity, Sensitivity.INTERNAL),
        masking_policy=version.masking_policy or "",
        expected_behaviour=version.expected_behaviour or "",
        glossary_term=version.glossary_term or "",
        owner_id=version.owner_id or "",
    )


def dataset_declaration_of(version: Any, attributes: Any = ()) -> DatasetDeclaration:
    """A stored dataset version as Γ's input.

    ``name`` is the slug rather than the display name: controls are written
    against the name that appears in SQL, and a control saying
    ``CHECK End-of-day Positions`` does not parse.
    """
    return DatasetDeclaration(
        name=version.slug,
        slug=version.slug,
        description=version.description or "",
        purpose=version.purpose or "",
        shape=version.shape,
        domain_id=version.domain_id or "",
        owner_id=version.owner_id or "",
        steward_id=version.steward_id or "",
        custodian_id=version.custodian_id or "",
        criticality=_enum(Criticality, version.criticality, Criticality.TIER_4),
        grain=Grain.from_dict(version.grain_json) if version.grain_json else None,
        business_key=tuple(version.business_key_json or ()),
        temporality=_enum(Temporality, version.temporality, Temporality.SNAPSHOT),
        rhythm=Rhythm.from_dict(version.rhythm_json) if version.rhythm_json else None,
        authoritativeness=_enum(
            Authoritativeness, version.authoritativeness, Authoritativeness.UNKNOWN
        ),
        source_of_truth=version.source_of_truth_id or "",
        retention_days=version.retention_days,
        jurisdiction=version.jurisdiction or "",
        sensitivity=_enum(Sensitivity, version.sensitivity, Sensitivity.INTERNAL),
        lifecycle_state=version.lifecycle_state,
        tags=tuple(version.tags_json or ()),
        attributes=tuple(attribute_declaration_of(a) for a in attributes),
        # Provenance, so a generated control can answer "why does this exist?"
        # with a link rather than with a rule name.
        declared_by=getattr(version, "authored_by", "") or "",
        declared_at=str(getattr(version, "recorded_at", "") or ""),
        reference=version.dataset_id,
    )
