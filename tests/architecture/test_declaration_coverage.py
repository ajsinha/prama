"""The declaration view may not drift from the declaration.

``prama.derive.declaration`` is a plain, database-free view of
``SemDatasetVersion`` and ``SemAttributeVersion``. The generator needs one,
because Γ must be a pure function and ``prama.derive`` may not import
SQLAlchemy — but a second copy of a schema is exactly the thing that drifts
silently and in the flattering direction.

So the copy is audited. Add a control-generating column to the model without
adding it to the view, and this fails: not because the code would break, but
because it would quietly stop generating a control for something a business
owner had declared, and nobody would notice until an audit asked why the field
was not being checked.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

from prama.db.models.semantic import SemAttributeVersion, SemDatasetVersion
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration

#: Columns that exist for storage or audit rather than for meaning. Each one is
#: listed with why it cannot generate a control, so removing something from
#: this list is a deliberate act rather than a convenience.
NOT_DECLARATIONS: dict[str, str] = {
    "id": "the row's identity",
    "dataset_id": "a foreign key; carried as `reference`",
    "attribute_id": "a foreign key",
    "tenant_id": "isolation, not meaning",
    "recorded_at": "bitemporal bookkeeping; carried as `declared_at`",
    "recorded_by": "bitemporal bookkeeping; carried as `declared_by`",
    "superseded_at": "bitemporal bookkeeping",
    "supersedes_id": "bitemporal bookkeeping",
    "change_reason": "why the declaration changed, not what it says",
    "change_kind": "amend or correct; a property of the edit",
    "created_at": "storage",
    "ordinal": "column order in the source, which no control depends on",
    "concept_property_id": "a link to the concept model, not a rule",
    "version": "which revision of the declaration this is",
    "authored_by": "who wrote the revision; carried as `declared_by`",
    "approved_by": "who approved it, which governs whether it applies, not what it says",
    "approved_at": "when it was approved",
    # These two are genuinely close to being declarations, and the reason they
    # are not is worth stating. They say *when a declaration applies*, not what
    # it declares. Choosing which version of a declaration to generate from is
    # the caller's decision — a view represents exactly one version — so
    # carrying them here would put the same choice in two places.
    "valid_from": "the period the declaration applies to; the caller selects the version",
    "valid_to": "the period the declaration applies to; the caller selects the version",
}


def columns_of(model: type) -> set[str]:
    return {column.key for column in model.__table__.columns}


def fields_of(view: type) -> set[str]:
    return {field.name for field in dataclasses.fields(view)}


def normalise(column: str) -> set[str]:
    """The field names a column could reasonably be carried as.

    ``grain_json`` becomes ``grain``, ``source_of_truth_id`` becomes
    ``source_of_truth``, ``obligations_json`` becomes ``obligations``. The view
    is allowed to drop the storage suffix; it is not allowed to drop the field.
    """
    candidates = {column}
    for suffix in ("_json", "_id"):
        if column.endswith(suffix):
            candidates.add(column[: -len(suffix)])
    return candidates


def test_every_dataset_declaration_column_reaches_the_generator() -> None:
    missing = {
        column
        for column in columns_of(SemDatasetVersion) - set(NOT_DECLARATIONS)
        if not (normalise(column) & fields_of(DatasetDeclaration))
    }
    assert not missing, (
        f"SemDatasetVersion declares {sorted(missing)}, which the generator cannot "
        f"see. Either add the field to DatasetDeclaration so it can generate a "
        f"control, or add it to NOT_DECLARATIONS with the reason it cannot."
    )


def test_every_attribute_declaration_column_reaches_the_generator() -> None:
    missing = {
        column
        for column in columns_of(SemAttributeVersion) - set(NOT_DECLARATIONS)
        if not (normalise(column) & fields_of(AttributeDeclaration))
    }
    assert not missing, (
        f"SemAttributeVersion declares {sorted(missing)}, which the generator cannot "
        f"see. Either add the field to AttributeDeclaration, or add it to "
        f"NOT_DECLARATIONS with the reason it cannot generate a control."
    )


def test_the_view_invents_nothing_the_model_does_not_hold() -> None:
    """Drift runs both ways. A field only the view has is a declaration nobody
    can make and no UI will ever collect, so a control depending on it would
    never be generated in production and would pass every test here."""
    carried = {"attributes", "declared_by", "declared_at", "reference"}
    columns = {c for column in columns_of(SemDatasetVersion) for c in normalise(column)}
    invented = fields_of(DatasetDeclaration) - columns - carried
    assert not invented, (
        f"DatasetDeclaration has {sorted(invented)} with nothing behind it in the "
        f"schema. Nothing can ever set it, so any control derived from it will only "
        f"ever appear in a test."
    )


def test_the_attribute_view_invents_nothing_either() -> None:
    columns = {c for column in columns_of(SemAttributeVersion) for c in normalise(column)}
    invented = fields_of(AttributeDeclaration) - columns
    assert not invented, f"AttributeDeclaration has {sorted(invented)} with nothing behind it"


def test_the_view_can_be_built_from_the_columns_it_claims_to_mirror() -> None:
    """The audit above compares names. This one proves the constructor works,
    because a mapping that type-checks and raises on real input is no better
    than no mapping."""
    dataset = DatasetDeclaration.from_row(
        {
            "name": "positions",
            "slug": "pos",
            "criticality": 1,
            "grain_json": {"attributes": ["account_id"], "statement": "one per account"},
            "rhythm_json": {"frequency": "daily", "arrival_by": "06:30"},
            "authoritativeness": "replica",
            "source_of_truth_id": "DS02",
            "temporality": "as_of_dated",
            "business_key_json": ["account_id"],
            "tags_json": ["regulatory"],
        },
        (
            {
                "name": "lei",
                "semantic_type": "lei",
                "is_cde": 1,
                "optionality": "mandatory",
                "obligations_json": ["FR Y-14Q"],
                "sensitivity": "confidential",
                "value_domain_json": {"kind": "free_text"},
            },
        ),
    )
    assert dataset.grain is not None
    assert dataset.rhythm is not None
    assert dataset.is_replica
    assert dataset.source_of_truth == "DS02"
    assert dataset.cdes[0].name == "lei"
    assert dataset.obligations == ("FR Y-14Q",)
