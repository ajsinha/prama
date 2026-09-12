"""Customer-managed keys.

The promise is not "your data is encrypted". It is "we can take the key away
and you cannot read it any more", so the tests are about who holds what and
about the failures that are silent when they go wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

pytest.importorskip("cryptography", reason="needs the 'sso' extra")

from prama.core.errors import PramaError
from prama.security.cmk import (
    DATA_KEY_BYTES,
    NONCE_BYTES,
    Envelope,
    KeyProvider,
    KeyRevoked,
    LocalTestKeyProvider,
    decrypt,
    encrypt,
)

SECRET = b"the notional is 10,000,000 EUR"


@pytest.fixture
def provider() -> LocalTestKeyProvider:
    return LocalTestKeyProvider()


def sealed(provider: LocalTestKeyProvider, **changes) -> Envelope:
    kwargs = {"tenant_id": "t1", "purpose": "samples"}
    kwargs.update(changes)
    return encrypt(SECRET, provider=provider, **kwargs)


class TestTheRoundTrip:
    def test_what_goes_in_comes_out(self, provider) -> None:
        assert decrypt(sealed(provider), provider=provider) == SECRET

    def test_the_envelope_survives_serialisation(self, provider) -> None:
        """It is stored as JSON beside the data it protects."""
        envelope = sealed(provider)
        assert decrypt(Envelope.from_dict(envelope.to_dict()), provider=provider) == SECRET

    def test_the_plaintext_is_nowhere_in_the_envelope(self, provider) -> None:
        rendered = str(sealed(provider).to_dict())
        assert "notional" not in rendered
        assert "10,000,000" not in rendered


class TestRevocation:
    def test_revoking_makes_existing_data_unreadable(self, provider) -> None:
        """The product. Not a side effect."""
        envelope = sealed(provider)
        provider.revoke()
        with pytest.raises(KeyRevoked, match="has been revoked"):
            decrypt(envelope, provider=provider)

    def test_the_message_says_it_is_usually_not_a_fault(self, provider) -> None:
        """An operator who reads "decryption failed" opens a ticket about a bug
        that does not exist."""
        envelope = sealed(provider)
        provider.revoke()
        with pytest.raises(KeyRevoked) as caught:
            decrypt(envelope, provider=provider)
        assert "on purpose" in caught.value.remedy

    def test_the_message_says_it_is_neither_reversible_nor_selective(self, provider) -> None:
        """A customer who revokes to satisfy an erasure request has also made
        every backup unreadable, including ones taken for their own recovery
        obligations."""
        envelope = sealed(provider)
        provider.revoke()
        with pytest.raises(KeyRevoked) as caught:
            decrypt(envelope, provider=provider)
        assert "reversible" in caught.value.remedy
        assert "selective" in caught.value.remedy

    def test_a_revoked_key_cannot_wrap_either(self, provider) -> None:
        provider.revoke()
        with pytest.raises(KeyRevoked):
            sealed(provider)

    def test_a_revoked_key_is_its_own_error_type(self) -> None:
        assert KeyRevoked.code == "CMK.UNWRAP_REFUSED"


class TestTheContextIsAuthenticated:
    def test_an_envelope_moved_between_tenants_fails_to_decrypt(self, provider) -> None:
        """Storing the tenant alongside would let it decrypt fine into the
        wrong tenant, which is the failure that looks like nothing at all."""
        envelope = sealed(provider)
        moved = dataclasses.replace(envelope, context={"tenant": "t2", "purpose": "samples"})
        with pytest.raises(KeyRevoked):
            decrypt(moved, provider=provider)

    def test_an_envelope_reused_for_another_purpose_fails(self, provider) -> None:
        envelope = sealed(provider)
        repurposed = dataclasses.replace(envelope, context={"tenant": "t1", "purpose": "evidence"})
        with pytest.raises(KeyRevoked):
            decrypt(repurposed, provider=provider)

    def test_two_tenants_envelopes_do_not_cross(self, provider) -> None:
        one = sealed(provider, tenant_id="t1")
        two = sealed(provider, tenant_id="t2")
        crossed = dataclasses.replace(one, ciphertext=two.ciphertext, nonce=two.nonce)
        with pytest.raises(KeyRevoked):
            decrypt(crossed, provider=provider)

    def test_an_envelope_needs_a_tenant(self, provider) -> None:
        with pytest.raises(PramaError, match="needs a tenant"):
            encrypt(SECRET, provider=provider, tenant_id="", purpose="samples")

    def test_a_null_byte_in_the_context_is_refused(self, provider) -> None:
        """It would let one field forge another in the canonical encoding."""
        with pytest.raises(PramaError, match="null byte"):
            encrypt(SECRET, provider=provider, tenant_id="t\x001", purpose="x")

    def test_the_canonical_encoding_is_order_independent(self, provider) -> None:
        envelope = sealed(provider)
        reordered = dataclasses.replace(
            envelope, context=dict(reversed(list(envelope.context.items())))
        )
        assert decrypt(reordered, provider=provider) == SECRET


class TestTamperDetection:
    def test_an_altered_ciphertext_fails(self, provider) -> None:
        envelope = sealed(provider)
        flipped = bytearray(envelope.ciphertext)
        flipped[0] ^= 0x01
        with pytest.raises(KeyRevoked):
            decrypt(dataclasses.replace(envelope, ciphertext=bytes(flipped)), provider=provider)

    def test_an_altered_wrapped_key_fails(self, provider) -> None:
        envelope = sealed(provider)
        flipped = bytearray(envelope.wrapped_key)
        flipped[-1] ^= 0x01
        with pytest.raises(KeyRevoked):
            decrypt(dataclasses.replace(envelope, wrapped_key=bytes(flipped)), provider=provider)

    def test_an_altered_nonce_fails(self, provider) -> None:
        envelope = sealed(provider)
        with pytest.raises(KeyRevoked):
            decrypt(dataclasses.replace(envelope, nonce=b"\x00" * NONCE_BYTES), provider=provider)

    def test_the_untampered_envelope_still_works(self, provider) -> None:
        """So the four above are not vacuous."""
        assert decrypt(sealed(provider), provider=provider) == SECRET


class TestNoncesAndKeys:
    def test_every_encryption_uses_a_fresh_data_key(self, provider) -> None:
        """A data key is used once. Reusing one would make two ciphertexts
        share a key across a boundary nobody drew."""
        wrapped = {sealed(provider).wrapped_key for _ in range(20)}
        assert len(wrapped) == 20

    def test_every_encryption_uses_a_fresh_nonce(self, provider) -> None:
        """Reusing a nonce under one key in GCM does not merely weaken it — it
        leaks the XOR of the plaintexts and lets an attacker forge."""
        nonces = {sealed(provider).nonce for _ in range(50)}
        assert len(nonces) == 50

    def test_identical_plaintexts_give_different_ciphertexts(self, provider) -> None:
        assert sealed(provider).ciphertext != sealed(provider).ciphertext

    def test_the_nonce_is_ninety_six_bits(self, provider) -> None:
        assert len(sealed(provider).nonce) == NONCE_BYTES == 12

    def test_the_data_key_is_aes_256(self) -> None:
        assert DATA_KEY_BYTES == 32


class TestWhoHoldsWhat:
    def test_the_envelope_records_which_key_wrapped_it(self, provider) -> None:
        """Rotation without this means re-encrypting everything at once."""
        assert sealed(provider).key_id == "local-test-key"

    def test_a_provider_cannot_generate_the_customer_key(self) -> None:
        """A provider that could would mean Prama had it at some point, and "we
        never had it" is the claim the whole arrangement exists to make."""
        assert not hasattr(KeyProvider, "generate")
        assert not hasattr(KeyProvider, "create_key")

    def test_the_test_provider_is_named_for_what_it_is(self) -> None:
        """A class called LocalKeyProvider would end up in somebody's
        deployment, and a customer-managed key held by Prama is not one."""
        assert "Test" in LocalTestKeyProvider.__name__
        assert "Never for production" in (LocalTestKeyProvider.__doc__ or "")

    def test_no_cloud_kms_client_is_imported(self) -> None:
        import ast
        import pathlib

        from prama.security import cmk

        tree = ast.parse(pathlib.Path(cmk.__file__).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not {"boto3", "azure", "google"} & imported

    def test_the_module_says_no_cloud_kms_was_exercised(self) -> None:
        from prama.security import cmk

        assert "No cloud KMS has been exercised" in (cmk.__doc__ or "")


class TestAnEnvelopeCannotBeMovedBetweenEstates:
    """Finding S6. The module promises that "a ciphertext moved from one
    tenant's row to another's fails to decrypt".

    The AAD does bind ciphertext to context — but the context travels *inside*
    the envelope, and `decrypt` reconstructed the AAD from the envelope itself.
    Its signature was `decrypt(envelope, *, provider)`: there was no parameter
    with which a caller could say which estate it believed it was reading, so
    the check the docstring describes could not be expressed at all.

    The existing tests exercised the two weaker claims — editing the `context`
    field, and swapping the ciphertext while keeping the context. Copying the
    whole serialised envelope, which is what "moved from one tenant's row to
    another's" means, was never tried, and it worked.
    """

    def sealed(self, tenant: str = "tenant-a", purpose: str = "payroll") -> tuple[Any, Any]:
        provider = LocalTestKeyProvider()
        envelope = encrypt(
            b"tenant-A payroll", provider=provider, tenant_id=tenant, purpose=purpose
        )
        return envelope, provider

    def test_reading_it_as_its_own_estate_works(self) -> None:
        """The positive control. A check that refuses every read is not a
        tenant boundary, it is an outage."""
        envelope, provider = self.sealed()
        assert decrypt(envelope, provider=provider, tenant_id="tenant-a") == b"tenant-A payroll"

    def test_a_whole_envelope_copied_into_another_estate_is_refused(self) -> None:
        """The attack the docstring describes, and the one nothing tried.

        Serialised and rehydrated, because that is how a row moves: through
        `to_dict()` and back, carrying its context with it.
        """
        envelope, provider = self.sealed()
        moved = Envelope.from_dict(envelope.to_dict())
        with pytest.raises(KeyRevoked, match="different estate"):
            decrypt(moved, provider=provider, tenant_id="tenant-b")

    def test_it_is_refused_before_any_key_is_unwrapped(self) -> None:
        """Refused on the context, not by a failed decryption. A provider that
        is asked to unwrap a key for the wrong estate has already been asked
        one question too many."""
        envelope, provider = self.sealed()
        asked: list[Any] = []
        original = provider.unwrap

        def watching(*arguments: Any, **keywords: Any) -> Any:
            asked.append(arguments)
            return original(*arguments, **keywords)

        provider.unwrap = watching  # type: ignore[method-assign]
        with pytest.raises(KeyRevoked):
            decrypt(envelope, provider=provider, tenant_id="tenant-b")
        assert not asked, "the key provider was asked to unwrap for the wrong estate"

    def test_a_purpose_it_was_not_sealed_for_is_refused(self) -> None:
        """The same argument one level down: a key scoped to one purpose must
        not open another's data."""
        envelope, provider = self.sealed()
        with pytest.raises(KeyRevoked, match="different purpose"):
            decrypt(envelope, provider=provider, tenant_id="tenant-a", purpose="reporting")

    def test_omitting_the_tenant_still_works_and_still_checks_nothing(self) -> None:
        """Stated rather than implied. The parameter is optional, so a caller
        that does not pass it gets the old behaviour — which is why
        `tests/architecture` should grow a rule about it before the first
        production caller lands."""
        envelope, provider = self.sealed()
        assert decrypt(envelope, provider=provider) == b"tenant-A payroll"
