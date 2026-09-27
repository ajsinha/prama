"""Control proposals derived from lineage.

Two deterministic rules, each stated so its proposal explains itself:

* **Carry a control downstream** (`lineage_propagated`). The business already
  asserts something about a column (not null, unique, a valid ISIN). Where
  that column is copied or renamed into another dataset, the same assertion
  should hold of the copy, and a pipeline that breaks it is a defect.
* **A key must come from its source** (`lineage_referential`). A key column
  copied across a hop gets a `REFERENCES` check back to where it came from:
  every value in the copy must exist in the source.

Proposals from an `inferred` edge are held until a person confirms the edge;
a proposal built on a guessed edge would propose a guessed control. Nothing
here decides a verdict: a person accepts a proposal, and the deterministic
engine runs it (CON-007).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Iterable
from typing import Any

from prama.core.errors import PramaError
from prama.pql.ast import quote_dataset
from prama.pql.parser import parse_control

#: Column names that are keys, by the conventions the estates use.
_KEY = re.compile(r"(^id$|_id$|_key$|_code$|^code$|_ref$)", re.IGNORECASE)

#: Transforms that leave a value essentially itself.
_CARRIED = ("identity", "rename")


@dataclasses.dataclass(frozen=True, slots=True)
class LineageProposal:
    identity: str
    rule: str
    dataset: str
    pql: str
    sentence: str
    deferred_because: str = ""


def _identity(*parts: str) -> str:
    return "lineage-" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def _checked(pql: str) -> str | None:
    try:
        parse_control(pql)
    except PramaError:
        return None
    return pql


def propose(edges: Iterable[Any], controls: Iterable[Any]) -> list[LineageProposal]:
    """Proposals from lineage *edges* (stored rows) and the estate's live *controls*."""
    by_dataset: dict[str, list[Any]] = {}
    for control in controls:
        by_dataset.setdefault(control.dataset, []).append(control)
    out: dict[str, LineageProposal] = {}
    for edge in edges:
        if edge.transform not in _CARRIED:
            continue
        held = (
            "the lineage edge it rests on is inferred; confirm the edge on the Lineage page first"
            if edge.status == "inferred"
            else ""
        )
        source = f"{edge.source_dataset}.{edge.source_column}"
        target = f"{edge.target_dataset}.{edge.target_column}"
        written_source = f"{quote_dataset(edge.source_dataset)}.{edge.source_column}"
        written_target = f"{quote_dataset(edge.target_dataset)}.{edge.target_column}"
        for control in by_dataset.get(edge.source_dataset, []):
            text = control.pql or ""
            spelled = next(
                (
                    form
                    for form in (written_source, source)
                    if len(re.findall(re.escape(form) + r"\b", text)) == 1
                ),
                None,
            )
            if spelled is None:
                continue  # not a one-column assertion about this column
            pql = _checked(re.sub(re.escape(spelled) + r"\b", written_target, text, count=1))
            if pql is None:
                continue
            origin = getattr(control, "identity", None) or control.control_id
            key = _identity("propagated", str(origin), target)
            out[key] = LineageProposal(
                identity=key,
                rule="lineage_propagated",
                dataset=edge.target_dataset,
                pql=pql,
                sentence=(
                    f"{target} is copied from {source}, which already has the control "
                    f"{control.name or origin!r}; the copy should hold it too."
                ),
                deferred_because=held,
            )
        if _KEY.search(edge.target_column) and edge.source_dataset != edge.target_dataset:
            pql = _checked(
                f"CHECK {written_target} REFERENCES {written_source} "
                f"BECAUSE 'lineage: every {edge.target_column} is copied from {source}'"
            )
            if pql is not None:
                key = _identity("referential", source, target)
                out[key] = LineageProposal(
                    identity=key,
                    rule="lineage_referential",
                    dataset=edge.target_dataset,
                    pql=pql,
                    sentence=f"Every {target} is copied from {source}, so each must exist there.",
                    deferred_because=held,
                )
    return sorted(out.values(), key=lambda p: (p.dataset, p.rule, p.identity))
