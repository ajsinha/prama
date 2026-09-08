"""The console renders, and says true things while it does.

These are not smoke tests. A template that renders is not a template that is
correct, and the failures this suite is written against are the ones that pass
a 200 check: a nav that never marks where you are, a map that silently drops
edges, a dataset page that reports a gap it does not have.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import httpx
import pytest

from prama.core.config import ConfigurationBuilder
from prama.core.errors import SecretMissingError
from prama.db import Database
from prama.web.rendering import NAVIGATION
from prama.web.viewmodels import DatasetCard

pytestmark = pytest.mark.anyio


async def _declare(database: Database, tenant_id: str, **fields: object) -> str:
    async with database.unit_of_work() as uow:
        _, version = await uow.datasets.create(
            tenant_id=tenant_id,
            name=fields.pop("name", "Positions"),
            slug=fields.pop("slug", "positions"),
            **fields,
        )
        await uow.flush()
        return str(version.dataset_id)


class TestShell:
    async def test_root_redirects_to_the_estate(self, ui: httpx.AsyncClient) -> None:
        response = await ui.get("/")
        assert response.status_code == 307
        assert response.headers["location"] == "/estate"

    async def test_the_estate_page_renders(self, ui: httpx.AsyncClient) -> None:
        response = await ui.get("/estate")
        assert response.status_code == 200
        assert "Prama" in response.text

    async def test_static_assets_are_served_from_the_package(self, ui: httpx.AsyncClient) -> None:
        """Vendored, not fetched. An air-gapped deployment is the requirement."""
        for asset in (
            "/static/css/prama.css",
            "/static/js/prama.js",
            "/static/vendor/bootstrap/css/bootstrap.min.css",
            "/static/vendor/jquery/jquery.min.js",
            "/static/vendor/sigma/sigma.min.js",
            "/static/vendor/graphology/graphology.umd.min.js",
        ):
            response = await ui.get(asset)
            assert response.status_code == 200, asset
            assert response.content, asset

    async def test_no_page_references_an_external_host(self, ui: httpx.AsyncClient) -> None:
        """The counterfactual for the vendoring claim.

        A single CDN link would make the console blank behind a firewall, and
        it would look fine everywhere it was developed.
        """
        response = await ui.get("/estate")
        for marker in ("https://cdn.", "http://cdn.", "//unpkg.com", "//cdnjs.", "googleapis"):
            assert marker not in response.text, marker

    async def test_every_nav_entry_points_at_a_registered_route(
        self, ui: httpx.AsyncClient
    ) -> None:
        """A nav item naming a route that does not exist 500s the whole shell.

        It is an easy mistake — the endpoint name is a string — and it takes
        down every page at once rather than the one that is wrong.
        """
        response = await ui.get("/estate")
        assert response.status_code == 200
        for item in NAVIGATION:
            assert item.label in response.text, item.label

    async def test_the_current_section_is_marked(self, ui: httpx.AsyncClient) -> None:
        response = await ui.get("/estate")
        assert 'aria-current="page"' in response.text

    async def test_the_skip_link_is_first(self, ui: httpx.AsyncClient) -> None:
        response = await ui.get("/estate")
        body = response.text.split("<body>", 1)[1]
        assert body.index("skip-link") < body.index("<nav")


class TestEstateMap:
    async def test_the_graph_endpoint_returns_declared_datasets(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        dataset_id = await _declare(started_database, tenant_id, name="Positions")
        payload = (await ui.get("/estate/graph.json")).json()
        assert [node["key"] for node in payload["nodes"]] == [dataset_id]
        assert payload["nodes"][0]["attributes"]["label"] == "Positions"

    async def test_an_edge_to_a_retired_dataset_is_dropped_and_counted(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The failure this prevents is a blank map.

        Sigma throws on an edge whose endpoint is not in the node set, and the
        whole canvas disappears — for a condition that is legitimate, because a
        relationship outlives its counterparty being retired. Dropping it
        silently would be the other failure: a map that lies by omission.
        """
        left = await _declare(started_database, tenant_id, name="Trades", slug="trades")
        async with started_database.unit_of_work() as uow:
            await uow.relationships.create(
                tenant_id=tenant_id,
                kind="reconciles_with",
                from_dataset_id=left,
                to_dataset_id="01ZZZZZZZZZZZZZZZZZZZZZZZZ",
                status="confirmed",
            )
            await uow.flush()

        payload = (await ui.get("/estate/graph.json")).json()
        assert payload["edges"] == []
        assert payload["dangling_edges"] == 1

    async def test_an_unbound_dataset_is_not_coloured_as_healthy(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _declare(started_database, tenant_id, name="Ledger", slug="ledger")
        payload = (await ui.get("/estate/graph.json")).json()
        assert payload["nodes"][0]["attributes"]["bound"] is False


class TestDatasetPage:
    async def test_it_names_the_controls_that_cannot_be_generated(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        dataset_id = await _declare(started_database, tenant_id, name="Positions")
        response = await ui.get(f"/estate/{dataset_id}")
        assert response.status_code == 200
        # Phrased as the lost capability, not the null column.
        assert "no timeliness control" in response.text
        assert "no uniqueness or completeness control" in response.text

    async def test_a_complete_declaration_reports_no_gaps(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        dataset_id = await _declare(
            started_database,
            tenant_id,
            name="Positions",
            description="End-of-day positions per account.",
            shape="table",
            grain_json={"attributes": ["account_id", "as_of_date"]},
            rhythm_json={"cadence": "daily"},
        )
        response = await ui.get(f"/estate/{dataset_id}")
        assert "generates the full control set" in response.text
        assert "no timeliness control" not in response.text


class TestGapWording:
    """The gap list is derived, and the derivation is what is asserted."""

    def _card(self, **overrides: object) -> DatasetCard:
        base: dict[str, object] = {
            "id": "01AAA",
            "name": "Positions",
            "slug": "positions",
            "description": "what it is",
            "shape": "table",
            "criticality": 1,
            "lifecycle_state": "active",
            "domain_id": None,
            "is_bound": True,
            "has_grain": True,
            "has_rhythm": True,
            "owner_id": None,
        }
        base.update(overrides)
        return DatasetCard(**base)  # type: ignore[arg-type]

    def test_a_complete_card_has_no_gaps(self) -> None:
        assert self._card().gaps == []
        assert self._card().is_complete

    def test_each_missing_declaration_names_one_lost_control(self) -> None:
        assert len(self._card(has_grain=False).gaps) == 1
        assert len(self._card(has_rhythm=False).gaps) == 1
        assert len(self._card(is_bound=False).gaps) == 1

    def test_a_blank_description_counts_as_missing(self) -> None:
        """Whitespace is not a description, and it is what gets typed."""
        assert self._card(description="   ").gaps


class TestBootRefusal:
    async def test_the_ui_refuses_to_mount_without_a_session_secret(
        self, sqlite_config: object
    ) -> None:
        """Shipped empty on purpose; the refusal is the feature.

        A default secret is a cookie-forgery hole that nobody notices, because
        everything works.
        """
        from prama.api import create_app

        config = (
            ConfigurationBuilder()
            .with_defaults(sqlite_config.raw())  # type: ignore[attr-defined]
            .with_mapping({"security": {"session_secret": ""}}, name="no-secret")
            .build()
        )
        with pytest.raises(SecretMissingError):
            create_app(config)


class TestDeclarationForm:
    async def test_the_approval_requirement_is_derived_from_the_policy(
        self, ui: httpx.AsyncClient
    ) -> None:
        """Not restated in the template.

        A hard-coded "Tier 1 needs approval" goes stale the moment the policy
        is configured differently, and it goes stale in the flattering
        direction — telling the reader no approval is needed when one is.
        """
        from prama.semantic.policy import ApprovalPolicy

        body = (await ui.get("/declarations/new")).text
        policy = ApprovalPolicy()
        for tier in (1, 2, 3, 4):
            needed = 1 if policy.for_criticality(tier).needs_approver else 0
            marker = f'value="{tier}"'
            fragment = body[body.index(marker) : body.index(marker) + 220]
            assert f'data-needs-approver="{needed}"' in fragment, tier

    async def test_the_form_asks_questions_not_column_names(self, ui: httpx.AsyncClient) -> None:
        """The whole reason this product exists is that a business owner can
        answer 'what does one row represent?' and cannot answer 'grain_json'."""
        response = await ui.get("/declarations/new")
        assert response.status_code == 200
        assert "What does one row represent?" in response.text
        assert "grain_json" not in response.text

    async def test_declaring_lands_on_the_dataset(self, ui: httpx.AsyncClient) -> None:
        response = await ui.post(
            "/declarations/new",
            data={
                "name": "Positions EOD",
                "description": "End-of-day positions.",
                "shape": "table",
                "criticality": "3",
                "grain": "account_id, instrument_id",
                "grain_statement": "one position per account per instrument",
            },
        )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/estate/")

    async def test_a_rejected_declaration_keeps_what_was_typed(self, ui: httpx.AsyncClient) -> None:
        """A validation error that empties the form teaches the user to
        distrust it, and they start drafting in a text editor instead."""
        payload = {
            "name": "Positions EOD",
            "description": "End-of-day positions.",
            "shape": "table",
            "criticality": "3",
            "grain": "account_id",
            "grain_statement": "one position per account",
        }
        assert (await ui.post("/declarations/new", data=payload)).status_code == 303
        clash = await ui.post("/declarations/new", data=payload)
        assert clash.status_code == 422
        assert "End-of-day positions." in clash.text
        assert "one position per account" in clash.text

    async def test_a_tier_one_declaration_is_refused_without_an_approver(
        self, ui: httpx.AsyncClient
    ) -> None:
        """Maker-checker, surfaced where it is typed rather than swallowed.

        The refusal carries the policy's own remedy, so the person reading it
        learns what to do next instead of retrying the same form.
        """
        response = await ui.post(
            "/declarations/new",
            data={"name": "Regulatory Return", "shape": "table", "criticality": "1"},
        )
        assert response.status_code == 422
        assert "requires approval" in response.text
        assert "held as proposed" in response.text

    async def test_the_list_puts_tier_one_first(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _declare(started_database, tenant_id, name="Aardvark", slug="aardvark", criticality=4)
        await _declare(started_database, tenant_id, name="Zebra", slug="zebra", criticality=1)
        body = (await ui.get("/declarations")).text
        assert body.index("Zebra") < body.index("Aardvark")


class TestControlStudio:
    async def test_the_studio_renders_with_the_declared_slugs(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _declare(started_database, tenant_id, name="Positions", slug="positions_eod")
        response = await ui.get("/controls")
        assert response.status_code == 200
        assert "positions_eod" in response.text

    async def test_a_syntax_error_is_reported_and_nothing_else_is_claimed(
        self, ui: httpx.AsyncClient
    ) -> None:
        response = await ui.post("/controls/check", data={"source": "CHECK CHECK CHECK"})
        assert response.status_code == 200
        assert "does not parse" in response.text
        # No explanation is offered for something that did not parse: a
        # sentence describing a control nobody could read is an invention.
        assert "What these controls say" not in response.text

    async def test_a_valid_control_is_explained_from_its_plan(self, ui: httpx.AsyncClient) -> None:
        source = (
            "CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id) "
            "SEVERITY critical DIMENSION uniqueness BECAUSE 'Declared grain'"
        )
        response = await ui.post("/controls/check", data={"source": source})
        assert "at most one row for each combination" in response.text
        assert "Declared grain" in response.text

    async def test_compiling_shows_the_sql_that_will_run(self, ui: httpx.AsyncClient) -> None:
        """Inspectable rather than trusted. This is the panel a DBA asks for
        before granting access, which is why it is not behind a toggle."""
        source = (
            "CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id) "
            "SEVERITY critical DIMENSION uniqueness BECAUSE 'Declared grain'"
        )
        response = await ui.post(
            "/controls/compile", data={"source": source, "target": "postgresql"}
        )
        assert response.status_code == 200
        assert "SELECT" in response.text.upper()
        assert "ir:sha256:" in response.text


class TestProposalQueue:
    async def test_it_lists_what_the_declarations_imply(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _declare(
            started_database,
            tenant_id,
            name="Positions",
            slug="positions_eod",
            shape="table",
            criticality=1,
            grain_json={"attributes": ["account_id", "instrument_id"]},
        )
        response = await ui.get("/proposals")
        assert response.status_code == 200
        assert "grain" in response.text

    async def test_an_empty_queue_is_not_reported_as_healthy(self, ui: httpx.AsyncClient) -> None:
        """The flattering direction. Nothing derived means the declarations do
        not say enough yet — it is not a clean bill of health, and a screen
        that reads like one is worse than no screen."""
        response = await ui.get("/proposals")
        assert "not a clean bill of health" in response.text


class TestOperationsScreens:
    @pytest.mark.parametrize("path", ["/incidents", "/reconciliation", "/scorecards"])
    async def test_no_runs_is_said_out_loud(self, ui: httpx.AsyncClient, path: str) -> None:
        """The single most dangerous screen a DQ product can ship is an empty
        incident list that reads as a clean one."""
        response = await ui.get(path)
        assert response.status_code == 200
        assert "Nothing has been examined" in response.text
        assert "absence of observation, not the absence of problems" in response.text


class TestPackaging:
    def test_every_template_and_asset_is_declared_package_data(self) -> None:
        """An installed wheel must carry the templates and the vendored assets.

        Left out, they are simply absent at run time and every page 500s — while
        a source checkout, where the files happen to be on disk, passes the whole
        suite. This is the one defect a test run from the repository cannot see,
        so it is checked against the packaging declaration directly.
        """
        import fnmatch
        import tomllib
        from pathlib import Path

        from prama.web.rendering import PACKAGE_ROOT

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyproject.open("rb") as handle:
            patterns = tomllib.load(handle)["tool"]["setuptools"]["package-data"]["prama.web"]

        shipped = []
        for path in PACKAGE_ROOT.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix == ".py":
                continue  # ordinary module, carried by the package itself
            relative = path.relative_to(PACKAGE_ROOT).as_posix()
            if not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
                shipped.append(relative)
        assert shipped == [], f"not covered by package-data: {shipped[:10]}"


class TestRelationships:
    async def test_the_kind_options_carry_the_question_and_what_they_generate(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Both derived from RelationshipKind.

        The prompt is the sentence a business owner recognises; the generated
        control list is the reason to choose carefully, since this is the
        difference between drawing a line on a diagram and switching on a
        reconciliation.
        """
        from prama.semantic.relationships import RelationshipKind

        await _declare(started_database, tenant_id, name="Trades", slug="trades")
        await _declare(started_database, tenant_id, name="Ledger", slug="ledger")
        body = (await ui.get("/relationships/new")).text
        for kind in RelationshipKind:
            assert kind.prompt in body, kind.value
            for generated in kind.generates:
                assert generated in body, generated

    async def test_the_form_refuses_when_there_is_only_one_dataset(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _declare(started_database, tenant_id, name="Trades", slug="trades")
        body = (await ui.get("/relationships/new")).text
        assert "needs two datasets" in body

    async def test_declaring_a_relationship_lands_on_the_list(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        left = await _declare(started_database, tenant_id, name="Trades", slug="trades")
        right = await _declare(started_database, tenant_id, name="Ledger", slug="ledger")
        response = await ui.post(
            "/relationships/new",
            data={
                "kind": "reconciles_with",
                "from_dataset_id": left,
                "to_dataset_id": right,
                "match_keys": "trade_id = txn_id, trade_date",
                "cardinality": "one_to_one",
                "tolerance_absolute": "1.00",
                "tolerance_currency": "eur",
                "tolerance_relative_percent": "0.1",
                "compare": "amount",
            },
        )
        assert response.status_code == 303
        listing = (await ui.get("/relationships")).text
        assert "reconciles_with" in listing
        assert "confirmed" in listing

    async def test_a_proposal_offers_both_answers(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A queue that offers only "confirm" is not asking a question."""
        left = await _declare(started_database, tenant_id, name="Trades", slug="trades")
        right = await _declare(started_database, tenant_id, name="Ledger", slug="ledger")
        async with started_database.unit_of_work() as uow:
            _, version = await uow.relationships.create(
                tenant_id=tenant_id,
                kind="references",
                from_dataset_id=left,
                to_dataset_id=right,
                status="proposed",
                confidence=0.82,
            )
            await uow.flush()
            relationship_id = str(version.relationship_id)

        body = (await ui.get("/relationships")).text
        assert "Confirm" in body
        assert "Reject" in body
        assert f"/relationships/{relationship_id}/reject" in body

    async def test_a_rejection_is_recorded_not_deleted(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A rejection is a training signal. Re-proposing something a steward
        has already turned down is the fastest way to lose their attention."""
        left = await _declare(started_database, tenant_id, name="Trades", slug="trades")
        right = await _declare(started_database, tenant_id, name="Ledger", slug="ledger")
        async with started_database.unit_of_work() as uow:
            _, version = await uow.relationships.create(
                tenant_id=tenant_id,
                kind="references",
                from_dataset_id=left,
                to_dataset_id=right,
                status="proposed",
            )
            await uow.flush()
            relationship_id = str(version.relationship_id)

        await ui.post(f"/relationships/{relationship_id}/reject", data={"reason": "not true"})
        async with started_database.unit_of_work() as uow:
            current = await uow.relationships.require_current(relationship_id)
            assert current.status == "rejected"

    async def test_a_proposed_edge_is_not_drawn_as_a_declared_one(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Drawing an inference identically to a statement of fact is the exact
        confusion the confirm/reject workflow exists to prevent."""
        left = await _declare(started_database, tenant_id, name="Trades", slug="trades")
        right = await _declare(started_database, tenant_id, name="Ledger", slug="ledger")
        async with started_database.unit_of_work() as uow:
            await uow.relationships.create(
                tenant_id=tenant_id,
                kind="references",
                from_dataset_id=left,
                to_dataset_id=right,
                status="proposed",
            )
            await uow.flush()
        payload = (await ui.get("/estate/graph.json")).json()
        assert payload["edges"][0]["attributes"]["style"] == "dashed"


class TestTolerance:
    def test_percent_on_the_form_becomes_a_fraction_in_the_model(self) -> None:
        """The unit mismatch that makes a tolerance a thousand times too wide,
        with nothing about the resulting run looking wrong."""
        from prama.web.routes.relationship_routes import _parse_tolerance

        tolerance = _parse_tolerance("", "", "0.1")
        assert tolerance is not None
        assert tolerance.relative == 0.001

    def test_a_currency_is_normalised(self) -> None:
        from prama.web.routes.relationship_routes import _parse_tolerance

        tolerance = _parse_tolerance("1.00", "eur", "")
        assert tolerance is not None
        assert tolerance.currency == "EUR"

    def test_nothing_typed_is_no_tolerance_not_a_zero_one(self) -> None:
        """A zero tolerance breaks on the first rounding difference; the
        declaration refuses a missing one with the right message, so this must
        pass the absence through rather than invent a bound."""
        from prama.web.routes.relationship_routes import _parse_tolerance

        assert _parse_tolerance("", "", "") is None

    async def test_a_kind_that_needs_a_tolerance_says_so_when_it_is_missing(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        left = await _declare(started_database, tenant_id, name="Trades", slug="trades")
        right = await _declare(started_database, tenant_id, name="Ledger", slug="ledger")
        response = await ui.post(
            "/relationships/new",
            data={
                "kind": "reconciles_with",
                "from_dataset_id": left,
                "to_dataset_id": right,
                "match_keys": "trade_id",
            },
        )
        assert response.status_code == 422
        assert "needs a tolerance" in response.text
        assert "breaks on the first rounding difference" in response.text


class TestMatchKeyParsing:
    def test_both_forms_people_actually_write(self) -> None:
        from prama.web.routes.relationship_routes import _parse_match_keys

        keys = _parse_match_keys("account_id = acct_id, trade_date")
        assert [(k.left, k.right) for k in keys] == [
            ("account_id", "acct_id"),
            ("trade_date", None),
        ]

    def test_blank_and_stray_commas_are_ignored(self) -> None:
        from prama.web.routes.relationship_routes import _parse_match_keys

        assert _parse_match_keys("  ,, a , ") == _parse_match_keys("a")
