"""Print artefacts.

A pack is read by an auditor six months later with nothing but the paper. The
failures these tests are written against are the ones that make such a document
worse than useless: it cannot say where it came from, it lists forty datasets
without saying whether that is the estate, or it quietly omits what it could not
produce and so reads as complete.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from prama.report.render import (
    Artefact,
    Coverage,
    Provenance,
    control_pack,
    declaration_pack,
)
from prama.version import VERSION

INSTANT = datetime(2026, 9, 8, 6, 30, 0, tzinfo=UTC)


def _provenance() -> Provenance:
    return Provenance(tenant_id="acme-bank", generated_at=INSTANT, generated_by="alice")


def _dataset(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Positions EOD",
        "description": "End-of-day positions per account.",
        "criticality": 1,
        "tier_label": "Tier 1 · regulatory",
        "shape": "table",
        "is_bound": True,
        "has_grain": True,
        "grain_statement": "one position per account per instrument per business day",
        "grain_attributes": ["account_id"],
        "owner": "Front Office Ops",
    }
    base.update(overrides)
    return base


class TestCoverageArithmetic:
    def test_a_complete_pack_says_so_plainly(self) -> None:
        assert Coverage(included=12).is_complete
        assert "All 12 covered" in Coverage(included=12).describe()

    def test_a_partial_pack_gives_both_numbers_and_the_reason(self) -> None:
        """A pack of forty datasets is a claim about forty datasets; without
        the denominator the reader cannot tell whether that is the estate or a
        fifth of it, and every tool of this kind lets them assume the former."""
        described = Coverage(included=40, excluded=160, exclusion_reason="retired").describe()
        assert "40 of 200" in described
        assert "20%" in described
        assert "retired" in described

    def test_an_empty_estate_does_not_divide_by_zero(self) -> None:
        assert Coverage(included=0).describe()


class TestProvenanceIsOnThePage:
    """An artefact that cannot say which build produced it, from which tenant,
    at which instant, is a screenshot rather than evidence."""

    def test_the_pack_carries_instant_estate_author_and_build(self) -> None:
        html = declaration_pack(
            provenance=_provenance(), datasets=[_dataset()], coverage=Coverage(included=1)
        ).html
        assert "2026-09-08 06:30:00Z" in html
        assert "acme-bank" in html
        assert "alice" in html
        assert VERSION in html

    def test_the_version_comes_from_the_one_authority(self) -> None:
        """Not a string typed into a template. Every other version in the
        repository is a copy that can rot."""
        assert _provenance().version == VERSION

    def test_the_legal_notice_is_on_every_pack(self) -> None:
        for artefact in (
            declaration_pack(provenance=_provenance(), datasets=[], coverage=Coverage(included=0)),
            control_pack(provenance=_provenance(), controls=[], coverage=Coverage(included=0)),
        ):
            assert "Ashutosh Sinha" in artefact.html
            assert "Proprietary and confidential" in artefact.html


class TestTheCoverageStatementIsNeverSuppressed:
    def test_it_appears_even_when_the_pack_is_complete(self) -> None:
        """A reader who sees the box only on partial packs learns to skim it,
        and then misses the one that matters."""
        html = declaration_pack(
            provenance=_provenance(), datasets=[_dataset()], coverage=Coverage(included=1)
        ).html
        assert "What this document covers" in html

    def test_a_partial_pack_is_marked_as_partial(self) -> None:
        html = declaration_pack(
            provenance=_provenance(),
            datasets=[_dataset()],
            coverage=Coverage(included=1, excluded=9, exclusion_reason="retired"),
        ).html
        assert 'class="coverage partial"' in html


class TestDeclarationPack:
    def test_an_undeclared_grain_names_the_lost_control(self) -> None:
        """Not "grain: —". The reader of a pack cannot ask a follow-up
        question, so the consequence has to be printed."""
        html = declaration_pack(
            provenance=_provenance(),
            datasets=[_dataset(has_grain=False, grain_statement="", grain_attributes=[])],
            coverage=Coverage(included=1),
        ).html
        assert "no uniqueness or completeness control" in html

    def test_an_unconnected_dataset_is_listed_and_counted(self) -> None:
        """The interesting rows. A physical-first tool cannot produce them at
        all, because it only knows what it managed to crawl."""
        html = declaration_pack(
            provenance=_provenance(),
            datasets=[_dataset(is_bound=False)],
            coverage=Coverage(included=1),
        ).html
        assert "not connected" in html
        assert "1 of the datasets listed here are declared but not connected" in html

    def test_the_grain_sentence_is_preferred_to_the_column_list(self) -> None:
        """It is what the business wrote, and what the generated control quotes
        back. Reconstructing prose from column names produces a sentence nobody
        wrote and nobody will stand behind."""
        html = declaration_pack(
            provenance=_provenance(), datasets=[_dataset()], coverage=Coverage(included=1)
        ).html
        assert "one position per account per instrument per business day" in html

    def test_an_empty_estate_renders_rather_than_failing(self) -> None:
        html = declaration_pack(
            provenance=_provenance(), datasets=[], coverage=Coverage(included=0)
        ).html
        assert "Nothing declared" in html


class TestControlPack:
    def test_the_sql_is_printed(self) -> None:
        """The point of the document is that the platform is inspectable rather
        than trusted. A reader who cannot see the query is being asked to take
        the verdict on faith."""
        html = control_pack(
            provenance=_provenance(),
            controls=[
                {
                    "name": "positions_unique",
                    "dataset": "positions_eod",
                    "pql": "CHECK positions_eod HAS UNIQUE KEY (a, b)",
                    "description": "at most one row per a, b",
                    "plan_id": "ir:sha256:abc",
                    "metric_query": "SELECT count(*) FROM positions_eod",
                    "residual_validators": [],
                }
            ],
            coverage=Coverage(included=1),
        ).html
        assert "SELECT count(*) FROM positions_eod" in html
        assert "ir:sha256:abc" in html

    def test_an_incomplete_screen_is_disclosed_as_a_lower_bound(self) -> None:
        html = control_pack(
            provenance=_provenance(),
            controls=[
                {
                    "name": "c",
                    "dataset": "d",
                    "pql": "CHECK d.lei IS VALID LEI",
                    "description": "every lei is a valid LEI",
                    "plan_id": "ir:sha256:abc",
                    "metric_query": "SELECT 1",
                    "residual_validators": [{"validator": "lei", "column": "lei"}],
                }
            ],
            coverage=Coverage(included=1),
        ).html
        assert "does not decide the control on its own" in html
        assert "lower bound" in html

    def test_what_could_not_be_generated_is_printed_too(self) -> None:
        """Every tool of this kind lists what it generated. Without this
        section the set above looks complete when it is not."""
        html = control_pack(
            provenance=_provenance(),
            controls=[],
            unsatisfiable=[
                {
                    "dataset": "Positions",
                    "rule": "grain.uniqueness",
                    "declared": "one row per settlement_date",
                    "reason": "the grain names settlement_date, which this dataset lacks",
                }
            ],
            coverage=Coverage(included=0, excluded=1, exclusion_reason="nothing generated"),
        ).html
        assert "no control could be generated" in html
        assert "which this dataset lacks" in html
        assert "produced no control at all" in html

    def test_an_empty_control_pack_is_not_a_clean_bill_of_health(self) -> None:
        html = control_pack(
            provenance=_provenance(), controls=[], coverage=Coverage(included=0)
        ).html
        assert "not a clean bill of health" in html


class TestArtefactFile:
    def test_the_filename_sorts_chronologically_and_names_the_document(self) -> None:
        artefact = declaration_pack(
            provenance=_provenance(), datasets=[], coverage=Coverage(included=0)
        )
        assert artefact.filename == "20260908-063000-declaration-pack.html"

    def test_two_packs_for_the_same_day_do_not_collide(self) -> None:
        """A normal thing to produce, and silently overwriting the first is
        not an acceptable outcome for an evidence artefact."""
        morning = Artefact("Pack", "", Provenance("t", datetime(2026, 9, 8, 6, 0, tzinfo=UTC)))
        evening = Artefact("Pack", "", Provenance("t", datetime(2026, 9, 8, 18, 0, tzinfo=UTC)))
        assert morning.filename != evening.filename

    def test_it_writes_itself_to_disk(self, tmp_path: Path) -> None:
        artefact = declaration_pack(
            provenance=_provenance(), datasets=[_dataset()], coverage=Coverage(included=1)
        )
        path = artefact.write(tmp_path / "packs")
        assert path.read_text(encoding="utf-8") == artefact.html


class TestSelfContained:
    """A document that leaves the building must not depend on the console's
    stylesheet, its fonts, or anything on the network."""

    @pytest.fixture
    def html(self) -> str:
        return declaration_pack(
            provenance=_provenance(), datasets=[_dataset()], coverage=Coverage(included=1)
        ).html

    def test_the_stylesheet_is_inlined(self, html: str) -> None:
        assert "<style>" in html
        assert "@page" in html
        assert "<link" not in html

    def test_nothing_is_fetched_from_a_network(self, html: str) -> None:
        for marker in ("http://", "https://", "//cdn", "src="):
            assert marker not in html, marker

    def test_hostile_content_cannot_break_out(self) -> None:
        """Dataset names are user data, imported from dbt and read out of
        warehouse catalogues, and this document gets emailed."""
        html = declaration_pack(
            provenance=_provenance(),
            datasets=[_dataset(name="<script>alert(1)</script>")],
            coverage=Coverage(included=1),
        ).html
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_a_missing_template_variable_fails_loudly(self) -> None:
        """StrictUndefined, so a renamed field produces an error rather than a
        blank cell in a document somebody signs."""
        with pytest.raises(Exception, match=r"undefined|has no attribute|is undefined"):
            declaration_pack(
                provenance=_provenance(),
                datasets=[{"name": "only a name"}],
                coverage=Coverage(included=1),
            )


class TestPackaging:
    def test_the_report_templates_are_declared_package_data(self) -> None:
        """An installed wheel that carries the code and not the templates
        renders nothing, and passes every test run from a source checkout."""
        import fnmatch
        import tomllib

        from prama.report.render import TEMPLATES_DIR

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyproject.open("rb") as handle:
            patterns = tomllib.load(handle)["tool"]["setuptools"]["package-data"]["prama.report"]

        missing = [
            path.relative_to(TEMPLATES_DIR.parent).as_posix()
            for path in TEMPLATES_DIR.rglob("*")
            if path.is_file()
            and not any(
                fnmatch.fnmatch(path.relative_to(TEMPLATES_DIR.parent).as_posix(), pattern)
                for pattern in patterns
            )
        ]
        assert missing == [], missing
