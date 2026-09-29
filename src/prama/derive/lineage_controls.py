"""Control proposals derived from lineage.

Two deterministic rules, each stated so its proposal explains itself:

* **Carry a control downstream** (`lineage_propagated`). The business already
  asserts something about a column (not null, unique, a valid ISIN). Where
  that column is copied or renamed into another dataset, the same assertion
  should hold of the copy, and a pipeline that breaks it is a defect.
* **A key must come from its source** (`lineage_referential`). A key column
  copied across a hop gets a `REFERENCES` check back to where it came from:
  every value in the copy must exist in the source.
* **A copied amount must still agree** (`lineage_reconcile`). When a dataset
  copies both its key columns and an amount from one source, row for row, the
  two should reconcile: `RECONCILE copy AGAINST source ON (keys) COMPARING
  amount`. Only for copies at the same grain; an aggregated amount is not
  proposed, because comparing a total with its detail rows would find breaks
  that are not there. Where the copy is filtered, the same filter is applied
  to the source (`AGAINST source WHERE …`), so the rows it dropped are not
  reported as missing; a filter that cannot be carried over holds the proposal.
* **Every row must find its match** (`lineage_join`). Where a dataset is built
  by joining another on a key, a row whose key has no match is dropped by an
  inner join, or arrives with nothing joined to it by a left join, and in
  neither case does anything fail. So the driving side's key gets a
  `REFERENCES` check against the side it is joined to: the defect case study 8
  found only at its source, now caught where it happens.
* **A looked-up key must be unique** (`lineage_join_unique`). If the table a
  join looks up holds two rows for one key, every matching row is counted
  twice, and nothing fails either. The key is every column the statement joins
  that table on, so a composite key is checked as one.

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

#: Column names that hold an amount worth reconciling.
_AMOUNT = re.compile(
    r"(amount|amt|notional|balance|exposure|value|price|qty|quantity|total|pnl|mtm)", re.I
)


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
    edges = list(edges)  # read by three rules
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
    out.update(_reconciliations(edges))
    out.update(_joins(edges))
    out.update(_fan_outs(edges))
    return sorted(out.values(), key=lambda p: (p.dataset, p.rule, p.identity))


def _reconciliations(edges: Iterable[Any]) -> dict[str, LineageProposal]:
    by_pair: dict[tuple[str, str], list[Any]] = {}
    filtered: dict[tuple[str, str], list[Any]] = {}
    for edge in edges:
        if edge.transform == "filter":
            filtered.setdefault((edge.source_dataset, edge.target_dataset), []).append(edge)
        if edge.transform in _CARRIED and edge.source_dataset != edge.target_dataset:
            by_pair.setdefault((edge.source_dataset, edge.target_dataset), []).append(edge)
    out: dict[str, LineageProposal] = {}
    for (source, target), carried in sorted(by_pair.items()):
        keys = sorted(
            {(e.target_column, e.source_column) for e in carried if _KEY.search(e.target_column)}
        )
        amounts = sorted(
            {
                (e.target_column, e.source_column)
                for e in carried
                if _AMOUNT.search(e.target_column) and not _KEY.search(e.target_column)
            }
        )
        if not keys or not amounts:
            continue
        held = (
            "a lineage edge it rests on is inferred; confirm it on the Lineage page first"
            if any(e.status == "inferred" for e in carried)
            else ""
        )
        # The copy keeps only the source rows that pass its filter. The same
        # filter goes on the source side, or every row it dropped would be
        # reported as missing. Only a condition the parser could carry over
        # (one table, one condition) can be applied; anything else is held.
        against_where = ""
        filters = filtered.get((source, target), [])
        conditions = {str(e.expression)[len("WHERE ") :] for e in filters}
        unmovable = [e for e in filters if not str(e.expression).startswith("WHERE ")]
        if not held and filters and (unmovable or len(conditions) != 1):
            held = (
                f"{target} keeps only the rows of {source} that pass a filter on "
                f"{', '.join(sorted({e.source_column for e in filters}))}, and the condition "
                "could not be carried over; a reconciliation would report every filtered "
                "row as missing"
            )
        elif filters:
            against_where = f" WHERE {next(iter(conditions))}"
        on = ", ".join(t if t == s else f"{t} = {s}" for t, s in keys)
        for mine, theirs in amounts:
            compared = mine if mine == theirs else f"{mine} = {theirs}"
            # A copy is exact: the tolerance is zero, stated, because a
            # reconciliation with no bound at all cannot run.
            reason = f"BECAUSE 'lineage: {target} copies {mine} and its keys from {source}'"
            head = f"RECONCILE {quote_dataset(target)} AGAINST {quote_dataset(source)}"
            tail = f" ON ({on}) COMPARING {compared} WITHIN 0 {reason}"
            pql = _checked(head + against_where + tail) if against_where else None
            deferred = held
            if pql is None:
                if against_where and not held:
                    deferred = (
                        f"{target} keeps only the rows of {source} where "
                        f"{against_where[7:]}, which PQL cannot state; a reconciliation "
                        "would report every filtered row as missing"
                    )
                pql = _checked(head + tail)
            if pql is None:
                continue
            key = _identity("reconcile", source, target, mine)
            out[key] = LineageProposal(
                identity=key,
                rule="lineage_reconcile",
                dataset=target,
                pql=pql,
                sentence=(
                    f"{target} copies {mine} and its key from {source} row for row, so the "
                    f"two should agree on it; a difference is a break."
                ),
                deferred_because=deferred,
            )
    return out


#: ``<kind> join: <dataset>.<column> = <dataset>.<column>``, as
#: `prama.lineage.parsed` writes it on a join-key edge.
_PAIRING = re.compile(r"^(?P<kind>inner|left) join: (?P<driving>\S+) = (?P<looked_up>\S+)$")


def _joins(edges: Iterable[Any]) -> dict[str, LineageProposal]:
    """A REFERENCES check wherever a dataset is built by joining on a key."""
    by_join: dict[tuple[str, str], list[Any]] = {}
    for edge in edges:
        if edge.transform == "join_key" and _PAIRING.match(str(edge.expression)):
            by_join.setdefault((edge.target_dataset, str(edge.expression)), []).append(edge)
    out: dict[str, LineageProposal] = {}
    for (target, expression), found in sorted(by_join.items()):
        match = _PAIRING.match(expression)
        assert match is not None  # filtered above
        kind = match["kind"]
        driving, _, key = match["driving"].rpartition(".")
        looked_up, _, theirs = match["looked_up"].rpartition(".")
        effect = (
            f"is dropped from {target}"
            if kind == "inner"
            else f"reaches {target} with nothing joined to it"
        )
        pql = _checked(
            f"CHECK {quote_dataset(driving)}.{key} REFERENCES "
            f"{quote_dataset(looked_up)}.{theirs} DIMENSION integrity "
            f"BECAUSE 'lineage: {target} {kind}-joins {driving} to {looked_up} on {key}; a "
            f"row with no match {effect}, and nothing fails'"
        )
        if pql is None:
            continue
        identity = _identity("join", f"{driving}.{key}", f"{looked_up}.{theirs}")
        out[identity] = LineageProposal(
            identity=identity,
            rule="lineage_join",
            dataset=driving,
            pql=pql,
            sentence=(
                f"{target} {kind}-joins {driving} to {looked_up} on {key}. A {driving} row "
                f"whose {key} has no match in {looked_up} {effect}, silently."
            ),
            deferred_because=(
                "a lineage edge it rests on is inferred; confirm it on the Lineage page first"
                if any(e.status == "inferred" for e in found)
                else ""
            ),
        )
    return out


def _fan_outs(edges: Iterable[Any]) -> dict[str, LineageProposal]:
    """A uniqueness check on the columns each statement looks a table up by."""
    keys: dict[tuple[str, str, str, str], set[str]] = {}
    inferred: set[tuple[str, str, str, str]] = set()
    for edge in edges:
        match = _PAIRING.match(str(edge.expression)) if edge.transform == "join_key" else None
        if match is None:
            continue
        driving = match["driving"].rpartition(".")[0]
        looked_up, _, column = match["looked_up"].rpartition(".")
        group = (edge.target_dataset, str(getattr(edge, "produced_by", "")), driving, looked_up)
        keys.setdefault(group, set()).add(column)
        if edge.status == "inferred":
            inferred.add(group)
    out: dict[str, LineageProposal] = {}
    for group, columns in sorted(keys.items()):
        target, _, driving, looked_up = group
        key = ", ".join(sorted(columns))
        pql = _checked(
            f"CHECK {quote_dataset(looked_up)} HAS UNIQUE KEY ({key}) DIMENSION uniqueness "
            f"BECAUSE 'lineage: {target} looks up {looked_up} on {key}; a second row per key "
            f"would count every matching {driving} row twice'"
        )
        if pql is None:
            continue
        identity = _identity("join-unique", looked_up, key)
        out[identity] = LineageProposal(
            identity=identity,
            rule="lineage_join_unique",
            dataset=looked_up,
            pql=pql,
            sentence=(
                f"{target} looks {looked_up} up on {key}. Two rows for one key would "
                f"double every matching {driving} row, silently."
            ),
            deferred_because=(
                "a lineage edge it rests on is inferred; confirm it on the Lineage page first"
                if group in inferred
                else ""
            ),
        )
    return out
