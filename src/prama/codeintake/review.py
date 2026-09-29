"""What a change to ETL code does to lineage and to the controls resting on it.

Run on a pull request, before it merges:

    prama code review --base origin/main --head HEAD --format markdown

Both versions are taken from git (`git archive`, so nothing is checked out and
the working tree is untouched) and read by the same sandboxed reader intake
uses: parsed, never executed. Then four questions, in the order a reviewer asks
them:

* **What lineage changed?** Column edges added, removed, or whose transform
  changed. A copy becoming an aggregation is a change even though both files
  still "use" the column.
* **What does it reach?** The blast radius of every changed column, in the
  head's lineage, down to the dashboards.
* **Which controls lose their basis?** Lineage-derived proposals are computed
  for both versions. One present at the base and gone at the head rested on an
  edge the change removed; if a control with that identity is live, it now
  checks something the pipeline no longer does, and the review fails.
* **What does the change imply?** Proposals new at the head: the checks the new
  code owes, such as a join's `REFERENCES`.

Deterministic, and no model is asked anything.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import subprocess
import tarfile
import tempfile
import types
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from prama.codeintake.archive import IntakeRefused
from prama.lineage.graph import Column, Edge, LineageGraph, Transform

#: Rows in a markdown table before it is cut, with the count of the rest.
_TABLE_ROWS = 40


def extract(repo: Path, ref: str, into: Path) -> Path:
    """The tree at *ref*, written under *into*, without touching the working tree."""
    into.mkdir(parents=True, exist_ok=True)
    try:
        archive = subprocess.Popen(
            ["git", "-C", str(repo), "archive", "--format=tar", ref],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise IntakeRefused(
            "git is not available to read the two versions",
            remedy="Install git, or run the review where the repository is checked out.",
        ) from exc
    assert archive.stdout is not None
    try:
        with tarfile.open(fileobj=archive.stdout, mode="r|") as tar:
            # The data filter: no absolute paths, no links out, no device files.
            tar.extractall(into, filter="data")
    except tarfile.ReadError:
        pass  # nothing came out: git says why, below
    _, errors = archive.communicate()
    if archive.returncode != 0:
        raise IntakeRefused(
            f"git could not read {ref!r}: {errors.decode('utf-8', 'replace').strip()[:200]}",
            remedy="Name a commit, branch or tag that exists in this repository.",
            context={"ref": ref},
        )
    return into


def _rows(result: dict[str, Any]) -> list[Any]:
    """Worker edges as the rows `derive.lineage_controls.propose` reads."""
    from prama.codeintake.service import PARSED_METHODS

    return [
        types.SimpleNamespace(
            source_dataset=e["source"][0],
            source_column=e["source"][1],
            target_dataset=e["target"][0],
            target_column=e["target"][1],
            transform=e["transform"],
            expression=e.get("expression", ""),
            status="parsed" if e.get("method") in PARSED_METHODS else "inferred",
            unit=e.get("unit", ""),
        )
        for e in result.get("edges", [])
    ]


@dataclasses.dataclass(frozen=True, slots=True)
class Change:
    kind: str  # added | removed | retyped
    source: str
    target: str
    transform: str
    was: str = ""
    unit: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class Review:
    base: str
    head: str
    changes: tuple[Change, ...]
    #: Changed column -> the columns its change reaches, strongest first.
    impact: dict[str, list[str]]
    #: Proposals at the base and not the head, and new at the head.
    lost: tuple[Any, ...]
    implied: tuple[Any, ...]
    #: Live controls whose basis the change removed: identity -> name.
    broken: dict[str, str]
    gaps: int

    @property
    def fails(self) -> bool:
        return bool(self.broken)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "head": self.head,
            "changes": [dataclasses.asdict(c) for c in self.changes],
            "impact": self.impact,
            "lost": [_proposal(p) for p in self.lost],
            "implied": [_proposal(p) for p in self.implied],
            "broken": self.broken,
            "gaps_at_head": self.gaps,
            "fails": self.fails,
        }

    def to_markdown(self) -> str:
        counts = {
            k: sum(1 for c in self.changes if c.kind == k) for k in ("added", "removed", "retyped")
        }
        lines = [
            f"## Prama lineage review: `{self.base}` → `{self.head}`",
            "",
            f"**{counts['added']}** edges added, **{counts['removed']}** removed, "
            f"**{counts['retyped']}** changed in kind. "
            + (
                f"**{len(self.broken)} live control(s) lose their basis.**"
                if self.broken
                else "No live control loses its basis."
            ),
            "",
        ]
        if self.broken:
            lines += ["### Controls that lose their basis", ""]
            lines += [f"- `{identity}` {name}" for identity, name in sorted(self.broken.items())]
            lines.append("")
        if self.changes:
            lines += [
                "### Lineage that changed",
                "",
                "| | From | To | Transform |",
                "|---|---|---|---|",
            ]
            for c in self.changes[:_TABLE_ROWS]:
                kind = {"added": "+", "removed": "-", "retyped": "~"}[c.kind]
                how = f"{c.was} → {c.transform}" if c.kind == "retyped" else c.transform
                lines.append(f"| {kind} | `{c.source}` | `{c.target}` | {how} |")
            if len(self.changes) > _TABLE_ROWS:
                lines.append(f"| | *…and {len(self.changes) - _TABLE_ROWS} more* | | |")
            lines.append("")
        if self.impact:
            lines += ["### What the change reaches", ""]
            for column, reached in sorted(self.impact.items()):
                shown = ", ".join(f"`{r}`" for r in reached[:6])
                more = f" and {len(reached) - 6} more" if len(reached) > 6 else ""
                lines.append(f"- `{column}` → {shown or 'nothing downstream'}{more}")
            lines.append("")
        if self.implied:
            lines += ["### Controls this change implies (proposed, for review)", ""]
            lines += [f"- `{p.pql.split(' BECAUSE')[0]}`" for p in self.implied]
            lines.append("")
        if self.lost:
            lines += ["### Proposals the change retires", ""]
            lines += [f"- `{p.pql.split(' BECAUSE')[0]}`" for p in self.lost]
            lines.append("")
        if self.gaps:
            lines += [
                f"*{self.gaps} statement(s) at the head could not be read fully; see "
                "`prama code add-git` for the gaps.*",
                "",
            ]
        return "\n".join(lines)


def _identity_of(control: Any) -> str:
    """A live control's identity.

    A stored control version carries it on its control (`version.control.identity`),
    not on itself. Reading only `control.identity` matched every test double and
    no real estate, so a review against live controls could never fail.
    """
    own = getattr(control, "identity", None)
    if own:
        return str(own)
    return str(getattr(getattr(control, "control", None), "identity", "") or "")


def _proposal(p: Any) -> dict[str, str]:
    return {"identity": p.identity, "rule": p.rule, "dataset": p.dataset, "pql": p.pql}


def _key(row: Any) -> tuple[str, str]:
    return (
        f"{row.source_dataset}.{row.source_column}",
        f"{row.target_dataset}.{row.target_column}",
    )


def diff(base: Iterable[Any], head: Iterable[Any]) -> list[Change]:
    """Edges added, removed, and changed in kind, between two readings."""
    before: dict[tuple[str, str], set[str]] = {}
    after: dict[tuple[str, str], set[str]] = {}
    units: dict[tuple[str, str], str] = {}
    for row in base:
        before.setdefault(_key(row), set()).add(str(row.transform))
    for row in head:
        after.setdefault(_key(row), set()).add(str(row.transform))
        units.setdefault(_key(row), str(getattr(row, "unit", "")))
    changes: list[Change] = []
    for key in sorted(set(before) | set(after)):
        was, now = before.get(key, set()), after.get(key, set())
        if was == now:
            continue
        if not was:
            changes += [Change("added", *key, t, unit=units.get(key, "")) for t in sorted(now)]
        elif not now:
            changes += [Change("removed", *key, t) for t in sorted(was)]
        else:
            changes.append(
                Change(
                    "retyped",
                    *key,
                    ", ".join(sorted(now)),
                    ", ".join(sorted(was)),
                    unit=units.get(key, ""),
                )
            )
    return changes


def review(
    repo: Path,
    base: str,
    head: str,
    *,
    dialect: str = "ansi",
    live: Iterable[Any] = (),
    timeout: float = 300.0,
) -> Review:
    """Read both versions and answer the four questions. *live* is the estate's controls."""
    with tempfile.TemporaryDirectory(prefix="prama-review-") as scratch:
        base_root = extract(repo, base, Path(scratch) / "base")
        head_root = extract(repo, head, Path(scratch) / "head")
        return review_trees(
            base_root, head_root, base, head, dialect=dialect, live=live, timeout=timeout
        )


