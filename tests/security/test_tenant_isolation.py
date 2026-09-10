"""W10.2 — that one estate cannot see another's anything.

Prama is sold to banks, and the question a bank's security review asks first is
not "is it encrypted" but "what stops tenant A reading tenant B". The answer has
to be a property of the code, demonstrated, rather than a claim.

Two kinds of test here, and the second is the one that matters:

* **Per-DAO.** Write into two estates, read as one, assert the other's rows are
  absent. Thorough but unfalsifiable as a whole: it only covers the methods
  somebody remembered to list.
* **By scanning.** Every tenant-scoped DAO is enumerated from the class
  hierarchy, and each is required to have been exercised above. A DAO added next
  year fails this file until somebody has thought about its isolation — which is
  the only version of this suite that stays true.

The web tier is checked the same way: a signed-in caller of one estate is given
another estate's identifiers, and must be told the row does not exist rather
than that it is forbidden. Which identifiers exist elsewhere is also not this
caller's business.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from prama.core.errors import NotFoundError
from prama.db import Database
from prama.evidence.record import GENESIS, EvidenceRecord
from prama.recon.classify import Break, BreakKind

pytestmark = pytest.mark.anyio

PQL = (
    "CHECK positions_eod.notional IS NOT NULL "
    "SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
)

#: DAOs exercised below. The scan at the bottom checks this list against what
#: actually exists, so it cannot quietly fall behind.
COVERED = {
    "PrincipalDao",
    "RoleDao",
    "ApiKeyDao",
    "ControlDao",
    "RejectionDao",
    "BreakDao",
    "AttestationDao",
    "DatasetDao",
    "AttributeDao",
}


@pytest.fixture
async def other_tenant(started_database: Database) -> str:
    async with started_database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug="rival-bank", display_name="Rival Bank")
        await uow.flush()
        return str(tenant.id)


class TestThePlatformTables:
    async def test_principals_are_not_visible_across_estates(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            uow.principals.create(tenant_id=other_tenant, username="theirs", display_name="Theirs")
            await uow.flush()
            assert await uow.principals.by_username(tenant_id, "theirs") is None
            assert await uow.principals.list_for_tenant(tenant_id) == []

    async def test_a_username_may_repeat_across_estates(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        """Two banks both employing an "alice" is ordinary. A global unique
        constraint would leak the existence of one estate's people into
        another's sign-up."""
        async with started_database.unit_of_work() as uow:
            uow.principals.create(tenant_id=tenant_id, username="alice", display_name="Ours")
            uow.principals.create(tenant_id=other_tenant, username="alice", display_name="Theirs")
            await uow.flush()
            mine = await uow.principals.by_username(tenant_id, "alice")
            theirs = await uow.principals.by_username(other_tenant, "alice")
        assert mine is not None and theirs is not None
        assert mine.id != theirs.id

    async def test_authentication_is_scoped_to_one_estate(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        """The credential test that matters: their password must not open our
        estate, even though the username is the same."""
        async with started_database.unit_of_work() as uow:
            principal = uow.principals.create(
                tenant_id=other_tenant, username="alice", display_name="Theirs"
            )
            uow.principals.set_password(principal, "their-long-password")
            await uow.flush()

        async with started_database.unit_of_work() as uow:
            assert (
                await uow.principals.authenticate(tenant_id, "alice", "their-long-password") is None
            )
            assert (
                await uow.principals.authenticate(other_tenant, "alice", "their-long-password")
                is not None
            )

    async def test_roles_do_not_cross(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            uow.roles.create(tenant_id=other_tenant, name="admin", permissions=["*"])
            await uow.flush()
            assert await uow.roles.by_name(tenant_id, "admin") is None

    async def test_api_keys_do_not_cross(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            principal = uow.principals.create(
                tenant_id=other_tenant, username="svc", display_name="Service"
            )
            await uow.flush()
            uow.api_keys.create(
                tenant_id=other_tenant,
                principal_id=str(principal.id),
                name="theirs",
                key_prefix="pk_theirs",
                key_hash="deadbeef",
                scopes=["control:read"],
            )
            await uow.flush()
            assert await uow.api_keys.list_for_tenant(tenant_id) == []


class TestTheEstate:
    async def test_datasets_do_not_cross(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        from prama.semantic.services.datasets import DatasetService

        async with started_database.unit_of_work() as uow:
            await DatasetService(uow).declare(
                tenant_id=other_tenant, name="Their Positions", description="theirs"
            )
            await uow.flush()
            assert await uow.datasets.list_current(tenant_id, limit=100) == []
            assert await uow.datasets.count_current(tenant_id) == 0

    async def test_controls_do_not_cross(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.controls.declare(tenant_id=other_tenant, identity="a", pql=PQL)
            await uow.flush()
            assert await uow.controls.live(tenant_id) == []
            assert await uow.controls.by_identity(tenant_id, "a") is None

    async def test_a_control_is_not_reachable_by_id_from_another_estate(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(tenant_id=other_tenant, identity="a", pql=PQL)
            await uow.flush()
            assert await uow.controls.by_control_id(tenant_id, str(control.id)) is None

    async def test_rejections_do_not_cross(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.rejections.record(
                tenant_id=other_tenant,
                identity="a",
                content_hash="ab",
                rejected_at="2026-09-09T00:00:00Z",
            )
            await uow.flush()
            assert await uow.rejections.for_tenant(tenant_id) == []
            assert not await uow.rejections.was_rejected(tenant_id, "a", "ab")


class TestEvidenceAndAttestation:
    async def test_the_ledger_does_not_cross(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(
                EvidenceRecord(
                    control_id="01THEIRS",
                    dataset="positions_eod",
                    verdict="fail",
                    metrics={"scanned_rows": 10.0, "violating_rows": 4.0},
                    finished_at="2026-09-10T06:00:00Z",
                ),
                tenant_id=other_tenant,
            )

        async with started_database.unit_of_work() as uow:
            assert await uow.evidence.count_for(tenant_id) == 0
            assert await uow.evidence.chain(tenant_id) == []
            assert await uow.evidence.latest_per_control(tenant_id) == {}

    async def test_each_estate_has_its_own_hash_chain(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        """Not merely filtered — chained separately. A shared chain would let
        one estate's record count be inferred from another's sequence numbers,
        and would make one estate's erasure break the other's verification."""
        for tenant in (tenant_id, other_tenant):
            async with started_database.unit_of_work() as uow:
                await uow.evidence.append(
                    EvidenceRecord(
                        control_id="01C",
                        dataset="d",
                        verdict="pass",
                        metrics={"scanned_rows": 1.0, "violating_rows": 0.0},
                        finished_at="2026-09-10T06:00:00Z",
                    ),
                    tenant_id=tenant,
                )
        async with started_database.unit_of_work() as uow:
            mine = await uow.evidence.chain(tenant_id)
            theirs = await uow.evidence.chain(other_tenant)
            assert (await uow.evidence.verify(tenant_id)).is_intact
            assert (await uow.evidence.verify(other_tenant)).is_intact
        assert len(mine) == len(theirs) == 1
        # Both are a genesis record: each estate's chain starts at its own
        # beginning rather than continuing the other's.
        assert mine[0].sequence == theirs[0].sequence == 0
        assert mine[0].previous_hash == theirs[0].previous_hash == GENESIS

    async def test_attestations_do_not_cross(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        from prama.report.attestation import Attestation, Coverage

        attestation = Attestation(
            attester_id="1",
            attester_name="Theirs",
            statement="reviewed",
            scope="s",
            period_start="2026-09-01",
            period_end="2026-09-30",
            coverage=Coverage(controls_in_scope=1, controls_run=1, passed=1, failed=0),
            evidence_root="ab" * 32,
            evidence_records=1,
            signed_at="2026-10-01T00:00:00Z",
            tenant_id=other_tenant,
        )
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(attestation, seal=attestation.seal(b"k"))
            await uow.flush()
            identifier = str(row.id)
            assert await uow.attestations.current(tenant_id) == []
            with pytest.raises(NotFoundError):
                await uow.attestations.in_tenant(identifier, tenant_id)

    async def test_breaks_do_not_cross(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        from decimal import Decimal

        found = Break(
            key="ACC1",
            kind=BreakKind.GENUINE,
            left=Decimal("1"),
            right=Decimal("2"),
            because="x",
        )
        async with started_database.unit_of_work() as uow:
            await uow.breaks.observe(
                [found], tenant_id=other_tenant, definition="r", when="2026-09-01"
            )
            await uow.flush()
            assert await uow.breaks.for_definition(tenant_id, "r") == []
            assert await uow.breaks.definitions(tenant_id) == []


class TestTheWebTier:
    """A signed-in caller of one estate, handed another estate's identifiers."""

    async def test_another_estates_attestation_reads_as_absent(
        self, ui: httpx.AsyncClient, started_database: Database, other_tenant: str
    ) -> None:
        from prama.report.attestation import Attestation, Coverage

        attestation = Attestation(
            attester_id="1",
            attester_name="Theirs",
            statement="reviewed",
            scope="Their book",
            period_start="2026-09-01",
            period_end="2026-09-30",
            coverage=Coverage(controls_in_scope=1, controls_run=1, passed=1, failed=0),
            evidence_root="ab" * 32,
            evidence_records=1,
            signed_at="2026-10-01T00:00:00Z",
            tenant_id=other_tenant,
        )
        async with started_database.unit_of_work() as uow:
            row = await uow.attestations.sign(attestation, seal=attestation.seal(b"k"))
            identifier = str(row.id)

        for path in (f"/attestations/{identifier}", f"/attestations/{identifier}/pack"):
            response = await ui.get(path)
            assert response.status_code == 404, path
            assert "Their book" not in response.text

    async def test_another_estates_incident_reads_as_absent(
        self, ui: httpx.AsyncClient, started_database: Database, other_tenant: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(
                EvidenceRecord(
                    control_id="01THEIRCONTROL",
                    dataset="their_secret_dataset",
                    verdict="fail",
                    metrics={"scanned_rows": 10.0, "violating_rows": 4.0},
                    finished_at="2026-09-10T06:00:00Z",
                ),
                tenant_id=other_tenant,
            )

        response = await ui.get("/incidents/01THEIRCONTROL")
        assert response.status_code == 404
        assert "their_secret_dataset" not in response.text

    async def test_another_estates_break_cannot_be_dispositioned(
        self, ui: httpx.AsyncClient, started_database: Database, other_tenant: str
    ) -> None:
        from decimal import Decimal

        found = Break(
            key="THEIRS",
            kind=BreakKind.GENUINE,
            left=Decimal("1"),
            right=Decimal("2"),
            because="x",
        )
        async with started_database.unit_of_work() as uow:
            await uow.breaks.observe(
                [found], tenant_id=other_tenant, definition="r", when="2026-09-01"
            )
            await uow.flush()
            [row] = await uow.breaks.for_definition(other_tenant, "r")
            identifier = str(row.id)

        await ui.post(
            f"/reconciliation/breaks/{identifier}/accept",
            data={"definition": "r", "reason": "not mine"},
        )
        async with started_database.unit_of_work() as uow:
            unchanged = await uow.breaks.require(identifier)
        assert unchanged.state == "open"

    async def test_no_screen_shows_another_estates_rows(
        self, ui: httpx.AsyncClient, started_database: Database, other_tenant: str
    ) -> None:
        """The sweep. Every list screen, against an estate that has one of
        everything, asserting none of it appears."""
        from prama.semantic.services.datasets import DatasetService

        async with started_database.unit_of_work() as uow:
            await DatasetService(uow).declare(
                tenant_id=other_tenant,
                name="Their Secret Book",
                description="theirs alone",
            )
            await uow.controls.declare(tenant_id=other_tenant, identity="theirs", pql=PQL)
            await uow.evidence.append(
                EvidenceRecord(
                    control_id="01THEIRS",
                    dataset="their_secret_dataset",
                    verdict="fail",
                    metrics={"scanned_rows": 10.0, "violating_rows": 4.0},
                    finished_at="2026-09-10T06:00:00Z",
                ),
                tenant_id=other_tenant,
            )

        leaks = ("Their Secret Book", "their_secret_dataset", "01THEIRS", "theirs")
        for path in (
            "/estate",
            "/estate/gaps",
            "/declarations",
            "/controls",
            "/proposals",
            "/incidents",
            "/reconciliation",
            "/scorecards",
            "/evidence",
            "/attestations",
            "/reports",
        ):
            body = (await ui.get(path)).text
            for leak in leaks:
                assert leak not in body, f"{path} leaked {leak!r}"


def _tenant_scoped_methods() -> list[tuple[str, str]]:
    """Every DAO method that takes a ``tenant_id`` and needs nothing else.

    Scoping in this codebase is a *convention* — pass ``tenant_id`` — rather
    than a type: only three DAOs inherit ``TenantScopedDao`` and the other
    twenty take the tenant as an argument. A scan keyed on the base class
    therefore covered three of twenty-three while claiming to cover everything,
    which is worse than not scanning at all.

    So the signature is what is scanned. A method that accepts a tenant is a
    method that answers *for* a tenant, and every one of them must answer
    "nothing" for a tenant that owns nothing.
    """
    import inspect

    import prama.db.dao as package
    from prama.db.dao.base import Dao

    out: list[tuple[str, str]] = []
    for class_name in dir(package):
        candidate = getattr(package, class_name)
        if not isinstance(candidate, type) or not issubclass(candidate, Dao):
            continue
        for method_name, method in inspect.getmembers(candidate, inspect.isfunction):
            if method_name.startswith("_"):
                continue
            try:
                signature = inspect.signature(method)
            except (TypeError, ValueError):  # pragma: no cover - builtins
                continue
            parameters = list(signature.parameters.values())[1:]  # drop self
            if not parameters or parameters[0].name != "tenant_id":
                continue
            # Only those callable with the tenant alone: anything needing a
            # dataset name or an identifier is exercised by a bespoke test
            # above, because inventing arguments here would test nothing.
            if any(
                p.default is inspect.Parameter.empty
                and p.kind
                in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
                for p in parameters[1:]
            ):
                continue
            out.append((class_name, method_name))
    return sorted(out)


#: Verbs that write. Called with a tenant to put something *in* it rather than
#: to read from it, so "returns nothing for an empty estate" is not a property
#: they can have. Matched by name because the alternative — listing every write
#: method by hand — is the enumeration this scan exists to avoid.
WRITE_VERBS = frozenset(
    {"create", "record", "append", "declare", "sign", "observe", "put", "start", "add"}
)


class TestEveryTenantAwareReadIsScoped:
    """The sweep that does not depend on anyone remembering.

    For each DAO method that takes a tenant and nothing else: fill one estate,
    ask the *other* estate, and require the answer to be empty. A method that
    forgot its ``WHERE tenant_id`` fails here without anybody having written a
    test for that method.
    """

    async def test_the_scan_finds_a_realistic_number_of_methods(self) -> None:
        """Guards the guard. A scan that silently matched nothing would pass
        this whole class while checking not one query."""
        found = _tenant_scoped_methods()
        assert len(found) >= 15, f"the scan found only {len(found)}: {found}"
        assert len({name for name, _ in found}) >= 8

    async def test_an_empty_estate_sees_nothing_anywhere(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        from prama.semantic.services.datasets import DatasetService

        # One of everything, in the *other* estate.
        async with started_database.unit_of_work() as uow:
            await DatasetService(uow).declare(
                tenant_id=other_tenant, name="Their Book", description="theirs"
            )
            their_control, _ = await uow.controls.declare(
                tenant_id=other_tenant, identity="t", pql=PQL
            )
            # Activated, not merely declared. A proposal is invisible to
            # `live()` whatever the tenant filter says, so leaving it as one
            # would make this probe pass against a DAO with no filter at all —
            # which is exactly what it did before somebody checked.
            await uow.controls.activate(str(their_control.id), approved_by="them")
            await uow.rejections.record(
                tenant_id=other_tenant,
                identity="r",
                content_hash="ab",
                rejected_at="2026-09-09T00:00:00Z",
            )
            uow.principals.create(tenant_id=other_tenant, username="theirs", display_name="T")
            uow.roles.create(tenant_id=other_tenant, name="admin", permissions=["*"])
            await uow.flush()
        async with started_database.unit_of_work() as uow:
            await uow.evidence.append(
                EvidenceRecord(
                    control_id="01T",
                    dataset="d",
                    verdict="fail",
                    metrics={"scanned_rows": 1.0, "violating_rows": 1.0},
                    finished_at="2026-09-10T06:00:00Z",
                ),
                tenant_id=other_tenant,
            )

        # What only the other estate has. A result is a leak if it carries one
        # of these, not merely if it is truthy: an empty chain's genesis hash
        # and a zero-record verification are truthful "nothing here" answers
        # that happen not to be falsy.
        markers = ("Their Book", "01T", "theirs", "admin", other_tenant)

        empty: list[str] = []
        async with started_database.unit_of_work() as uow:
            for class_name, method_name in _tenant_scoped_methods():
                if method_name in WRITE_VERBS:
                    continue
                dao = _dao_for(uow, class_name)
                if dao is None:
                    continue
                # By keyword: some of these declare tenant_id keyword-only.
                result = getattr(dao, method_name)(tenant_id=tenant_id)
                if hasattr(result, "__await__"):
                    result = await result
                complaint = _leaks(result, markers)
                if complaint:
                    empty.append(f"{class_name}.{method_name} {complaint}")

        assert not empty, "these answered for an estate that owns nothing:\n" + "\n".join(empty)


def _leaks(result: Any, markers: tuple[str, ...]) -> str:
    """What is wrong with this answer, or "" if nothing is.

    Two separate properties. A collection answering for an estate that owns
    nothing must be empty — a non-empty one is a missing ``WHERE``. Anything
    else is checked for the other estate's markers, because a scalar summary
    that mentions their dataset has leaked it just as surely as a list would.
    """
    if isinstance(result, (list, tuple, set)):
        return f"returned {len(result)} row(s): {result!r}" if result else ""
    if isinstance(result, dict):
        return f"returned {len(result)} entr(ies): {result!r}" if result else ""
    if isinstance(result, bool):
        return "returned True" if result else ""
    if isinstance(result, int):
        return f"counted {result}" if result else ""
    rendered = repr(result)
    found = [marker for marker in markers if marker in rendered]
    return f"mentioned {found}: {rendered[:200]}" if found else ""


def _dao_for(uow: Any, class_name: str) -> Any:
    """The unit-of-work property exposing this DAO, if it exposes one."""
    for attribute in dir(type(uow)):
        if attribute.startswith("_"):
            continue
        try:
            candidate = getattr(uow, attribute)
        except Exception:  # pragma: no cover - a property that needs more setup
            continue
        if type(candidate).__name__ == class_name:
            return candidate
    return None


class TestTheSuiteCannotFallBehind:
    def test_every_tenant_scoped_dao_is_covered(self) -> None:
        """The test that makes this file mean something.

        A per-DAO suite only covers what somebody remembered to list. This
        enumerates the tenant-scoped DAOs from the class hierarchy and fails
        when one has not been thought about — so a DAO added next year fails
        here until it has been.
        """
        import prama.db.dao as dao_package
        from prama.db.dao.base import TenantScopedDao

        scoped = {
            name
            for name in dir(dao_package)
            if isinstance(getattr(dao_package, name), type)
            and issubclass(getattr(dao_package, name), TenantScopedDao)
            and getattr(dao_package, name) is not TenantScopedDao
        }
        missing = scoped - COVERED
        assert not missing, (
            f"tenant-scoped DAOs with no isolation test: {sorted(missing)}. "
            "Add one above and list it in COVERED."
        )
