import sys, subprocess, tempfile, dataclasses, json, os
from pathlib import Path
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.bundle import Manifest, Entry, build_manifest, verify, digest

REPO = "/home/ashutosh/PycharmProjects/prama"
PRAMA = "/home/ashutosh/PycharmProjects/prama/.venv/bin/prama"
WHEN = "2026-09-10T06:00:00Z"

def a_bundle():
    d = Path(tempfile.mkdtemp())
    (d / "image").mkdir(); (d / "chart").mkdir(); (d / "wheels").mkdir()
    (d / "image" / "prama.tar").write_bytes(b"pretend this is an image")
    (d / "chart" / "prama-0.1.0.tgz").write_bytes(b"pretend this is a chart")
    (d / "wheels" / "prama-0.1.0-py3-none-any.whl").write_bytes(b"a wheel")
    (d / "sqlite.sql").write_text("-- schema")
    return d

def run_prama(args, cwd=None, env=None):
    full_env = dict(os.environ)
    if env: full_env.update(env)
    r = subprocess.run([PRAMA] + args, capture_output=True, text=True, cwd=cwd or REPO, env=full_env)
    return r.returncode, r.stdout, r.stderr

ENV = {"PRAMA_SECURITY__SESSION_SECRET": "a-real-secret-not-empty"}

# SEC-162: exits 3 on an untrustworthy bundle, text and --json both, "Do not install this bundle."
bundle = a_bundle()
run_prama(["bundle", "seal", str(bundle)], env=ENV)
(bundle / "sqlite.sql").write_text("-- tampered")
code_text, out_text, err_text = run_prama(["bundle", "verify", str(bundle)], env=ENV)
code_json, out_json, err_json = run_prama(["--json", "bundle", "verify", str(bundle)], env=ENV)
ok = code_text == 3 and code_json == 3 and "Do not install this bundle." in out_text
line("SEC-162", "PASS" if ok else "FAIL", f"text_exit={code_text} json_exit={code_json} do_not_install_present={'Do not install this bundle.' in out_text} text_out={out_text!r}")

# SEC-163: --json reports same verdict as text; JSON carries required keys; note signature_holds omission
d_json = json.loads(out_json)
required = {"missing", "modified", "unexpected", "manifest_intact", "seal_holds", "trustworthy"}
has_all = required <= set(d_json.keys())
same_verdict = (code_json == 3) == (not d_json["trustworthy"]) == (code_text == 3)
signature_holds_omitted = "signature_holds" not in d_json
line("SEC-163", "PASS" if (has_all and same_verdict) else "FAIL",
     f"json_keys={sorted(d_json.keys())} has_required={has_all} same_verdict={same_verdict} signature_holds_omitted_from_to_dict={signature_holds_omitted} (catalogue's own Why flags this as a known gap, not asserted in Expected)")

# SEC-164: sealing refuses with empty session secret
bundle164 = a_bundle()
code164, out164, err164 = run_prama(["bundle", "seal", str(bundle164)], env={"PRAMA_SECURITY__SESSION_SECRET": ""})
ok = code164 != 0 and ("session_secret" in (out164+err164) or "secret" in (out164+err164).lower())
line("SEC-164", "PASS" if ok else "FAIL", f"exit={code164} stdout={out164!r} stderr={err164!r}")

# SEC-165: private key read from file, never argv -- flag only accepts a path; check no hex-argument form exists
code165, out165, err165 = run_prama(["bundle", "seal", "--help"])
only_pem_path_flag = "KEY.pem" in out165 and "--sign-with-hex" not in out165 and "--private-key-hex" not in out165
line("SEC-165", "PASS" if only_pem_path_flag else "FAIL", f"help_excerpt={[l for l in out165.splitlines() if 'sign-with' in l]}")

# SEC-166: encrypted PEM refused with a usable message
bundle166 = a_bundle()
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, BestAvailableEncryption
priv166 = Ed25519PrivateKey.generate()
enc_pem = priv166.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, BestAvailableEncryption(b"a-passphrase"))
keyfile166 = bundle166 / "enc.pem"
keyfile166.write_bytes(enc_pem)
code166, out166, err166 = run_prama(["bundle", "seal", str(bundle166), "--sign-with", str(keyfile166)], env=ENV)
combined = out166 + err166
mentions_encrypted = "encrypt" in combined.lower() or "passphrase" in combined.lower() or "password" in combined.lower()
crashed_with_type_error = "TypeError" in combined and "Traceback" in combined
line("SEC-166", "PASS" if (code166 != 0 and mentions_encrypted and not crashed_with_type_error) else "FAIL",
     f"exit={code166} mentions_encrypted_or_passphrase={mentions_encrypted} raw_traceback_leaked={crashed_with_type_error} combined_tail={combined[-400:]!r}")

# SEC-167: sealing says how much the seal is worth, success path, with and without --sign-with
bundle167a = a_bundle()
code167a, out167a, _ = run_prama(["bundle", "seal", str(bundle167a)], env=ENV)
from cryptography.hazmat.primitives.serialization import NoEncryption
priv167 = Ed25519PrivateKey.generate()
pem167 = priv167.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
bundle167b = a_bundle()
keyfile167 = bundle167b / "priv.pem"; keyfile167.write_bytes(pem167)
code167b, out167b, _ = run_prama(["bundle", "seal", str(bundle167b), "--sign-with", str(keyfile167)], env=ENV)
hmac_paragraph_always = ("HMAC" in out167a and "HMAC" in out167b)
ed25519_paragraph_when_signed = "Ed25519" in out167b
warning_when_unsigned = "cannot check" in out167a or "no provenance" in out167a or "carries no provenance" in out167a
ok = hmac_paragraph_always and ed25519_paragraph_when_signed and warning_when_unsigned
line("SEC-167", "PASS" if ok else "FAIL", f"hmac_paragraph_always={hmac_paragraph_always} ed25519_paragraph_when_signed={ed25519_paragraph_when_signed} unsigned_warning_present={warning_when_unsigned}")

print("SECTION SEC-162..167 DONE")
