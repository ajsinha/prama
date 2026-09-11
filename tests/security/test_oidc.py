"""ID token verification, attacked.

Every test here that passes a *good* token is scaffolding. The tests that matter
are the ones that forge one, and each forgery is a real attack that has been
accepted by verifiers written in good faith.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from prama.security import oidc
from prama.security.oidc import InvalidToken, KeySet, verify_id_token

cryptography = pytest.importorskip("cryptography", reason="needs the 'sso' extra")

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa  # noqa: E402

ISSUER = "https://idp.example.com"
CLIENT = "prama-console"
NOW = 1_760_000_000


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64json(payload: dict) -> str:
    return b64(json.dumps(payload, separators=(",", ":")).encode())


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def jwks(rsa_key):
    numbers = rsa_key.public_key().public_numbers()
    return KeySet.from_jwks(
        {
            "keys": [
                {
                    "kid": "key-1",
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "n": b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                    "e": b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
                }
            ]
        }
    )


def claims(**changes) -> dict:
    base = {
        "sub": "user-42",
        "iss": ISSUER,
        "aud": CLIENT,
        "exp": NOW + 300,
        "iat": NOW - 10,
        "email": "jsmith@example.com",
        "name": "J Smith",
        "groups": ["data-owners", "everyone"],
    }
    base.update(changes)
    return base


def sign_rs256(rsa_key, payload: dict, *, header: dict | None = None) -> str:
    head = b64json(header or {"alg": "RS256", "kid": "key-1", "typ": "JWT"})
    body = b64json(payload)
    signature = rsa_key.sign(f"{head}.{body}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{b64(signature)}"


def verify(token: str, **changes):
    kwargs = {"issuer": ISSUER, "audience": CLIENT, "now": NOW}
    kwargs.update(changes)
    return verify_id_token(token, **kwargs)


class TestAGoodToken:
    def test_it_verifies_and_returns_the_claims(self, rsa_key, jwks) -> None:
        identity = verify(sign_rs256(rsa_key, claims()), keys=jwks)
        assert identity.subject == "user-42"
        assert identity.email == "jsmith@example.com"
        assert identity.groups == ("data-owners", "everyone")

    def test_an_audience_list_containing_us_is_accepted(self, rsa_key, jwks) -> None:
        token = sign_rs256(rsa_key, claims(aud=["other-app", CLIENT]))
        assert verify(token, keys=jwks).subject == "user-42"

    def test_a_matching_nonce_is_accepted(self, rsa_key, jwks) -> None:
        token = sign_rs256(rsa_key, claims(nonce="abc"))
        assert verify(token, keys=jwks, nonce="abc").nonce == "abc"

    def test_clock_skew_inside_a_minute_is_tolerated(self, rsa_key, jwks) -> None:
        """Clocks drift, and zero tolerance rejects valid tokens in the seconds
        either side of expiry."""
        token = sign_rs256(rsa_key, claims(exp=NOW - 30))
        assert verify(token, keys=jwks).subject == "user-42"


class TestForgeries:
    def test_alg_none_is_refused(self, rsa_key, jwks) -> None:
        """A token asserting it is unsigned. A verifier that dispatches on the
        token's own alg happily verifies nothing."""
        head = b64json({"alg": "none", "kid": "key-1"})
        body = b64json(claims())
        with pytest.raises(InvalidToken, match="not accepted"):
            verify(f"{head}.{body}.", keys=jwks)

    def test_hmac_signed_with_the_public_key_is_refused(self, rsa_key, jwks) -> None:
        """Algorithm confusion. The attacker signs with HMAC using the
        provider's *public* key as the secret — which is public."""
        public_pem = rsa_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        head = b64json({"alg": "HS256", "kid": "key-1"})
        body = b64json(claims(sub="attacker"))
        mac = hmac.new(public_pem, f"{head}.{body}".encode("ascii"), hashlib.sha256).digest()
        with pytest.raises(InvalidToken, match="not accepted"):
            verify(f"{head}.{body}.{b64(mac)}", keys=jwks)

    def test_a_token_signed_by_another_key_is_refused(self, jwks) -> None:
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with pytest.raises(InvalidToken, match="does not verify"):
            verify(sign_rs256(other, claims()), keys=jwks)

    def test_an_unknown_kid_is_refused_rather_than_tried_against_every_key(
        self, rsa_key, jwks
    ) -> None:
        """Trying every key until one verifies turns a rotated-out key — whose
        private half may since have been published — into a valid signer."""
        token = sign_rs256(rsa_key, claims(), header={"alg": "RS256", "kid": "key-rotated-out"})
        with pytest.raises(InvalidToken, match="no key called"):
            verify(token, keys=jwks)

    def test_an_altered_payload_is_refused(self, rsa_key, jwks) -> None:
        token = sign_rs256(rsa_key, claims())
        head, _, signature = token.split(".")
        forged = f"{head}.{b64json(claims(sub='admin'))}.{signature}"
        with pytest.raises(InvalidToken, match="does not verify"):
            verify(forged, keys=jwks)

    def test_a_token_for_another_client_is_refused(self, rsa_key, jwks) -> None:
        """Genuinely signed, genuinely current, and not for us."""
        token = sign_rs256(rsa_key, claims(aud="some-other-app"))
        with pytest.raises(InvalidToken, match="not issued for this client"):
            verify(token, keys=jwks)

    def test_a_token_from_another_issuer_is_refused(self, rsa_key, jwks) -> None:
        token = sign_rs256(rsa_key, claims(iss="https://evil.example.com"))
        with pytest.raises(InvalidToken, match="different provider"):
            verify(token, keys=jwks)

    def test_an_expired_token_is_refused(self, rsa_key, jwks) -> None:
        token = sign_rs256(rsa_key, claims(exp=NOW - 3600))
        with pytest.raises(InvalidToken, match="expired"):
            verify(token, keys=jwks)

    def test_a_token_from_the_future_is_refused(self, rsa_key, jwks) -> None:
        """Accepting one extends its usable life by however far ahead it
        claims to have been issued."""
        token = sign_rs256(rsa_key, claims(iat=NOW + 86400))
        with pytest.raises(InvalidToken, match="in the future"):
            verify(token, keys=jwks)

    def test_a_not_yet_valid_token_is_refused(self, rsa_key, jwks) -> None:
        token = sign_rs256(rsa_key, claims(nbf=NOW + 3600))
        with pytest.raises(InvalidToken, match="not valid yet"):
            verify(token, keys=jwks)

    def test_a_replayed_token_without_our_nonce_is_refused(self, rsa_key, jwks) -> None:
        token = sign_rs256(rsa_key, claims(nonce="from-another-session"))
        with pytest.raises(InvalidToken, match="nonce"):
            verify(token, keys=jwks, nonce="ours")

    def test_a_token_with_no_nonce_is_refused_when_one_was_issued(self, rsa_key, jwks) -> None:
        with pytest.raises(InvalidToken, match="nonce"):
            verify(sign_rs256(rsa_key, claims()), keys=jwks, nonce="ours")

    def test_an_empty_subject_is_refused(self, rsa_key, jwks) -> None:
        """The subject is the identity. An empty one identifies nobody."""
        with pytest.raises(InvalidToken, match="subject is empty"):
            verify(sign_rs256(rsa_key, claims(sub="")), keys=jwks)

    @pytest.mark.parametrize("missing", ["sub", "iss", "aud", "exp"])
    def test_a_missing_required_claim_is_refused(self, rsa_key, jwks, missing: str) -> None:
        payload = claims()
        del payload[missing]
        with pytest.raises(InvalidToken, match=f"no {missing!r} claim"):
            verify(sign_rs256(rsa_key, payload), keys=jwks)

    def test_a_malformed_token_is_refused(self, jwks) -> None:
        with pytest.raises(InvalidToken, match="three dot-separated"):
            verify("not-a-jwt", keys=jwks)

    def test_an_empty_key_set_verifies_nothing(self, rsa_key) -> None:
        with pytest.raises(InvalidToken, match="key set is empty"):
            verify(sign_rs256(rsa_key, claims()), keys=KeySet())


