"""Identifiers.

Prama identifiers are **ULIDs**: 128 bits, 26 characters in Crockford base32,
lexicographically sortable by creation time. Three properties earn that choice:

* they sort by time, so a B-tree index on a primary key is append-friendly and
  an evidence ledger reads in creation order without a secondary sort;
* they are generated client-side, so a worker can mint an id without a round
  trip and an idempotent retry can reuse it;
* they carry no host or sequence information, so they leak nothing about fleet
  size or throughput.

Typed wrappers (``DatasetId``, ``EvidenceId``, …) exist so that passing a control
id where a dataset id belongs is a type error rather than a runtime mystery.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
import threading
from typing import ClassVar, Final

from prama.core.clock import Clock, SystemClock

_ALPHABET: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
_DECODE: Final[dict[str, int]] = {c: i for i, c in enumerate(_ALPHABET)}
ULID_LENGTH: Final[int] = 26
_TIME_CHARS: Final[int] = 10
_RANDOM_BITS: Final[int] = 80


class UlidFactory:
    """Mints monotonic ULIDs.

    Within a single millisecond the random component is incremented rather than
    redrawn, so ids minted in a tight loop remain strictly increasing. That
    matters because several stores rely on id order to page deterministically.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._lock = threading.Lock()
        self._last_ms = -1
        self._last_rand = 0

    def new(self) -> str:
        ms = self._clock.epoch_millis()
        with self._lock:
            if ms == self._last_ms:
                self._last_rand += 1
                if self._last_rand >= (1 << _RANDOM_BITS):
                    # Astronomically unlikely; wait for the next millisecond
                    # rather than emit a non-monotonic id.
                    ms += 1
                    self._last_ms = ms
                    self._last_rand = int.from_bytes(os.urandom(10), "big")
            else:
                self._last_ms = ms
                self._last_rand = int.from_bytes(os.urandom(10), "big")
            rand = self._last_rand
        return _encode(ms, _TIME_CHARS) + _encode(rand, ULID_LENGTH - _TIME_CHARS)


def _encode(value: int, length: int) -> str:
    chars = [""] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(chars)


_DEFAULT_FACTORY = UlidFactory()


def new_ulid() -> str:
    """Mint a ULID from the process-wide monotonic factory."""
    return _DEFAULT_FACTORY.new()


def is_ulid(value: str) -> bool:
    """True if *value* is a syntactically valid ULID."""
    return len(value) == ULID_LENGTH and all(c in _DECODE for c in value)


def ulid_timestamp_millis(value: str) -> int:
    """Recover the creation timestamp (epoch millis) encoded in a ULID."""
    if not is_ulid(value):
        raise ValueError(f"not a ULID: {value!r}")
    ms = 0
    for c in value[:_TIME_CHARS]:
        ms = (ms << 5) | _DECODE[c]
    return ms


class EntityId(str):
    """A typed identifier.

    Subclasses declare a ``prefix`` used only for display and log readability;
    the stored value is the bare ULID, so a prefix rename is never a data
    migration.
    """

    __slots__ = ()
    prefix: ClassVar[str] = "id"

    @classmethod
    def new(cls) -> EntityId:
        return cls(new_ulid())

    @classmethod
    def parse(cls, value: str) -> EntityId:
        raw = value.split(":", 1)[1] if ":" in value else value
        if not is_ulid(raw):
            raise ValueError(f"{cls.__name__} expects a ULID, got {value!r}")
        return cls(raw)

    @property
    def qualified(self) -> str:
        """``prefix:ULID`` — the form shown to humans and used in URLs."""
        return f"{type(self).prefix}:{self}"


class TenantId(EntityId):
    __slots__ = ()
    prefix = "tenant"


class PrincipalId(EntityId):
    __slots__ = ()
    prefix = "user"


class RoleId(EntityId):
    __slots__ = ()
    prefix = "role"


class ApiKeyId(EntityId):
    __slots__ = ()
    prefix = "key"


class AuditEventId(EntityId):
    __slots__ = ()
    prefix = "audit"


class LeaseId(EntityId):
    __slots__ = ()
    prefix = "lease"
