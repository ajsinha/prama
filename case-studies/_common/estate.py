"""Declaring an estate the way a business owner would.

Every dataset here is described in business terms — what one row represents,
how often it arrives, how much a defect matters — and *nothing* is written in
SQL. That is the claim these studies exist to test: the controls come from the
declaration, not from somebody who already knew what to check.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.semantic.services import DatasetService
from prama.semantic.values import (
    Frequency,
    Grain,
    Optionality,
    Rhythm,
    ValueDomain,
    ValueDomainKind,
)


@dataclasses.dataclass(frozen=True, slots=True)
class Attribute:
    """One field, described rather than typed."""

    name: str
    definition: str
    #: A semantic type drives a validator: ``isin``, ``lei``, ``currency``.
    #: This is what turns "it is an ISIN" into a checksum control.
    semantic_type: str = ""
    unit: str = ""
    mandatory: bool = False
    is_cde: bool = False
    #: A closed set of permitted values, when there is one.
    codelist: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    currency_attribute: str = ""
    obligations: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class Dataset:
    """A dataset as its owner would describe it.

    There is no separate "physical name" field, deliberately. Prama derives the
    identifier a control is written against from the business name, and the
    generators name their tables and views to match. A study that carried both
    would be carrying a mapping — and a mapping is the thing that drifts.
    """

    name: str
    description: str
    #: What one row represents, in the owner's own words. The single most
    #: valuable sentence in the whole study: it becomes uniqueness,
    #: duplication and completeness controls, and it is quoted back in every
    #: one of them.
    grain_statement: str
    grain: tuple[str, ...]
    criticality: int
    shape: str = "table"
    attributes: tuple[Attribute, ...] = ()
    arrival_by: str = ""
    frequency: str = "daily"
    obligations: tuple[str, ...] = ()


def _domain(attribute: Attribute) -> ValueDomain:
    if attribute.codelist:
        return ValueDomain(
            kind=ValueDomainKind.CODELIST, allowed_values=tuple(attribute.codelist)
        )
    if attribute.minimum is not None or attribute.maximum is not None:
        return ValueDomain(
            kind=ValueDomainKind.RANGE,
            minimum=attribute.minimum,
            maximum=attribute.maximum,
        )
    return ValueDomain()


async def declare_estate(
    uow: Any, tenant_id: str, datasets: list[Dataset], *, author: str, approver: str
) -> dict[str, str]:
    """Record every declaration, and return the dataset ids by slug."""
    service = DatasetService(uow)
    ids: dict[str, str] = {}
    for dataset in datasets:
        _, version = await service.declare(
            tenant_id=tenant_id,
            name=dataset.name,
            description=dataset.description,
            criticality=dataset.criticality,
            shape=dataset.shape,
            grain=(
                Grain(attributes=dataset.grain, statement=dataset.grain_statement)
                if dataset.grain
                else None
            ),
            rhythm=(
                Rhythm(
                    frequency=Frequency(dataset.frequency),
                    arrival_by=dataset.arrival_by or None,
                )
                if dataset.arrival_by
                else None
            ),
            tags=list(dataset.obligations),
            authored_by=author,
            approved_by=approver,
        )
        ids[version.slug] = str(version.dataset_id)

        for attribute in dataset.attributes:
            # ``**extra`` lands on the ORM columns, so these are column names
            # rather than the value objects the service takes for a dataset.
            await service.declare_attribute(
                tenant_id=tenant_id,
                dataset_id=str(version.dataset_id),
                name=attribute.name,
                definition=attribute.definition,
                semantic_type=attribute.semantic_type or None,
                is_cde=attribute.is_cde,
                obligations=list(attribute.obligations),
                authored_by=author,
                unit=attribute.unit or None,
                currency_attribute=attribute.currency_attribute or None,
                value_domain_json=_domain(attribute).to_dict(),
                optionality=(
                    Optionality.MANDATORY.value
                    if attribute.mandatory
                    else Optionality.OPTIONAL.value
                ),
            )
    return ids
