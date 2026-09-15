"""The Prama error taxonomy.

Every failure surfaced to a human states three things: **what happened**, **why**,
and **what to do next** (NFR-USA-004). That is not a documentation aspiration —
it is the constructor signature, so an error that omits the next action cannot be
raised.

Each error also carries a stable machine-readable `code`. Codes are part of the
public contract: they appear in API problem details, in logs, and in support
conversations, and they may not be renamed without a deprecation window.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any


class PramaError(Exception):
    """Base of every deliberate Prama failure.

    Args:
        message: what happened, in one sentence, in the reader's terms.
        code: stable machine-readable identifier, ``AREA.CONDITION``.
        remedy: the next action the reader can take. Required — an error a
            reader cannot act on is a defect in the error, not in the reader.
        context: structured detail for logs and problem documents. Values must
            be safe to log: never a credential, never a data value from a
            customer source unless it has already passed the masking policy.
    """

    #: Default code for subclasses that do not set one.
    code: str = "PRAMA.ERROR"

    def __init__(
        self,
        message: str,
        *,
        remedy: str,
        code: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.remedy = remedy
        self.code = code or type(self).code
        self.context: dict[str, Any] = dict(context or {})
        self.__cause__ = cause

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}", f"Next: {self.remedy}"]
        if self.context:
            rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
            parts.append(f"Context: {rendered}")
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Render for an API problem document or a structured log record."""
        return {
            "code": self.code,
            "message": self.message,
            "remedy": self.remedy,
            "context": self.context,
        }


class ConfigError(PramaError):
    """Configuration is missing, malformed, or internally inconsistent."""

    code = "CONFIG.INVALID"


class ConfigMissingError(ConfigError):
    """A required configuration key has no value from any source."""

    code = "CONFIG.MISSING"


class ConfigTypeError(ConfigError):
    """A configuration value exists but cannot be coerced to the declared type."""

    code = "CONFIG.TYPE"


class SecretMissingError(ConfigError):
    """A secret is required and the shipped default is deliberately empty."""

    code = "CONFIG.SECRET_MISSING"


class RegistryError(PramaError):
    """A plugin could not be resolved, loaded, or validated."""

    code = "REGISTRY.INVALID"


class DatabaseError(PramaError):
    """A database operation failed, or the database is not usable as configured."""

    code = "DB.ERROR"


class SchemaDriftError(DatabaseError):
    """The live database does not match the authoritative schema file.

    Prama has no migrations by design. Drift is reported, never repaired
    silently: a schema that has diverged is a fact the operator must decide
    about, not something a tool should guess at.
    """

    code = "DB.SCHEMA_DRIFT"


class ConcurrencyError(PramaError):
    """A structured-concurrency invariant was violated."""

    code = "CONCURRENCY.INVARIANT"


class LeaseLostError(ConcurrencyError):
    """A lease expired or was taken by another holder while still in use."""

    code = "CONCURRENCY.LEASE_LOST"


class BackPressureError(ConcurrencyError):
    """A bounded queue refused work because accepting it would breach its budget."""

    code = "CONCURRENCY.BACKPRESSURE"


class NotFoundError(PramaError):
    """A referenced entity does not exist."""

    code = "ENTITY.NOT_FOUND"


class ConflictError(PramaError):
    """The requested change conflicts with the current state."""

    code = "ENTITY.CONFLICT"


class ValidationError(PramaError):
    """Input failed validation before any state was changed."""

    code = "INPUT.INVALID"


class UnauthorisedError(PramaError):
    """The caller did not establish who they are.

    Distinct from :class:`ForbiddenError`, and the distinction is the useful
    one: this says *we do not know who you are*, which is fixed by presenting a
    credential, where forbidden says *we know, and no*.
    """

    code = "AUTH.UNAUTHORISED"


class ForbiddenError(PramaError):
    """The caller is known and may not do this."""

    code = "AUTH.FORBIDDEN"


def first_line(exc: BaseException) -> str:
    """Somebody else's exception, reduced to the part worth repeating.

    A driver's first line is where it names the constraint, the file or the
    column; everything after it is the statement, the bound parameters and the
    stack. This goes into `context["detail"]`, which is read in a log line and
    on an error page — both of which have a width.

    Here rather than beside any one caller because it had already been written
    three times: `db/session.py`, `db/guard.py` and
    `connect/sources/query.py`, in two of which it was written by the same
    change that removed a different restatement. Two more open-coded copies
    remain in `connect/sources/objectstore.py` and `db/schema/bootstrap.py`,
    both truncating at 300 rather than 400 — which is what a restatement looks
    like after it has drifted.
    """
    text = str(exc).strip()
    return text.splitlines()[0][:400] if text else exc.__class__.__name__