class TestKeySetHygiene:
    def test_an_encryption_key_is_not_a_signing_key(self, rsa_key) -> None:
        """Accepting one would let a key the provider never signs with verify a
        token."""
        numbers = rsa_key.public_key().public_numbers()
        keys = KeySet.from_jwks(
            {
                "keys": [
                    {
                        "kid": "enc-1",
                        "kty": "RSA",
                        "use": "enc",
                        "n": b64(numbers.n.to_bytes(256, "big")),
                        "e": b64(b"\x01\x00\x01"),
                    }
                ]
            }
        )
        assert keys.keys == ()

    def test_a_token_with_no_kid_against_several_keys_is_refused(self, rsa_key) -> None:
        """Guessing is not verification."""
        numbers = rsa_key.public_key().public_numbers()
        entry = {
            "kty": "RSA",
            "use": "sig",
            "n": b64(numbers.n.to_bytes(256, "big")),
            "e": b64(b"\x01\x00\x01"),
        }
        keys = KeySet.from_jwks({"keys": [{**entry, "kid": "a"}, {**entry, "kid": "b"}]})
        token = sign_rs256(rsa_key, claims(), header={"alg": "RS256"})
        with pytest.raises(InvalidToken, match="names no key"):
            verify(token, keys=keys)


class TestEllipticCurve:
    def test_an_es256_token_verifies(self) -> None:
        key = ec.generate_private_key(ec.SECP256R1())
        numbers = key.public_key().public_numbers()
        keys = KeySet.from_jwks(
            {
                "keys": [
                    {
                        "kid": "ec-1",
                        "kty": "EC",
                        "crv": "P-256",
                        "use": "sig",
                        "x": b64(numbers.x.to_bytes(32, "big")),
                        "y": b64(numbers.y.to_bytes(32, "big")),
                    }
                ]
            }
        )
        head = b64json({"alg": "ES256", "kid": "ec-1"})
        body = b64json(claims())
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        der = key.sign(f"{head}.{body}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        assert verify(f"{head}.{body}.{b64(raw)}", keys=keys).subject == "user-42"


class TestClaimMapping:
    def test_an_unmapped_group_grants_nothing(self) -> None:
        """An unmapped group silently granting a default role is how everybody
        in the directory becomes an owner."""
        mapping = oidc.ClaimMapping(roles={"data-owners": "owner"})
        assert mapping.roles_for(["data-owners", "everyone"]) == ("owner",)

    def test_unmapped_groups_are_reported(self) -> None:
        """Somebody who signs in and can see nothing has a configuration
        problem that looks exactly like a permissions bug."""
        mapping = oidc.ClaimMapping(roles={"data-owners": "owner"})
        assert mapping.unmapped(["data-owners", "everyone"]) == ("everyone",)

    def test_no_mapping_at_all_grants_no_roles(self) -> None:
        assert oidc.ClaimMapping().roles_for(["admins"]) == ()


class TestIdentityKeying:
    def test_the_local_identifier_includes_the_issuer(self) -> None:
        """A subject is unique within its issuer and nowhere else, so keying on
        subject alone lets two providers collide onto one account."""
        a = oidc.subject_digest("https://idp-a", "user-1")
        b = oidc.subject_digest("https://idp-b", "user-1")
        assert a != b

    def test_it_is_stable(self) -> None:
        assert oidc.subject_digest(ISSUER, "u") == oidc.subject_digest(ISSUER, "u")


class TestNonces:
    def test_a_nonce_is_unpredictable(self) -> None:
        """A predictable nonce is no protection against replay, which is the
        only thing a nonce is for."""
        assert len({oidc.new_nonce() for _ in range(50)}) == 50
        assert len(oidc.new_nonce()) >= 32
