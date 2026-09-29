"""Baselines, and an honest account of which ones were actually run.

``docs/15 §4`` names five classes of baseline: declarative OSS, ML
observability, platform-native, enterprise DQ, and ablations of Prama. **None of
the external tools is run here.** Running Great Expectations or Soda Core
fairly means configuring each the way its own documentation recommends, ideally
reviewed by a practitioner of that tool, and a comparison configured by the
party that benefits from the result is not evidence. :data:`NOT_RUN` records
them by name so that a reader of any output from this module can see the
absence rather than infer coverage from a table of numbers.

What *is* here are the baselines that can be run honestly on this machine:
trivial bounds and ablations.

The **trivial bounds** exist because a benchmark without them cannot be read.
"Recall 0.82" means nothing until you know that alerting on every column scores
1.0 and that the corpus has a floor. They are not strawmen — they are the axes.

The **ablations** are the comparison ``docs/15`` calls the most important, and
the reason is that they answer the question a reviewer and a buyer both ask:
which of the claims is doing the work? A pattern-only detector is what a
schema-derived rule set gets you; if it scores within noise of the full system,
the semantic layer is not earning its place.

Every detector here is deterministic and inspectable. None of them is Prama:
they are reference points against which Prama's own detection is measured
elsewhere.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable
from typing import Any, Final

from prama.bench.corpus import Corpus, Family, Row, Scenario
from prama.bench.scoring import Alert, Score, score

__all__ = [
    "BASELINES",
    "NOT_RUN",
    "Baseline",
    "Comparison",
    "baseline",
    "compare",
]

#: Baselines named in the methodology and *not* run here. Listed rather than
#: omitted: a comparison table with four rows reads as four contenders, and a
#: reader has no way to know that eleven others were never attempted.
NOT_RUN: Final[dict[str, str]] = {
    "Great Expectations": "declarative OSS; needs a fair configuration by a practitioner",
    "Soda Core": "declarative OSS; same",
    "dbt tests + dbt-expectations": "declarative OSS; needs a dbt project to be meaningful",
    "Deequ": "declarative OSS; JVM, and a Spark cluster to be representative",
    "DQOps": "declarative OSS",
    "Evidently": "ML observability, open",
    "Elementary": "ML observability, open",
    "Snowflake DMFs": "platform-native; needs the platform",
    "Databricks Lakehouse Monitoring": "platform-native; needs the platform",
    "AWS Glue Data Quality": "platform-native; needs the platform",
    "HoloClean / Raha / Baran / ZeroED": "research error detection",
    "Splink / Zingg": "research entity resolution",
    "Metanome / Desbordante": "research constraint discovery",
    "Commercial ML observability platform": "licence permitting; otherwise a faithful "
    "reimplementation of its published method",
    "Established augmented-DQ suite": "needs a partner or evaluation licence",
}


@dataclasses.dataclass(frozen=True, slots=True)
class Baseline:
    """A detector, and an honest statement of what it stands for."""

    name: str
    #: ``bound`` (an axis, not a contender) or ``ablation`` (a claim removed).
    kind: str
    describes: str
    detect: Callable[[Corpus], tuple[Alert, ...]] = dataclasses.field(repr=False)

    def run(self, corpus: Corpus) -> Score:
        return score(corpus.defects, self.detect(corpus))


def _alert(corpus: Corpus, scenario: Scenario, column: str, detail: str) -> Alert:
    return Alert(dataset=corpus.dataset, column=column, window=scenario.window, detail=detail)


def _numbers(rows: Iterable[Row], column: str) -> list[float]:
    return [r[column] for r in rows if isinstance(r.get(column), int | float)]


def _detect_nothing(_: Corpus) -> tuple[Alert, ...]:
    return ()


def _detect_everything(corpus: Corpus) -> tuple[Alert, ...]:
    """Every column of every window.

    Perfect recall by construction, at the cost of an alert on everything that
    was fine. This is the shape of "something is wrong with this table", and
    the reason ``docs/15 §3.1`` insists on scoring the locus.
    """
    alerts = []
    for scenario in corpus.scenarios:
        columns: dict[str, None] = {}
        for row in (*scenario.clean, *scenario.rows):
            for key in row:
                columns.setdefault(key, None)
        for column in columns:
            alerts.append(_alert(corpus, scenario, column, "this column exists"))
    return tuple(alerts)


def _detect_schema_only(corpus: Corpus) -> tuple[Alert, ...]:
    """What comparing two schemas finds: columns that appeared or vanished.

    The honest floor for point-and-shoot tooling — no declarations, no history,
    no statistics.
    """
    alerts = []
    for scenario in corpus.scenarios:
        before = {key for row in scenario.clean for key in row}
        after = {key for row in scenario.rows for key in row}
        for column in sorted(before ^ after):
            alerts.append(_alert(corpus, scenario, column, "the set of columns changed"))
        # A column dropped from *some* rows is still in the union of keys, so
        # comparing key sets alone reports nothing. Presence in every row is
        # what a schema-derived check actually asserts.
        partial = sorted(
            column for column in before & after if not all(column in row for row in scenario.rows)
        )
        for column in partial:
            alerts.append(_alert(corpus, scenario, column, "the column is missing from some rows"))
    return tuple(alerts)


def _detect_patterns_only(corpus: Corpus) -> tuple[Alert, ...]:
    """Format and code-list checks derived from the schema, and nothing else.

    The ablation that matters most: this is what a generated rule set gets you
    without a semantic layer. Whatever it cannot see is the part the rest of
    the system has to justify.
    """
    alerts = []
    for scenario in corpus.scenarios:
        rows = scenario.rows
        if any(r.get("currency") not in {"GBP", "EUR", "USD"} for r in rows):
            alerts.append(_alert(corpus, scenario, "currency", "outside the code list"))
        if any(not isinstance(r.get("iban"), str) or not r["iban"][:2].isalpha() for r in rows):
            alerts.append(_alert(corpus, scenario, "iban", "does not match the IBAN pattern"))
        if any(r.get("amount") is None for r in rows):
            alerts.append(_alert(corpus, scenario, "amount", "null in a column declared not-null"))
        if any(not isinstance(r.get("amount"), int | float) for r in rows):
            alerts.append(_alert(corpus, scenario, "amount", "not a number"))
        if any(isinstance(r.get("party_name"), str) and "Ã" in r["party_name"] for r in rows):
            alerts.append(_alert(corpus, scenario, "party_name", "mojibake"))
    return tuple(alerts)


def _detect_statistics_only(corpus: Corpus) -> tuple[Alert, ...]:
    """Monitors with no declarations: outliers, range shifts, new categories."""
    alerts = []
    for scenario in corpus.scenarios:
        seen = _numbers(scenario.rows, "amount")
        base = _numbers(scenario.clean, "amount")
        if seen and base and max(seen) > max(base) * 1.5:
            alerts.append(_alert(corpus, scenario, "amount", "the maximum moved"))
        if {r.get("product") for r in scenario.rows} - {r.get("product") for r in scenario.clean}:
            alerts.append(_alert(corpus, scenario, "product", "a category nobody declared"))
        rates_now = {r.get("rate") for r in scenario.rows}
        rates_before = {r.get("rate") for r in scenario.clean}
        if len(rates_now) < len(rates_before):
            alerts.append(_alert(corpus, scenario, "rate", "the values stopped moving"))
    return tuple(alerts)


BASELINES: Final[tuple[Baseline, ...]] = (
    Baseline(
        name="detect-nothing",
        kind="bound",
        describes=(
            "The floor. Any claim that does not beat it is not a claim. Its "
            "precision is undefined rather than zero, which is the correct "
            "answer to 'how many of your alerts were right' when there were none."
        ),
        detect=_detect_nothing,
    ),
    Baseline(
        name="alert-on-everything",
        kind="bound",
        describes=(
            "Perfect recall at the column level, and useless. It is here "
            "because a recall figure cannot be read without it: the interesting "
            "question is always what precision was paid for that recall."
        ),
        detect=_detect_everything,
    ),
    Baseline(
        name="schema-only",
        kind="ablation",
        describes=(
            "What comparing two schemas finds. No declarations, no history, no "
            "statistics — the honest floor for point-and-shoot tooling."
        ),
        detect=_detect_schema_only,
    ),
    Baseline(
        name="patterns-only",
        kind="ablation",
        describes=(
            "Format and code-list rules derived from the schema. This is what a "
            "generated rule set gets you without a semantic layer, and whatever "
            "it cannot see is what the rest of the system has to justify."
        ),
        detect=_detect_patterns_only,
    ),
    Baseline(
        name="statistics-only",
        kind="ablation",
        describes=(
            "Monitors with no declarations. Finds shifts and outliers; blind to "
            "anything that is only wrong relative to a stated business rule."
        ),
        detect=_detect_statistics_only,
    ),
    Baseline(
        name="prama-declared",
        kind="system",
        describes=(
            "Prama's declared path: controls derived from an owner's declaration of "
            "the dataset, run per window by the reference interpreter. Written from "
            "the schema's domain, not tuned to the defects; no relationships, history "
            "or monitors, so what it cannot see is stated rather than hidden."
        ),
        detect=lambda corpus: _declared(corpus),
    ),
)


def _declared(corpus: Corpus) -> tuple[Alert, ...]:
    from prama.bench.declared import detect

    return detect(corpus)


def baseline(name: str) -> Baseline:
    for entry in BASELINES:
        if entry.name == name:
            return entry
    from prama.core.errors import ValidationError

    raise ValidationError(
        f"no such baseline: {name!r}",
        remedy=f"One of: {', '.join(b.name for b in BASELINES)}.",
    )


@dataclasses.dataclass(frozen=True, slots=True)
class Comparison:
    """Every baseline against one corpus, plus what was not run."""

    corpus: Corpus
    results: tuple[tuple[Baseline, Score], ...]

    @property
    def blind_families(self) -> dict[str, tuple[str, ...]]:
        """Per baseline, the families it found nothing in.

        The most useful column in the table. A detector's blind spots are the
        argument for whatever covers them, and they do not appear in an
        aggregate F1 at all.
        """
        blind: dict[str, tuple[str, ...]] = {}
        for entry, result in self.results:
            missed = tuple(
                family.value
                for family in Family
                if self.corpus.of_family(family)
                and not any(f.family == family.value and f.found for f in result.families)
            )
            blind[entry.name] = missed
        return blind

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus": self.corpus.to_dict(),
            "baselines": [
                {
                    "name": entry.name,
                    "kind": entry.kind,
                    "describes": entry.describes,
                    **result.to_dict(),
                }
                for entry, result in self.results
            ],
            "blind_families": self.blind_families,
            "not_run": NOT_RUN,
        }


def compare(corpus: Corpus, baselines: Iterable[Baseline] | None = None) -> Comparison:
    chosen = tuple(baselines) if baselines is not None else BASELINES
    return Comparison(corpus=corpus, results=tuple((b, b.run(corpus)) for b in chosen))
