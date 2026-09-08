"""Health, version and capability routes.

``/capabilities`` exists so a client can degrade gracefully rather than
discovering a missing feature through a 404 in production.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from fastapi import APIRouter

from prama.api.deps import Db
from prama.api.schemas import CapabilitiesOut, HealthOut
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


@router.get("/capabilities", response_model=CapabilitiesOut)
async def capabilities() -> CapabilitiesOut:
    return CapabilitiesOut(
        version=VERSION,
        ir_version=IR_VERSION,
        schema_version=SCHEMA_VERSION,
        dialects=list(DbSettings.SUPPORTED),
        relationship_kinds=[k.value for k in RelationshipKind],
        features={
            # Honest about what exists. A client that trusts this and finds it
            # wrong will never trust it again.
            "semantic_layer": True,
            "bitemporal_history": True,
            "gitops": True,
            "estate_maturity": True,
            "conflict_detection": True,
            "connectors": False,  # Wave 3
            "pql": False,  # Wave 4
            "execution": False,  # Wave 5
            "evidence": False,  # Wave 5
            "monitoring": False,  # Wave 7
            "reconciliation": False,  # Wave 8
        },
    )
