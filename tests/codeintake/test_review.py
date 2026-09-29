"""The change-impact review, on a real git repository with two commits.

The base is case study 8's ETL. The head makes two changes a reviewer should
hear about: staging now writes ``ABS(notional_amt)``, so the notional is no
longer a copy (and the control carried onto it loses its basis), and the mart
joins a new rating table, which implies a check that every account has one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import shutil
import subprocess
import types
from pathlib import Path

import pytest

from prama.codeintake.review import review

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

STAGE = """INSERT INTO stg.trades (trade_id, account_id, notional, ccy)
SELECT t.id, t.acct, {notional}, t.currency FROM raw.trades t WHERE t.status = 'BOOKED';
"""
MART = """CREATE VIEW mart.positions AS
SELECT s.account_id AS account_id, SUM(s.notional * fx.rate) AS exposure_usd{extra}
FROM stg.trades s JOIN ref.fx_rates fx ON s.ccy = fx.ccy{join}
GROUP BY s.account_id{group};
"""
RAW_CONTROL = types.SimpleNamespace(
    identity="raw:notional-non-negative",
    control_id="c-raw",
    name="raw notional non-negative",
    dataset="raw.trades",
    pql="CHECK \"raw.trades\".notional_amt >= 0 BECAUSE 'a size'",
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "etl"
    (root / "sql").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "sql" / "01_stage.sql").write_text(STAGE.format(notional="t.notional_amt"))
    (root / "sql" / "02_mart.sql").write_text(MART.format(extra="", join="", group=""))
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    (root / "sql" / "01_stage.sql").write_text(STAGE.format(notional="ABS(t.notional_amt)"))
    (root / "sql" / "02_mart.sql").write_text(
        MART.format(
            extra=", r.grade AS grade",
            join=" JOIN ref.ratings r ON s.account_id = r.account_id",
            group=", r.grade",
        )
    )
    _git(root, "commit", "-q", "-am", "head")
    return root


def test_a_copy_that_becomes_a_derivation_is_a_change_with_reach(repo: Path) -> None:
    result = review(repo, "HEAD~1", "HEAD", live=[RAW_CONTROL])
    retyped = [c for c in result.changes if c.kind == "retyped"]
    assert [(c.source, c.target, c.was, c.transform) for c in retyped] == [
        ("raw.trades.notional_amt", "stg.trades.notional", "identity", "derived")
    ]
    assert "mart.positions.exposure_usd" in result.impact["stg.trades.notional"]
    added = {(c.source, c.target) for c in result.changes if c.kind == "added"}
    assert ("ref.ratings.grade", "mart.positions.grade") in added


def test_the_change_implies_a_check_at_its_new_join(repo: Path) -> None:
    result = review(repo, "HEAD~1", "HEAD", live=[RAW_CONTROL])
    implied = [p.pql for p in result.implied if p.rule == "lineage_join"]
    assert any('"stg.trades".account_id REFERENCES "ref.ratings".account_id' in q for q in implied)


def test_a_live_control_that_loses_its_basis_fails_the_review(repo: Path) -> None:
    """Counterfactual first: with only the raw control live, nothing is broken."""
    alone = review(repo, "HEAD~1", "HEAD", live=[RAW_CONTROL])
    assert not alone.fails
    (carried,) = [p for p in alone.lost if p.rule == "lineage_propagated"]
    accepted = types.SimpleNamespace(
        identity=carried.identity,
        control_id="c-stg",
        name="staging notional non-negative",
        dataset="stg.trades",
        pql=carried.pql,
    )
    result = review(repo, "HEAD~1", "HEAD", live=[RAW_CONTROL, accepted])
    assert result.fails and result.broken == {carried.identity: "staging notional non-negative"}
    report = result.to_markdown()
    assert "1 live control(s) lose their basis" in report
    assert "raw.trades.notional_amt" in report and "identity → derived" in report


def test_an_unknown_ref_is_refused_with_the_ref_named(repo: Path) -> None:
    from prama.codeintake.archive import IntakeRefused

    with pytest.raises(IntakeRefused, match="no-such-branch"):
        review(repo, "no-such-branch", "HEAD")


def test_the_working_tree_is_untouched(repo: Path) -> None:
    before = (repo / "sql" / "01_stage.sql").read_text()
    review(repo, "HEAD~1", "HEAD")
    assert (repo / "sql" / "01_stage.sql").read_text() == before
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True
    )
    assert status.stdout == ""
