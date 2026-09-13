"""SEM-098..SEM-109: ApprovalPolicy / ApprovalRequirement cases."""
import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.core.errors import ValidationError
from prama.semantic.policy import ApprovalPolicy, ApprovalRequirement


def show(label, fn):
    try:
        result = fn()
        print(f"{label}: OK returned={result!r}")
    except ValidationError as e:
        print(f"{label}: ValidationError msg={e!r} context={getattr(e, 'context', None)} remedy={getattr(e, 'remedy', None)!r}")
    except Exception as e:
        print(f"{label}: {type(e).__name__}: {e!r}")


policy = ApprovalPolicy()

# SEM-098: tier 4, no approver
show("SEM-098", lambda: policy.check(criticality=4, authored_by="alice", approved_by=None))

# SEM-099: for_criticality(3) == NONE; accepted with no approver
print("SEM-099 for_criticality(3) =", policy.for_criticality(3))
show("SEM-099 check", lambda: policy.check(criticality=3, authored_by="alice", approved_by=None))

# SEM-100: tier 2, approved_by=None
show("SEM-100", lambda: policy.check(criticality=2, authored_by="alice", approved_by=None))

# SEM-101: tier 2, authored_by==approved_by=="alice"
show("SEM-101", lambda: policy.check(criticality=2, authored_by="alice", approved_by="alice"))

# SEM-102: tier 1, authored_by==approved_by=="alice"
show("SEM-102", lambda: policy.check(criticality=1, authored_by="alice", approved_by="alice"))

# SEM-103: tier 1, authored_by="alice", approved_by="bob"
show("SEM-103", lambda: policy.check(criticality=1, authored_by="alice", approved_by="bob"))

# SEM-104: tier 1, authored_by=None, approved_by="alice"
show("SEM-104", lambda: policy.check(criticality=1, authored_by=None, approved_by="alice"))

# SEM-105: tier 1, both None
show("SEM-105", lambda: policy.check(criticality=1, authored_by=None, approved_by=None))
# also test empty-string approver
show("SEM-105b (approved_by='')", lambda: policy.check(criticality=1, authored_by=None, approved_by=""))

# SEM-106: for_criticality(0), (5), (-1)
print("SEM-106 for_criticality(0) =", policy.for_criticality(0))
print("SEM-106 for_criticality(5) =", policy.for_criticality(5))
print("SEM-106 for_criticality(-1) =", policy.for_criticality(-1))
# also confirm that check() with criticality=0 and no approver does NOT raise (fails open)
show("SEM-106 check(0, alice, None)", lambda: policy.check(criticality=0, authored_by="alice", approved_by=None))
show("SEM-106 check(0, alice, alice)", lambda: policy.check(criticality=0, authored_by="alice", approved_by="alice"))

# SEM-107: non-default policy tier_three = MAKER_CHECKER, self-approved tier 3
custom_policy = ApprovalPolicy(tier_three=ApprovalRequirement.MAKER_CHECKER)
show("SEM-107", lambda: custom_policy.check(criticality=3, authored_by="alice", approved_by="alice"))

# SEM-108: trigger tier 1 refusal, inspect context
try:
    policy.check(criticality=1, authored_by="alice", approved_by="alice")
    print("SEM-108: no exception (unexpected)")
except ValidationError as e:
    print("SEM-108 context:", e.context)
    print("SEM-108 message:", str(e))

# SEM-109: 'what' appears in message, for three different values
for what in ("journey declaration", "dataset amendment", "relationship declaration"):
    try:
        policy.check(criticality=1, authored_by="alice", approved_by=None, what=what)
        print(f"SEM-109[{what}]: no exception (unexpected)")
    except ValidationError as e:
        print(f"SEM-109[{what}]: message={str(e)!r} contains_what={what in str(e)}")
