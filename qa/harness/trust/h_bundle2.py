import sys, subprocess, tempfile, dataclasses, json, os
from pathlib import Path
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.bundle import Manifest, Entry, build_manifest, verify, digest
from prama.core.errors import ValidationError
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS

KEY = b"a-deployment-key"
WHEN = "2026-09-10T06:00:00Z"
REPO = "/home/ashutosh/PycharmProjects/prama"
PRAMA = "/home/ashutosh/PycharmProjects/prama/.venv/bin/prama"

def a_bundle():
    d = Path(tempfile.mkdtemp())
    (d / "image").mkdir()
    (d / "chart").mkdir()
    (d / "wheels").mkdir()
    (d / "image" / "prama.tar").write_bytes(b"pretend this is an image")
    (d / "chart" / "prama-0.1.0.tgz").write_bytes(b"pretend this is a chart")
    (d / "wheels" / "prama-0.1.0-py3-none-any.whl").write_bytes(b"a wheel")
    (d / "sqlite.sql").write_text("-- schema")
    return d

def run_prama(args, cwd=None, env=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    r = subprocess.run([PRAMA] + args, capture_output=True, text=True, cwd=cwd or REPO, env=full_env)
    return r.returncode, r.stdout, r.stderr

# SEC-143: stripped seal is not a passing seal
bundle = a_bundle()
manifest = build_manifest(bundle, created_at=WHEN)
result_no_seal = verify(bundle, manifest, key=KEY)  # no seal offered at all
ok = result_no_seal.seal_holds is None and not result_no_seal.is_trustworthy and "proves nothing about where it came from" in result_no_seal.describe()
line("SEC-143", "PASS" if ok else "FAIL", f"seal_holds={result_no_seal.seal_holds} is_trustworthy={result_no_seal.is_trustworthy} describe={result_no_seal.describe()!r}")

# SEC-144: stripped publisher signature does not downgrade to a pass -- via real CLI with --sign-with then delete manifest.ed25519
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
priv = Ed25519PrivateKey.generate()
pem = priv.private_bytes(
    encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.PEM,
    format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PrivateFormat"]).PrivateFormat.PKCS8,
    encryption_algorithm=__import__("cryptography.hazmat.primitives.serialization", fromlist=["NoEncryption"]).NoEncryption(),
)
pub_pem = priv.public_key().public_bytes(
    encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.PEM,
    format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.SubjectPublicKeyInfo,
)
bundle2 = a_bundle()
keyfile = bundle2 / "priv.pem"
keyfile.write_bytes(pem)
pubfile = bundle2 / "pub.pem"
pubfile.write_bytes(pub_pem)
env = {"PRAMA_SECURITY__SESSION_SECRET": "a-real-secret-not-empty"}
code_seal, out_seal, err_seal = run_prama(["bundle", "seal", str(bundle2), "--sign-with", str(keyfile)], env=env)
(bundle2 / "manifest.ed25519").unlink()  # strip the publisher signature
code_verify, out_verify, err_verify = run_prama(["bundle", "verify", str(bundle2), "--publisher-key", str(pubfile)], env=env)
ok = code_verify != 0 and ("publisher key was given" in (out_verify+err_verify) or "no publisher signature was checked" in (out_verify+err_verify) or "proves nothing" in (out_verify+err_verify))
line("SEC-144", "PASS" if ok else "FAIL", f"seal_exit={code_seal} verify_exit={code_verify} verify_stdout={out_verify!r}")

# SEC-145: signature offered with no key to check it -- CLI prints paragraph telling operator to pass a key
code_v2, out_v2, err_v2 = run_prama(["bundle", "verify", str(bundle2)], env=env)  # no --publisher-key, but manifest.sig exists (seal); did we sign without ed25519? need a bundle WITH a signature file present but no key given
# rebuild a fresh signed bundle for this specific case
bundle2b = a_bundle()
keyfile2b = bundle2b / "priv.pem"; keyfile2b.write_bytes(pem)
run_prama(["bundle", "seal", str(bundle2b), "--sign-with", str(keyfile2b)], env=env)
code_v3, out_v3, err_v3 = run_prama(["bundle", "verify", str(bundle2b)], env=env)  # no --publisher-key at all
ok = "Pass --publisher-key" in out_v3 or "pass a key" in out_v3.lower() or "no key was given" in out_v3.lower()
line("SEC-145", "PASS" if ok else "FAIL", f"exit={code_v3} stdout={out_v3!r}")

# SEC-149: either signature suffices, neither silently assumed -- 4 bundles: seal only, signature only, both, neither
bundle_both = a_bundle()
m_both = build_manifest(bundle_both, created_at=WHEN)
seal_both = m_both.seal(KEY)
sig_both = m_both.sign(priv)
r_seal_only = verify(bundle_both, m_both, key=KEY, seal=seal_both)
r_sig_only = verify(bundle_both, m_both, public_key=priv.public_key(), signature=sig_both)
r_both = verify(bundle_both, m_both, key=KEY, seal=seal_both, public_key=priv.public_key(), signature=sig_both)
r_neither = verify(bundle_both, m_both)
ok = r_seal_only.is_trustworthy and r_sig_only.is_trustworthy and r_both.is_trustworthy and not r_neither.is_trustworthy
line("SEC-149", "PASS" if ok else "FAIL", f"seal_only={r_seal_only.is_trustworthy} sig_only={r_sig_only.is_trustworthy} both={r_both.is_trustworthy} neither={r_neither.is_trustworthy}")

# SEC-150: seal pinned to independent HMAC vector (RFC 2104, hashlib only, no hmac import)
import hashlib
def manual_hmac_sha256(key, msg):
    block_size = 64
    if len(key) > block_size:
        key = hashlib.sha256(key).digest()
    key = key.ljust(block_size, b"\x00")
    o_pad = bytes(x ^ 0x5c for x in key)
    i_pad = bytes(x ^ 0x36 for x in key)
    inner = hashlib.sha256(i_pad + msg).digest()
    return hashlib.sha256(o_pad + inner).hexdigest()
expect = manual_hmac_sha256(KEY, manifest.content_hash.encode("ascii"))
actual = manifest.seal(KEY)
line("SEC-150", "PASS" if actual == expect else "FAIL", f"manifest.seal(KEY)={actual} manual_rfc2104={expect}")

# SEC-151: seal comparison constant-time (hmac.compare_digest), requires a key -- key=None doesn't crash, doesn't pass
bundle5 = a_bundle()
m5 = build_manifest(bundle5, created_at=WHEN)
seal5 = m5.seal(KEY)
result5 = verify(bundle5, m5, key=None, seal=seal5)
import inspect
src = inspect.getsource(verify)
uses_compare_digest = "hmac.compare_digest" in src
ok = result5.seal_holds is False and uses_compare_digest
line("SEC-151", "PASS" if ok else "FAIL", f"seal_holds_with_key_None={result5.seal_holds} uses_compare_digest={uses_compare_digest}")

print("SECTION SEC-143..151 DONE")
