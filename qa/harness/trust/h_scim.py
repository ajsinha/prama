import sys, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.scim import ScimUser, Account, Change, Decision, reconcile, reconcile_all
from prama.security.oidc import ClaimMapping

mapping = ClaimMapping(roles={"owners": "owner", "stewards": "steward"})

# SEC-098: new directory user -> CREATE
u = ScimUser(external_id="ext-1", user_name="alice", active=True, groups=("owners",))
d = reconcile(u, None, mapping=mapping)
ok = d.change is Change.CREATE and d.roles == ("owner",) and d.reason
line("SEC-098", "PASS" if ok else "FAIL", f"change={d.change} roles={d.roles} reason={d.reason!r}")

# SEC-099: leaver never held -> NONE
u2 = ScimUser(external_id="ext-2", user_name="bob", active=False)
d2 = reconcile(u2, None, mapping=mapping)
ok = d2.change is Change.NONE and d2.reason
line("SEC-099", "PASS" if ok else "FAIL", f"change={d2.change} reason={d2.reason!r}")

# SEC-100: delete deactivates, never deletes
acct = Account(external_id="ext-3", user_name="carol", active=True, roles=("steward",))
u3 = ScimUser(external_id="ext-3", user_name="carol", active=False)
d3 = reconcile(u3, acct, mapping=mapping)
ok = d3.change is Change.DEACTIVATE and "attestation" in d3.reason
line("SEC-100", "PASS" if ok else "FAIL", f"change={d3.change} reason={d3.reason!r}")

# SEC-101: last active admin cannot be deprovisioned
acct_admin = Account(external_id="ext-4", user_name="dave", active=True, roles=("admin",))
u4 = ScimUser(external_id="ext-4", user_name="dave", active=False)
d4 = reconcile(u4, acct_admin, mapping=mapping, other_active_admins=0, admin_role="admin")
ok = d4.change is Change.REFUSED and "lock" in d4.reason.lower()
line("SEC-101", "PASS" if ok else "FAIL", f"change={d4.change} reason={d4.reason!r}")

# SEC-102: batch deactivating 3 of 4 admins refuses on the 4th (recomputed pool, not first-reached)
accounts = {f"admin-{i}": Account(external_id=f"admin-{i}", user_name=f"admin{i}", active=True, roles=("admin",)) for i in range(4)}
users = [ScimUser(external_id=f"admin-{i}", user_name=f"admin{i}", active=False) for i in range(4)]
decisions = reconcile_all(users, accounts, mapping=mapping, admin_role="admin")
n_deactivate = sum(1 for d in decisions if d.change is Change.DEACTIVATE)
n_refused = sum(1 for d in decisions if d.change is Change.REFUSED)
refused_is_last = decisions[3].change is Change.REFUSED
ok = n_deactivate == 3 and n_refused == 1 and refused_is_last
line("SEC-102", "PASS" if ok else "FAIL", f"decisions={[(d.external_id, d.change) for d in decisions]} n_deactivate={n_deactivate} n_refused={n_refused}")

# SEC-103: roles replaced, never unioned
acct5 = Account(external_id="ext-5", user_name="erin", active=True, roles=("owner", "steward"))
u5 = ScimUser(external_id="ext-5", user_name="erin", active=True, groups=("stewards",))
d5 = reconcile(u5, acct5, mapping=mapping)
ok = d5.change is Change.UPDATE and d5.roles == ("steward",) and any(f[0] == "roles" for f in d5.fields)
line("SEC-103", "PASS" if ok else "FAIL", f"change={d5.change} roles={d5.roles} fields={d5.fields}")

# SEC-104: omitted field in partial update does not blank stored one -- email empty from a PATCH means "unchanged"
acct6 = Account(external_id="ext-6", user_name="frank", active=True, email="frank@bank.com", roles=())
u6 = ScimUser(external_id="ext-6", user_name="frank", active=True, email="")  # PATCH omitting emails -> parsed as empty
d6 = reconcile(u6, acct6, mapping=mapping)
email_field_changed = any(f[0] == "email" for f in d6.fields)
line("SEC-104", "PASS" if not email_field_changed else "FAIL", f"fields={d6.fields} (expected: no 'email' field change)")

# SEC-105: no external id refused
u7 = ScimUser(external_id="", user_name="ghost")
d7 = reconcile(u7, None, mapping=mapping)
ok = d7.change is Change.REFUSED and "duplicate" in d7.reason
line("SEC-105", "PASS" if ok else "FAIL", f"change={d7.change} reason={d7.reason!r}")

