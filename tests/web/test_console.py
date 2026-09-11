"""The console renders, and says true things while it does.

These are not smoke tests. A template that renders is not a template that is
correct, and the failures this suite is written against are the ones that pass
a 200 check: a nav that never marks where you are, a map that silently drops
edges, a dataset page that reports a gap it does not have.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re

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
        response = await ui.get("/controls/studio")
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
            current = await uow.relationships.require_current(relationship_id, tenant_id=tenant_id)
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


class TestRuleBuilder:
    async def test_the_form_asks_in_business_terms(self, ui: httpx.AsyncClient) -> None:
        body = (await ui.get("/controls/build")).text
        assert "Every row must have a value in this column" in body
        assert "No two rows may share these columns" in body
        # Not one of these appears anywhere on the form.
        for jargon in ("PredicateAssertion", "is_not_null", "unknown_policy"):
            assert jargon not in body, jargon

    async def test_building_shows_the_pql_it_wrote(self, ui: httpx.AsyncClient) -> None:
        """Always, never behind a toggle. A builder that hides its output
        produces controls nobody reviews."""
        response = await ui.post(
            "/controls/build",
            data={
                "dataset": "positions_eod",
                "rule": "not_null",
                "column": "notional_amount",
                "because": "CDE for FRTB",
                "severity": "critical",
            },
        )
        assert response.status_code == 200
        assert "CHECK positions_eod.notional_amount IS NOT NULL" in response.text
        assert "SEVERITY critical" in response.text
        assert "CDE for FRTB" in response.text

    async def test_it_also_shows_what_the_control_means(self, ui: httpx.AsyncClient) -> None:
        """From the lowered plan, the same structure the SQL comes from — so
        the sentence and the query cannot describe different controls."""
        response = await ui.post(
            "/controls/build",
            data={
                "dataset": "positions_eod",
                "rule": "unique_key",
                "columns": "account_id, instrument_id",
                "because": "declared grain",
            },
        )
        assert "at most one row for each combination" in response.text

    async def test_a_refusal_carries_its_remedy(self, ui: httpx.AsyncClient) -> None:
        response = await ui.post(
            "/controls/build",
            data={"dataset": "positions_eod", "rule": "not_null", "column": "a"},
        )
        assert response.status_code == 200
        assert "needs a reason" in response.text
        assert "what the alert quotes" in response.text

    async def test_the_unknown_default_is_explained_not_just_set(
        self, ui: httpx.AsyncClient
    ) -> None:
        """Unticking it restores SQL's behaviour, under which a rule over an
        entirely empty column passes for years. That has to be said next to the
        checkbox, not buried in documentation."""
        body = (await ui.get("/controls/build")).text
        assert "entirely empty will pass" in body


class TestReportPacks:
    async def test_the_index_states_there_is_no_pdf_engine(self, ui: httpx.AsyncClient) -> None:
        """Stated rather than discovered. Bundling WeasyPrint would mean native
        graphics libraries in every on-premises install for a job the browser
        already does correctly, and that trade should be visible."""
        body = (await ui.get("/reports")).text
        assert "does not bundle a PDF engine" in body
        assert "Save as PDF" in body

    async def test_the_declaration_pack_renders_the_estate(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _declare(
            started_database,
            tenant_id,
            name="Positions EOD",
            slug="positions_eod",
            shape="table",
            criticality=1,
            grain_json={
                "attributes": ["account_id"],
                "statement": "one position per account per day",
            },
        )
        response = await ui.get("/reports/declarations")
        assert response.status_code == 200
        assert "Positions EOD" in response.text
        assert "one position per account per day" in response.text
        assert "Declaration pack" in response.text

    async def test_a_retired_dataset_is_excluded_and_counted(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Out of scope, and said so with a number. An auditor asking "is this
        everything?" gets an answer rather than a shrug."""
        await _declare(started_database, tenant_id, name="Live", slug="live")
        await _declare(
            started_database,
            tenant_id,
            name="Old",
            slug="old",
            lifecycle_state="retired",
        )
        body = (await ui.get("/reports/declarations")).text
        assert "Live" in body
        assert "1 of 2 covered" in body
        assert "retired" in body

    async def test_the_control_pack_counts_datasets_not_controls(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """ "220 controls" says nothing about how much of the estate they touch,
        and a pack whose coverage number counts its own contents can never
        report a gap."""
        await _declare(
            started_database,
            tenant_id,
            name="Described",
            slug="described",
            shape="table",
            grain_json={"attributes": ["id"]},
        )
        await _declare(started_database, tenant_id, name="Bare", slug="bare")
        body = (await ui.get("/reports/controls")).text
        assert "1 of 2 covered" in body

    async def test_the_pack_is_self_contained(self, ui: httpx.AsyncClient) -> None:
        body = (await ui.get("/reports/declarations")).text
        assert "<style>" in body
        assert "/static/" not in body


async def _record(database: Database, tenant_id: str, **overrides: object) -> None:
    from prama.evidence.record import EvidenceRecord

    fields: dict[str, object] = {
        "plan_id": "ir:sha256:abc",
        "control_id": "c1",
        "dataset": "positions_eod",
        "verdict": "pass",
        "metrics": {"scanned_rows": 1000.0, "violating_rows": 0.0},
        "finished_at": "2026-09-08T06:00:00Z",
    }
    fields.update(overrides)
    async with database.unit_of_work() as uow:
        await uow.evidence.append(EvidenceRecord(**fields), tenant_id=tenant_id)  # type: ignore[arg-type]


class TestScreensBackedByTheLedger:
    async def test_a_failing_control_appears_as_an_incident(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _record(
            started_database,
            tenant_id,
            verdict="fail",
            metrics={"scanned_rows": 1000.0, "violating_rows": 12.0},
        )
        body = " ".join((await ui.get("/incidents")).text.split())
        assert "positions_eod" in body
        assert "12 of 1,000 rows" in body
        assert "Nothing has been examined" not in body

    async def test_one_row_per_control_not_per_run(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A control failing every hour for a week is one problem. Listing it
        168 times is how a triage queue becomes something nobody opens."""
        for _ in range(10):
            await _record(started_database, tenant_id, verdict="fail")
        body = (await ui.get("/incidents")).text
        assert body.count("ir:sha256:abc") + body.count(">c1<") <= 2

    async def test_an_incremental_verdict_is_not_stated_as_a_full_one(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """ "Passed" after a full scan says the dataset is sound; after an
        incremental run it says only that the rows examined were."""
        await _record(started_database, tenant_id, verdict="fail", coverage="incremental")
        body = (await ui.get("/incidents")).text
        assert "over the rows examined" in body
        assert "incremental scan" in body

    async def test_a_control_that_could_not_run_is_not_omitted(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A list of problems that quietly dropped it would report the controls
        that did run as though they were all of them."""
        await _record(
            started_database, tenant_id, verdict="error", detail="the warehouse refused the query"
        )
        body = (await ui.get("/incidents")).text
        assert "the warehouse refused the query" in body

    async def test_a_clean_estate_says_how_many_controls_ran(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A green tick with no denominator means nothing."""
        await _record(started_database, tenant_id, verdict="pass")
        body = (await ui.get("/incidents")).text
        assert "1 control(s) ran and passed" in body

    async def test_an_unfinished_run_is_declared_before_the_numbers(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Its controls have no verdict, so everything below is quietly
        missing them."""
        async with started_database.unit_of_work() as uow:
            await uow.evidence_runs.start(tenant_id=tenant_id, started_at="2026-09-08T06:00:00Z")
        await _record(started_database, tenant_id)
        for path in ("/incidents", "/scorecards", "/reconciliation"):
            body = (await ui.get(path)).text
            assert "started and have not reported" in body, path

    async def test_a_skipped_control_lowers_coverage_not_the_score(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A dataset scoring 100% because half its controls were skipped is the
        most misleading number this product could produce."""
        await _record(started_database, tenant_id, control_id="a", verdict="pass")
        await _record(started_database, tenant_id, control_id="b", verdict="skipped")
        body = (await ui.get("/scorecards")).text
        assert "1 of 2 controls did not run" in body
        assert "describes 50% of what was meant to be checked" in body

    async def test_a_record_without_a_dimension_is_bucketed_and_counted(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Records written before evidence format 1.1 carry no dimension.
        Spreading them across the six by guesswork would make the scorecard's
        most legible feature its least trustworthy one."""
        await _record(started_database, tenant_id, evidence_version="1.0")
        body = " ".join((await ui.get("/scorecards")).text.split())
        assert "before the evidence format carried a dimension" in body
        assert "incomplete rather than invented" in body

    async def test_a_dimension_carrying_record_is_decomposed(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _record(
            started_database,
            tenant_id,
            control_id="a",
            dimensions=("uniqueness",),
            metrics={"scanned_rows": 100.0, "violating_rows": 10.0},
        )
        await _record(
            started_database,
            tenant_id,
            control_id="b",
            dimensions=("completeness",),
            metrics={"scanned_rows": 100.0, "violating_rows": 0.0},
        )
        body = (await ui.get("/scorecards")).text
        assert "dim-uniqueness" in body
        assert "dim-completeness" in body
        assert "90.0%" in body
        assert "before the evidence format carried a dimension" not in " ".join(body.split())

    async def test_a_control_covering_two_dimensions_counts_in_both(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A control can be about completeness *and* validity, and giving it to
        whichever was listed first would understate one of them."""
        await _record(
            started_database,
            tenant_id,
            dimensions=("completeness", "validity"),
            metrics={"scanned_rows": 100.0, "violating_rows": 5.0},
        )
        body = (await ui.get("/scorecards")).text
        assert "dim-completeness" in body
        assert "dim-validity" in body

    async def test_a_reconciliation_over_no_rows_is_not_zero_per_cent(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Scored as a total failure it is a false alarm; it is not a
        measurement at all."""
        await _record(
            started_database,
            tenant_id,
            metrics={"scanned_rows": 0.0, "matched_rows": 0.0},
        )
        body = (await ui.get("/reconciliation")).text
        assert "nothing compared" in body
        assert "0.00%" not in body


class TestEvidenceScreen:
    async def test_it_reports_the_chain_as_intact(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """On a screen, not only in a CLI: "is our audit trail intact?" is a
        question an owner should answer without asking an engineer."""
        await _record(started_database, tenant_id)
        body = (await ui.get("/evidence")).text
        assert "chain verified" in body
        assert "Merkle root" in body

    async def test_tampering_is_reported_on_the_screen(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        from sqlalchemy import text

        await _record(started_database, tenant_id, verdict="fail")
        with started_database.sync_engine().begin() as connection:
            connection.execute(text("UPDATE ev_record SET verdict = 'pass'"))
        body = (await ui.get("/evidence")).text
        assert "does not verify" in body

    async def test_an_erased_record_is_shown_as_erased(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Visible as a tombstone rather than as a hole nobody can account
        for — and the chain still verifies across it."""
        await _record(started_database, tenant_id)
        async with started_database.unit_of_work() as uow:
            await uow.evidence.erase(tenant_id, 0, by="dpo@acme", authority="DSAR-1")
        body = (await ui.get("/evidence")).text
        assert "erased" in body
        assert "chain verified" in body


class TestControlEstate:
    async def test_accepting_a_proposal_puts_it_in_the_estate(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        await _declare(
            started_database,
            tenant_id,
            name="Positions",
            slug="positions_eod",
            shape="table",
            grain_json={"attributes": ["account_id", "instrument_id"]},
        )
        queue = (await ui.get("/proposals")).text
        assert "Accept" in queue

        identity = re.search(r'name="identity" value="([^"]+)"', queue)
        pql = re.search(r'name="pql" value="([^"]+)"', queue)
        assert identity and pql

        import html as html_module

        response = await ui.post(
            "/proposals/accept",
            data={"identity": identity.group(1), "pql": html_module.unescape(pql.group(1))},
        )
        assert response.status_code == 303

        async with started_database.unit_of_work() as uow:
            live = await uow.controls.live(tenant_id)
        assert len(live) == 1
        assert live[0].status == "active"

    async def test_an_accepted_proposal_is_not_offered_again(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Showing it again would invite somebody to accept it twice."""
        await _declare(
            started_database,
            tenant_id,
            name="Positions",
            slug="positions_eod",
            shape="table",
            grain_json={"attributes": ["account_id"]},
        )
        queue = (await ui.get("/proposals")).text
        identity = re.search(r'name="identity" value="([^"]+)"', queue)
        pql = re.search(r'name="pql" value="([^"]+)"', queue)
        assert identity and pql

        import html as html_module

        await ui.post(
            "/proposals/accept",
            data={"identity": identity.group(1), "pql": html_module.unescape(pql.group(1))},
        )
        again = (await ui.get("/proposals")).text
        assert "already accepted" in again

    async def test_a_rejection_is_recorded_and_not_re_proposed(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Asking again every night is the fastest way to lose a steward's
        attention."""
        await _declare(
            started_database,
            tenant_id,
            name="Positions",
            slug="positions_eod",
            shape="table",
            grain_json={"attributes": ["account_id"]},
        )
        queue = (await ui.get("/proposals")).text
        identity = re.search(r'name="identity" value="([^"]+)"', queue)
        digest = re.search(r'name="content_hash" value="([^"]+)"', queue)
        assert identity and digest

        await ui.post(
            "/proposals/reject",
            data={
                "identity": identity.group(1),
                "content_hash": digest.group(1),
                "reason": "too_noisy",
                "note": "fires every month end",
            },
        )
        again = (await ui.get("/proposals")).text
        assert "already turned down" in again

        async with started_database.unit_of_work() as uow:
            [rejection] = await uow.rejections.for_tenant(tenant_id)
        assert rejection.reason == "too_noisy"

    async def test_the_rejection_reasons_come_from_the_enum(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """So a new reason appears in the form the moment it exists, and the
        form can never offer one the schema will refuse."""
        from prama.propose.proposal import RejectionReason

        await _declare(
            started_database,
            tenant_id,
            name="Positions",
            slug="positions_eod",
            shape="table",
            grain_json={"attributes": ["account_id"]},
        )
        body = (await ui.get("/proposals")).text
        for reason in RejectionReason:
            assert f'value="{reason.value}"' in body, reason.value

    async def test_a_proposal_that_changes_a_control_says_so(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A different decision from adding a new control, and a queue that
        rendered them identically would get this one waved through."""
        await _declare(
            started_database,
            tenant_id,
            name="Positions",
            slug="positions_eod",
            shape="table",
            grain_json={"attributes": ["account_id"]},
        )
        queue = (await ui.get("/proposals")).text
        identity = re.search(r'name="identity" value="([^"]+)"', queue)
        assert identity

        async with started_database.unit_of_work() as uow:
            await uow.controls.declare(
                tenant_id=tenant_id,
                identity=identity.group(1),
                pql=(
                    "CHECK positions_eod.account_id IS NOT NULL "
                    "SEVERITY minor DIMENSION completeness BECAUSE 'something else'"
                ),
            )
        again = (await ui.get("/proposals")).text
        assert "changes an existing control" in again

    async def test_the_estate_page_separates_running_from_proposed(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """ "We have 340 controls" is the number every tool reports; how many
        actually run is the number that decides whether the estate is
        protected."""
        async with started_database.unit_of_work() as uow:
            await uow.controls.declare(
                tenant_id=tenant_id,
                identity="i1",
                pql=(
                    "CHECK positions_eod.a IS NOT NULL SEVERITY major "
                    "DIMENSION completeness BECAUSE 'why'"
                ),
            )
        body = (await ui.get("/controls")).text
        assert "Proposed, not running" in body
        assert "are not protecting anything yet" in body

    async def test_silencing_needs_a_date_and_a_reason(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="i1",
                pql=(
                    "CHECK positions_eod.a IS NOT NULL SEVERITY major "
                    "DIMENSION completeness BECAUSE 'why'"
                ),
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
            control_id = str(control.id)

        await ui.post(f"/controls/{control_id}/suppress", data={"until": "", "because": ""})
        async with started_database.unit_of_work() as uow:
            still_live = await uow.controls.live(tenant_id)
        assert len(still_live) == 1

    async def test_an_expired_suppression_is_named_on_the_page(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """Prama does not lift it automatically — that would surprise whoever
        silenced it — but leaving it unsaid is how "temporary" becomes
        permanent."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="i1",
                pql=(
                    "CHECK positions_eod.a IS NOT NULL SEVERITY major "
                    "DIMENSION completeness BECAUSE 'why'"
                ),
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
            await uow.controls.suppress(
                str(control.id),
                tenant_id=tenant_id,
                until="2020-01-01T00:00:00Z",
                because="migration",
            )
        body = (await ui.get("/controls")).text
        assert "still silent past the date" in body
        assert "nobody turned it back on" in body

    async def test_an_unreadable_schedule_is_visible_on_the_page(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """A control that silently stops being scheduled is indistinguishable
        from one that is passing."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="i1",
                pql=(
                    "CHECK positions_eod.a IS NOT NULL SEVERITY major "
                    "DIMENSION completeness BECAUSE 'why'"
                ),
                schedule="30 6 * * 1-5",
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")

        body = " ".join((await ui.get("/controls")).text.split())
        assert "schedule Prama cannot read" in body
        assert "They will never run again" in body

    async def test_a_readable_schedule_is_shown_as_a_sentence(
        self, ui: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="i1",
                pql=(
                    "CHECK positions_eod.a IS NOT NULL SEVERITY major "
                    "DIMENSION completeness BECAUSE 'why'"
                ),
                schedule="every 4 hours",
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")

        body = (await ui.get("/controls")).text
        assert "every 4 hour(s)" in body
        assert "cannot read" not in body
