import sys, subprocess, tempfile, dataclasses, json
from pathlib import Path
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.bundle import Manifest, Entry, build_manifest, verify, digest, installed_distributions
from prama.core.errors import ValidationError

KEY = b"a-deployment-key"
WHEN = "2026-09-10T06:00:00Z"

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

# run the real existing test file, map its results
r = subprocess.run([sys.executable, "-m", "pytest", "tests/security/test_bundle.py", "-v"],
                    capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout
def pyresult(name):
    for l in out.splitlines():
        if name in l:
            return "PASSED" in l
    return None

mapping = {
    "SEC-137": "test_a_modified_file_is_named_as_modified",
    "SEC-138": "test_a_missing_file_is_named_as_missing",
    "SEC-139": "test_modified_is_reported_before_missing",
    "SEC-146": "test_another_key_does_not_verify",
    "SEC-147": "test_a_malformed_signature_is_just_no",
    "SEC-148": "test_a_holding_signature_with_a_failing_seal_is_not_a_finding",
    "SEC-152": "test_the_serialisation_is_stable",
    "SEC-153": "test_it_excludes_itself_and_its_signature",
    "SEC-155": "test_it_classifies_what_it_finds",
    "SEC-156": "test_it_records_what_is_installed_not_what_was_asked_for",
    "SEC-159": "test_a_missing_directory_is_refused",
}
for cid, testname in mapping.items():
    ok = pyresult(testname)
    matching = [l.strip() for l in out.splitlines() if testname in l]
    line(cid, "PASS" if ok else "FAIL", f"pytest tests/security/test_bundle.py::{testname} -> {matching}")

# SEC-136: sealed bundle verifies, description names which signature held (both HMAC and Ed25519 paths)
bundle = a_bundle()
manifest = build_manifest(bundle, created_at=WHEN)
seal = manifest.seal(KEY)
result = verify(bundle, manifest, key=KEY, seal=seal)
ok = result.is_trustworthy and "seal holds" in result.describe()
line("SEC-136", "PASS" if ok else "FAIL", f"is_trustworthy={result.is_trustworthy} describe={result.describe()!r}")

# SEC-140: a file nobody signed for -- does is_trustworthy actually go False? (Q-18)
bundle2 = a_bundle()
manifest2 = build_manifest(bundle2, created_at=WHEN)
seal2 = manifest2.seal(KEY)
(bundle2 / "evil.whl").write_bytes(b"arbitrary code")
result2 = verify(bundle2, manifest2, key=KEY, seal=seal2)
ok = result2.unexpected == ("evil.whl",) and not result2.is_trustworthy
line("SEC-140", "PASS" if ok else "FAIL", f"unexpected={result2.unexpected} is_trustworthy={result2.is_trustworthy} (expected: False -- Q-18 says an unexpected file must make the bundle untrustworthy) describe={result2.describe()!r}")

# SEC-141: manifest.sig and manifest.ed25519 not reported as unsigned-for files (sealed AND signed scenario)
bundle3 = a_bundle()
manifest3 = build_manifest(bundle3, created_at=WHEN)
seal3 = manifest3.seal(KEY)
(bundle3 / "manifest.json").write_text(json.dumps(json.loads(manifest3.content())))
(bundle3 / "manifest.sig").write_text(seal3)
(bundle3 / "manifest.ed25519").write_text("deadbeef" * 16)
result3 = verify(bundle3, manifest3, key=KEY, seal=seal3)
ok = result3.unexpected == ()
line("SEC-141", "PASS" if ok else "FAIL", f"unexpected={result3.unexpected}")

# SEC-142: a manifest whose stated hash doesn't match its actual bytes -- T6 shape check
# verify() computes stored_hash = manifest.content_hash (same object) then recomputes
# hashlib.sha256(manifest.content()) from the SAME object -- can this EVER be False?
bundle4 = a_bundle()
manifest4 = build_manifest(bundle4, created_at=WHEN)
# simulate a "hand-edited manifest.json on disk with one entry's hash edited" by building
# a Manifest object with a tampered entry (this is what a real caller would pass in after
# loading a tampered manifest.json from disk)
tampered_entries = list(manifest4.entries)
tampered_entries[0] = dataclasses.replace(tampered_entries[0], sha256="0" * 64)
tampered_manifest = dataclasses.replace(manifest4, entries=tuple(tampered_entries))
result4 = verify(bundle4, tampered_manifest, key=KEY, seal=manifest4.seal(KEY))
line("SEC-142", "FAIL" if result4.manifest_intact else "PASS",
     f"manifest_intact={result4.manifest_intact} (expected False -- a manifest whose entries were edited after being read from disk should be caught, but verify() recomputes content_hash from the SAME tampered object it was just given, so intact = (tampered_manifest.content_hash == sha256(tampered_manifest.content())) is a tautology and can NEVER be False) modified={result4.modified}")

print("SECTION SEC-136..142 DONE")
