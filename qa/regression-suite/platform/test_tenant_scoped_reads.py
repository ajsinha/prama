"""A by-parent read must not cross an estate boundary.

QA round 2, `DB-201`, `DB-244`, `DB-245`, `DB-142`. Round 1 found this shape
once (`F-02`) and four methods were fixed. These were not, and the sweep in
`tests/security/test_tenant_isolation.py` could not see them, because it probes
methods whose *first* parameter is `tenant_id` — and none of these takes one at
all. The guard and the defect had the same blind spot, which is why a guard
written from the shape of the fix rather than the shape of the risk is worth
less than it looks.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.db import Database
from prama.db.temporal import Provenance

SHARED_PROPERTY = "prop-exposure-amount"


async def _attribute_in(uow, tenant_id: str, *, slug: str, name: str):
    """One estate's attribute, mapped onto a shared canonical property."""
    dataset, _ = await uow.datasets.create(
        tenant_id=tenant_id,
        name=f"Positions {slug}",
        slug=slug,
        provenance=Provenance(authored_by="user-1", reason="qa regression"),
    )
    return await uow.attributes.create(
        tenant_id=tenant_id,
        identity_fields={"dataset_id": dataset.id},
        name=name,
        concept_property_id=SHARED_PROPERTY,
    )


async def test_attributes_mapped_to_a_property_stay_inside_their_estate(
    estate: Database, two_tenants: tuple[str, str]
) -> None:
    """Two estates may map attributes onto the same canonical property.

    That is the normal case — a shared concept library is the whole point — so
    a property id is not a secret and must not be treated as one. Holding it
    cannot be sufficient to read another estate's attributes.
    """
    ours, theirs = two_tenants
    async with estate.unit_of_work() as uow:
        await _attribute_in(uow, ours, slug="ours", name="our_amount")
        await _attribute_in(uow, theirs, slug="theirs", name="their_amount")
        await uow.flush()

    async with estate.unit_of_work() as uow:
        mine = await uow.attributes.mapped_to_property(SHARED_PROPERTY, tenant_id=ours)

    assert [a.name for a in mine] == ["our_amount"]


async def test_the_shared_property_really_is_shared(
    estate: Database, two_tenants: tuple[str, str]
) -> None:
    """The counterfactual for the test above.

    If both estates did not genuinely map onto the same property id, the
    isolation assertion would pass for the wrong reason — there would be
    nothing to leak. This proves the leak was possible.
    """
    ours, theirs = two_tenants
    async with estate.unit_of_work() as uow:
        _, mine = await _attribute_in(uow, ours, slug="ours", name="our_amount")
        _, yours = await _attribute_in(uow, theirs, slug="theirs", name="their_amount")
        await uow.flush()
        assert mine.concept_property_id == yours.concept_property_id == SHARED_PROPERTY
