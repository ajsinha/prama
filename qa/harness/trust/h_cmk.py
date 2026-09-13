import sys, subprocess, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.cmk import (
    encrypt, decrypt, Envelope, KeyProvider, LocalTestKeyProvider, KeyRevoked, CmkUnavailable,
    DATA_KEY_BYTES, NONCE_BYTES, _aad, _aesgcm,
)
from prama.core.errors import PramaError

# SEC-045: round trip
p = LocalTestKeyProvider()
env = encrypt(b"the quick brown fox", provider=p, tenant_id="acme", purpose="samples")
pt = decrypt(env, provider=p, tenant_id="acme", purpose="samples")
line("SEC-045", "PASS" if pt == b"the quick brown fox" else "FAIL", f"decrypted={pt!r}")

# SEC-046: fresh data key every encryption
e1 = encrypt(b"same plaintext", provider=p, tenant_id="acme", purpose="samples")
e2 = encrypt(b"same plaintext", provider=p, tenant_id="acme", purpose="samples")
ok = e1.ciphertext != e2.ciphertext and e1.nonce != e2.nonce and e1.wrapped_key != e2.wrapped_key
line("SEC-046", "PASS" if ok else "FAIL", f"ciphertext_differs={e1.ciphertext!=e2.ciphertext} nonce_differs={e1.nonce!=e2.nonce} wrapped_key_differs={e1.wrapped_key!=e2.wrapped_key}")

# SEC-047: nonce 96 bits, no parameter to supply it
sig = inspect.signature(encrypt)
has_nonce_param = "nonce" in sig.parameters
ok = (not has_nonce_param) and NONCE_BYTES == 12 and len(e1.nonce) == 12
line("SEC-047", "PASS" if ok else "FAIL", f"signature={sig} has_nonce_param={has_nonce_param} NONCE_BYTES={NONCE_BYTES} actual_nonce_len={len(e1.nonce)}")

# SEC-048: data key AES-256, not configurable
r = subprocess.run(["grep", "-rn", "DATA_KEY_BYTES\\s*=", "/home/ashutosh/PycharmProjects/prama/src/prama/security/cmk.py"], capture_output=True, text=True)
r2 = subprocess.run(["grep", "-rn", "config.*key.*bytes\\|DATA_KEY_BYTES", "/home/ashutosh/PycharmProjects/prama/config"], capture_output=True, text=True)
ok = DATA_KEY_BYTES == 32 and not r2.stdout.strip()
line("SEC-048", "PASS" if ok else "FAIL", f"DATA_KEY_BYTES={DATA_KEY_BYTES} config_references={r2.stdout.strip() or '(none)'}")

# SEC-049: ciphertext moved between tenants fails, KeyRevoked before unwrap is asked (test via a provider that errors if asked)
class CountingProvider(LocalTestKeyProvider):
    def __init__(self, key=None):
        super().__init__(key)
        self.unwrap_calls = 0
    def unwrap(self, wrapped, *, context):
        self.unwrap_calls += 1
        return super().unwrap(wrapped, context=context)

cp = CountingProvider()
env_a = encrypt(b"secret data", provider=cp, tenant_id="tenant-A", purpose="samples")
try:
    decrypt(env_a, provider=cp, tenant_id="tenant-B")
    line("SEC-049", "FAIL", "no exception raised when decrypting tenant A's envelope as tenant B")
except KeyRevoked as e:
    ok = "estate" in str(e).lower() and cp.unwrap_calls == 0
    line("SEC-049", "PASS" if ok else "FAIL", f"KeyRevoked: {e} unwrap_was_called={cp.unwrap_calls > 0} (expected: refused BEFORE provider.unwrap is asked)")
except Exception as e:
    line("SEC-049", "FAIL", f"wrong exception {type(e)}: {e}")

# SEC-050: no tenant_id supplied -> decrypts (no cross-tenant protection), and enumerate real call sites
try:
    pt2 = decrypt(env_a, provider=cp)  # tenant_id=None
    decrypts_without_check = pt2 == b"secret data"
except Exception as e:
    decrypts_without_check = False
r3 = subprocess.run(["grep", "-rn", "cmk.decrypt\\|from prama.security.cmk import\\|security\\.cmk\\.decrypt", "/home/ashutosh/PycharmProjects/prama/src"], capture_output=True, text=True)
call_sites = [l for l in r3.stdout.splitlines() if "def decrypt" not in l and "cmk.py" not in l]
line("SEC-050", "PASS" if decrypts_without_check else "FAIL",
     f"decrypt(envelope, provider=p) with tenant_id=None decrypts_without_cross_tenant_check={decrypts_without_check}; real call sites of cmk.decrypt outside cmk.py itself: {call_sites}")

# SEC-051: purpose mismatch refused before unwrap
env_purpose = encrypt(b"x", provider=cp, tenant_id="acme", purpose="samples")
try:
    decrypt(env_purpose, provider=cp, tenant_id="acme", purpose="evidence")
    line("SEC-051", "FAIL", "no exception")
