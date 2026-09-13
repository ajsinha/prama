import sys, subprocess, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.scopes import SCOPES, WILDCARD, permits, unknown
from prama.cli.principal import BUILTIN_ROLES

# SEC-001 & SEC-002: run the real architecture test file
r = subprocess.run([sys.executable, "-m", "pytest", "tests/architecture/test_scopes.py", "-v"],
                    capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout
def test_result(nodeid):
    for l in out.splitlines():
        if nodeid in l:
            return l.strip()
    return "(not found)"
sec001 = test_result("test_every_granted_permission_is_a_declared_scope")
sec002 = test_result("test_every_scope_a_route_requires_can_be_held")
line("SEC-001", "PASS" if "PASSED" in sec001 else "FAIL", f"pytest tests/architecture/test_scopes.py::TestThereIsOneVocabulary::test_every_granted_permission_is_a_declared_scope -> {sec001}")
line("SEC-002", "PASS" if "PASSED" in sec002 else "FAIL", f"pytest ...::test_every_scope_a_route_requires_can_be_held -> {sec002}")

# SEC-003: every scope has a non-empty sentence, not a restatement of the key
bad = [k for k, v in SCOPES.items() if not v or v.strip() == k or len(v) < 5]
ok = len(SCOPES) == 16 and not bad
line("SEC-003", "PASS" if ok else "FAIL", f"n_scopes={len(SCOPES)} bad={bad}")

# SEC-004: exact grant permits exactly its own scope
a = permits(["control:approve"], "control:approve")
b = permits(["control:approve"], "control:propose")
line("SEC-004", "PASS" if (a and not b) else "FAIL", f"exact_match={a} different_scope={b}")

# SEC-005: wildcard matches one level and no more
c1 = permits(["control:*"], "control:approve")
c2 = permits(["control:*"], "incident:read")
c3 = permits(["con:*"], "control:approve")
ok = c1 is True and c2 is False and c3 is False
line("SEC-005", "PASS" if ok else "FAIL", f"control:*->control:approve={c1} control:*->incident:read={c2} con:*->control:approve={c3}")

# SEC-006: bare wildcard permits everything
results = {s: permits(["*"], s) for s in SCOPES}
ok = all(results.values())
line("SEC-006", "PASS" if ok else "FAIL", f"all_true={ok} failures={[k for k,v in results.items() if not v]}")

# SEC-007: empty grant permits nothing
results2 = {s: permits([], s) for s in SCOPES}
ok = not any(results2.values())
line("SEC-007", "PASS" if ok else "FAIL", f"all_false={ok} unexpected_true={[k for k,v in results2.items() if v]}")

# SEC-008: unknown scope never satisfied, caught by unknown()
u = unknown(["semantic:read", "control:read"])
ok = u == ["semantic:read"]
line("SEC-008", "PASS" if ok else "FAIL", f"unknown(['semantic:read','control:read'])={u}")

# SEC-009: unknown() ignores wildcards, including bogus family wildcards
u2 = unknown(["*", "control:*", "nonsense:*"])
ok = u2 == []
line("SEC-009", "PASS" if ok else "FAIL", f"unknown(['*','control:*','nonsense:*'])={u2} -- nonsense:* silently accepted, confirming the catalogue's concern that unknown() does not catch a typo in a wildcard prefix")

# SEC-010: case-sensitive, no trim
d1 = permits(["Control:Approve"], "control:approve")
d2 = permits([" control:approve"], "control:approve")
ok = d1 is False and d2 is False
line("SEC-010", "PASS" if ok else "FAIL", f"case_mismatch_permits={d1} leading_space_permits={d2}")

# SEC-011: one matcher serves both callers -- grep for a second wildcard-matching implementation
r2 = subprocess.run(["grep", "-rn", "-E", "endswith\\(.:\\*.\\)|startswith\\(grant", "/home/ashutosh/PycharmProjects/prama/src"],
                     capture_output=True, text=True)
hits = [l for l in r2.stdout.splitlines() if "security/scopes.py" not in l]
line("SEC-011", "PASS" if not hits else "FAIL", f"grep for a second wildcard matcher outside security/scopes.py -> {hits}")

print("SECTION SEC-001..011 DONE")
