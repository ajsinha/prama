import sys, subprocess, base64, json, ast, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.oidc import (
    verify_id_token, KeySet, InvalidToken, SsoUnavailable, ClaimMapping,
    new_nonce, subject_digest,
)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

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
            "email": "jsmith@example.com", "name": "J Smith"}
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

# SEC-088 (full spec): 1000 nonces, all distinct, length matches secrets.token_urlsafe(32)
nonces = [new_nonce() for _ in range(1000)]
ok = len(set(nonces)) == 1000 and all(len(n) == 43 for n in nonces)  # token_urlsafe(32) -> 43 chars
line("SEC-088", "PASS" if ok else "FAIL", f"n_generated=1000 n_distinct={len(set(nonces))} all_len_43={all(len(n)==43 for n in nonces)} sample_len={len(nonces[0])}")

# SEC-089 (all 4 variants): two segments, four segments, non-base64url segment, empty string
variants = {
    "two_segments": "abc.def",
    "four_segments": "abc.def.ghi.jkl",
    "non_base64url_segment": f"{b64json({'alg':'RS256'})}.!!!not-valid-base64url!!!.{b64(b'x'*32)}",
    "empty_string": "",
}
results = {}
for name, tok in variants.items():
    try:
        verify(tok)
        results[name] = "NOT REFUSED"
    except InvalidToken:
        results[name] = "InvalidToken"
    except Exception as e:
        results[name] = f"CRASHED: {type(e).__name__}: {e}"
ok = all(v == "InvalidToken" for v in results.values())
line("SEC-089", "PASS" if ok else "FAIL", f"results={results}")

# SEC-092: failure reason reaches operator (logs/exception) not the browser -- static check of the console sign-in route
r = subprocess.run(["grep", "-rn", "-B3", "-A15", "InvalidToken\\|SsoUnavailable", "/home/ashutosh/PycharmProjects/prama/src/prama/web/routes/auth_routes.py"], capture_output=True, text=True)
auth_src = r.stdout
line("SEC-092", "INFO-PENDING", f"grep context around OIDC exception handling in auth_routes.py ({len(auth_src.splitlines())} lines) -- see follow-up manual read")

# SEC-092 follow-up: the case's Steps say "drive a failed sign-in through the
# console" -- that requires a console route that calls into
# prama.security.oidc at all. Check the whole web+api tree, not just
# auth_routes.py, for any such wiring.
r2 = subprocess.run(["grep", "-rn", "-l", "InvalidToken\\|SsoUnavailable\\|verify_id_token\\|prama\\.security\\.oidc\\|from prama\\.security import oidc\\|security\\.oidc",
                      "/home/ashutosh/PycharmProjects/prama/src/prama/web", "/home/ashutosh/PycharmProjects/prama/src/prama/api"],
                     capture_output=True, text=True)
wired_files = [l for l in r2.stdout.strip().splitlines() if "__pycache__" not in l]
console_has_oidc_route = bool(wired_files)
if console_has_oidc_route:
    verdict_note = "a console route exists to drive; case is executable"
else:
    verdict_note = ("no console or API route calls prama.security.oidc at all; the module ships "
                     "tested and standalone (docs/19 W10.3) but sign-in (auth_routes.py) is "
                     "local-password-only, so this case's Steps (drive a failed sign-in through the "
                     "console) cannot be carried out against this build -- cannot be verified true or "
                     "false, treated as FAIL rather than a silent pass")
line("SEC-092", "PASS" if console_has_oidc_route else "FAIL",
     f"files under src/prama/web or src/prama/api referencing OIDC verification machinery: {wired_files} -- {verdict_note}")

# SEC-093: subject keyed on issuer+subject together
d1 = subject_digest("https://idp-a.example.com", "user-42")
d2 = subject_digest("https://idp-b.example.com", "user-42")  # same sub, different issuer
ok = d1 != d2
line("SEC-093", "PASS" if ok else "FAIL", f"digest(idp-a,user-42)={d1} digest(idp-b,user-42)={d2} differ={ok}")

# SEC-095: groups as string, as roles, or absent
t_string = sign_rs256(rsa_key, claims(groups="owners"))
t_roles = sign_rs256(rsa_key, claims(roles=["owners"]))
t_absent = sign_rs256(rsa_key, claims())
c1 = verify(t_string); c2 = verify(t_roles); c3 = verify(t_absent)
ok = c1.groups == ("owners",) and c2.groups == ("owners",) and c3.groups == ()
line("SEC-095", "PASS" if ok else "FAIL", f"groups_as_string={c1.groups} roles_as_list={c2.groups} absent={c3.groups}")

# SEC-096: without sso extra, SsoUnavailable by name
script = '''
import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
import builtins
real_import = builtins.__import__
def fake_import(name, *a, **kw):
    if name == "cryptography" or name.startswith("cryptography."):
        raise ImportError("masked for QA")
    return real_import(name, *a, **kw)
builtins.__import__ = fake_import
from prama.security.oidc import verify_id_token, KeySet, SsoUnavailable
try:
    verify_id_token("a.b.c", keys=KeySet(), issuer="x", audience="y", now=0)
    print("NO_EXCEPTION")
except SsoUnavailable as e:
    print("SsoUnavailable", getattr(e, "code", "?"), "sso" in str(e))
except Exception as e:
    print("WRONG_TYPE", type(e).__name__, e)
'''
r2 = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
out2 = r2.stdout.strip()
ok = out2.startswith("SsoUnavailable") and "SSO.UNAVAILABLE" in out2 and "True" in out2
line("SEC-096", "PASS" if ok else "FAIL", f"subprocess with cryptography masked -> stdout={out2!r} stderr={r2.stderr[-200:]!r}")

# SEC-097: verifier fetches nothing -- no network call/HTTP client import anywhere in oidc.py
src = open("/home/ashutosh/PycharmProjects/prama/src/prama/security/oidc.py").read()
tree = ast.parse(src)
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports.update(a.name for a in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imports.add(node.module)
network_names = {"httpx", "requests", "urllib.request", "http.client", "aiohttp", "socket"}
hits = imports & network_names
line("SEC-097", "PASS" if not hits else "FAIL", f"imports={sorted(imports)} network_hits={hits}")

print("SECTION OIDC-supplement-2 DONE")
