"""Failing rows, kept apart from the evidence record that names them.

In the kernel because an agent takes its samples beside the data, under its
zone's residency policy, before anything crosses the boundary.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

from prama_kernel.pjson import canonical


@dataclasses.dataclass(frozen=True, slots=True)
class SampleSet:
    """Failing rows, kept apart from the record that refers to them."""

    digest: str
    rows: tuple[dict[str, Any], ...] = ()
    #: Which columns were masked before storage, so a reader knows what they
    #: are not seeing rather than assuming the row is complete.
    masked: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "count": self.count,
            "masked": list(self.masked),
            "rows": [dict(r) for r in self.rows],
        }


class SampleStore:
    """Where samples live. In memory here; the seam is deliberately two methods.

    Separate from the ledger because their lifetimes differ by years: an
    evidence record is kept for as long as the regulation requires, and the
    rows behind it are usually kept for as long as somebody might investigate.
    Storing them together forces the shorter retention onto both or the longer
    cost onto both, and neither is right.
    """

    def __init__(self) -> None:
        self._sets: dict[str, SampleSet] = {}

    def put(self, rows: list[dict[str, Any]], *, masked: tuple[str, ...] = ()) -> SampleSet:
        digest = "sha256:" + hashlib.sha256(canonical(rows)).hexdigest()[:32]
        sample = SampleSet(digest=digest, rows=tuple(rows), masked=masked)
        self._sets[digest] = sample
        return sample

    def get(self, digest: str) -> SampleSet | None:
        return self._sets.get(digest)

    def forget(self, digest: str) -> bool:
        """Expire one sample set, leaving the record that names it intact.

        Which is the point of the separation: the evidence still says what was
        found and how many rows, and says honestly that the rows themselves are
        gone.
        """
        return self._sets.pop(digest, None) is not None

    def __len__(self) -> int:
        return len(self._sets)
