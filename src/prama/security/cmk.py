"""Customer-managed keys: envelope encryption Prama cannot undo.

The promise a regulated buyer actually wants is not "your data is encrypted".
It is **"we can take the key away and you cannot read it any more"** — which is
a promise about who holds what, not about an algorithm.

So the shape is envelope encryption and the arrangement is deliberate:

- A fresh **data key** encrypts each payload. It is random, used once, and never
  written down.
- The **customer's key** (in their KMS, their HSM, their Vault) encrypts the
  data key. Prama stores the *wrapped* data key beside the ciphertext.
- Prama never holds the customer key and cannot unwrap without asking. Revoke it
  and every envelope it wrapped becomes unreadable, permanently, with no action
  needed on Prama's side and none possible.

That last property is the product, and it has a cost that is stated here rather
than discovered: **revocation is not reversible and it is not selective**. A
customer who revokes to satisfy an erasure request has also made every backup
of that data unreadable, including the ones taken for their own recovery
obligations. This module will not pretend otherwise.

Three decisions that are easy to get wrong and silent when wrong:

**The nonce is fresh per encryption and stored with the ciphertext.** Reusing a
nonce under one key in GCM does not merely weaken it — it leaks the XOR of the
plaintexts and lets an attacker forge. It is generated here, never supplied.

**The context is authenticated, not merely recorded.** The tenant id and purpose
go into the AAD, so a ciphertext moved from one tenant's row to another's
*fails* to decrypt. Storing the tenant alongside would let it decrypt fine into
the wrong tenant, which is the failure that looks like nothing at all.

**An unwrap failure is not an error to retry.** It usually means the customer
revoked the key, which is a state they chose. The message says so, because an
operator who reads "decryption failed" opens a ticket about a bug.

The key provider is an ABC. Nothing here talks to AWS KMS, Azure Key Vault or
GCP KMS — those clients belong to the deployment, and keeping them out is what
lets the envelope logic be tested. **No cloud KMS has been exercised.**

Needs the ``sso`` extra for AES-GCM, and refuses by name without it rather than
falling back to something weaker.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import base64
import dataclasses
import os
from typing import Any, Final

from prama.core.errors import PramaError, required_field

__all__ = [
    "DATA_KEY_BYTES",
    "NONCE_BYTES",
    "Envelope",
    "KeyProvider",
    "KeyRevoked",
    "LocalTestKeyProvider",
    "decrypt",
    "encrypt",
]

#: AES-256. Not configurable: a key length knob is a way to end up with AES-128
#: in production because somebody changed a default years ago.
DATA_KEY_BYTES: Final = 32

#: 96 bits, which is what GCM is specified for. A longer nonce is hashed down
#: internally and buys nothing; a shorter one raises collision probability.
NONCE_BYTES: Final = 12


class KeyRevoked(PramaError):
    """The customer key could not unwrap this envelope.

    Its own type because it is usually not a fault. A customer who revoked a key
    has made this data unreadable on purpose, and an operator who reads
    "decryption failed" opens a ticket about a bug that does not exist.
    """

    code = "CMK.UNWRAP_REFUSED"


class CmkUnavailable(PramaError):
    """AES-GCM is not installed."""

    code = "CMK.UNAVAILABLE"


def _aesgcm() -> Any:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - exercised by the extra being absent
        raise CmkUnavailable(
            "customer-managed keys need the 'sso' extra, which is not installed",
            remedy=(
                'Install it: pip install -e ".[sso]". This refuses rather than '
                "encrypting with something weaker."
            ),
        ) from exc
    return AESGCM


class KeyProvider(abc.ABC):
    """Wraps and unwraps a data key with a key Prama does not hold.

    Two methods and no third. A provider that could also *generate* the customer
    key would mean Prama had it at some point, and "we never had it" is the
    claim the whole arrangement exists to be able to make.
    """

    #: Which key this is, as the customer's KMS names it. Stored in the envelope
    #: so a rotated key can still unwrap what it wrapped.
    key_id: str = ""

    @abc.abstractmethod
    def wrap(self, data_key: bytes, *, context: dict[str, str]) -> bytes:
        """Encrypt a data key. ``context`` is the KMS encryption context."""

    @abc.abstractmethod
    def unwrap(self, wrapped: bytes, *, context: dict[str, str]) -> bytes:
        """Decrypt a data key, or raise :class:`KeyRevoked`."""


class LocalTestKeyProvider(KeyProvider):
    """A provider holding the key in memory. **Never for production.**

    Exists so the envelope logic can be exercised without a KMS, and so a real
    provider has something to be checked against. It is named for what it is: a
    class called ``LocalKeyProvider`` would end up in somebody's deployment, and
    a customer-managed key held by Prama is not a customer-managed key.
    """

    key_id = "local-test-key"

    def __init__(self, key: bytes | None = None) -> None:
        self._key = key or os.urandom(DATA_KEY_BYTES)
        self.revoked = False

    def revoke(self) -> None:
        """Make every envelope this wrapped unreadable, as a real revocation does."""
        self.revoked = True

    def wrap(self, data_key: bytes, *, context: dict[str, str]) -> bytes:
        if self.revoked:
            raise KeyRevoked(
                "this key has been revoked and cannot wrap",
                remedy="Provision a new key. The revoked one is not coming back.",
            )
        aesgcm = _aesgcm()
        nonce = os.urandom(NONCE_BYTES)
        sealed: bytes = aesgcm(self._key).encrypt(nonce, data_key, _aad(context))
        return nonce + sealed

    def unwrap(self, wrapped: bytes, *, context: dict[str, str]) -> bytes:
        if self.revoked:
            raise KeyRevoked(
                "the customer key has been revoked",
                remedy=(
                    "This is usually not a fault: revoking makes the data "
                    "unreadable on purpose, and it is neither reversible nor "
                    "selective."
                ),
            )
        aesgcm = _aesgcm()
        try:
            opened: bytes = aesgcm(self._key).decrypt(
                wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:], _aad(context)
            )
            return opened
        except Exception as exc:
            raise KeyRevoked(
                "the customer key did not unwrap this data key",
                remedy=(
                    "Either the key was rotated out and the old version is gone, "
                    "or this envelope belongs to a different tenant or purpose — "
                    "the context is authenticated, so it cannot decrypt into the "
                    "wrong one."
                ),
            ) from exc


def _aad(context: dict[str, str]) -> bytes:
    """The authenticated context, canonically.

    Sorted and delimited so two contexts with the same meaning produce the same
    bytes, and so a value containing the delimiter cannot forge a second field.
    """
    parts = []
    for key in sorted(context):
        value = context[key]
        if "\x00" in key or "\x00" in value:
            raise PramaError(
                "an encryption context value contains a null byte",
                code="CMK.BAD_CONTEXT",
                remedy=(
                    "Context keys and values are text. A null byte "
                    "would let one field forge another."
                ),
            )
        parts.append(f"{key}\x00{value}")
    return "\x01".join(parts).encode("utf-8")


#: What this module is reading, for refusals that name it.
OF = "a key envelope"


@dataclasses.dataclass(frozen=True, slots=True)
class Envelope:
    """A ciphertext and everything needed to decrypt it except the key."""

    #: The data key, encrypted under the customer's key.
    wrapped_key: bytes
    nonce: bytes
    ciphertext: bytes
    #: Which customer key wrapped it, so a rotated key can still unwrap what it
    #: wrapped. Rotation without this means re-encrypting everything at once.
    key_id: str
    #: The authenticated context. Stored so a reader can reconstruct it, and
    #: *authenticated* so altering it here breaks decryption rather than
    #: silently changing which tenant this belongs to.
    context: dict[str, str] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wrapped_key": base64.b64encode(self.wrapped_key).decode("ascii"),
            "nonce": base64.b64encode(self.nonce).decode("ascii"),
            "ciphertext": base64.b64encode(self.ciphertext).decode("ascii"),
            "key_id": self.key_id,
            "context": dict(self.context),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Envelope:
        return cls(
            wrapped_key=base64.b64decode(required_field(payload, "wrapped_key", of=OF)),
            nonce=base64.b64decode(required_field(payload, "nonce", of=OF)),
            ciphertext=base64.b64decode(required_field(payload, "ciphertext", of=OF)),
            key_id=str(payload.get("key_id", "")),
            context=dict(payload.get("context", {})),
        )


def encrypt(plaintext: bytes, *, provider: KeyProvider, tenant_id: str, purpose: str) -> Envelope:
    """Encrypt under a fresh data key wrapped by the customer's key.

    ``tenant_id`` and ``purpose`` are authenticated, not merely recorded: an
    envelope moved between tenants fails to decrypt rather than decrypting into
    the wrong one.
    """
    if not tenant_id:
        raise PramaError(
            "an envelope needs a tenant",
            code="CMK.NO_TENANT",
            remedy=(
                "The tenant is authenticated into the ciphertext. Without it, an "
                "envelope moved between tenants would decrypt cleanly into the "
                "wrong one."
            ),
        )
    aesgcm = _aesgcm()
    context = {"tenant": tenant_id, "purpose": purpose}

    data_key = os.urandom(DATA_KEY_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = aesgcm(data_key).encrypt(nonce, plaintext, _aad(context))
    wrapped = provider.wrap(data_key, context=context)
    # The data key goes out of scope here and is never stored. Python gives no
    # way to wipe it, and claiming otherwise would be the kind of security
    # theatre this codebase avoids.
    return Envelope(
        wrapped_key=wrapped,
        nonce=nonce,
        ciphertext=ciphertext,
        key_id=provider.key_id,
        context=context,
    )


def decrypt(
    envelope: Envelope,
    *,
    provider: KeyProvider,
    tenant_id: str | None = None,
    purpose: str | None = None,
) -> bytes:
    """Decrypt, or raise :class:`KeyRevoked`.

    *tenant_id* is the estate the caller believes this ciphertext belongs to.
    Supply it, and an envelope from another estate is refused before any key is
    unwrapped — finding S6.

    The module docstring promises "a ciphertext moved from one tenant's row to
    another's fails to decrypt". The AAD does bind ciphertext to context, but
    the context travels **inside the envelope**: `decrypt` reconstructed the AAD
    from the envelope itself, so a whole serialised envelope copied from one
    tenant's row into another's decrypted perfectly for anyone holding it. The
    guarantee held against editing the context and against swapping the
    ciphertext — the two things the tests exercised — and not against moving the
    pair together, which is the attack the sentence describes.

    Optional rather than required because the parameter is new and a caller
    that cannot name the tenant is better served by an explicit `None` than by
    a value invented to satisfy a signature. A caller that *can* name it and
    does not is the case `tests/security/test_cmk.py` now makes visible.
    """
    sealed_tenant = str(envelope.context.get("tenant", ""))
    sealed_purpose = str(envelope.context.get("purpose", ""))
    if tenant_id is not None and sealed_tenant != tenant_id:
        raise KeyRevoked(
            "this envelope belongs to a different estate",
            remedy=(
                "The ciphertext is sealed to the tenant it was written for. "
                "Read it as that tenant, or investigate how a row from one "
                "estate came to be read as another's."
            ),
            context={"expected": tenant_id, "sealed_for": sealed_tenant},
        )
    if purpose is not None and sealed_purpose != purpose:
        raise KeyRevoked(
            "this envelope was sealed for a different purpose",
            remedy=(
                "A key scoped to one purpose must not open another's data. "
                "Use the purpose the envelope was written under."
            ),
            context={"expected": purpose, "sealed_for": sealed_purpose},
        )
    aesgcm = _aesgcm()
    data_key = provider.unwrap(envelope.wrapped_key, context=envelope.context)
    try:
        plaintext: bytes = aesgcm(data_key).decrypt(
            envelope.nonce, envelope.ciphertext, _aad(envelope.context)
        )
        return plaintext
    except Exception as exc:
        raise KeyRevoked(
            "the envelope did not decrypt under its own data key",
            remedy=(
                "The ciphertext or its context was altered. The context is "
                "authenticated, so a tenant or purpose changed after the fact "
                "breaks decryption rather than quietly changing what this is."
            ),
        ) from exc
