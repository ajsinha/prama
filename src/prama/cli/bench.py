"""``prama bench`` — the labelled corpus, and what a detector scores on it.

Runs without a database and without a network, so a result can be reproduced
from a change ticket by somebody who has installed nothing else.

The seed is required. A benchmark whose seed was not recorded cannot be
re-run, and a number that cannot be re-run is an anecdote.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import textwrap
from typing import Any

from prama.cli.base import EXIT_OK, Command, CommandContext, CommandGroup
from prama.core.errors import ValidationError


class BenchTaxonomyCommand(Command):
    name = "taxonomy"
    help = "the defect classes a corpus can plant, by family and difficulty"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--family", help="one family only")

    def run(self, ctx: CommandContext) -> int:
        from prama.bench.corpus import CLASSES, Family

        chosen = CLASSES
        if ctx.args.family:
            try:
                wanted = Family(ctx.args.family.lower())
            except ValueError:
                # `Family("wizard")` raises a bare ValueError that reaches the
                # terminal as a stack trace. The refusal names the families
                # rather than making the reader find them. QA round 3, Q-68.
                raise ValidationError(
                    f"{ctx.args.family!r} is not a defect family",
                    remedy="One of: " + ", ".join(f.value for f in Family) + ".",
                    context={"family": ctx.args.family},
                ) from None
            chosen = tuple(c for c in CLASSES if c.family is wanted)

        if ctx.json_output:
            ctx.emit_json({"classes": [c.to_dict() for c in chosen]})
            return EXIT_OK

        ctx.emit(f"{len(chosen)} defect class(es) (docs/15 §2.1)")
        ctx.emit()
        for family in Family:
            entries = [c for c in chosen if c.family is family]
            if not entries:
                continue
            ctx.emit(f"{family.value}")
            for entry in entries:
                ctx.emit(f"  {entry.name:32} {entry.difficulty.value:12} {entry.description}")
            ctx.emit()
        ctx.emit("The semantic family is the discriminator: those defects pass every")
        ctx.emit("format and range check, and only a declared relationship sees them.")
        return EXIT_OK


class BenchRunCommand(Command):
    name = "run"
    help = "build a corpus and score every baseline against it"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--seed", type=int, required=True, help="required; recorded in output")
        parser.add_argument("--rows", type=int, default=200, help="rows per scenario")
        parser.add_argument(
            "--rate", type=float, default=0.05, help="share of rows each class attempts"
        )

    def run(self, ctx: CommandContext) -> int:
        from prama.bench.baselines import NOT_RUN, compare
        from prama.bench.corpus import build

        # The library refuses a bad rate or row count with `ValueError`, which is
        # Python's meaning for "right type, wrong value" and what a benchmark
        # script driving `prama.bench.corpus` would catch. `Application.run`
        # translates only `PramaError`, so without this the refusal reached the
        # terminal as a stack trace (QA `Q-68`).
        #
        # Translated *here*, at the boundary, rather than in the library: raising
        # the taxonomy from `build()` fixed the terminal and broke every
        # `except ValueError` caller, which is `Q-77`. The remedy belongs here
        # anyway — this layer knows the flags are called `--rate` and `--rows`,
        # and the library does not.
        try:
            corpus = build(seed=ctx.args.seed, rows=ctx.args.rows, rate=ctx.args.rate)
        except ValueError as exc:
            bad_rate = not 0 < ctx.args.rate <= 1
            raise ValidationError(
                str(exc),
                remedy=(
                    "Pass --rate above 0 and at most 1, as in --rate 0.05 for five percent."
                    if bad_rate
                    else "Pass --rows with a positive count, as in --rows 10000."
                ),
                context=({"rate": ctx.args.rate} if bad_rate else {"rows": ctx.args.rows}),
            ) from None
        comparison = compare(corpus)

        if ctx.json_output:
            ctx.emit_json(comparison.to_dict())
            return EXIT_OK

        summary = corpus.to_dict()
        ctx.emit(
            f"Corpus: seed {corpus.seed}, {summary['scenarios']} scenarios "
            f"of {summary['rows_per_scenario']} rows, {corpus.planted} defect(s) planted"
        )
        ctx.emit(
            "  by difficulty: " + ", ".join(f"{k} {v}" for k, v in summary["by_difficulty"].items())
        )
        if corpus.barren:
            # Loud, because a class that plants nothing is recall a detector is
            # credited with never having had to earn.
            ctx.emit()
            ctx.emit("  planted nothing this run:")
            for name, why in corpus.barren:
                ctx.emit(f"    {name}: {why}")
        ctx.emit()

        header = f"  {'baseline':<22}{'kind':<11}{'found':>8}{'prec':>8}{'recall':>8}{'f1':>7}"
        ctx.emit(header)
        for entry, result in comparison.results:
            payload: dict[str, Any] = result.to_dict()
            ctx.emit(
                f"  {entry.name:<22}{entry.kind:<11}"
                f"{payload['found']:>4}/{payload['planted']:<3}"
                f"{_num(payload['precision']):>8}{_num(payload['recall']):>8}"
                f"{_num(payload['f1']):>7}"
            )
        ctx.emit()

        ctx.emit("Blind spots — families in which the detector found nothing:")
        for name, families in comparison.blind_families.items():
            listed = ", ".join(families) or "none"
            wrapped = textwrap.wrap(listed, width=50) or ["none"]
            ctx.emit(f"  {name:<22}{wrapped[0]}")
            for line in wrapped[1:]:
                ctx.emit(f"  {'':<22}{line}")
        ctx.emit()
        ctx.emit("A detector's blind spots are the argument for whatever covers")
        ctx.emit("them, and they do not appear in an aggregate F1 at all.")
        ctx.emit()

        # Printed every run, not behind a flag. A five-row table reads as five
        # contenders, and nothing in it says fifteen others were never tried.
        ctx.emit(f"NOT run here ({len(NOT_RUN)} baselines named in docs/15 §4):")
        for line in textwrap.wrap(", ".join(sorted(NOT_RUN)), width=72):
            ctx.emit(f"  {line}")
        ctx.emit()
        ctx.emit("Configuring a competitor is a job for someone incentivised to make it")
        ctx.emit("look good. These numbers are bounds and ablations, not a comparison.")
        return EXIT_OK


def _num(value: float | None) -> str:
    """A number, or a dash where the metric is undefined.

    Undefined is not zero: a detector that raised no alerts has no precision,
    and printing 0.00 would say it was wrong every time it spoke.
    """
    return "-" if value is None else f"{value:.2f}"


class BenchCommand(CommandGroup):
    name = "bench"
    help = "the labelled defect corpus, and what scores on it"

    def commands(self) -> list[Command]:
        return [BenchTaxonomyCommand(), BenchRunCommand()]


__all__: list[str] = ["BenchCommand"]
