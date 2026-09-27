"""Power BI models: Power Query sources, native SQL and DAX, and what is a gap.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from prama.lineage import powerbi

MODEL = (
    Path(__file__).resolve().parents[1] / "fixtures" / "code" / "bankco-etl" / "bi" / "model.bim"
)


def _pbit(schema: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("DataModelSchema", json.dumps(schema).encode("utf-16-le"))
    return buffer.getvalue()


def _edges(extraction: powerbi.Extraction) -> dict[tuple[str, str], str]:
    return {(e.source.qualified, e.target.qualified): e.transform.value for e in extraction.edges}


def test_a_pbit_and_a_model_bim_give_the_same_lineage() -> None:
    schema = json.loads(MODEL.read_text())
    from_bim = powerbi.extract(powerbi.schema_of(MODEL.read_bytes(), "model.bim"), name="model")
    from_pbit = powerbi.extract(powerbi.schema_of(_pbit(schema), "risk.pbit"), name="risk")
    assert _edges(from_bim) == _edges(from_pbit)


def test_renames_aggregates_and_derivations_are_told_apart() -> None:
    edges = _edges(powerbi.extract(json.loads(MODEL.read_text()), name="m"))
    p = "powerbi.risk_dashboard"
    assert edges[("mart.positions.exposure_usd", f"{p}.positions.exposure")] == "rename"
    assert edges[("mart.positions.account_id", f"{p}.positions.account_id")] == "identity"
    assert edges[(f"{p}.positions.exposure", f"{p}.positions.total exposure")] == "aggregated"
    assert edges[(f"{p}.var.notional", f"{p}.positions.exposure per var")] == "derived"


def test_an_unfollowed_source_is_a_gap_not_a_guess() -> None:
    extraction = powerbi.extract(json.loads(MODEL.read_text()), name="m")
    assert not any("fx_feed" in e.target.dataset for e in extraction.edges)
    assert any("FX Feed" in g.detail and "Web.Contents" in g.detail for g in extraction.gaps)