# SEC-106: reactivation distinguished from creation
acct8 = Account(external_id="ext-8", user_name="hank", active=False, roles=())
u8 = ScimUser(external_id="ext-8", user_name="hank", active=True, groups=("owners",))
d8 = reconcile(u8, acct8, mapping=mapping)
ok = d8.change is Change.REACTIVATE and d8.roles == ("owner",)
line("SEC-106", "PASS" if ok else "FAIL", f"change={d8.change} roles={d8.roles}")

# SEC-107: agreement reported as agreement, applies False
acct9 = Account(external_id="ext-9", user_name="iris", active=True, email="iris@bank.com", display_name="Iris", roles=("owner",))
u9 = ScimUser(external_id="ext-9", user_name="iris", active=True, email="iris@bank.com", display_name="Iris", groups=("owners",))
d9 = reconcile(u9, acct9, mapping=mapping)
ok = d9.change is Change.NONE and not d9.applies
line("SEC-107", "PASS" if ok else "FAIL", f"change={d9.change} applies={d9.applies}")

# SEC-108: REFUSED distinct from NONE, neither applies
ok = (not d7.applies) and (not d9.applies) and d7.change != d9.change
line("SEC-108", "PASS" if ok else "FAIL", f"REFUSED.applies={d7.applies} NONE.applies={d9.applies} distinct={d7.change != d9.change}")

# SEC-109: SCIM resource parsed in every shape allowed
r1 = ScimUser.from_resource({"externalId": "x1", "userName": "u1", "groups": [{"display": "Owners"}]})
r2 = ScimUser.from_resource({"externalId": "x2", "userName": "u2", "groups": [{"value": "owners-id"}]})
r3 = ScimUser.from_resource({"externalId": "x3", "userName": "u3", "groups": ["owners"]})
r4 = ScimUser.from_resource({"externalId": "x4", "userName": "u4", "emails": [{"value": "a@x.com", "primary": False}, {"value": "b@x.com", "primary": True}]})
r5 = ScimUser.from_resource({"externalId": "x5", "userName": "u5", "name": {"formatted": "Full Name"}})
r6 = ScimUser.from_resource({"externalId": "x6", "userName": "u6", "displayName": "Display Only"})
ok = (r1.groups == ("Owners",) and r2.groups == ("owners-id",) and r3.groups == ("owners",)
      and r4.email == "b@x.com" and r5.display_name == "Full Name" and r6.display_name == "Display Only")
line("SEC-109", "PASS" if ok else "FAIL", f"groups_display={r1.groups} groups_value={r2.groups} groups_string={r3.groups} primary_email={r4.email} formatted_name={r5.display_name} displayName={r6.display_name}")

# SEC-110: active defaults true when absent, documented warning present
r7 = ScimUser.from_resource({"externalId": "x7", "userName": "u7"})
docstring = ScimUser.from_resource.__doc__ or ""
ok = r7.active is True and "PATCH" in docstring and "not a request to activate" in docstring
line("SEC-110", "PASS" if ok else "FAIL", f"active={r7.active} docstring_has_warning={'not a request to activate' in docstring}")

# SEC-111: decision names fields it would change, old to new
acct11 = Account(external_id="ext-11", user_name="jill", active=True, email="old@bank.com", display_name="Old Name", roles=("owner",))
u11 = ScimUser(external_id="ext-11", user_name="jill", active=True, email="new@bank.com", display_name="New Name", groups=("stewards",))
d11 = reconcile(u11, acct11, mapping=mapping)
desc = d11.describe()
ok = "old@bank.com" in desc and "new@bank.com" in desc and "Old Name" in desc and "New Name" in desc
line("SEC-111", "PASS" if ok else "FAIL", f"describe={desc!r}")

# SEC-112: no SCIM HTTP routes exist, and the module/docs say so
r = subprocess.run(["grep", "-rln", "scim", "/home/ashutosh/PycharmProjects/prama/src/prama/api", "/home/ashutosh/PycharmProjects/prama/src/prama/web"], capture_output=True, text=True)
no_routes = not r.stdout.strip()
module_says_so = "not written" in open("/home/ashutosh/PycharmProjects/prama/src/prama/security/scim.py").read()
r2 = subprocess.run(["grep", "-rn", "-i", "scim.*not written\\|routes.*scim.*not\\|SCIM would close", "/home/ashutosh/PycharmProjects/prama/docs"], capture_output=True, text=True)
docs_say_so = bool(r2.stdout.strip())
ok = no_routes and module_says_so and docs_say_so
line("SEC-112", "PASS" if ok else "FAIL", f"no_http_routes_found={no_routes} module_docstring_says_not_written={module_says_so} docs_confirm={docs_say_so} docs_hits={r2.stdout.strip().splitlines()[:3]}")

print("SECTION SEC-098..112 DONE")
