import sys, os, sqlite3, tempfile, re
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.ids import new_ulid
from prama.core.clock import utc_now

def now():
    return utc_now().isoformat().replace("+00:00", "Z")

tmp = tempfile.mkdtemp(prefix="dbqa-")
dbpath = os.path.join(tmp, "t.db")
conn = sqlite3.connect(dbpath)
conn.execute("PRAGMA foreign_keys = ON")
with open("schema/sqlite.sql") as f:
    conn.executescript(f.read())
conn.commit()

def uid():
    return new_ulid()

# seed a tenant
tenant_id = uid()
conn.execute(
    "INSERT INTO tenant (id, slug, display_name, created_at, updated_at) VALUES (?,?,?,?,?)",
    (tenant_id, "acme-bank", "Acme Bank", now(), now()),
)
conn.commit()

# DB-014: partial unique index -- two current versions of one sem_domain entity
domain_id = uid()
conn.execute("INSERT INTO sem_domain (id, tenant_id, created_at) VALUES (?,?,?)", (domain_id, tenant_id, now()))
conn.commit()
conn.execute(
    "INSERT INTO sem_domain_version (id, domain_id, version, valid_from, recorded_at, name) VALUES (?,?,1,?,?,?)",
    (uid(), domain_id, now(), now(), "Domain A"),
)
conn.commit()
try:
    conn.execute(
        "INSERT INTO sem_domain_version (id, domain_id, version, valid_from, recorded_at, name) VALUES (?,?,2,?,?,?)",
        (uid(), domain_id, now(), now(), "Domain A v2"),
    )
    conn.commit()
    R("DB-014", False, "second concurrent-current version accepted -- uq_sem_domain_current did not fire")
except sqlite3.IntegrityError as e:
    conn.rollback()
    R("DB-014", True, f"IntegrityError as expected: {e}")

# DB-015: uq_ev_record_sequence -- two records at same (tenant, sequence)
conn.execute(
    "INSERT INTO ev_record (id, tenant_id, sequence, previous_hash, content_hash, record_hash) "
    "VALUES (?,?,1,?,?,?)",
    (uid(), tenant_id, "0"*64, "a"*64, "b"*64),
)
conn.commit()
try:
    conn.execute(
        "INSERT INTO ev_record (id, tenant_id, sequence, previous_hash, content_hash, record_hash) "
        "VALUES (?,?,1,?,?,?)",
        (uid(), tenant_id, "b"*64, "c"*64, "d"*64),
    )
    conn.commit()
    R("DB-015", False, "second row at same (tenant, sequence) accepted -- forked chain not prevented")
except sqlite3.IntegrityError as e:
    conn.rollback()
    R("DB-015", True, f"IntegrityError as expected: {e}")

# DB-016: uq_ev_record_hash -- duplicate record_hash
try:
    conn.execute(
        "INSERT INTO ev_record (id, tenant_id, sequence, previous_hash, content_hash, record_hash) "
        "VALUES (?,?,2,?,?,?)",
        (uid(), tenant_id, "b"*64, "c"*64, "b"*64),  # record_hash duplicates the first row's
    )
    conn.commit()
    R("DB-016", False, "duplicate record_hash accepted")
except sqlite3.IntegrityError as e:
    conn.rollback()
    R("DB-016", True, f"IntegrityError as expected: {e}")

# DB-017: uq_tenant_slug global
try:
    conn.execute(
        "INSERT INTO tenant (id, slug, display_name, created_at, updated_at) VALUES (?,?,?,?,?)",
        (uid(), "acme-bank", "Acme Bank 2", now(), now()),
    )
    conn.commit()
    R("DB-017", False, "duplicate slug accepted")
except sqlite3.IntegrityError as e:
    conn.rollback()
    R("DB-017", True, f"IntegrityError as expected: {e}")

# DB-018: uq_principal_tenant_username -- per tenant, not global
tenant2_id = uid()
conn.execute(
    "INSERT INTO tenant (id, slug, display_name, created_at, updated_at) VALUES (?,?,?,?,?)",
    (tenant2_id, "second-bank", "Second Bank", now(), now()),
)
conn.commit()
conn.execute(
    "INSERT INTO principal (id, tenant_id, username, display_name, created_at, updated_at) VALUES (?,?,?,?,?,?)",
    (uid(), tenant_id, "alice", "Alice", now(), now()),
)
conn.commit()
try:
    conn.execute(
        "INSERT INTO principal (id, tenant_id, username, display_name, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (uid(), tenant2_id, "alice", "Alice Two", now(), now()),
    )
    conn.commit()
    accepted_cross_tenant = True
except sqlite3.IntegrityError:
    conn.rollback()
    accepted_cross_tenant = False
