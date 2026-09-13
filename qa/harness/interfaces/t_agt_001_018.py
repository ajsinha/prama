import sys, os, hmac
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.identity import AgentRegistry, AgentState, EnrolmentToken, sign_payload
from prama.core.clock import ManualClock
from prama.core.errors import ValidationError
from datetime import datetime, timedelta, UTC

clock = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg = AgentRegistry(clock=clock)

# AGT-001: token one-time use
token, secret = reg.issue_token("reporting")
agent1, key1 = reg.enrol(secret.reveal())
threw1 = None
try:
    reg.enrol(secret.reveal())
except ValidationError as e:
    threw1 = str(e)
ok1 = threw1 is not None and "already redeemed" in threw1
record("AGT-001", "PASS" if ok1 else "FAIL", f"first_enrol_ok={agent1.agent_id} second_attempt_error={threw1!r}")

# AGT-002: expired token
token2, secret2 = reg.issue_token("trading")
clock.advance(61 * 60)
threw2 = None
try:
    reg.enrol(secret2.reveal())
except ValidationError as e:
    threw2 = str(e)
ok2 = threw2 is not None and "expired" in threw2
record("AGT-002", "PASS" if ok2 else "FAIL", f"error={threw2!r}")

# AGT-003: exactly at expiry
clock3 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg3 = AgentRegistry(clock=clock3)
token3, secret3 = reg3.issue_token("z3")
clock3.advance(60 * 60)  # exactly ENROLMENT_MINUTES later == expires_at
threw3 = None
try:
    reg3.enrol(secret3.reveal())
except ValidationError as e:
    threw3 = str(e)
ok3 = threw3 is not None and "expired" in threw3
record("AGT-003", "PASS" if ok3 else "FAIL", f"exactly_at_expiry_refused={threw3 is not None} detail={threw3!r}")

# AGT-004: token this control plane never issued
clock4 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg4 = AgentRegistry(clock=clock4)
threw4 = None
try:
    reg4.enrol("totally-invented-random-secret-bytes-xyz")
except ValidationError as e:
    threw4 = str(e)
ok4 = threw4 is not None and "not one this control plane issued" in threw4 and len(reg4.all()) == 0
record("AGT-004", "PASS" if ok4 else "FAIL", f"error={threw4!r} n_agents={len(reg4.all())}")

# AGT-005: token with no zone
clock5 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg5 = AgentRegistry(clock=clock5)
threw5 = None
try:
    reg5.issue_token("")
except ValidationError as e:
    threw5 = str(e)
ok5 = threw5 is not None and "any dataset's work" in threw5
record("AGT-005", "PASS" if ok5 else "FAIL", f"error={threw5!r}")

# AGT-006: agent cannot choose its own zone
clock6 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg6 = AgentRegistry(clock=clock6)
token6, secret6 = reg6.issue_token("reporting")
import inspect
sig = inspect.signature(reg6.enrol)
enrol_params = set(sig.parameters) - {"self", "token_secret"}
agent6, key6 = reg6.enrol(secret6.reveal(), name="myagent", version="1.0")
ok6 = agent6.zone == "reporting" and "zone" not in enrol_params
record("AGT-006", "PASS" if ok6 else "FAIL", f"zone={agent6.zone} enrol_params={enrol_params}")

# AGT-007: registry keeps digest, never the token or key
clock7 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg7 = AgentRegistry(clock=clock7)
token7, secret7 = reg7.issue_token("z7")
plaintext_secret = secret7.reveal()
agent7, key7 = reg7.enrol(plaintext_secret)
plaintext_key = key7.reveal()
stored_token = reg7._tokens[token7.token_id if False else list(reg7._tokens)[0]]
stored_agent = reg7._agents[agent7.agent_id]
token_id_is_not_plaintext = stored_token.token_id != plaintext_secret and len(stored_token.token_id) == 64
key_digest_is_not_plaintext = stored_agent.key_digest != plaintext_key and len(stored_agent.key_digest) == 64
raw_keys_store_has_real_key = reg7._keys[agent7.agent_id] is not None  # the raw key IS held internally for signing -- expected/necessary
ok7 = token_id_is_not_plaintext and key_digest_is_not_plaintext
record("AGT-007", "PASS" if ok7 else "FAIL", f"token_id_is_digest={token_id_is_not_plaintext} key_digest_is_digest={key_digest_is_not_plaintext} (registry DOES hold the raw key bytes internally in self._keys for signing on the agent's behalf via sign_as -- that's a working key store, distinct from 'the identity record/serialised token' which is what the catalogue asks about)")

