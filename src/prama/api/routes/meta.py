"""Health, version and capability routes.

``/capabilities`` exists so a client can degrade gracefully rather than
discovering a missing feature through a 404 in production.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from fastapi import APIRouter

from prama.api.deps import Db
from prama.api.schemas import CapabilitiesOut, HealthOut
from prama.connect.builtin import BUILTIN
from prama.db.settings import DbSettings
from prama.semantic.relationships import RelationshipKind
from prama.version import IR_VERSION, SCHEMA_VERSION, VERSION

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthOut)
async def health(database: Db) -> HealthOut:
    """A liveness probe that actually touches the database."""
    state = await database.health()
    return HealthOut(
        status="ok",
        version=VERSION,
        schema_version=SCHEMA_VERSION,
        dialect=str(state["dialect"]),
        schema_file=str(state["schema_file"]),
    )


def _features() -> dict[str, bool]:
    """What this build can actually do, asked rather than asserted.

    The comment this replaces read: "Honest about what exists. A client that
    trusts this and finds it wrong will never trust it again." It then declared
    `pql`, `execution`, `evidence`, `monitoring`, `reconciliation` and
    `connectors` all `False`, annotated with the wave each was due in — and
    every one of them shipped waves ago. A client integrating against this would
    have refused to use features that work, which is the same defect as
    overclaiming and harder to notice because it errs quietly.

    So each answer is derived from the thing itself. A feature that is removed
    stops reporting `True` without anybody remembering to edit a dict, which is
    the failure mode a restated list has and this does not.
    """
    from importlib.util import find_spec

    def importable(module: str) -> bool:
        try:
            return find_spec(module) is not None
        except (ImportError, ValueError):  # pragma: no cover - a broken package
            return False

    from prama.pql.library import FUNCTIONS

    return {
        "semantic_layer": importable("prama.semantic"),
        "bitemporal_history": importable("prama.db.temporal"),
        "gitops": importable("prama.semantic.gitops"),
        "estate_maturity": importable("prama.semantic.services.estate"),
        "conflict_detection": importable("prama.semantic.services.estate"),
        "connectors": bool(BUILTIN),
        # Not merely that the package imports: that the language has functions
        # in it, which is what a client asking "can this compile PQL" means.
        "pql": bool(FUNCTIONS.names()),
        "execution": importable("prama.execute.run"),
        "evidence": importable("prama.evidence.ledger"),
        "monitoring": importable("prama.monitor.drift"),
        "reconciliation": importable("prama.recon.engine"),
    }


@router.get("/capabilities", response_model=CapabilitiesOut)
async def capabilities() -> CapabilitiesOut:
    return CapabilitiesOut(
        version=VERSION,
        ir_version=IR_VERSION,
        schema_version=SCHEMA_VERSION,
        dialects=list(DbSettings.SUPPORTED),
        relationship_kinds=[k.value for k in RelationshipKind],
        features=_features(),
    )
