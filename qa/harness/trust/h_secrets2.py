import sys, subprocess, threading, logging, io, json as _json
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.secrets.reference import SecretRef, _LOOKS_LIKE_A_SECRET
from prama.secrets.providers import FileSecretProvider, _field_of
from prama.secrets.resolver import SecretResolver, default_resolver
from prama.secrets.spi import SecretProvider, SecretResolutionError
from prama.secrets.value import SecretValue
from prama.secrets.vault import VaultSecretProvider
from prama.core.log import redact_mapping, RedactionFilter, SENSITIVE_KEYS, get_logger

REPO = "/home/ashutosh/PycharmProjects/prama"

# SEC-173: _LOOKS_LIKE_A_SECRET used or removed
r = subprocess.run(["grep", "-rn", "_LOOKS_LIKE_A_SECRET", f"{REPO}/src", f"{REPO}/tests"], capture_output=True, text=True)
hits = [l for l in r.stdout.splitlines() if ":32:" not in l]  # exclude the definition line itself
line("SEC-173", "PASS" if hits else "FAIL", f"grep -rn _LOOKS_LIKE_A_SECRET src/ tests/ (excluding the definition) -> {hits or '(no other references: defined and never used)'}")

# SEC-177: no root configured, file provider reads any readable file
import tempfile, os
p = FileSecretProvider(root=None)
tf = tempfile.NamedTemporaryFile(delete=False, suffix=".secret")
tf.write(b"root-secret-content\n"); tf.close()
refused_with = None
try:
    ref = SecretRef(scheme="file", location=tf.name)
    v = p.resolve(ref)
    can_read_arbitrary = v.reveal() == "root-secret-content"
except SecretResolutionError as e:
    can_read_arbitrary = False
    refused_with = str(e)
finally:
    os.unlink(tf.name)
r2 = subprocess.run(["grep", "-rn", "-i", "file_root\\|file\\.root\\|secrets\\.file\\.root", f"{REPO}/config"], capture_output=True, text=True)
documented_requirement = bool(r2.stdout.strip())
line("SEC-177", "FAIL" if (can_read_arbitrary and not documented_requirement) else "PASS",
     f"with root=None, resolve(file://{tf.name!r}) succeeded reading an arbitrary file={can_read_arbitrary}; documented deployment requirement for secrets.file.root in config/ = {documented_requirement} (grep hits: {r2.stdout.strip().splitlines()[:5]})"
     + (f"; resolve() now raises SecretResolutionError instead of reading: {refused_with}" if refused_with else ""))

# SEC-180: fragment on non-JSON secret refused, secret text never in message
try:
    _field_of("hunter2-plaintext-secret", "password", SecretRef(scheme="file", location="x"))
    line("SEC-180", "FAIL", "no exception")
except SecretResolutionError as e:
    ok = "hunter2-plaintext-secret" not in str(e) and "hunter2-plaintext-secret" not in str(e.context)
    line("SEC-180", "PASS" if ok else "FAIL", f"SecretResolutionError: {e} context={e.context} -- secret_leaked={not ok}")

# SEC-182: non-string field serialised via json.dumps, not TypeError
result = _field_of('{"port": 5432}', "port", SecretRef(scheme="file", location="x"))
line("SEC-182", "PASS" if result == "5432" else "FAIL", f"_field_of('port')={result!r}")

# SEC-185: token resolved through the ordinary resolver as a reference (design pattern), and note the wiring gap
os.environ["QA_VAULT_TOKEN_TEST"] = "s.abc123realtoken"
resolver = SecretResolver([__import__("prama.secrets.providers", fromlist=["EnvironmentSecretProvider"]).EnvironmentSecretProvider()])
resolved_token = resolver.resolve("env://QA_VAULT_TOKEN_TEST").reveal()
vp = VaultSecretProvider(transport=lambda path, token: {}, token=resolved_token, address="https://vault.example.com")
r3 = subprocess.run(["grep", "-rn", "VaultSecretProvider(", f"{REPO}/src/prama"], capture_output=True, text=True)
wired_construction_sites = [l for l in r3.stdout.splitlines() if "vault.py:" not in l and "token=" in l]
ok = resolved_token == "s.abc123realtoken" and vp.available()
line("SEC-185", "PASS" if ok else "FAIL",
     f"token resolved via env:// reference and passed as a literal into VaultSecretProvider(token=...) -- pattern works: available()={vp.available()}. "
     f"grep for a real production call site constructing VaultSecretProvider(token=<resolved-reference>) outside vault.py: {r3.stdout.strip().splitlines()} -- "
     f"only default_resolver() constructs it (with no token at all, unconfigured); no wiring exists yet that resolves env://VAULT_TOKEN and passes it in, so this is a supported-but-unwired mechanism")
del os.environ["QA_VAULT_TOKEN_TEST"]

# SEC-192: Vault not verified against real server -- caveat in docs
r4 = subprocess.run(["grep", "-rln", "-i", "not verified against a real vault\\|nobody has run this against a live\\|not been exercised.*vault\\|neither Vault nor a cloud KMS", f"{REPO}/docs", f"{REPO}/src/prama/secrets"], capture_output=True, text=True)
line("SEC-192", "PASS" if r4.stdout.strip() else "FAIL", f"grep hits: {r4.stdout.strip().splitlines()}")

print("SECTION Secrets-supplement-1 DONE")
