"""What the data already obeys, offered as candidates rather than as rules.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.mine.constraints import (
    ConstraintFindings,
    ConstraintMiner,
    Invariant,
    InvariantKind,
    invariant_identity,
    invariant_provenance,
)
from prama.mine.dependencies import (
    Dependency,
    DependencyFindings,
    DependencyMiner,
    Inclusion,
    InclusionMiner,
    dependency_identity,
    dependency_provenance,
    inclusion_identity,
    inclusion_provenance,
)
from prama.mine.keys import Candidate, KeyFindings, KeyMiner, as_provenance, key_identity
from prama.mine.sample import Evidence, Sample

__all__ = [
    "Candidate",
    "ConstraintFindings",
    "ConstraintMiner",
    "Dependency",
    "DependencyFindings",
    "DependencyMiner",
    "Evidence",
    "Inclusion",
    "InclusionMiner",
    "Invariant",
    "InvariantKind",
    "KeyFindings",
    "KeyMiner",
    "Sample",
    "as_provenance",
    "dependency_identity",
    "dependency_provenance",
    "inclusion_identity",
    "inclusion_provenance",
    "invariant_identity",
    "invariant_provenance",
    "key_identity",
]
