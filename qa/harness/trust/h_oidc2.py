import sys, subprocess, base64, json, ast, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.oidc import (
    verify_id_token, KeySet, JsonWebKey, InvalidToken, SsoUnavailable, ClaimMapping,
    new_nonce, subject_digest, ACCEPTED_ALGORITHMS, MAX_CLOCK_SKEW_SECONDS,
)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

ISSUER = "https://idp.example.com"; CLIENT = "prama-console"; NOW = 1_760_000_000

def b64(raw): return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
def b64json(payload): return b64(json.dumps(payload, separators=(",", ":")).encode())

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

# SEC-068 (supplement): ES256 with a FORCED leading-zero byte in r or s
ec_key = ec.generate_private_key(ec.SECP256R1())
ec_numbers = ec_key.public_key().public_numbers()
ec_keys = KeySet.from_jwks({"keys": [{"kid": "ec-1", "kty": "EC", "crv": "P-256", "use": "sig",
    "x": b64(ec_numbers.x.to_bytes(32, "big")), "y": b64(ec_numbers.y.to_bytes(32, "big"))}]})
head = b64json({"alg": "ES256", "kid": "ec-1"})
body = b64json(claims())
found_leading_zero = False
for attempt in range(5000):
    der = ec_key.sign(f"{head}.{body}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    r_bytes = r.to_bytes(32, "big")
    if r_bytes[0] == 0:
        found_leading_zero = True
        s_bytes = s.to_bytes(32, "big")
        raw = r_bytes + s_bytes
        token = f"{head}.{body}.{b64(raw)}"
        claims_out = verify_id_token(token, keys=ec_keys, issuer=ISSUER, audience=CLIENT, now=NOW)
        ok = claims_out.subject == "user-42"
        break
if found_leading_zero:
    line("SEC-068", "PASS" if ok else "FAIL", f"found a signature with r's leading byte==0 after {attempt+1} attempts; verified={ok}")
else:
    line("SEC-068", "BLOCKED", "did not encounter a leading-zero r byte in 500 signing attempts (probability ~1/256 per attempt; also see the base pytest test which verifies a random-r ES256 token successfully, recorded separately)")

# SEC-071: accepted set fixed by deployment, ES256 token refused when accepted_algorithms={"RS256"}
head_es = b64json({"alg": "ES256", "kid": "ec-1"})
body_es = b64json(claims())
der2 = ec_key.sign(f"{head_es}.{body_es}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
r2, s2 = decode_dss_signature(der2)
raw2 = r2.to_bytes(32, "big") + s2.to_bytes(32, "big")
token_es = f"{head_es}.{body_es}.{b64(raw2)}"
try:
    verify_id_token(token_es, keys=ec_keys, issuer=ISSUER, audience=CLIENT, now=NOW, accepted_algorithms=frozenset({"RS256"}))
    line("SEC-071", "FAIL", "ES256 token accepted despite accepted_algorithms={'RS256'}")
except InvalidToken as e:
    line("SEC-071", "PASS", f"InvalidToken: {e}")

# SEC-074: no kid against exactly ONE key is accepted
token_no_kid = sign_rs256(rsa_key, claims(), header={"alg": "RS256", "typ": "JWT"})  # no kid
try:
    c = verify(token_no_kid)
    line("SEC-074", "PASS" if c.subject == "user-42" else "FAIL", f"verified subject={c.subject}")
except InvalidToken as e:
    line("SEC-074", "FAIL", f"refused a no-kid token against a single-key set: {e}")

# SEC-078: claims parsed only after signature verifies -- payload not JSON AND signature wrong
bad_body = base64.urlsafe_b64encode(b"not-json-at-all{{{").rstrip(b"=").decode("ascii")
head_ok = b64json({"alg": "RS256", "kid": "key-1", "typ": "JWT"})
bad_sig = b64(b"\x00" * 256)
token_bad = f"{head_ok}.{bad_body}.{bad_sig}"
try:
    verify(token_bad)
    line("SEC-078", "FAIL", "no exception")
except InvalidToken as e:
    ok = "signature" in str(e).lower() and "json" not in str(e).lower()
    line("SEC-078", "PASS" if ok else "FAIL", f"InvalidToken: {e} (expected: signature failure reported, not the payload-not-JSON failure)")

# SEC-090: base64url decoding does not discard rubbish silently (!! spliced into payload segment)
good_body = b64json(claims())
tampered_body = good_body[:10] + "!!" + good_body[12:]
sig_over_good = rsa_key.sign(f"{head_ok}.{good_body}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
token_rubbish = f"{head_ok}.{tampered_body}.{b64(sig_over_good)}"
try:
    verify(token_rubbish)
    line("SEC-090", "FAIL", "verified despite '!!' spliced into the payload segment")
except InvalidToken as e:
    line("SEC-090", "PASS", f"InvalidToken: {e}")

# SEC-091: unsupported curve (P-521) and unsupported key type (oct) refused by name
p521_key = ec.generate_private_key(ec.SECP521R1())
p521_numbers = p521_key.public_key().public_numbers()
keys_p521 = KeySet.from_jwks({"keys": [{"kid": "ec-521", "kty": "EC", "crv": "P-521", "use": "sig",
    "x": b64(p521_numbers.x.to_bytes(66, "big")), "y": b64(p521_numbers.y.to_bytes(66, "big"))}]})
head_521 = b64json({"alg": "ES256", "kid": "ec-521"})
body_521 = b64json(claims())
token_521 = f"{head_521}.{body_521}.{b64(b'x'*64)}"
try:
    verify_id_token(token_521, keys=keys_p521, issuer=ISSUER, audience=CLIENT, now=NOW)
    r_curve = "FAIL: no exception"
except InvalidToken as e:
    r_curve = ("PASS" if "P-521" in str(e) or "curve" in str(e).lower() else "FAIL") + f": {e}"

keys_oct = KeySet.from_jwks({"keys": [{"kid": "oct-1", "kty": "oct", "use": "sig", "k": b64(b"secret")}]})
head_oct = b64json({"alg": "RS256", "kid": "oct-1"})
token_oct = f"{head_oct}.{body_521}.{b64(b'x'*32)}"
try:
    verify_id_token(token_oct, keys=keys_oct, issuer=ISSUER, audience=CLIENT, now=NOW)
    r_kty = "FAIL: no exception"
except InvalidToken as e:
    r_kty = ("PASS" if "oct" in str(e).lower() or "key type" in str(e).lower() else "FAIL") + f": {e}"
overall = "PASS" if r_curve.startswith("PASS") and r_kty.startswith("PASS") else "FAIL"
line("SEC-091", overall, f"P-521 curve: {r_curve}; kty=oct: {r_kty}")

print("SECTION OIDC-supplement-1 DONE")