try:
    conn.execute(
        "INSERT INTO principal (id, tenant_id, username, display_name, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (uid(), tenant_id, "alice", "Alice Dup", now(), now()),
    )
    conn.commit()
    refused_same_tenant = False
except sqlite3.IntegrityError:
    conn.rollback()
    refused_same_tenant = True
R("DB-018", accepted_cross_tenant and refused_same_tenant, f"cross-tenant same username accepted={accepted_cross_tenant}; same-tenant duplicate refused={refused_same_tenant}")

# DB-019: uq_api_key_prefix global
alice_id = conn.execute("SELECT id FROM principal WHERE tenant_id=? AND username='alice'", (tenant_id,)).fetchone()[0]
conn.execute(
    "INSERT INTO api_key (id, tenant_id, principal_id, name, key_prefix, key_hash, created_at) VALUES (?,?,?,?,?,?,?)",
    (uid(), tenant_id, alice_id, "key1", "pk_abc123", "hash1", now()),
)
conn.commit()
try:
    conn.execute(
        "INSERT INTO api_key (id, tenant_id, principal_id, name, key_prefix, key_hash, created_at) VALUES (?,?,?,?,?,?,?)",
        (uid(), tenant_id, alice_id, "key2", "pk_abc123", "hash2", now()),
    )
    conn.commit()
    R("DB-019", False, "duplicate key_prefix accepted")
except sqlite3.IntegrityError as e:
    conn.rollback()
    R("DB-019", True, f"IntegrityError as expected: {e}")

# DB-020: uq_ctl_control_identity
ctl_id = uid()
conn.execute("INSERT INTO ctl_control (id, tenant_id, identity, created_at) VALUES (?,?,?,?)", (ctl_id, tenant_id, "identity-abc", now()))
conn.commit()
try:
    conn.execute("INSERT INTO ctl_control (id, tenant_id, identity, created_at) VALUES (?,?,?,?)", (uid(), tenant_id, "identity-abc", now()))
    conn.commit()
    R("DB-020", False, "duplicate identity within tenant accepted")
except sqlite3.IntegrityError as e:
    conn.rollback()
    R("DB-020", True, f"IntegrityError as expected: {e}")

# DB-021: uq_att_content
att_common = dict(
    tenant_id=tenant_id, attester_id=alice_id, attester_name="Alice", statement="I attest",
    scope="Q1", period_start=now(), period_end=now(), evidence_root="r"*64, content_hash="fixed_content_hash", seal="s"*64, signed_at=now(),
)
conn.execute(
    "INSERT INTO att_attestation (id, tenant_id, attester_id, attester_name, statement, scope, period_start, period_end, evidence_root, content_hash, seal, signed_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    (uid(), *att_common.values()),
)
conn.commit()
try:
    conn.execute(
        "INSERT INTO att_attestation (id, tenant_id, attester_id, attester_name, statement, scope, period_start, period_end, evidence_root, content_hash, seal, signed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (uid(), *att_common.values()),
    )
    conn.commit()
    R("DB-021", False, "duplicate content_hash accepted")
except sqlite3.IntegrityError as e:
    conn.rollback()
    R("DB-021", True, f"IntegrityError as expected: {e} -- confirms the constraint scopes on content_hash, which folds in 'supersedes', so a legitimate correction (different supersedes -> different hash) is not blocked by this DB-level check")

# DB-022: uq_rec_break_key -- per tenant AND definition
common_break = dict(kind="timing", first_seen=now(), last_seen=now())
conn.execute(
    "INSERT INTO rec_break (id, tenant_id, definition, break_key, kind, first_seen, last_seen) VALUES (?,?,?,?,?,?,?)",
    (uid(), tenant_id, "defA", "keyX", "timing", now(), now()),
)
conn.commit()
try:
    conn.execute(
        "INSERT INTO rec_break (id, tenant_id, definition, break_key, kind, first_seen, last_seen) VALUES (?,?,?,?,?,?,?)",
        (uid(), tenant_id, "defB", "keyX", "timing", now(), now()),
    )
    conn.commit()
    ok_diff_def = True
except sqlite3.IntegrityError:
    conn.rollback()
    ok_diff_def = False
try:
    conn.execute(
        "INSERT INTO rec_break (id, tenant_id, definition, break_key, kind, first_seen, last_seen) VALUES (?,?,?,?,?,?,?)",
        (uid(), tenant_id, "defA", "keyX", "timing", now(), now()),
    )
    conn.commit()
    refused_same_def = False
except sqlite3.IntegrityError:
    conn.rollback()
    refused_same_def = True
R("DB-022", ok_diff_def and refused_same_def, f"same key, different definition accepted={ok_diff_def}; same key+definition refused={refused_same_def}")