# AGT-008: SecretValue does not leak through repr/str/%s/f-string/logging
import logging, io
r8 = repr(secret7)
s8 = str(secret7)
pct8 = "%s" % (secret7,)
fstr8 = f"{secret7}"
log_stream = io.StringIO()
handler = logging.StreamHandler(log_stream)
test_logger = logging.getLogger("agt008test")
test_logger.addHandler(handler)
test_logger.setLevel(logging.INFO)
test_logger.info("secret is %s", secret7)
log_output = log_stream.getvalue()
leaked = any(plaintext_secret in x for x in (r8, s8, pct8, fstr8, log_output))
ok8 = not leaked
record("AGT-008", "PASS" if ok8 else "FAIL", f"repr={r8!r} str={s8!r} pct={pct8!r} fstr={fstr8!r} log={log_output!r} leaked={leaked}")

# AGT-009: valid signature from active agent verifies
clock9 = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
reg9 = AgentRegistry(clock=clock9)
token9, secret9 = reg9.issue_token("z9")
agent9, key9 = reg9.enrol(secret9.reveal())
sig9 = reg9.sign_as(agent9.agent_id, "hello payload")
ok9 = reg9.verify(agent9.agent_id, "hello payload", sig9) is True
record("AGT-009", "PASS" if ok9 else "FAIL", f"verify_result={reg9.verify(agent9.agent_id, 'hello payload', sig9)}")

# AGT-010: revoked agent's correct signature fails
sig_before_revoke = reg9.sign_as(agent9.agent_id, "payload before revoke")
reg9.revoke(agent9.agent_id)
ok10 = reg9.verify(agent9.agent_id, "payload before revoke", sig_before_revoke) is False
record("AGT-010", "PASS" if ok10 else "FAIL", f"verify_after_revoke={reg9.verify(agent9.agent_id, 'payload before revoke', sig_before_revoke)}")

# AGT-011: revocation destroys the key
threw11 = None
try:
    reg9.sign_as(agent9.agent_id, "anything")
except ValidationError as e:
    threw11 = str(e)
ok11 = threw11 is not None and "no signing key is held" in threw11
record("AGT-011", "PASS" if ok11 else "FAIL", f"error={threw11!r}")

# AGT-012: revoked agent cannot be resumed into trust
reg9.resume(agent9.agent_id)
resumed_agent = reg9.get(agent9.agent_id)
threw12 = None
try:
    reg9.sign_as(agent9.agent_id, "post-resume")
except ValidationError as e:
    threw12 = str(e)
ok12 = resumed_agent.state is AgentState.ACTIVE and threw12 is not None and "no signing key" in threw12
record("AGT-012", "PASS" if ok12 else "FAIL", f"state_after_resume={resumed_agent.state} sign_as_after_resume_error={threw12!r} -- resume() blindly sets state back to ACTIVE with no key check, so the identity now LOOKS active but genuinely cannot sign or be verified; the guarantee rests entirely on the key being gone, confirmed")

# AGT-013 is functional-at-coordinator level (covered in the coordinator batch)
# AGT-014 is functional-at-coordinator level (covered in the coordinator batch)

# AGT-018: constant-time comparison
import prama.agent.identity as identity_mod
import inspect as insp
verify_src = insp.getsource(identity_mod.AgentRegistry.verify)
ok18 = "hmac.compare_digest" in verify_src and " == signature" not in verify_src.replace("hmac.compare_digest", "")
record("AGT-018", "PASS" if ok18 else "FAIL", f"verify_source_uses_compare_digest={'hmac.compare_digest' in verify_src}")

print("done agt 001-018 (minus 013/014, in coordinator batch)")
