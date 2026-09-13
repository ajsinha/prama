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

def write_manifest_json(d, manifest):
    """Write manifest.json exactly as `prama bundle seal` and the real
    tests/security/test_bundle.py `bundle` fixture do: `manifest.to_dict()`,
    which is the only serialisation that includes `content_hash`. verify()'s
    `declared_hash` now defaults to reading that field from *this* file on
    disk (see security/bundle.py::_declared_on_disk) rather than from the
    in-memory Manifest object; a fixture that never writes this file makes
    every verify() call see an absent declared hash and therefore always
    manifest_intact=False by construction -- correct per the fix (SEC-142),
    but it means a test relying on manifest_intact must write this file or
    the assertion is not testing what it claims to."""
    (d / "manifest.json").write_text(json.dumps(manifest.to_dict()))

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
# NOTE (round 3): verify()'s declared_hash now defaults to reading
# manifest.json's content_hash from disk (SEC-142's fix); a bundle built with
# build_manifest() alone and never written to disk has no such file, so
# manifest_intact -- and therefore is_trustworthy -- would be False by
# construction regardless of whether the bundle is genuinely clean. Writing
# manifest.json is what `prama bundle seal` and the real
# tests/security/test_bundle.py `bundle` fixture both do; added here to match.
bundle = a_bundle()
manifest = build_manifest(bundle, created_at=WHEN)
write_manifest_json(bundle, manifest)
seal = manifest.seal(KEY)
result = verify(bundle, manifest, key=KEY, seal=seal)
ok = result.is_trustworthy and "seal holds" in result.describe()
line("SEC-136", "PASS" if ok else "FAIL", f"is_trustworthy={result.is_trustworthy} describe={result.describe()!r}")

# SEC-140: a file nobody signed for -- does is_trustworthy actually go False? (Q-18)
bundle2 = a_bundle()
manifest2 = build_manifest(bundle2, created_at=WHEN)
write_manifest_json(bundle2, manifest2)
seal2 = manifest2.seal(KEY)
(bundle2 / "evil.whl").write_bytes(b"arbitrary code")
result2 = verify(bundle2, manifest2, key=KEY, seal=seal2)
ok = result2.unexpected == ("evil.whl",) and not result2.is_trustworthy
line("SEC-140", "PASS" if ok else "FAIL", f"unexpected={result2.unexpected} is_trustworthy={result2.is_trustworthy} (expected: False -- Q-18 says an unexpected file must make the bundle untrustworthy) describe={result2.describe()!r}")

# SEC-141: manifest.sig and manifest.ed25519 not reported as unsigned-for files (sealed AND signed scenario)
bundle3 = a_bundle()
manifest3 = build_manifest(bundle3, created_at=WHEN)
seal3 = manifest3.seal(KEY)
(bundle3 / "manifest.json").write_text(json.dumps(manifest3.to_dict()))
(bundle3 / "manifest.sig").write_text(seal3)
(bundle3 / "manifest.ed25519").write_text("deadbeef" * 16)
result3 = verify(bundle3, manifest3, key=KEY, seal=seal3)
ok = result3.unexpected == ()
line("SEC-141", "PASS" if ok else "FAIL", f"unexpected={result3.unexpected}")

# SEC-142: a manifest whose stated hash doesn't match its actual bytes -- T6 shape check.
# Precondition per the catalogue: "a bundle whose manifest.json has an entry's
# hash edited and its content_hash left alone". This requires an on-disk
# manifest.json that is internally inconsistent (one entry's sha256 edited,
# the top-level content_hash left stale), loaded back the way the real CLI's
# `_load()` does -- a Manifest rebuilt from the JSON payload, with the stale
# `content_hash` field returned separately as `declared` rather than trusted.
bundle4 = a_bundle()
manifest4 = build_manifest(bundle4, created_at=WHEN)
write_manifest_json(bundle4, manifest4)
correct_declared_hash = manifest4.content_hash
# Hand-edit manifest.json on disk: change one entry's sha256, leave content_hash alone.
payload = json.loads((bundle4 / "manifest.json").read_text())
payload["entries"][0]["sha256"] = "0" * 64
(bundle4 / "manifest.json").write_text(json.dumps(payload))
# Reload exactly as cli/bundle.py::_load() does: rebuild the Manifest from the
# (now-tampered) entries, and take `declared` from the JSON's content_hash
# field separately -- which is still the OLD, stale, correct value.
tampered_entries = tuple(
    Entry(path=e["path"], sha256=e["sha256"], bytes=e["bytes"], kind=e.get("kind", "other"))
    for e in payload["entries"]
)
loaded_manifest = Manifest(
    product=payload["product"], version=payload["version"], created_at=payload["created_at"],
    entries=tampered_entries, sbom=tuple((n, v) for n, v in payload.get("sbom", [])),
    manifest_version=payload.get("manifest_version", "1.0"),
    publisher_signed=bool(payload.get("publisher_signed", False)),
)
declared_from_disk = str(payload.get("content_hash", ""))
assert declared_from_disk == correct_declared_hash, "test setup: content_hash should still be the stale, untampered value"
result4 = verify(bundle4, loaded_manifest, key=KEY, seal=manifest4.seal(KEY), declared_hash=declared_from_disk)
line("SEC-142", "FAIL" if result4.manifest_intact else "PASS",
     f"declared(stale, from disk)={declared_from_disk[:16]}... computed(from tampered entries)={loaded_manifest.content_hash[:16]}... "
     f"manifest_intact={result4.manifest_intact} (expected False -- an entry's hash was edited on disk without updating the stale content_hash alongside it, so a genuine recomputation over the tampered content must disagree with what the file claims) modified={result4.modified}")

print("SECTION SEC-136..142 DONE")