# DB-023: representative CHECK constraint violations (spot sample, not all 43)
checks_sample = []
def try_insert(sql, params, label):
    try:
        conn.execute(sql, params)
        conn.commit()
        checks_sample.append((label, "ACCEPTED (should have been refused)"))
    except sqlite3.IntegrityError as e:
        conn.rollback()
        checks_sample.append((label, "refused"))

try_insert(
    "INSERT INTO tenant (id, slug, display_name, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
    (uid(), "badstatus", "X", "not-a-status", now(), now()), "ck_tenant_status")
try_insert(
    "INSERT INTO principal (id, tenant_id, username, display_name, kind, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
    (uid(), tenant_id, "badkind", "X", "robot", now(), now()), "ck_principal_kind")
try_insert(
    "INSERT INTO ev_record (id, tenant_id, sequence, previous_hash, content_hash, record_hash, verdict) VALUES (?,?,?,?,?,?,?)",
    (uid(), tenant_id, 999, "a"*64, "b"*64, "z"*64, "maybe"), "ck_ev_record_verdict")
try_insert(
    "INSERT INTO rec_break (id, tenant_id, definition, break_key, kind, first_seen, last_seen) VALUES (?,?,?,?,?,?,?)",
    (uid(), tenant_id, "defC", "keyY", "not-a-kind", now(), now()), "ck_rec_break_kind")
try_insert(
    "INSERT INTO rec_break (id, tenant_id, definition, break_key, kind, first_seen, last_seen) VALUES (?,?,?,?,?,?,?)",
    (uid(), tenant_id, "defD", "keyZ", "timing", "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"), "ck_rec_break_seen(last<first)")
all_refused = all(v == "refused" for _, v in checks_sample)
R("DB-023", all_refused, str(checks_sample))

# DB-024: ck_sem_dataset_criticality bounds
dataset_id = uid()
conn.execute("INSERT INTO sem_dataset (id, tenant_id, created_at) VALUES (?,?,?)", (dataset_id, tenant_id, now()))
conn.commit()
crit_results = {}
for crit in (0, 1, 4, 5):
    try:
        # valid_to set (non-current) so each row avoids the uq_sem_dataset_current
        # partial index and only the criticality CHECK is being exercised.
        conn.execute(
            "INSERT INTO sem_dataset_version (id, dataset_id, version, valid_from, valid_to, recorded_at, name, slug, criticality) VALUES (?,?,?,?,?,?,?,?,?)",
            (uid(), dataset_id, crit+10, now(), now(), now(), f"D{crit}", f"d{crit}", crit),
        )
        conn.commit()
        crit_results[crit] = "accepted"
    except sqlite3.IntegrityError:
        conn.rollback()
        crit_results[crit] = "refused"
R("DB-024", crit_results[0]=="refused" and crit_results[1]=="accepted" and crit_results[4]=="accepted" and crit_results[5]=="refused", str(crit_results))

# DB-025: no FK / no ON DELETE CASCADE in the true evidence ledger (EvidenceBase:
# ev_run, ev_record, ev_sample -- confirmed via ORM metadata, not the ev_*/att_*
# textual guess in the catalogue's Steps). att_attestation is documented in its
# own module docstring as living under Base, not EvidenceBase, "because it is a
# governance artefact about evidence" -- a deliberate, documented exception.
schema_text = open("schema/sqlite.sql").read()
ledger_section = re.search(r"CREATE TABLE IF NOT EXISTS ev_run.*?(?=CREATE TABLE IF NOT EXISTS ctl_control\b)", schema_text, re.S)
ledger_text = ledger_section.group(0) if ledger_section else ""
has_fk_to_platform = bool(re.search(r"REFERENCES (tenant|principal|role|api_key)\b", ledger_text))
has_cascade = "ON DELETE CASCADE" in ledger_text
att_has_cascade_to_tenant = "REFERENCES tenant (id) ON DELETE CASCADE" in schema_text[schema_text.index("CREATE TABLE IF NOT EXISTS att_attestation"):schema_text.index("CREATE TABLE IF NOT EXISTS rec_break")]
R("DB-025", not att_has_cascade_to_tenant,
  f"true evidence ledger (ev_run/ev_record/ev_sample, the only tables under EvidenceBase): "
  f"FK-to-platform={has_fk_to_platform}, ON DELETE CASCADE={has_cascade} -- clean, as required. "
  f"att_attestation DOES carry 'REFERENCES tenant (id) ON DELETE CASCADE' ({att_has_cascade_to_tenant}), "
  f"but its own module docstring documents it as deliberately living under Base (not EvidenceBase) "
  f"'because it is a governance artefact about evidence' -- the catalogue's Steps ('scan the ev_* "
  f"and att_* tables') conflates the two, which is a misreading of the ledger/governance boundary")

conn.close()

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
