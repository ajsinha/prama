"""Credential handling.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.db.security import ApiKeyIssuer, PasswordHasher


class TestPasswordHasher:
    def test_hash_verifies_and_is_salted(self) -> None:
        hasher = PasswordHasher(iterations=100_000)
        first, second = hasher.hash("correct horse"), hasher.hash("correct horse")
        assert first != second  # per-password salt
        assert hasher.verify("correct horse", first)
        assert hasher.verify("correct horse", second)

    def test_wrong_password_fails(self) -> None:
        hasher = PasswordHasher(iterations=100_000)
        assert not hasher.verify("wrong", hasher.hash("right"))

    @pytest.mark.parametrize("stored", ["", "garbage", "md5$1$a$b", "pbkdf2_sha256$x$y$z"])
    def test_a_malformed_stored_hash_returns_false_rather_than_raising(self, stored: str) -> None:
        # A bad row must not turn the authentication path into an outage.
        assert PasswordHasher(iterations=100_000).verify("anything", stored) is False

    def test_iteration_count_travels_with_the_hash(self) -> None:
        old = PasswordHasher(iterations=100_000).hash("pw")
        stronger = PasswordHasher(iterations=200_000)
        assert stronger.verify("pw", old)  # still verifies at its own cost
        assert stronger.needs_rehash(old)  # and is flagged for upgrade

    def test_a_dangerously_low_iteration_count_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="safe floor"):
            PasswordHasher(iterations=1000)


class TestApiKeyIssuer:
    def test_issued_key_verifies_by_prefix_and_hash(self) -> None:
        issuer = ApiKeyIssuer()
        issued = issuer.issue()
        assert issued.plaintext.startswith("pk_live_")
        assert issued.prefix == issued.plaintext[:12]
        assert issuer.verify(issued.plaintext, issued.hash)

    def test_a_different_key_does_not_verify(self) -> None:
        issuer = ApiKeyIssuer()
        assert not issuer.verify(issuer.issue().plaintext, issuer.issue().hash)

    def test_keys_are_unique(self) -> None:
        issuer = ApiKeyIssuer()
        keys = {issuer.issue().plaintext for _ in range(500)}
        assert len(keys) == 500

    def test_the_plaintext_is_never_part_of_the_stored_form(self) -> None:
        issued = ApiKeyIssuer().issue()
        secret = issued.plaintext.split("_", 2)[2]
        assert secret not in issued.hash
