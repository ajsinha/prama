"""A secret that resists being written down.

The dangerous moment for a credential is not storage — that is the part
everybody thinks about. It is the incidental copy: a debug log line, an
exception's ``repr`` of its arguments, a config dict serialised into an audit
record, a traceback rendered into an error page. Each of those is one line of
ordinary, well-intentioned code.

``SecretValue`` makes that class of accident impossible by construction. It
renders as ``<secret>`` everywhere a value is normally rendered, and the plain
text comes out only through :meth:`reveal`, which is deliberately ugly and
trivial to grep for. Auditing "where do credentials go" becomes a search for one
method name rather than a reading of the whole codebase.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

REDACTED = "<secret>"


class SecretValue:
    """A string that will not print itself."""

    __slots__ = ("_origin", "_value")

    def __init__(self, value: str, *, origin: str = "") -> None:
        self._value = value
        #: Where it came from — a reference, never a value. Safe to log, and
        #: what makes "which vault entry was used" answerable after the fact.
        self._origin = origin

    def reveal(self) -> str:
        """The plain text. The only way out, and the only thing to audit."""
        return self._value

    @property
    def origin(self) -> str:
        return self._origin

    @property
    def is_empty(self) -> bool:
        return not self._value

    def fingerprint(self) -> str:
        """A stable, non-reversible identifier for this value.

        Lets two configurations be compared, or a rotation detected, without
        anything sensitive being recorded. Truncated because the purpose is
        equality, not authentication.
        """
        return hashlib.blake2b(self._value.encode("utf-8"), digest_size=8).hexdigest()

    def matches(self, other: str) -> bool:
        """Constant-time comparison against a plain string."""
        return hmac.compare_digest(self._value, other)

    # -- everything that could leak it ------------------------------------

    def __repr__(self) -> str:
        return f"SecretValue({REDACTED}, origin={self._origin!r})"

    def __str__(self) -> str:
        return REDACTED

    def __format__(self, spec: str) -> str:
        # Without this, an f-string with a format spec would bypass __str__.
        return REDACTED

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        # The length of the secret is itself a small leak, and no legitimate
        # caller needs it. Returning the redaction's length keeps len() honest
        # about what this object renders as.
        return len(REDACTED)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretValue):
            return hmac.compare_digest(self._value, other._value)
        return NotImplemented

    def __hash__(self) -> int:
        # Hashing the value would let a dictionary of secrets be probed. The
        # fingerprint is stable and non-reversible, which is all a hash needs.
        return hash(self.fingerprint())

    def __reduce__(self) -> Any:
        """Refuse to pickle.

        Pickling is how a secret ends up in a task queue, a cache file or a
        crash dump. There is no legitimate reason to move one that way.
        """
        raise TypeError(
            "a SecretValue cannot be serialised; pass its reference and resolve "
            "it again at the point of use"
        )