except KeyRevoked as e:
    ok = "purpose" in str(e).lower()
    line("SEC-051", "PASS" if ok else "FAIL", f"KeyRevoked: {e}")

# SEC-052: editing stored context breaks decryption
env_ctx = encrypt(b"y", provider=p, tenant_id="acme", purpose="samples")
d = env_ctx.to_dict()
d["context"]["tenant"] = "acme-modified"
env_tampered = Envelope.from_dict(d)
try:
    decrypt(env_tampered, provider=p, tenant_id="acme-modified", purpose="samples")
    line("SEC-052", "FAIL", "decrypted successfully after editing stored context")
except Exception as e:
    line("SEC-052", "PASS", f"{type(e).__name__}: {e}")

# SEC-053: tampered ciphertext refused
env_c = encrypt(b"z", provider=p, tenant_id="acme", purpose="samples")
tampered_ct = bytearray(env_c.ciphertext)
tampered_ct[0] ^= 0xFF
env_c2 = Envelope(wrapped_key=env_c.wrapped_key, nonce=env_c.nonce, ciphertext=bytes(tampered_ct), key_id=env_c.key_id, context=env_c.context)
try:
    decrypt(env_c2, provider=p, tenant_id="acme", purpose="samples")
    line("SEC-053", "FAIL", "decrypted after bit-flipping ciphertext")
except KeyRevoked as e:
    ok = "own data key" in str(e).lower() or "did not unwrap" in str(e).lower() or "did not decrypt" in str(e).lower()
    line("SEC-053", "PASS" if ok else "FAIL", f"KeyRevoked: {e}")

# SEC-054: tampered wrapped key refused
env_w = encrypt(b"w", provider=p, tenant_id="acme", purpose="samples")
tampered_wk = bytearray(env_w.wrapped_key)
tampered_wk[0] ^= 0xFF
env_w2 = Envelope(wrapped_key=bytes(tampered_wk), nonce=env_w.nonce, ciphertext=env_w.ciphertext, key_id=env_w.key_id, context=env_w.context)
try:
    decrypt(env_w2, provider=p, tenant_id="acme", purpose="samples")
    line("SEC-054", "FAIL", "decrypted after bit-flipping wrapped_key")
except KeyRevoked as e:
    ok = "rotated" in str(e).lower() and "tenant" in str(e).lower()
    line("SEC-054", "PASS" if ok else "FAIL", f"KeyRevoked: {e}")

# SEC-055: wrong customer key cannot unwrap
p_other = LocalTestKeyProvider()
env_x = encrypt(b"v", provider=p, tenant_id="acme", purpose="samples")
try:
    decrypt(env_x, provider=p_other, tenant_id="acme", purpose="samples")
    line("SEC-055", "FAIL", "decrypted with a different provider's key")
except KeyRevoked as e:
    line("SEC-055", "PASS", f"KeyRevoked: {e}")

# SEC-056: revoked key makes every envelope it wrapped unreadable
p_rev = LocalTestKeyProvider()
envs = [encrypt(f"payload-{i}".encode(), provider=p_rev, tenant_id="acme", purpose="samples") for i in range(3)]
p_rev.revoke()
results = []
for e in envs:
    try:
        decrypt(e, provider=p_rev, tenant_id="acme", purpose="samples")
        results.append("decrypted")
    except KeyRevoked as exc:
        results.append("KeyRevoked" if "not a fault" in str(exc).lower() or "usually" in str(exc).lower() else "KeyRevoked(no remedy text)")
ok = all(r.startswith("KeyRevoked") for r in results)
line("SEC-056", "PASS" if ok else "FAIL", f"results={results}")

# SEC-057: revoked key cannot wrap either
p_rev2 = LocalTestKeyProvider()
p_rev2.revoke()
try:
    encrypt(b"nope", provider=p_rev2, tenant_id="acme", purpose="samples")
    line("SEC-057", "FAIL", "no exception on encrypt with revoked provider")
except KeyRevoked as e:
    ok = "new key" in str(e).lower() or "provision" in str(e).lower()
    line("SEC-057", "PASS" if ok else "FAIL", f"KeyRevoked: {e}")

# SEC-058: revocation irreversible/not selective -- check module docstring AND search buyer-facing docs
docstring_ok = "not reversible" in __import__("prama.security.cmk", fromlist=["x"]).__doc__ and "not selective" in __import__("prama.security.cmk", fromlist=["x"]).__doc__
r4 = subprocess.run(["grep", "-rln", "-i", "revoc", "/home/ashutosh/PycharmProjects/prama/docs"], capture_output=True, text=True)
docs_hits = r4.stdout.strip().splitlines()
line("SEC-058", "PASS" if (docstring_ok and docs_hits) else "FAIL", f"module_docstring_states_irreversible_and_not_selective={docstring_ok} docs_mentioning_revocation={docs_hits}")

print("SECTION SEC-045..058 DONE")
