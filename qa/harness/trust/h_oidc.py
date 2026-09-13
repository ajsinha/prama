import sys, subprocess, base64, json, hmac, hashlib, ast, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.oidc import (
    verify_id_token, KeySet, JsonWebKey, InvalidToken, SsoUnavailable, ClaimMapping,
    new_nonce, subject_digest, ACCEPTED_ALGORITHMS, MAX_CLOCK_SKEW_SECONDS, _b64url,
)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

ISSUER = "https://idp.example.com"
CLIENT = "prama-console"
NOW = 1_760_000_000

def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def b64json(payload: dict) -> str:
    return b64(json.dumps(payload, separators=(",", ":")).encode())

rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
numbers = rsa_key.public_key().public_numbers()
jwks = KeySet.from_jwks({"keys": [{
    "kid": "key-1", "kty": "RSA", "alg": "RS256", "use": "sig",
    "n": b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
    "e": b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
}]})

def claims(**changes):
    base = {"sub": "user-42", "iss": ISSUER, "aud": CLIENT, "exp": NOW + 300, "iat": NOW - 10,
            "email": "jsmith@example.com", "name": "J Smith", "groups": ["data-owners", "everyone"]}
    base.update(changes)
    return base

def sign_rs256(key, payload, *, header=None):
    head = b64json(header or {"alg": "RS256", "kid": "key-1", "typ": "JWT"})
    body = b64json(payload)
    signature = key.sign(f"{head}.{body}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{b64(signature)}"

def verify(token, **changes):
    kwargs = {"issuer": ISSUER, "audience": CLIENT, "now": NOW}
    kwargs.update(changes)
    return verify_id_token(token, keys=jwks, **kwargs)

# --- 1. run the real existing test suite, map results ---
r = subprocess.run([sys.executable, "-m", "pytest", "tests/security/test_oidc.py", "-v"],
                    capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout

def pyresult(name):
    for l in out.splitlines():
        if name in l:
            return "PASSED" in l
    return None

mapping = {
    "SEC-067": "test_it_verifies_and_returns_the_claims",
    "SEC-069": "test_alg_none_is_refused",
    "SEC-070": "test_hmac_signed_with_the_public_key_is_refused",
    "SEC-072": "test_an_unknown_kid_is_refused_rather_than_tried_against_every_key",
    "SEC-073": "test_a_token_with_no_kid_against_several_keys_is_refused",
    "SEC-075": "test_an_empty_key_set_verifies_nothing",
    "SEC-076": "test_an_encryption_key_is_not_a_signing_key",
    "SEC-077": "test_an_altered_payload_is_refused",
    "SEC-079": "test_a_token_from_another_issuer_is_refused",
    "SEC-080": "test_a_token_for_another_client_is_refused",
    "SEC-081": "test_an_audience_list_containing_us_is_accepted",
    "SEC-082": "test_an_expired_token_is_refused",
    "SEC-083": "test_a_token_from_the_future_is_refused",
    "SEC-084": "test_a_not_yet_valid_token_is_refused",
    "SEC-085": "test_a_missing_required_claim_is_refused",
    "SEC-086": "test_an_empty_subject_is_refused",
    "SEC-087": "test_a_replayed_token_without_our_nonce_is_refused",
    "SEC-088": "test_a_nonce_is_unpredictable",
    "SEC-089": "test_a_malformed_token_is_refused",
    "SEC-068": "test_an_es256_token_verifies",
    "SEC-094": "test_an_unmapped_group_grants_nothing",
}
for cid, testname in mapping.items():
    ok = pyresult(testname)
    matching = [l.strip() for l in out.splitlines() if testname in l]
    line(cid, "PASS" if ok else "FAIL", f"pytest tests/security/test_oidc.py::{testname} -> {matching}")

print("SECTION OIDC-mapped-from-pytest DONE")
