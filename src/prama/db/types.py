"""Portable column types.

Prama's schema uses three physical types only — ``TEXT``, ``INTEGER`` and
``REAL`` — because only those three mean the same thing in PostgreSQL and
SQLite (schema/*.sql explains the reasoning in full). These decorators give the
ORM the *logical* types the domain wants while storing exactly what the schema
files declare.

The critical property is round-trip fidelity: what goes in comes out equal, on
both engines, with no dialect-dependent behaviour anywhere above this module.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Dialect as SaDialect
from sqlalchemy import Integer, String, Text, TypeDecorator

from prama.core import pjson

#: A ULID is exactly 26 characters. Declaring the width means PostgreSQL
#: enforces it and SQLite documents it — the same reasoning the schema files
#: give for using VARCHAR(n) throughout rather than bare TEXT.
ULID_WIDTH = 26

#: An ISO-8601 UTC timestamp with microseconds and a trailing Z is 28
#: characters; 32 leaves room without pretending to be unbounded.
TIMESTAMP_WIDTH = 32


class UtcDateTime(TypeDecorator[datetime]):
    """A timezone-aware UTC instant, stored as ISO-8601 text ending in ``Z``.

    Text is not a compromise here. ISO-8601 UTC sorts lexicographically in
    exactly chronological order, so ``ORDER BY``, range predicates and B-tree
    indexes behave identically on both engines — which a native timestamp type
    on one engine and a string on the other would not.

    A naive datetime is refused rather than assumed to be UTC. Silent
    localisation is how an evidence record ends up an hour wrong twice a year.
    """

    impl = String(TIMESTAMP_WIDTH)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: SaDialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            raise ValueError("refusing to store a naive datetime; attach UTC before persisting")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def process_result_value(self, value: Any, dialect: SaDialect) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):  # a driver that already parsed it
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text).astimezone(UTC)


class JsonText(TypeDecorator[Any]):
    """A JSON document stored as text, encoded through ``prama.core.pjson``.

    Encoding goes through the platform's one JSON API so that a value written
    by a repository and a value written by the evidence ledger are byte-wise
    comparable — which matters as soon as anything is hashed.
    """

    impl = Text
    cache_ok = True

    def __init__(self, *, sort_keys: bool = True) -> None:
        super().__init__()
        self._sort_keys = sort_keys

    def process_bind_param(self, value: Any, dialect: SaDialect) -> str | None:
        if value is None:
            return None
        return pjson.dumps(value, sort_keys=self._sort_keys)

    def process_result_value(self, value: Any, dialect: SaDialect) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):  # a driver that already parsed it
            return value
        return pjson.loads(value)


class BoolInt(TypeDecorator[bool]):
    """A boolean stored as ``INTEGER`` 0/1, with a CHECK constraint in the schema.

    PostgreSQL has a real BOOLEAN and SQLite does not, so using it would make
    the two schemas semantically different in exactly the way this platform
    refuses to tolerate. 0/1 is unambiguous on both.
    """

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: SaDialect) -> int | None:
        if value is None:
            return None
        return 1 if bool(value) else 0

    def process_result_value(self, value: Any, dialect: SaDialect) -> bool | None:
        if value is None:
            return None
        return bool(value)


#: A ULID identifier column. Aliased so intent is readable in model definitions
#: and so a width change has exactly one place to happen.
Ulid = String(ULID_WIDTH)
