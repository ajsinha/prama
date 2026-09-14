"""Withdrawing an attestation requires saying why.

QA round 4, `UI-123`. `attestation_sign` validated the signer's name and, when
`supersedes` was set, checked the superseded attestation belonged to the
caller's estate (`UI-122`, which works). It never checked
`supersedes_because`, so an attestation could be superseded with an empty
reason and the row was written.

The catalogue's *Why* is the whole argument: **"an attestation withdrawn without
a reason is an audit trail with a hole in exactly the interesting place."** Every
other record in this system carries its justification — a control has `BECAUSE`,
an incident has its signals, a break has its explanation. The one record that
says "the thing I previously attested no longer stands" could be written with
nothing at all.

**How this was found, which is the reason it is worth a file of its own.** The
round-3 and round-4 harness measured it as `status_code != 303` — and both the
success path and the caught-refusal path redirect with 303, so the check could
never tell them apart. `UI-122` and `UI-123` looked identical under it: one was
a false failure and one was this. Repairing the harness to count rows separated
them, and the repair did not make `UI-123` pass — it made its failure mean
something.

**What a careless version of this test would assert.** A non-303 status, which
is the measurement that hid the defect in the first place. Or a flash message,
which the success path can also carry. The only answer that cannot be faked by a
redirect is whether a row exists.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from prama.core.config import Configuration
from prama.db import Database

PASSWORD = "correct-horse-battery-staple"
SIGNED = {
    "attester_name": "alice",
    "statement": "the estate stands as reported",
    "scope": "estate",
    "period_start": "2026-01-01",
    "period_end": "2026-01-31",
}


@pytest.fixture
async def console(
    qa_config: Configuration, estate: Database, two_tenants: tuple[str, str]
) -> AsyncIterator[httpx.AsyncClient]:
    """Signed in as an admin: this case is about the form, not about scopes."""
    from prama.api import create_app
    from prama.cli.principal import BUILTIN_ROLES

    ours, _ = two_tenants
    async with estate.unit_of_work() as uow:
        principal = uow.principals.create(tenant_id=ours, username="alice", display_name="Alice")
        uow.principals.set_password(principal, PASSWORD)
        principal.status = "active"
        await uow.flush()
        description, permissions = BUILTIN_ROLES["admin"]
        role = uow.roles.create(
            tenant_id=ours,
            name="admin",
            permissions=permissions,
            description=description,
            builtin=True,
        )
        await uow.flush()
        await uow.roles.grant(str(principal.id), str(role.id))
        await uow.flush()

    app = create_app(qa_config, database=estate)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        response = await http.post(
            "/sign-in", data={"username": "alice", "password": PASSWORD, "tenant": "acme-bank"}
        )
        assert response.status_code == 303, f"sign-in failed: {response.status_code}"
        yield http


async def count(estate: Database, tenant_id: str) -> int:
    """Every row ever signed, superseded ones included.

    `history`, not `current`. `current` filters `superseded_by IS NULL`, so a
    *successful* supersede leaves it unchanged — it cannot tell "the write was
    refused" from "the write happened and replaced the old row". That is the
    same shape as the `status_code != 303` measurement this file exists because
    of, reproduced in the test written to fix it.

    (An earlier draft called `for_tenant`, which does not exist at all. Two
    measurement mistakes in one helper, both from writing against a remembered
    interface instead of a read one.)
    """
    async with estate.unit_of_work() as uow:
        return len(await uow.attestations.history(tenant_id, "estate"))


@pytest.mark.parametrize("because", ["", "   "], ids=["empty", "whitespace"])
async def test_superseding_without_a_reason_writes_nothing(
    console: httpx.AsyncClient, estate: Database, two_tenants: tuple[str, str], because: str
) -> None:
    ours, _ = two_tenants
    await console.post("/attestations/new", data=SIGNED)
    before = await count(estate, ours)
    assert before == 1, "the first attestation was not created, so this proves nothing"

    async with estate.unit_of_work() as uow:
        first = (await uow.attestations.history(ours, "estate"))[0]

    response = await console.post(
        "/attestations/new",
        data={
            **SIGNED,
            "period_start": "2026-02-01",
            "period_end": "2026-02-28",
            "supersedes": str(first.id),
            "supersedes_because": because,
        },
    )
    after = await count(estate, ours)

    assert after == before, (
        f"an attestation superseded {first.id} with because={because!r} and the row was "
        f"written ({before} -> {after}). Status was {response.status_code} and location "
        f"{response.headers.get('location', '')!r} — both of which a successful sign also "
        "produces, which is how this went unnoticed."
    )


async def test_superseding_with_a_reason_still_works(
    console: httpx.AsyncClient, estate: Database, two_tenants: tuple[str, str]
) -> None:
    """The counterfactual to the refusal.

    Without this the file is satisfied by refusing every supersede, which would
    remove the capability rather than guard it.
    """
    ours, _ = two_tenants
    await console.post("/attestations/new", data=SIGNED)
    async with estate.unit_of_work() as uow:
        first = (await uow.attestations.history(ours, "estate"))[0]

    await console.post(
        "/attestations/new",
        data={
            **SIGNED,
            "period_start": "2026-02-01",
            "period_end": "2026-02-28",
            "supersedes": str(first.id),
            "supersedes_because": "the January figures were restated",
        },
    )

    assert await count(estate, ours) == 2, "a supersede with a reason was refused"


async def test_an_ordinary_attestation_needs_no_reason(
    console: httpx.AsyncClient, estate: Database, two_tenants: tuple[str, str]
) -> None:
    """`supersedes_because` is required only when something is superseded.

    The obvious over-correction is to demand it always, which would make every
    first attestation in an estate impossible.
    """
    ours, _ = two_tenants
    await console.post("/attestations/new", data=SIGNED)
    assert await count(estate, ours) == 1
