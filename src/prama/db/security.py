"""Credential handling, kept beside the columns that store it.

Password hashing lives next to ``principal.password_hash`` and key issuance
next to ``api_key.key_hash`` rather than in a service layer, for one reason:
the algorithm and the storage format are a single decision. Separating them is
how a system ends up with a hasher that has moved on and a column that has not.

Both classes are pure — no session, no I/O — so they are trivially testable and
can be used by the CLI, the API and a migration script alike.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import secrets

from prama.core.errors import ValidationError

#: Stored form: ``pbkdf2_sha256$<iterations>$<salt-hex>$<hash-hex>``. The
#: iteration count travels with the hash so that raising it later does not
#: invalidate existing credentials — old hashes verify at their own cost and
#: are re-hashed on next successful login.
HASH_ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 210_000
SALT_BYTES = 16


class PasswordHasher:
    """PBKDF2-SHA256 hashing with a per-password random salt."""

    def __init__(self, iterations: int = DEFAULT_ITERATIONS) -> None:
        if iterations < 100_000:
            raise ValidationError(
                f"password hash iterations ({iterations}) is below the safe floor",
                remedy=(
                    "Construct the hasher with iterations=100000 or more. This is a "
                    "code-level floor, not a setting: the value comes from "
                    "PasswordHasher(iterations=...) and its DEFAULT_ITERATIONS, and "
                    "nothing reads it from configuration."
                ),
                context={"iterations": iterations},
            )
        self._iterations = iterations

    def hash(self, password: str) -> str:
        salt = secrets.token_hex(SALT_BYTES)
        digest = self._derive(password, salt, self._iterations)
        return f"{HASH_ALGORITHM}${self._iterations}${salt}${digest}"

    def verify(self, password: str, stored: str) -> bool:
        """Constant-time verification.

        A malformed stored hash returns False rather than raising: it is a data
        problem, and turning it into an exception on the authentication path
        converts a bad row into an outage.
        """
        try:
            algorithm, iterations, salt, digest = stored.split("$", 3)
        except ValueError:
            return False
        if algorithm != HASH_ALGORITHM:
            return False
        try:
            candidate = self._derive(password, salt, int(iterations))
        except ValueError:
            return False
        return hmac.compare_digest(candidate, digest)

    def needs_rehash(self, stored: str) -> bool:
        """True when the stored hash uses fewer iterations than we now require."""
        parts = stored.split("$", 3)
        if len(parts) != 4 or parts[0] != HASH_ALGORITHM:
            return True
        try:
            return int(parts[1]) < self._iterations
        except ValueError:
            return True

    @staticmethod
    def _derive(password: str, salt: str, iterations: int) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
        ).hex()


@dataclasses.dataclass(frozen=True, slots=True)
class IssuedApiKey:
    """A freshly minted key.

    ``plaintext`` exists only in this object, is returned to the caller once,
    and is never persisted. ``prefix`` is stored and indexed so a presented key
    can be located in one lookup without scanning every hash.
    """

    plaintext: str
    prefix: str
    hash: str


class ApiKeyIssuer:
    """Mints and verifies API keys.

    Keys are hashed with SHA-256 rather than PBKDF2. That is deliberate and not
    a weakening: a 256-bit random key has no guessable structure, so the slow
    KDF that protects a human-chosen password buys nothing here and would cost a
    six-figure iteration count on every authenticated request.
    """

    PREFIX_LABEL = "pk"
    SECRET_BYTES = 32
    PREFIX_LENGTH = 12

    def issue(self, *, environment: str = "live") -> IssuedApiKey:
        secret = secrets.token_urlsafe(self.SECRET_BYTES)
        plaintext = f"{self.PREFIX_LABEL}_{environment}_{secret}"
        return IssuedApiKey(
            plaintext=plaintext,
            prefix=plaintext[: self.PREFIX_LENGTH],
            hash=self.fingerprint(plaintext),
        )

    @staticmethod
    def fingerprint(plaintext: str) -> str:
        return "sha256:" + hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    def prefix_of(self, plaintext: str) -> str:
        return plaintext[: self.PREFIX_LENGTH]

    def verify(self, plaintext: str, stored_hash: str) -> bool:
        return hmac.compare_digest(self.fingerprint(plaintext), stored_hash)