def review_trees(
    base_root: Path,
    head_root: Path,
    base: str,
    head: str,
    *,
    dialect: str = "ansi",
    live: Iterable[Any] = (),
    timeout: float = 300.0,
) -> Review:
    """The review of two trees already on disk, labelled *base* and *head*.

    What `review` does once the two versions are written out, and what the API
    does with two uploaded archives: the same sandboxed reader, never executed,
    and the same four questions.
    """
    from prama.codeintake.service import run_worker
    from prama.derive.lineage_controls import propose

    live = list(live)
    readings = {
        "base": run_worker(base_root, dialect, timeout=timeout),
        "head": run_worker(head_root, dialect, timeout=timeout),
    }
    before, after = _rows(readings["base"]), _rows(readings["head"])
    changes = diff(before, after)

    graph = LineageGraph()
    for row in after:
        graph.add(
            Edge(
                source=Column(row.source_dataset, row.source_column),
                target=Column(row.target_dataset, row.target_column),
                transform=Transform(row.transform),
                produced_by=str(getattr(row, "unit", "")),
            )
        )
    impact: dict[str, list[str]] = {}
    for change in changes:
        if change.kind == "removed":
            continue
        dataset, _, name = change.target.rpartition(".")
        radius = graph.blast_radius(Column(dataset, name))
        impact[change.target] = [r.column.qualified for r in radius.reached]

    at_base = {p.identity: p for p in propose(before, live)}
    at_head = {p.identity: p for p in propose(after, live)}
    lost = tuple(p for i, p in sorted(at_base.items()) if i not in at_head)
    implied = tuple(p for i, p in sorted(at_head.items()) if i not in at_base)
    by_identity = {_identity_of(c): c for c in live}
    broken = {
        p.identity: str(getattr(by_identity[p.identity], "name", "") or p.pql.split(" BECAUSE")[0])
        for p in lost
        if p.identity in by_identity
    }
    gaps = sum(len(u.get("gaps", [])) for u in readings["head"].get("units", []))
    return Review(
        base=base,
        head=head,
        changes=tuple(changes),
        impact=impact,
        lost=lost,
        implied=implied,
        broken=broken,
        gaps=gaps,
    )
