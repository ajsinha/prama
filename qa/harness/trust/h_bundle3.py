import sys, subprocess, tempfile, dataclasses, json, os
from pathlib import Path
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.bundle import Manifest, Entry, build_manifest, verify, digest, installed_distributions
from prama.core.errors import ValidationError

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

ENV = {"PRAMA_SECURITY__SESSION_SECRET": "a-real-secret-not-empty"}

# SEC-154: manifest.ed25519 excluded from entry list too? Re-seal a directory that already has one.
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
priv = Ed25519PrivateKey.generate()
pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
bundle154 = a_bundle()
keyfile = bundle154 / "priv.pem"
keyfile.write_bytes(pem)
code1, out1, err1 = run_prama(["bundle", "seal", str(bundle154), "--sign-with", str(keyfile)], env=ENV)
# re-seal the SAME directory (ordinary release operation)
code2, out2, err2 = run_prama(["bundle", "seal", str(bundle154), "--sign-with", str(keyfile)], env=ENV)
code3, out3, err3 = run_prama(["bundle", "verify", str(bundle154)], env=ENV)
ok = code3 == 0
line("SEC-154", "PASS" if ok else "FAIL",
     f"seal1_exit={code1} reseal_exit={code2} verify_after_reseal_exit={code3} (expected: a re-sealed bundle still verifies; predicted defect: manifest.ed25519 gets catalogued as a regular entry on re-seal since build_manifest only skips manifest.json/manifest.sig by name, then gets overwritten with a new signature whose hash no longer matches the catalogued one, so the SECOND seal's own signature file reads as 'modified' forever) verify_stdout={out3!r}")

# SEC-157: --no-sbom possible, help text says rarely right
code4, out4, err4 = run_prama(["bundle", "seal", "--help"])
help_says_rarely_right = "rarely right" in out4.lower()
# NOTE (round 3): case-sensitive substring missed the sentence-initial,
# capitalised "Rarely right:" the help text actually uses -- a harness bug,
# not a product defect (round 2's own published verdict already caught this).
bundle157 = a_bundle()
code5, out5, err5 = run_prama(["bundle", "seal", str(bundle157), "--no-sbom"], env=ENV)
manifest157 = json.loads((bundle157 / "manifest.json").read_text())
empty_sbom = manifest157.get("sbom") == []
line("SEC-157", "PASS" if (help_says_rarely_right and empty_sbom) else "FAIL", f"help_mentions_rarely_right={help_says_rarely_right} sbom_empty={empty_sbom}")

# SEC-158: hashing a multi-gigabyte file bounded memory -- use resource.getrusage before/after hashing a 512MB sparse file (scaled down from 3GiB for practicality)
import resource
bundle158 = a_bundle()
big = bundle158 / "image" / "big.tar"
size = 512 * 1024 * 1024
with open(big, "wb") as f:
    f.seek(size - 1)
    f.write(b"\0")
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
h = digest(big)
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
delta_mb = (after - before) / 1024  # ru_maxrss is in KB on Linux
ok = delta_mb < (size / 1024 / 1024) / 2  # nowhere near loading the whole 512MB into growth
line("SEC-158", "PASS" if ok else "FAIL", f"SCALED PROBE (512MiB, not the stated 3GiB): file_size_mb={size/1024/1024:.0f} rss_growth_mb={delta_mb:.1f} digest={h[:16]}...")

# SEC-160: verifying a directory that is not a bundle says so
bundle160 = Path(tempfile.mkdtemp())
(bundle160 / "random.txt").write_text("nothing to see")
code6, out6, err6 = run_prama(["bundle", "verify", str(bundle160)], env=ENV)
ok = code6 != 0 and ("no manifest.json" in (out6+err6) or "not a bundle" in (out6+err6) or "carries a manifest" in (out6+err6))
line("SEC-160", "PASS" if ok else "FAIL", f"exit={code6} stdout={out6!r} stderr={err6!r}")

# SEC-161: manifest with a missing key fails cleanly (typed refusal, not KeyError)
bundle161 = a_bundle()
run_prama(["bundle", "seal", str(bundle161)], env=ENV)
m = json.loads((bundle161 / "manifest.json").read_text())
del m["entries"]
(bundle161 / "manifest.json").write_text(json.dumps(m))
code7, out7, err7 = run_prama(["bundle", "verify", str(bundle161)], env=ENV)
crashed = "Traceback" in err7 or "KeyError" in err7
line("SEC-161", "FAIL" if crashed else ("PASS" if code7 != 0 else "FAIL"),
     f"exit={code7} crashed_with_raw_traceback={crashed} stderr_tail={err7[-300:]!r} stdout={out7[:200]!r}")

print("SECTION SEC-154..161 DONE")
