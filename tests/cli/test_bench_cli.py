"""``prama bench`` — a number somebody can re-run.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io

from prama.cli.base import EXIT_OK, EXIT_USAGE, Application
from prama.cli.commands import all_commands
from prama.core import pjson


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    return Application(all_commands()).run(argv, out=out), out.getvalue()


class TestTaxonomy:
    def test_it_lists_the_classes_by_family(self) -> None:
        code, text = run(["bench", "taxonomy"])
        assert code == EXIT_OK
        assert "plausible-but-wrong" in text
        assert "semantic" in text

    def test_it_says_which_family_is_the_discriminator(self) -> None:
        _, text = run(["bench", "taxonomy"])
        assert "semantic family is the discriminator" in text

    def test_it_filters_by_family(self) -> None:
        code, text = run(["bench", "taxonomy", "--family", "temporal"])
        assert code == EXIT_OK
        assert "late-arrival" in text
        assert "plausible-but-wrong" not in text

    def test_json_carries_difficulty(self) -> None:
        code, text = run(["--json", "bench", "taxonomy"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert all("difficulty" in c for c in payload["classes"])


class TestRun:
    def test_the_seed_is_required(self, capsys) -> None:
        """A benchmark whose seed was not recorded cannot be re-run, and a
        number that cannot be re-run is an anecdote."""
        import pytest

        with pytest.raises(SystemExit):
            run(["bench", "run"])
        assert "--seed" in capsys.readouterr().err

    def test_it_scores_every_baseline(self) -> None:
        code, text = run(["bench", "run", "--seed", "42"])
        assert code == EXIT_OK
        for name in ("detect-nothing", "alert-on-everything", "patterns-only"):
            assert name in text

    def test_the_same_seed_gives_the_same_output(self) -> None:
        assert run(["bench", "run", "--seed", "42"]) == run(["bench", "run", "--seed", "42"])

    def test_the_seed_is_printed(self) -> None:
        _, text = run(["bench", "run", "--seed", "1234"])
        assert "seed 1234" in text

    def test_an_undefined_metric_prints_a_dash_not_a_zero(self) -> None:
        """A detector that raised no alerts has no precision. Printing 0.00
        would say it was wrong every time it spoke."""
        _, text = run(["bench", "run", "--seed", "42"])
        line = next(ln for ln in text.splitlines() if "detect-nothing" in ln and "bound" in ln)
        # Recall of 0.00 is defined and correct — it found none of them.
        # Precision and F1 are not defined at all, and print as dashes.
        metrics = line.split("bound", 1)[1]
        assert metrics.count("-") == 2
        assert "0.00" in metrics

    def test_it_names_the_baselines_that_were_not_run(self) -> None:
        """Every run, not behind a flag."""
        _, text = run(["bench", "run", "--seed", "42"])
        assert "NOT run here" in text
        assert "Great Expectations" in text
        assert "not a comparison" in text

    def test_it_reports_blind_spots(self) -> None:
        _, text = run(["bench", "run", "--seed", "42"])
        assert "Blind spots" in text
        assert "semantic" in text

    def test_nothing_runs_off_the_terminal(self) -> None:
        _, text = run(["bench", "run", "--seed", "42"])
        assert max(len(line) for line in text.splitlines()) < 80

    def test_json_carries_the_corpus_and_the_absences(self) -> None:
        code, text = run(["--json", "bench", "run", "--seed", "42"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert payload["corpus"]["seed"] == 42
        assert payload["not_run"]
        assert payload["blind_families"]
        # Two bounds, three ablations, and Prama's declared path.
        assert len(payload["baselines"]) == 6
        assert payload["baselines"][-1]["name"] == "prama-declared"

    def test_the_group_without_a_subcommand_says_what_it_offers(self) -> None:
        code, text = run(["bench"])
        assert code == EXIT_USAGE
        assert "taxonomy" in text
