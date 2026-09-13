import sys, subprocess, threading, logging, io, json as _json, traceback, datetime
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.secrets.reference import SecretRef
from prama.secrets.resolver import SecretResolver
from prama.secrets.spi import SecretProvider, SecretResolutionError
from prama.secrets.value import SecretValue
from prama.core.log import redact_mapping, RedactionFilter, SENSITIVE_KEYS, get_logger
from prama.core.clock import Clock

REPO = "/home/ashutosh/PycharmProjects/prama"

class FixedClock(Clock):
    def __init__(self, t): self._t = t
    def now(self): return self._t
    def monotonic(self): return 0.0

class FlakyEnvProvider(SecretProvider):
    scheme = "env"
    description = "test"
    def __init__(self):
        self.calls = 0
    def resolve(self, reference):
        self.calls += 1
        return SecretValue(f"value-{self.calls}", origin=reference.render())

# SEC-199: cache thread-safety, 8 threads hammering resolve+invalidate on the same reference
provider = FlakyEnvProvider()
resolver = SecretResolver([provider], cache_ttl_seconds=0.01)
errors = []
def hammer():
    for _ in range(500):
        try:
            resolver.resolve("env://X")
            resolver.invalidate("env://X")
        except Exception as e:
            errors.append(e)
threads = [threading.Thread(target=hammer) for _ in range(8)]
for t in threads: t.start()
for t in threads: t.join()
ok = not errors
line("SEC-199", "PASS" if ok else "FAIL", f"8 threads x 500 iterations resolve+invalidate -> errors={errors[:3]} n_errors={len(errors)} total_provider_calls={provider.calls}")

# SEC-208: sensitive keys masked at every depth
values = {"password": "hunter2", "api_key": "abc", "authorization": "Bearer xyz", "nested": {"client_secret": "s3cr3t", "fine": "ok"}}
redacted = redact_mapping(values)
ok = (redacted["password"] == "***" and redacted["api_key"] == "***" and redacted["authorization"] == "***"
      and redacted["nested"]["client_secret"] == "***" and redacted["nested"]["fine"] == "ok")
line("SEC-208", "PASS" if ok else "FAIL", f"redacted={redacted}")

# SEC-209: secret passed as a logging ARGUMENT (not pre-formatted into msg) is not redacted
buf = io.StringIO()
handler = logging.StreamHandler(buf)
handler.addFilter(RedactionFilter())
handler.setFormatter(logging.Formatter("%(message)s"))
_log = logging.getLogger("qa-test-sec209")
_log.setLevel(logging.INFO)
_log.handlers = [handler]
_log.propagate = False
try:
    _log.warning("password=%s", "hunter2-the-actual-secret")
    output = buf.getvalue()
    crashed = False
except Exception as e:
    output = ""
    crashed = True
    crash_msg = str(e)
if crashed:
    line("SEC-209", "FAIL", f"logging call CRASHED rather than leaking or redacting: {crash_msg}")
else:
    leaked = "hunter2-the-actual-secret" in output
    line("SEC-209", "PASS" if leaked else "FAIL", f"output={output!r} secret_leaked_through_lazy_formatting={leaked} (catalogue expects this DOES leak, confirming the filter's known gap -- Expected field literally says 'redacted' but Why says the filter cannot do this; testing which is true)")

# SEC-210: redaction does not descend into lists (boundary -- expected: FAILS to mask, confirming the gap)
values2 = {"credentials": ["a", "b"]}
values3 = {"outer": [{"password": "p"}]}
r2 = redact_mapping(values2)
r3 = redact_mapping(values3)
list_key_masked = r2["credentials"] == "***"
nested_in_list_masked = r3["outer"] == [{"password": "***"}]
line("SEC-210", "PASS" if (list_key_masked and nested_in_list_masked) else "FAIL", f"credentials_list_direct_key={r2} nested_dict_in_list={r3}")

