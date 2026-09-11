"""Resolving references, and the record that one was resolved.

Two things here beyond dispatch:

* **Caching.** A vault call is a network round trip. One per connection test is
  fine; one per batch of a table read is not, and a vault that starts rate
  limiting a bank's data quality platform will be turned off rather than fixed.
  Entries expire, so a rotated credential is picked up without a restart.
* **Audit.** Every resolution is recorded — which reference, by whom, for what,
  and whether it succeeded. Never the value. "Which system read this credential
  and when" is a question an auditor will ask, and the answer should not require
  reading application logs.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from prama.core.clock import Clock, SystemClock
from prama.core.log import get_logger
from prama.secrets.reference import SecretRef
from prama.secrets.spi import SecretProvider, SecretResolutionError
from prama.secrets.value import SecretValue

_log = get_logger(__name__)

#: How long a resolved secret may be reused. Short enough that a rotation takes
#: effect without a restart, long enough that a table read is one vault call.
DEFAULT_CACHE_TTL_SECONDS = 300.0


@dataclasses.dataclass(frozen=True, slots=True)
class SecretAccess:
    """One resolution, as it will appear in the audit trail."""

    reference: str
    purpose: str
    principal: str
    at: datetime
    outcome: str
    fingerprint: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "reference": self.reference,
            "purpose": self.purpose,
            "principal": self.principal,
            "at": self.at.isoformat(),
            "outcome": self.outcome,
            # A non-reversible identity for the value, so a rotation is visible
            # in the audit trail without the trail holding a credential.
            "fingerprint": self.fingerprint,
            "detail": self.detail,
        }


@dataclasses.dataclass(slots=True)
class _CacheEntry:
    value: SecretValue
    expires_at: datetime


class SecretResolver:
    """Turns references into values, through registered providers."""

    def __init__(
        self,
        providers: list[SecretProvider] | None = None,
        *,
        clock: Clock | None = None,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        audit_sink: Callable[[SecretAccess], None] | None = None,
    ) -> None:
        self._providers: dict[str, SecretProvider] = {}
        self._clock = clock or SystemClock()
        self._ttl = cache_ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._audit = audit_sink
        # Resolution happens from request handlers and from background
        # re-examination at the same time; the cache must not be torn.
        self._lock = threading.Lock()
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: SecretProvider) -> SecretResolver:
        if not provider.scheme:
            raise SecretResolutionError(
                f"{type(provider).__name__} declares no scheme",
                remedy="Set the provider's scheme attribute, e.g. 'env'.",
            )
        self._providers[provider.scheme] = provider
        return self

    @property
    def schemes(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def describe(self) -> list[dict[str, str]]:
        return [p.describe() for p in self._providers.values()]

    def resolve(
        self,
        reference: str | SecretRef,
        *,
        purpose: str = "",
        principal: str = "system",
    ) -> SecretValue:
        """Resolve a reference, recording that it happened."""
        ref = reference if isinstance(reference, SecretRef) else SecretRef.parse(reference)
        cached = self._cached(ref)
        if cached is not None:
            return cached
        provider = self._providers.get(ref.scheme)
        if provider is None:
            self._record(ref, purpose, principal, "unknown-scheme")
            raise SecretResolutionError(
                f"no secret provider is installed for {ref.scheme}://",
                remedy=(
                    f"Installed: {', '.join(self.schemes) or '(none)'}. Either use one of "
                    f"those, or install the package providing {ref.scheme}."
                ),
                context={"scheme": ref.scheme, "installed": list(self.schemes)},
            )
        if not provider.available():
            self._record(ref, purpose, principal, "provider-unavailable")
            raise SecretResolutionError(
                f"the {ref.scheme} secret provider is not usable in this deployment",
                remedy=provider.unavailable_remedy(),
                context={"scheme": ref.scheme},
            )
        try:
            value = provider.resolve(ref)
        except SecretResolutionError as exc:
            self._record(ref, purpose, principal, "failed", detail=str(exc.args[0]))
            raise
        if value.is_empty:
            # An empty password reaches the driver and returns an authentication
            # failure, sending somebody to check a credential that was never
            # actually read. Better to fail where the truth is.
            self._record(ref, purpose, principal, "empty")
            raise SecretResolutionError(
                f"the secret at {ref.render()} is empty",
                remedy=(
                    "Store the credential at that location. An empty value would reach "
                    "the source as a blank password and be reported as bad credentials."
                ),
                context={"reference": ref.render()},
            )
        self._store(ref, value)
        self._record(ref, purpose, principal, "resolved", fingerprint=value.fingerprint())
        return value

    def resolve_optional(self, reference: str | None, **kwargs: str) -> SecretValue | None:
        """Resolve when a reference is present; ``None`` when it is not.

        For connections that legitimately have no credential — a file on a
        mounted share, a database using OS authentication.
        """
        if not reference:
            return None
        return self.resolve(reference, **kwargs)

    def invalidate(self, reference: str | SecretRef | None = None) -> None:
        """Forget a cached secret, or all of them. Used after a rotation."""
        ref = SecretRef.parse(reference) if isinstance(reference, str) else reference
        with self._lock:
            if ref is None:
                self._cache.clear()
            else:
                self._cache.pop(ref.render(), None)

    # -- internals ---------------------------------------------------------

    def _cached(self, ref: SecretRef) -> SecretValue | None:
        if self._ttl <= 0:
            return None
        with self._lock:
            entry = self._cache.get(ref.render())
            if entry is None:
                return None
            if entry.expires_at <= self._clock.now():
                del self._cache[ref.render()]
                return None
            return entry.value

    def _store(self, ref: SecretRef, value: SecretValue) -> None:
        if self._ttl <= 0:
            return
        with self._lock:
            self._cache[ref.render()] = _CacheEntry(
                value=value,
                expires_at=self._clock.now() + timedelta(seconds=self._ttl),
            )

    def _record(
        self,
        ref: SecretRef,
        purpose: str,
        principal: str,
        outcome: str,
        *,
        fingerprint: str = "",
        detail: str = "",
    ) -> None:
        access = SecretAccess(
            reference=ref.render(),
            purpose=purpose,
            principal=principal,
            at=self._clock.now(),
            outcome=outcome,
            fingerprint=fingerprint,
            detail=detail,
        )
        _log.info(
            "secret %s resolved for %s by %s: %s",
            access.reference,
            purpose or "(unstated)",
            principal,
            outcome,
        )
        if self._audit is not None:
            self._audit(access)


def default_resolver(
    *,
    file_root: str | None = None,
    clock: Clock | None = None,
    audit_sink: Callable[[SecretAccess], None] | None = None,
) -> SecretResolver:
    """The providers available with nothing extra installed.

    ``memory`` is deliberately absent: a provider that manufactures secrets is
    fine in a test and dangerous in a default.

    ``vault`` is present but unconfigured, which is not the same as absent. A
    reference to it then fails with "Vault is referenced but not configured"
    and what to set, rather than with "no provider for scheme 'vault'" — and
    the second message sends somebody to look for a plugin that is already
    installed.
    """
    from prama.secrets.providers import EnvironmentSecretProvider, FileSecretProvider
    from prama.secrets.vault import VaultSecretProvider

    return SecretResolver(
        [
            EnvironmentSecretProvider(),
            FileSecretProvider(root=file_root),
            VaultSecretProvider(),
        ],
        clock=clock,
        audit_sink=audit_sink,
    )
