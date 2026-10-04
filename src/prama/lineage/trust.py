"""Trust along the persisted lineage, derived from evidence.

`prama.score.trust.TrustPropagator` computes how far a column can be trusted
given its own evidence and everything upstream of it. It had no caller outside
the tests, because no graph was persisted to hand it (docs/corpus/23 §1, E1). This
supplies both halves from what Prama already stores: the lineage graph from the
lineage store, and each dataset's local trust from the latest verdict of every
control over it.

Local trust is derived, never typed: a passing control contributes 1.0, a
failing one the fraction of rows that did not violate it, and a dataset takes
its weakest control. A dataset nothing has examined contributes nothing, so its
columns inherit from upstream alone.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from prama.lineage.graph import Column, LineageGraph
from prama.score.trust import Trust, TrustPropagator


def dataset_trust(records: Iterable[Any]) -> dict[str, float]:
    """Each dataset's weakest control, from the latest record of every control."""
    scores: dict[str, float] = {}
    for record in records:
        dataset = str(getattr(record, "dataset", "") or "")
        if not dataset:
            continue
        verdict = str(getattr(record, "verdict", ""))
        if verdict == "pass":
            score = 1.0
        elif verdict == "fail":
            metrics = dict(getattr(record, "metrics", {}) or {})
            scanned = float(metrics.get("scanned_rows") or 0)
            bad = float(metrics.get("violating_rows") or 0)
            score = max(0.0, 1.0 - bad / scanned) if scanned else 0.0
        else:
            continue  # an error or an unknown verdict is not evidence of quality
        scores[dataset] = min(score, scores.get(dataset, 1.0))
    return scores


def local_trust(graph: LineageGraph, by_dataset: Mapping[str, float]) -> dict[Column, float]:
    """Every graph column of an examined dataset, at that dataset's trust."""
    return {
        column: by_dataset[column.dataset]
        for column in graph.columns
        if column.dataset in by_dataset
    }


def trust_of(column: Column, graph: LineageGraph, records: Iterable[Any]) -> Trust:
    """*column*'s trust, from its own evidence and everything upstream."""
    local = local_trust(graph, dataset_trust(records))
    return TrustPropagator(graph).trust(column, local)