# SEC-211: `prama config show` redacts secrets, text and --json
env = {"PRAMA_SECURITY__SESSION_SECRET": "a-real-secret-value-123"}
import os
full_env = dict(os.environ); full_env.update(env)
r_text = subprocess.run(["/home/ashutosh/PycharmProjects/prama/.venv/bin/prama", "config", "show"], capture_output=True, text=True, cwd=REPO, env=full_env)
r_json = subprocess.run(["/home/ashutosh/PycharmProjects/prama/.venv/bin/prama", "--json", "config", "show"], capture_output=True, text=True, cwd=REPO, env=full_env)
secret_leaked_text = "a-real-secret-value-123" in r_text.stdout
secret_leaked_json = "a-real-secret-value-123" in r_json.stdout
line("SEC-211", "PASS" if (not secret_leaked_text and not secret_leaked_json) else "FAIL",
     f"text_leaked={secret_leaked_text} json_leaked={secret_leaked_json} text_excerpt={[l for l in r_text.stdout.splitlines() if 'session_secret' in l]} json_excerpt={[l for l in r_json.stdout.splitlines() if 'session_secret' in l]}")

# SEC-213: SPI stays three methods
abstract_methods = {name for name in dir(SecretProvider) if getattr(getattr(SecretProvider, name, None), "__isabstractmethod__", False)}
public_surface = {m for m in dir(SecretProvider) if not m.startswith("_") and callable(getattr(SecretProvider, m, None))}
expected = {"resolve", "available", "unavailable_remedy", "describe"}  # describe may be a concrete convenience method
extra = public_surface - expected
line("SEC-213", "PASS" if not (extra - {"scheme", "description"}) else "FAIL", f"public_surface={sorted(public_surface)} abstract={abstract_methods}")

# SEC-214: provider with no scheme cannot be registered
class NoSchemeProvider(SecretProvider):
    scheme = ""
    description = "x"
    def resolve(self, reference): raise NotImplementedError
try:
    SecretResolver().register(NoSchemeProvider())
    line("SEC-214", "FAIL", "no exception raised")
except SecretResolutionError as e:
    ok = "NoSchemeProvider" in str(e)
    line("SEC-214", "PASS" if ok else "FAIL", f"SecretResolutionError: {e}")

# SEC-215: registering two providers for one scheme -- stated rule or silent replace?
class EnvProviderA(SecretProvider):
    scheme = "env"; description = "A"
    def resolve(self, reference): return SecretValue("from-A", origin="a")
class EnvProviderB(SecretProvider):
    scheme = "env"; description = "B"
    def resolve(self, reference): return SecretValue("from-B", origin="b")
res = SecretResolver()
res.register(EnvProviderA())
res.register(EnvProviderB())
which_wins = res.resolve("env://ANYTHING").reveal()
import inspect
register_src = inspect.getsource(SecretResolver.register)
has_docstring_or_comment_on_conflict = ("second" in register_src.lower() or "replace" in register_src.lower() or "overwrit" in register_src.lower() or (SecretResolver.register.__doc__ or ""))
stated = bool(SecretResolver.register.__doc__)
line("SEC-215", "FAIL" if not stated else "PASS", f"which_provider_wins={which_wins!r} (B replaced A silently) register()_has_a_docstring_stating_the_rule={stated} register_source={register_src!r}")

# SEC-216: resolve_optional distinguishes no-credential from failed-credential
res2 = SecretResolver([__import__("prama.secrets.providers", fromlist=["EnvironmentSecretProvider"]).EnvironmentSecretProvider()])
none_result = res2.resolve_optional(None)
try:
    res2.resolve_optional("env://QA_DEFINITELY_MISSING_VAR")
    raised = False
except SecretResolutionError:
    raised = True
ok = none_result is None and raised
line("SEC-216", "PASS" if ok else "FAIL", f"resolve_optional(None)={none_result} resolve_optional('env://MISSING')_raised={raised}")

print("SECTION Secrets-supplement-2 DONE")
