"""Declaration services — the business-facing operations on the semantic layer.

A service takes a ``UnitOfWork``, never a session, so nothing above ``prama.db``
sees SQLAlchemy. What lives here is logic *about the business* rather than about
storage: uniqueness of a name a person will type, the approval a criticality
tier demands, the validation that refuses a declaration where it is written, and
the audit record every mutation must leave.

    base.py           SemanticService, slugify
    datasets.py       datasets and their attributes
    relationships.py  the thirteen kinds, and confirming discovered ones
    graph.py          concepts, journeys, connections, bindings
    estate.py         maturity, conflicts, coverage gaps

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.semantic.services.base import SemanticService, slugify
from prama.semantic.services.connectivity import (
    ConnectivityService,
    ProfileRun,
    read_policy_from,
)
from prama.semantic.services.datasets import DatasetService
from prama.semantic.services.estate import EstateService
from prama.semantic.services.graph import (
    BindingService,
    ConceptService,
    ConnectionService,
    JourneyService,
)
from prama.semantic.services.relationships import RelationshipService, relationship_kinds

__all__ = [
    "BindingService",
    "ConceptService",
    "ConnectionService",
    "ConnectivityService",
    "DatasetService",
    "EstateService",
    "JourneyService",
    "ProfileRun",
    "RelationshipService",
    "SemanticService",
    "read_policy_from",
    "relationship_kinds",
    "slugify",
]
