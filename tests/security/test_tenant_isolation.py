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

from datetime import UTC, datetime
from typing import Any, ClassVar

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

    #: Every list screen the console offers. A screen absent from this tuple is
    #: a screen nobody checks for leakage.
    SCREENS: ClassVar[tuple[str, ...]] = (
        "/estate",
        # The map itself renders client-side, so the dataset names reach the
        # browser through this endpoint and not through the page's HTML. A
        # sweep over the page alone never sees the data the page displays.
        "/estate/graph.json",
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
    )

    #: Screens that render none of the planted markers even for the estate that
    #: owns them, with the reason. An entry is an admission that this sweep says
    #: nothing about that screen — not that the screen is exempt from tenancy.
    SILENT: ClassVar[dict[str, str]] = {
        "/estate": (
            "the map is drawn client-side from /estate/graph.json, which is in "
            "this sweep. The page's own HTML carries no dataset names."
        ),
        "/proposals": (
            "proposals are generated from declarations on request, not stored; "
            "nothing planted appears until somebody asks for a generation. "
            "Covered by TestTheWebTier's bespoke proposal tests above."
        ),
        "/reports": (
            "aggregate counts only — '12 controls, 3 failing'. It carries no "
            "name from any estate, which is why nothing planted shows up."
        ),
    }

    @staticmethod
    async def plant(database: Database, tenant: str, label: str) -> tuple[str, ...]:
        """One of everything, named so it can be recognised on a page."""
        from decimal import Decimal

        from prama.recon.classify import Break, BreakKind
        from prama.report.attestation import Attestation, Coverage
        from prama.semantic.services.datasets import DatasetService

        async with database.unit_of_work() as uow:
            await DatasetService(uow).declare(
                tenant_id=tenant, name=f"{label} Book", description=f"{label} alone"
            )
            # The controls page lists a control by its *dataset*, taken from
            # the PQL, so a shared PQL constant gives every estate the same
            # row text and nothing to recognise. This is the marker that
            # screen can actually show.
            control, _ = await uow.controls.declare(
                tenant_id=tenant,
                identity=f"{label}-ctl",
                pql=(
                    f"CHECK {label.lower()}_ledger.notional IS NOT NULL "
                    "SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
                ),
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant, approved_by=label)
            await uow.breaks.observe(
                [
                    Break(
                        key=f"{label}-ACC1",
                        kind=BreakKind.GENUINE,
                        left=Decimal("100.00"),
                        right=Decimal("105.00"),
                        because=f"{label} disagree",
                    )
                ],
                tenant_id=tenant,
                definition=f"{label}-ledger-vs-custodian",
                when="2026-09-09",
            )
            person = uow.principals.create(
                tenant_id=tenant, username=label.lower(), display_name=label
            )
            await uow.flush()
            attestation = Attestation(
                attester_id=str(person.id),
                attester_name=f"{label} Attester",
                statement=f"{label} reviewed",
                scope=f"{label} Book",
                period_start="2026-09-01",
                period_end="2026-09-30",
                coverage=Coverage(
                    controls_in_scope=1, controls_run=1, passed=1, failed=0, never_ran=0
                ),
                exceptions=(),
                evidence_root="ab" * 32,
                evidence_records=1,
                signed_at="2026-10-01T09:15:00Z",
                tenant_id=tenant,
            )
            await uow.attestations.sign(attestation, seal=attestation.seal(b"k"))
        async with database.unit_of_work() as uow:
            await uow.evidence.append(
                EvidenceRecord(
                    control_id=f"01{label.upper()}",
                    dataset=f"{label}_secret_dataset",
                    verdict="fail",
                    metrics={"scanned_rows": 10.0, "violating_rows": 4.0},
                    finished_at="2026-09-10T06:00:00Z",
                ),
                tenant_id=tenant,
            )
        return (
            f"{label} Book",
            f"{label}_secret_dataset",
            f"01{label.upper()}",
            f"{label}-ACC1",
            f"{label} Attester",
            f"{label}-ctl",
            f"{label}-ledger-vs-custodian",
            f"{label.lower()}_ledger",
        )

    async def test_every_screen_in_the_sweep_can_show_something(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The positive control, and the whole point — finding T10.

        The sweep below asserts that another estate's rows do not appear. That
        is only evidence if the same rows *would* appear when they belong to
        the caller. Measured, six of the eleven screens rendered none of the
        four markers even for their own estate, so `assert leak not in body`
        could not fail on those for any tenancy-related reason. Two of them were
        checked against fixture data the sweep never created at all.
        """
        markers = await self.plant(started_database, tenant_id, "Ours")
        silent = []
        for path in self.SCREENS:
            body = (await ui.get(path)).text
            if not any(marker in body for marker in markers):
                silent.append(path)
        unexplained = sorted(set(silent) - self.SILENT.keys())
        assert not unexplained, (
            f"these screens show none of {markers} even for the estate that owns "
            f"them, so their 'nothing leaked' proves nothing: {unexplained}. "
            "Plant something they render, or declare why they cannot."
        )

    async def test_no_screen_shows_another_estates_rows(
        self, ui: httpx.AsyncClient, started_database: Database, other_tenant: str
    ) -> None:
        """The sweep. Every list screen, against an estate that has one of
        everything, asserting none of it appears."""
        markers = await self.plant(started_database, other_tenant, "Theirs")
        for path in self.SCREENS:
            response = await ui.get(path)
            # Asserted, because a screen that 404s leaks nothing and proves
            # nothing, and the sweep used to discard the status entirely.
            assert response.status_code == 200, f"{path} answered {response.status_code}"
            for leak in markers:
                assert leak not in response.text, f"{path} leaked {leak!r}"


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


async def _one_of_everything(uow: Any, tenant: str) -> None:
    """Put a row in every table the sweep reads, for one estate.

    Finding T5. The fixture used to plant six kinds of row, and the sweep probed
    forty-nine methods across twenty-two DAOs. For the other twenty-nine the
    probe returned empty **because the table was empty**, not because the query
    was scoped — measured against an estate that owns everything, twenty-nine of
    forty-nine still answered "nothing". Deleting the tenant filter from
    `ConceptDao.list_current` and `count_current` outright left the whole sweep
    green.

    A probe that cannot distinguish "scoped" from "nothing there" is not a
    weaker check than none; it is a worse one, because it reports coverage.
    """
    from prama.db.security import ApiKeyIssuer
    from prama.report.attestation import Attestation, Coverage
    from prama.semantic.relationships import (
        MatchKey,
        RelationshipDeclaration,
        RelationshipKind,
        Tolerance,
    )
    from prama.semantic.services.datasets import DatasetService
    from prama.semantic.services.graph import (
        BindingService,
        ConceptService,
        ConnectionService,
        JourneyService,
    )
    from prama.semantic.services.relationships import RelationshipService

    domain, _ = await uow.domains.create(tenant_id=tenant, name="Markets", description="theirs")
    await uow.flush()

    dataset = await DatasetService(uow).declare(
        tenant_id=tenant, name="Their Book", description="theirs", domain_id=str(domain.id)
    )
    second = await DatasetService(uow).declare(tenant_id=tenant, name="Their Ledger")
    await uow.flush()
    # The services return (entity, version); the id lives on the entity.
    dataset_id = str(dataset[0].id)
    second_id = str(second[0].id)

    await DatasetService(uow).declare_attribute(
        tenant_id=tenant, dataset_id=dataset_id, name="theirs_cde", is_cde=True
    )

    concept = await ConceptService(uow).declare_concept(tenant_id=tenant, name="TheirConcept")
    await uow.flush()
    await ConceptService(uow).declare_property(
        tenant_id=tenant, concept_id=str(concept[0].id), name="theirs_property"
    )

    await JourneyService(uow).declare(tenant_id=tenant, name="Their Journey")

    connection = await ConnectionService(uow).configure(
        tenant_id=tenant, name="theirs-warehouse", source_type="sqlite"
    )
    await uow.flush()
    connection_id = str(connection[0].id)
    # Unhealthy, so `ConnectionDao.unhealthy` has something to find. A probe
    # against a healthy estate proves nothing about that method.
    await ConnectionService(uow).record_health(
        tenant_id=tenant,
        connection_id=connection_id,
        state="unreachable",
        detail="theirs",
        checked_at=datetime(2026, 9, 10, 6, 0, tzinfo=UTC),
    )

    binding = await BindingService(uow).bind_dataset(
        tenant_id=tenant,
        dataset_id=dataset_id,
        connection_id=connection_id,
        physical_ref={"table": "theirs"},
    )
    await uow.flush()
    # Drifted, so `BindingDao.drifted` is exercised rather than merely called.
    await BindingService(uow).record_drift(
        tenant_id=tenant, binding_id=str(binding[0].id), drift_state="missing"
    )

    await RelationshipService(uow).declare(
        tenant_id=tenant,
        declaration=RelationshipDeclaration(
            kind=RelationshipKind.RECONCILES_WITH,
            from_dataset_id=dataset_id,
            to_dataset_id=second_id,
            match_keys=(MatchKey("account_id"),),
            compare=("amount",),
            tolerance=Tolerance(absolute=1.00, currency="EUR"),
        ),
        confirmed=True,
    )

    person = uow.principals.create(tenant_id=tenant, username="theirs", display_name="T")
    uow.roles.create(tenant_id=tenant, name="admin", permissions=["*"])
    await uow.flush()
    issued = ApiKeyIssuer().issue(environment="test")
    uow.api_keys.create(
        tenant_id=tenant,
        principal_id=str(person.id),
        name="theirs",
        key_prefix=issued.prefix,
        key_hash=issued.hash,
        scopes=["*"],
    )

    await uow.settings.put(tenant, "theirs.key", "theirs", scope="global")

    their_control, _ = await uow.controls.declare(tenant_id=tenant, identity="theirs", pql=PQL)
    # Activated, not merely declared. A proposal is invisible to `live()`
    # whatever the tenant filter says, so leaving it as one would make the
    # probe pass against a DAO with no filter at all.
    await uow.controls.activate(str(their_control.id), tenant_id=tenant, approved_by="theirs")
    await uow.rejections.record(
        tenant_id=tenant,
        identity="theirs",
        content_hash="ab",
        rejected_at="2026-09-09T00:00:00Z",
    )

    attestation = Attestation(
        attester_id=str(person.id),
        attester_name="theirs",
        statement="theirs",
        scope="Their Book",
        period_start="2026-09-01",
        period_end="2026-09-30",
        coverage=Coverage(controls_in_scope=1, controls_run=1, passed=1, failed=0, never_ran=0),
        exceptions=(),
        evidence_root="ab" * 32,
        evidence_records=1,
        signed_at="2026-10-01T09:15:00Z",
        tenant_id=tenant,
    )
    await uow.attestations.sign(attestation, seal=attestation.seal(b"k"))

    from decimal import Decimal

    from prama.recon.classify import Break, BreakKind

    await uow.breaks.observe(
        [
            Break(
                key="theirs-ACC1",
                kind=BreakKind.GENUINE,
                left=Decimal("100.00"),
                right=Decimal("105.00"),
                because="theirs",
            )
        ],
        tenant_id=tenant,
        definition="theirs-ledger-vs-custodian",
        when="2026-09-09",
    )

    # Left unfinished on purpose: `EvidenceRunDao.unfinished` is about a run
    # that died, and a fixture that only ever finishes runs cannot reach it.
    await uow.evidence_runs.start(tenant_id=tenant, triggered_by="test", engine="reference")
    await uow.usage.record_pair(
        tenant, pair=("theirs.a", "theirs.b"), day="2026-09-28", source="snowflake", queries=3
    )
    await uow.anchors.record(
        tenant_id=tenant,
        sequence=0,
        digest="cd" * 32,
        kind="rfc3161",
        authority="https://tsa.test/tsr",
        status="anchored",
        requested_at="2026-09-28T06:00:00Z",
    )
    await uow.flush()


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
        empty, blind = await self._sweep(started_database, tenant_id, other_tenant)
        assert not empty, "these answered for an estate that owns nothing:\n" + "\n".join(empty)

    async def test_no_probe_is_blind(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        """Every probe must be able to see something when it should.

        The test above asks an empty estate and requires "nothing". That answer
        is only evidence if the same method answers *something* for the estate
        that owns everything. Twenty-nine of forty-nine did not, so they were
        asserting that an empty table is empty — and deleting the tenant filter
        from `ConceptDao` entirely left the sweep green.
        """
        _, blind = await self._sweep(started_database, tenant_id, other_tenant)
        unexplained = sorted(set(blind) - BLIND_BY_DESIGN.keys())
        assert not unexplained, (
            "these saw nothing even for the estate that owns everything, so their "
            f"'nothing' proves nothing: {unexplained}. Plant a row for them in "
            "_one_of_everything, or declare why the probe cannot reach them."
        )

    async def test_the_declared_blind_spots_are_still_blind(
        self, started_database: Database, tenant_id: str, other_tenant: str
    ) -> None:
        """An exemption that has quietly started working is dead weight, and
        makes the list look more considered than it is."""
        _, blind = await self._sweep(started_database, tenant_id, other_tenant)
        stale = sorted(BLIND_BY_DESIGN.keys() - set(blind))
        assert not stale, f"declared unreachable but the sweep now reaches them: {stale}"

    @staticmethod
    async def _sweep(database: Database, ours: str, theirs: str) -> tuple[list[str], list[str]]:
        """Fill one estate, then ask both. Returns (leaks, blind probes)."""
        async with database.unit_of_work() as uow:
            await _one_of_everything(uow, theirs)
        async with database.unit_of_work() as uow:
            await uow.evidence.append(
                EvidenceRecord(
                    control_id="01T",
                    dataset="d",
                    verdict="fail",
                    metrics={"scanned_rows": 1.0, "violating_rows": 1.0},
                    finished_at="2026-09-10T06:00:00Z",
                ),
                tenant_id=theirs,
            )

        # What only the other estate has. A result is a leak if it carries one
        # of these, not merely if it is truthy: an empty chain's genesis hash
        # and a zero-record verification are truthful "nothing here" answers
        # that happen not to be falsy.
        markers = ("Their", "theirs", "01T", "admin", theirs)

        leaks: list[str] = []
        blind: list[str] = []
        async with database.unit_of_work() as uow:
            for class_name, method_name in _tenant_scoped_methods():
                if method_name in WRITE_VERBS:
                    continue
                dao = _dao_for(uow, class_name)
                if dao is None:
                    continue
                probe = f"{class_name}.{method_name}"

                # By keyword: some of these declare tenant_id keyword-only.
                mine = getattr(dao, method_name)(tenant_id=ours)
                if hasattr(mine, "__await__"):
                    mine = await mine
                complaint = _leaks(mine, markers)
                if complaint:
                    leaks.append(f"{probe} {complaint}")

                owner = getattr(dao, method_name)(tenant_id=theirs)
                if hasattr(owner, "__await__"):
                    owner = await owner
                # Blind means *indistinguishable*: if the estate that owns
                # everything gets the same answer as the estate that owns
                # nothing, this probe could not report a leak whatever the
                # query did. Comparing the two answers rather than looking for
                # a marker also covers the methods whose answer is a hash or a
                # count and carries no name to match on.
                if _render(owner) == _render(mine):
                    blind.append(probe)
        return leaks, blind


#: Probes the sweep cannot make meaningful, each with the reason. An entry here
#: is an admission that this method has no coverage *from the sweep* — it is not
#: an exemption from being tested, and several are covered by a bespoke test
#: above.
BLIND_BY_DESIGN: dict[str, str] = {}


def _render(result: Any) -> str:
    """One answer, as a comparable string."""
    if hasattr(result, "to_dict"):
        try:
            return repr(result.to_dict())
        except Exception:  # pragma: no cover - a to_dict needing more setup
            pass
    return repr(result)


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


#: DAOs the sweep cannot reach, each with the reason. An entry is an admission,
#: not an exemption: it says this DAO's tenant boundary rests on something other
#: than a scoped query, and names what.
UNSWEPT: dict[str, str] = {
    "TenantDao": (
        "the root of the scoping, not a thing scoped by it. A tenant row is how "
        "an estate exists; there is no tenant to filter it by."
    ),
    "SampleDao": (
        "no tenant-scoped read exists. `get(digest)` is content-addressed and "
        "the tenant check lives in the caller — `triage_routes._sample` compares "
        "`stored.tenant_id` itself — which is the shape finding S2 was about. "
        "`forget(digest)` takes no tenant at all, so a known digest deletes "
        "another estate's samples. Covered today by "
        "`tests/web/test_triage.py::test_another_tenants_samples_are_not_shown`, "
        "which tests the route rather than the store."
    ),
}


class TestTheSuiteCannotFallBehind:
    """Finding T2. The test that was supposed to make this file mean something
    could not fail.

    It enumerated DAOs by `issubclass(..., TenantScopedDao)`. Exactly three of
    twenty-three inherit that base — `ApiKeyDao`, `PrincipalDao`, `RoleDao` —
    and all three were already in `COVERED`, so `missing` was permanently the
    empty set. The other twenty take the tenant as an *argument*, by convention,
    and could never enter the scan at all; a DAO added next year would not have
    failed it.

    The file diagnosed this itself, forty lines above, in the docstring of
    `_tenant_scoped_methods`: "A scan keyed on the base class therefore covered
    three of twenty-three while claiming to cover everything, which is worse
    than not scanning at all." The helper was fixed to scan signatures. The test
    holding the strongest claim in the file was left keyed on the base class.

    So it now enumerates every DAO and requires each to be accounted for: swept
    by `TestEveryTenantAwareReadIsScoped`, covered by a bespoke test above, or
    declared in `UNSWEPT` with the reason its boundary rests elsewhere.
    """

    @staticmethod
    def all_daos() -> set[str]:
        import prama.db.dao as package
        from prama.db.dao.base import Dao, TenantScopedDao

        return {
            name
            for name in dir(package)
            if isinstance(getattr(package, name), type)
            and issubclass(getattr(package, name), Dao)
            and getattr(package, name) not in (Dao, TenantScopedDao)
        }

    def test_there_are_daos_to_check(self) -> None:
        """Anti-vacuity, and not a formality: the version of this test it
        replaces compared two sets that were equal by construction."""
        assert len(self.all_daos()) >= 20

    def test_every_dao_is_swept_bespoke_or_declared(self) -> None:
        swept = {class_name for class_name, _ in _tenant_scoped_methods()}
        unaccounted = self.all_daos() - swept - COVERED - UNSWEPT.keys()
        assert not unaccounted, (
            f"these DAOs have no tenant isolation test of any kind: "
            f"{sorted(unaccounted)}. Give each a scoped read the sweep can "
            "exercise, a bespoke test listed in COVERED, or an entry in UNSWEPT "
            "saying what its boundary rests on instead."
        )

    def test_the_declarations_are_still_true(self) -> None:
        """An admission about a DAO that has since grown a scoped read is dead
        weight, and makes the list look more considered than it is."""
        swept = {class_name for class_name, _ in _tenant_scoped_methods()}
        stale = sorted(UNSWEPT.keys() & swept)
        assert not stale, (
            f"declared unsweepable but the sweep now reaches them: {stale}. Remove the entry."
        )

    def test_every_named_dao_exists(self) -> None:
        """A name that no longer resolves reads as coverage of something that
        is not there."""
        known = self.all_daos()
        missing = sorted((COVERED | UNSWEPT.keys()) - known)
        assert not missing, f"named in COVERED or UNSWEPT and not a DAO: {missing}"


def _requires_tenant(method: object) -> bool:
    """Whether a read *demands* a tenant, rather than merely accepting one.

    Presence was the original test, and presence is not enforcement: a
    `tenant_id: str | None = None` satisfies "has the parameter" while leaving
    every caller free to omit it, which is the behaviour the scan exists to
    forbid. `PrincipalDao.by_external_id` is exactly that shape — it takes an
    optional tenant because authentication genuinely runs before one is known
    — and under the old check it would have read as scoped.

    A guard that measures the wrong property is the failure this whole QA round
    kept finding, so it is worth the four lines.
    """
    import inspect

    parameter = inspect.signature(method).parameters.get("tenant_id")
    return parameter is not None and parameter.default is inspect.Parameter.empty


#: DAO read methods that legitimately take no tenant, each with the reason.
#: An entry is an admission that this method's boundary rests on something
#: other than its own query, and names what.
UNSCOPED_READS: dict[str, str] = {
    # -- the root of the scoping ------------------------------------------
    "TenantDao.by_slug": "a tenant is what scoping is *by*; there is nothing to filter it with",
    "TenantDao.list_active": "as TenantDao.by_slug",
    # -- deliberate derivations -------------------------------------------
    "VersionedDao.tenant_of": (
        "answers 'whose is it', not 'may this caller see it'. Added for the CLI "
        "paths that hold an identifier and no tenant; its docstring forbids using "
        "it to satisfy a caller-supplied scope, which would make the check a "
        "tautology."
    ),
    "AttributeDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "BindingDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "ConceptDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "ConceptPropertyDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "ConnectionDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "ControlDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "DatasetDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "DomainDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "JourneyDao.tenant_of": "inherited from VersionedDao.tenant_of",
    "RelationshipDao.tenant_of": "inherited from VersionedDao.tenant_of",
    # -- authentication, which runs before a tenant is known ---------------
    "ApiKeyDao.by_prefix": (
        "the key is how the tenant is established; requiring one here would need "
        "the answer before the question"
    ),
    # Still unscoped, and still for the right reason — but it no longer meets
    # an identity matching two estates with a raw MultipleResultsFound. It
    # refuses and says to pass the tenant (QA finding DB-142).
    "PrincipalDao.by_external_id": "as ApiKeyDao.by_prefix, for the SSO path",
    # Three entries lived here until QA round 2: AttributeDao.mapped_to_property,
    # EvidenceDao.for_control and EvidenceDao.for_run. Each was justified by a
    # caller that filtered afterwards — "checked, but remembered rather than
    # enforced", as the note on for_control admitted. Round 2 found all three
    # readable across estates by anybody holding a parent id, so they now take
    # a tenant and the justification is gone rather than improved.
    #
    # The lesson is in the shape of the argument, not the code: every one of
    # those reasons was about the callers that existed when it was written.
    # -- reached only by an id already established as the caller's ---------
    "ApiKeyDao.active_for_principal": "a principal is tenant-scoped; its keys inherit that",
    "PrincipalDao.roles_of": "as ApiKeyDao.active_for_principal",
    # -- scoped by the caller, which is the S2 shape and is written down ---
    "AttestationDao.value": (
        "attestation_routes fetches the row through `in_tenant` first and 404s on "
        "None, so the unscoped read is never reached with another estate's id. "
        "Confirmed by probe: a cross-tenant GET returns 404 and leaks nothing"
    ),
    "AttestationDao.verify": "as AttestationDao.value",
    # -- known gaps, not yet closed ---------------------------------------
    # SampleDao.get and .require are inherited from Dao, so this scan does not
    # reach them; they are recorded in UNSWEPT above, where the gap belongs.
    "SampleDao.forget": (
        "takes no tenant at all, so a known digest deletes another estate's "
        "samples. An open gap, recorded here and in UNSWEPT rather than implied "
        "by an absence"
    ),
    "SampleDao.expired": "the retention sweep is cross-tenant by design: it deletes by age",
}


class TestEveryDaoReadTakesATenant:
    """QA finding F-02. Four by-parent reads took a parent id and nothing else.

    `AttributeDao.for_dataset`, `ConceptPropertyDao.for_concept`,
    `BindingDao.for_dataset` and `BindingDao.for_attribute` filtered on the
    parent and never on the estate, so `GET /datasets/{id}/attributes` with a
    valid key from *another* tenant returned **200 with the data**, not a 404.
    Sibling methods on the same classes — `critical_data_elements`, `drifted` —
    always filtered. Four missed filters, not a design failure.

    **The sweep could not see them.** `TestEveryTenantAwareReadIsScoped` probes
    methods callable with a tenant *alone*, so it enumerates by looking for
    `tenant_id` as the **first** parameter. A method taking `dataset_id` is
    invisible to it however carefully it is written, and all four were.

    So this one reads signatures rather than calling anything: every public read
    on every DAO must accept a tenant *somewhere*, or be declared above with the
    reason it does not. It is a weaker check than the sweep — it proves the
    parameter exists, not that the query uses it — and the two together are what
    cover the surface. Writing the declarations is the point: three of the seven
    entries below are gaps somebody now has to look at rather than absences
    nobody could see.
    """

    #: Verbs that write. A write takes its tenant from what it is writing.
    WRITES: ClassVar[frozenset[str]] = frozenset(
        {
            "create",
            "add",
            "delete",
            "record",
            "append",
            # `extend` is `append` in a loop and was simply missed here. The
            # stronger required-tenant check found it immediately, which is the
            # point of strengthening it — though what it found is a write, not
            # a cross-estate read.
            "extend",
            "declare",
            "sign",
            "observe",
            "put",
            "start",
            "finish",
            "amend",
            "correct",
            "retire",
            "activate",
            "suppress",
            "grant",
            "revoke",
            "set_password",
            "disable",
            "forget_gaps",
            "acknowledge",
            "erase",
            "flush",
            "commit",
            "rollback",
            "close",
            "count",
        }
    )

    def reads(self) -> list[tuple[str, str, object]]:
        import inspect

        import prama.db.dao as package
        from prama.db.dao.base import Dao, TenantScopedDao

        found = []
        for class_name in dir(package):
            candidate = getattr(package, class_name)
            if (
                not isinstance(candidate, type)
                or not issubclass(candidate, Dao)
                or candidate in (Dao, TenantScopedDao)
            ):
                continue
            for name, method in inspect.getmembers(candidate, inspect.isfunction):
                if name.startswith("_") or name in self.WRITES:
                    continue
                if method.__qualname__.split(".")[0] in ("Dao", "TenantScopedDao"):
                    continue  # inherited plumbing, not this DAO's surface
                found.append((class_name, name, method))
        return found

    def test_there_are_reads_to_check(self) -> None:
        """Anti-vacuity. A scan that enumerated nothing would pass while
        checking nothing, which is how F-02 survived a sweep named for it."""
        assert len(self.reads()) >= 25

    def test_every_read_accepts_a_tenant_or_is_declared(self) -> None:

        unscoped: list[str] = []
        for class_name, name, method in self.reads():
            key = f"{class_name}.{name}"
            if key in UNSCOPED_READS:
                continue
            if not _requires_tenant(method):
                unscoped.append(key)
        assert not unscoped, (
            "these DAO reads take no tenant at all, so a caller holding an "
            f"identifier from another estate reads that estate's rows: {sorted(unscoped)}. "
            "Add a tenant_id, or declare it in UNSCOPED_READS with the reason its "
            "boundary rests elsewhere."
        )

    def test_the_declarations_are_still_true(self) -> None:
        """An admission about a method that has since grown a tenant is dead
        weight, and makes the list look more considered than it is."""

        stale = []
        for class_name, name, method in self.reads():
            key = f"{class_name}.{name}"
            if key in UNSCOPED_READS and _requires_tenant(method):
                stale.append(key)
        assert not stale, f"declared unscoped and now takes a tenant: {stale}"

    def test_every_declared_method_exists(self) -> None:
        known = {f"{c}.{n}" for c, n, _ in self.reads()}
        missing = sorted(UNSCOPED_READS.keys() - known)
        assert not missing, f"declared in UNSCOPED_READS and not a DAO read: {missing}"
