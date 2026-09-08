"""Trailer and manifest checks.

The cheapest genuine integrity checks that exist, and the ones content-level
controls structurally cannot replace: the sender counted the rows on the way
out, and comparing that number to what arrived catches truncation, a
half-written file and a failed transfer. Every row that *did* arrive is
perfectly valid, so nothing else would notice.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from decimal import Decimal, InvalidOperation
from typing import Any

from prama.connect.feed.definition import TrailerSpec


class IntegrityStatus(enum.Enum):
    MATCHED = "matched"
    COUNT_MISMATCH = "count_mismatch"
    TOTAL_MISMATCH = "total_mismatch"
    TRAILER_MISSING = "trailer_missing"
    TRAILER_UNREADABLE = "trailer_unreadable"
    MANIFEST_INCOMPLETE = "manifest_incomplete"

    @property
    def is_healthy(self) -> bool:
        return self is IntegrityStatus.MATCHED

    @property
    def severity(self) -> str:
        return "info" if self.is_healthy else "critical"

    @property
    def next_action(self) -> str:
        return {
            IntegrityStatus.MATCHED: "nothing",
            IntegrityStatus.COUNT_MISMATCH: (
                "request a re-send; the file is incomplete, and every row in it is valid, "
                "so no content check will catch this"
            ),
            IntegrityStatus.TOTAL_MISMATCH: (
                "reconcile with the sender: the rows arrived but the values do not add up"
            ),
            IntegrityStatus.TRAILER_MISSING: ("the transfer probably truncated; request a re-send"),
            IntegrityStatus.TRAILER_UNREADABLE: (
                "confirm the trailer layout with the sender, or correct the declaration"
            ),
            IntegrityStatus.MANIFEST_INCOMPLETE: (
                "wait for the remaining files, or chase them past the deadline"
            ),
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class IntegrityFinding:
    status: IntegrityStatus
    filename: str
    declared_count: int | None = None
    observed_count: int | None = None
    #: Decimal, not float: these carry money, and a report that renders a
    #: shortfall as 0.30000000000000004 is not one anyone will act on.
    declared_total: Decimal | None = None
    observed_total: Decimal | None = None
    missing_files: tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_healthy(self) -> bool:
        return self.status.is_healthy

    @property
    def shortfall(self) -> int | None:
        if self.declared_count is None or self.observed_count is None:
            return None
        return self.declared_count - self.observed_count

    def render(self) -> str:
        if self.status is IntegrityStatus.COUNT_MISMATCH:
            return (
                f"{self.filename}: trailer declares {self.declared_count:,} records, "
                f"{self.observed_count:,} arrived ({self.shortfall:+,})"
            )
        if self.status is IntegrityStatus.TOTAL_MISMATCH:
            return (
                f"{self.filename}: trailer total {self.declared_total:,.2f} against "
                f"{self.observed_total:,.2f} observed"
            )
        if self.status is IntegrityStatus.MANIFEST_INCOMPLETE:
            return f"{self.filename}: awaiting {', '.join(self.missing_files)}"
        return f"{self.filename}: {self.status.value.replace('_', ' ')}. {self.detail}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "severity": self.status.severity,
            "filename": self.filename,
            "declared_count": self.declared_count,
            "observed_count": self.observed_count,
            "shortfall": self.shortfall,
            "declared_total": str(self.declared_total) if self.declared_total is not None else None,
            "observed_total": str(self.observed_total) if self.observed_total is not None else None,
            "missing_files": list(self.missing_files),
            "next_action": self.status.next_action,
            "message": self.render(),
        }


class TrailerChecker:
    """Reads a file's trailer and compares it with what actually arrived."""

    def __init__(self, spec: TrailerSpec) -> None:
        self._spec = spec

    def check(self, filename: str, lines: list[str]) -> IntegrityFinding:
        """Compare the declared count against the data rows present.

        Takes lines rather than a path so the same logic serves a local file, an
        object-store stream and a test, and so a caller that has already read
        the file does not read it twice.
        """
        spec = self._spec
        if not spec.is_declared:
            return IntegrityFinding(
                status=IntegrityStatus.MATCHED,
                filename=filename,
                detail="no trailer declared for this feed",
            )

        trailer_index = self._find_trailer(lines)
        if trailer_index is None:
            return IntegrityFinding(
                status=IntegrityStatus.TRAILER_MISSING,
                filename=filename,
                detail=f"no line beginning {spec.marker!r} was found",
            )

        fields = lines[trailer_index].rstrip("\r\n").split(spec.delimiter)
        try:
            declared_count = int(fields[spec.count_field].strip())
        except (IndexError, ValueError):
            return IntegrityFinding(
                status=IntegrityStatus.TRAILER_UNREADABLE,
                filename=filename,
                detail=(
                    f"field {spec.count_field} of the trailer is not a number: "
                    f"{lines[trailer_index].strip()[:80]!r}"
                ),
            )

        observed = self._data_row_count(lines, trailer_index)
        if declared_count != observed:
            return IntegrityFinding(
                status=IntegrityStatus.COUNT_MISMATCH,
                filename=filename,
                declared_count=declared_count,
                observed_count=observed,
            )

        if spec.total_field is not None:
            return self._check_total(filename, lines, fields, trailer_index, declared_count)
        return IntegrityFinding(
            status=IntegrityStatus.MATCHED,
            filename=filename,
            declared_count=declared_count,
            observed_count=observed,
        )

    def _check_total(
        self,
        filename: str,
        lines: list[str],
        fields: list[str],
        trailer_index: int,
        declared_count: int,
    ) -> IntegrityFinding:
        spec = self._spec
        assert spec.total_field is not None
        try:
            declared_total = Decimal(fields[spec.total_field].strip())
        except (IndexError, InvalidOperation):
            return IntegrityFinding(
                status=IntegrityStatus.TRAILER_UNREADABLE,
                filename=filename,
                detail=f"field {spec.total_field} of the trailer is not a number",
            )
        column = spec.sum_column
        assert column is not None
        observed_total = Decimal(0)
        for line in lines[spec.header_lines : trailer_index]:
            parts = line.rstrip("\r\n").split(spec.delimiter)
            if len(parts) > column:
                try:
                    observed_total += Decimal(parts[column].strip())
                except InvalidOperation:
                    continue  # a blank line, or a non-numeric column
        # Decimal, not float. A hash total exists to detect small discrepancies;
        # summing a million amounts in binary floating point manufactures
        # exactly the kind of small discrepancy it is looking for, and the
        # resulting mismatch is indistinguishable from a real one.
        if abs(declared_total - observed_total) > Decimal(spec.total_tolerance):
            return IntegrityFinding(
                status=IntegrityStatus.TOTAL_MISMATCH,
                filename=filename,
                declared_count=declared_count,
                observed_count=trailer_index,
                declared_total=declared_total,
                observed_total=observed_total,
            )
        return IntegrityFinding(
            status=IntegrityStatus.MATCHED,
            filename=filename,
            declared_count=declared_count,
            observed_count=trailer_index,
            declared_total=declared_total,
            observed_total=observed_total,
        )

    def _data_row_count(self, lines: list[str], trailer_index: int) -> int:
        """Rows the sender was counting.

        Headers are excluded, and so are blank lines: a trailing newline is not
        a record, and counting it turns every delivery into a false mismatch.
        """
        spec = self._spec
        body = lines[spec.header_lines : trailer_index]
        count = sum(1 for line in body if line.strip())
        return count + 1 if spec.counts_itself else count

    def _find_trailer(self, lines: list[str]) -> int | None:
        marker = self._spec.marker
        for index in range(len(lines) - 1, -1, -1):
            if lines[index].startswith(marker):
                return index
        return None


class ManifestChecker:
    """Confirms that every file a delivery promised has actually landed.

    A multi-file batch is atomic in the sender's mind and is not atomic on the
    wire. Processing four of five files produces numbers that are wrong and look
    right — the failure this exists to prevent.
    """

    def check(
        self, manifest_name: str, expected: list[str], present: list[str]
    ) -> IntegrityFinding:
        missing = tuple(sorted(set(expected) - set(present)))
        if missing:
            return IntegrityFinding(
                status=IntegrityStatus.MANIFEST_INCOMPLETE,
                filename=manifest_name,
                declared_count=len(expected),
                observed_count=len(expected) - len(missing),
                missing_files=missing,
            )
        return IntegrityFinding(
            status=IntegrityStatus.MATCHED,
            filename=manifest_name,
            declared_count=len(expected),
            observed_count=len(expected),
        )
