import sys
from datetime import datetime, timedelta
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.alert.route import (
    Role, Fault, Delivery, Recipient, Alert, Change, Dispatch, Digest, Router,
    DEFAULT_QUIET, DIGEST_CEILING,
)
from prama.security.egress import Gate, Policy

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

base = datetime(2024,1,1,6,0)

# INC-042
contacts = {("ds", Role.CUSTODIAN): "cust1", ("ds", Role.STEWARD): "stew1"}
router = Router(contacts)
a_arrival = Alert(identity="a1", dataset="ds", fault=Fault.ARRIVAL, what="did not arrive", severity=0.1, at=base)
a_def = Alert(identity="a2", dataset="ds", fault=Fault.DEFINITION, what="wrong def", severity=0.9, at=base)
d1 = router.dispatch(a_arrival)
d2 = router.dispatch(a_def)
ok = d1.recipients[0].role == Role.CUSTODIAN and d2.recipients[0].role == Role.STEWARD
line("INC-042", "PASS" if ok else "FAIL", f"arrival_role={d1.recipients[0].role if d1.recipients else None} def_role={d2.recipients[0].role if d2.recipients else None}")

# INC-043
expected_routes = {
    Fault.ARRIVAL: Role.CUSTODIAN, Fault.SCHEMA: Role.CUSTODIAN, Fault.VALUE: Role.STEWARD,
    Fault.DEFINITION: Role.STEWARD, Fault.RECONCILIATION: Role.STEWARD, Fault.CALIBRATION: Role.CUSTODIAN,
}
actual_routes = {f: f.route_to for f in Fault}
ok = actual_routes == expected_routes
line("INC-043", "PASS" if ok else "FAIL", f"routes={ {k.value: v.value for k,v in actual_routes.items()} }")

# INC-044
ok = Fault.CALIBRATION.route_to == Role.CUSTODIAN
line("INC-044", "PASS" if ok else "FAIL", f"calibration_route={Fault.CALIBRATION.route_to}")

# INC-045
router45 = Router({})
a45 = Alert(identity="a", dataset="unknown_ds", fault=Fault.ARRIVAL, what="x", at=base)
d45 = router45.dispatch(a45)
ok = d45.delivery == Delivery.QUIET and "custodian" in d45.reason and "Assign one" in d45.reason
line("INC-045", "PASS" if ok else "FAIL", f"delivery={d45.delivery} reason={d45.reason!r}")

# INC-046
router46 = Router({("ds46", Role.OWNER): "owner1"})
a46 = Alert(identity="a", dataset="ds46", fault=Fault.ARRIVAL, what="x", at=base)
d46 = router46.dispatch(a46)
ok = len(d46.recipients) == 1 and d46.recipients[0].identity == "owner1" and d46.recipients[0].role == Role.OWNER
line("INC-046", "PASS" if ok else "FAIL", f"recipients={[(r.identity, r.role) for r in d46.recipients]}")

# INC-047
router47 = Router({("ds47", Role.CUSTODIAN): "cust"})
results47 = []
for h in [0,1,2]:
    a = Alert(identity="a", dataset="ds47", fault=Fault.ARRIVAL, what="x", severity=0.6, at=base+timedelta(hours=h))
    d = router47.dispatch(a)
    results47.append((d.change, d.sent))
ok = results47[0] == (Change.OPENED, True) and results47[1][0] == Change.UNCHANGED and not results47[1][1] and results47[2][0] == Change.UNCHANGED and not results47[2][1]
line("INC-047", "PASS" if ok else "FAIL", f"results={results47}")

# INC-048
a48a = Alert(identity="a", dataset="ds", fault=Fault.VALUE, what="62% malformed")
a48b = Alert(identity="a", dataset="ds", fault=Fault.VALUE, what="63% malformed")
ok = a48a.fingerprint == a48b.fingerprint
line("INC-048", "PASS" if ok else "FAIL", f"fp_a={a48a.fingerprint} fp_b={a48b.fingerprint}")

# INC-049
router49 = Router({("ds49", Role.CUSTODIAN): "cust"})
a49a = Alert(identity="a", dataset="ds49", fault=Fault.ARRIVAL, what="x", severity=0.4, at=base)
router49.dispatch(a49a)
a49b = Alert(identity="a", dataset="ds49", fault=Fault.ARRIVAL, what="x", severity=0.6, at=base+timedelta(minutes=30))
d49 = router49.dispatch(a49b)
ok = d49.change == Change.WORSENED and d49.sent
line("INC-049", "PASS" if ok else "FAIL", f"change={d49.change} sent={d49.sent}")

# INC-050
router50a = Router({("ds50", Role.CUSTODIAN): "cust"})
a50_base = Alert(identity="a", dataset="ds50", fault=Fault.ARRIVAL, what="x", severity=0.5, at=base)
router50a.dispatch(a50_base)
a50_09 = Alert(identity="a", dataset="ds50", fault=Fault.ARRIVAL, what="x", severity=0.59, at=base+timedelta(minutes=10))
d50_09 = router50a.dispatch(a50_09)

router50b = Router({("ds50", Role.CUSTODIAN): "cust"})
router50b.dispatch(a50_base)
a50_11 = Alert(identity="a", dataset="ds50", fault=Fault.ARRIVAL, what="x", severity=0.61, at=base+timedelta(minutes=10))
d50_11 = router50b.dispatch(a50_11)
ok = d50_09.change == Change.UNCHANGED and d50_11.change == Change.WORSENED
line("INC-050", "PASS" if ok else "FAIL", f"09_change={d50_09.change} 11_change={d50_11.change}")

# INC-051
router51 = Router({("ds51", Role.CUSTODIAN): "cust"})
a51a = Alert(identity="a", dataset="ds51", fault=Fault.ARRIVAL, what="x", severity=0.8, at=base)
router51.dispatch(a51a)
a51b = Alert(identity="a", dataset="ds51", fault=Fault.ARRIVAL, what="x", severity=0.6, at=base+timedelta(minutes=10))
d51 = router51.dispatch(a51b)
ok = d51.change == Change.IMPROVED and d51.sent
line("INC-051", "PASS" if ok else "FAIL", f"change={d51.change} sent={d51.sent}")

# INC-052
router52 = Router({("ds52", Role.CUSTODIAN): "cust"})
a52a = Alert(identity="a", dataset="ds52", fault=Fault.ARRIVAL, what="x", severity=0.5, at=base)
router52.dispatch(a52a)
a52b = Alert(identity="a", dataset="ds52", fault=Fault.ARRIVAL, what="x", severity=0.5, at=base+timedelta(hours=7))
d52 = router52.dispatch(a52b)
ok = d52.change == Change.OPENED and d52.sent
line("INC-052", "PASS" if ok else "FAIL", f"change={d52.change} sent={d52.sent}")

# INC-053
router53 = Router({("ds53", Role.CUSTODIAN): "cust"})
a53 = Alert(identity="a", dataset="ds53", fault=Fault.ARRIVAL, what="x", severity=0.6, at=None)
d53a = router53.dispatch(a53)
d53b = router53.dispatch(a53)
ok = d53a.change == Change.OPENED and d53b.change == Change.OPENED  # not deduplicated since at=None never written to _sent
line("INC-053", "PASS" if ok else "FAIL", f"first={d53a.change},{d53a.sent} second={d53b.change},{d53b.sent}")

# INC-054
router54 = Router({("ds54", Role.CUSTODIAN): "cust"})
a54_49 = Alert(identity="a", dataset="ds54", fault=Fault.ARRIVAL, what="x", severity=0.49, at=base)
a54_50 = Alert(identity="b", dataset="ds54", fault=Fault.ARRIVAL, what="x", severity=0.50, at=base)
d54_49 = router54.dispatch(a54_49)
d54_50 = router54.dispatch(a54_50)
ok = d54_49.delivery == Delivery.DIGEST and d54_50.delivery == Delivery.IMMEDIATE
line("INC-054", "PASS" if ok else "FAIL", f"0.49={d54_49.delivery} 0.50={d54_50.delivery}")

# INC-055
router55 = Router({("ds55", Role.STEWARD): "stew"})
a55 = Alert(identity="a", dataset="ds55", fault=Fault.DEFINITION, what="x", severity=0.2, consequence="blocks the FINREP submission", at=base)
d55 = router55.dispatch(a55)
ok = d55.delivery == Delivery.IMMEDIATE and "blocks a submission" in d55.reason
line("INC-055", "PASS" if ok else "FAIL", f"delivery={d55.delivery} reason={d55.reason!r}")

# INC-056
a56a = Alert(identity="a", dataset="ds56", fault=Fault.ARRIVAL, what="x", severity=0.1, consequence="Blocks submission")
a56b = Alert(identity="b", dataset="ds56", fault=Fault.ARRIVAL, what="x", severity=0.1, consequence="does not block anything")
a56c = Alert(identity="c", dataset="ds56", fault=Fault.ARRIVAL, what="x", severity=0.1, consequence="unblocks the queue")
ok = a56a.needs_immediate == True and a56b.needs_immediate == False and a56c.needs_immediate == True
line("INC-056", "PASS" if ok else "FAIL", f"a={a56a.needs_immediate} b={a56b.needs_immediate} c(unblocks)={a56c.needs_immediate}")

# INC-057
router57 = Router({("ds57", Role.CUSTODIAN): "cust"})
dispatches57 = []
for i in range(40):
    a = Alert(identity=f"low{i}", dataset="ds57", fault=Fault.ARRIVAL, what=f"finding {i}", severity=0.1, at=base+timedelta(minutes=i))
    dispatches57.append(router57.dispatch(a))
for i in range(2):
    a = Alert(identity=f"high{i}", dataset="ds57", fault=Fault.ARRIVAL, what=f"high {i}", severity=0.9, at=base+timedelta(minutes=100+i))
    dispatches57.append(router57.dispatch(a))
digest57 = router57.digest(dispatches57, at=base+timedelta(hours=3))
ok = len(digest57) == 40
line("INC-057", "PASS" if ok else "FAIL", f"digest_count={len(digest57)}")

# INC-058
empty_digest = Digest(at=base)
ok = empty_digest.compose() == "nothing to report"
line("INC-058", "PASS" if ok else "FAIL", f"compose={empty_digest.compose()!r}")

# INC-059
desc59 = digest57.compose()
ok = "40 findings" in desc59 and desc59.count("finding ") <= 6  # only worst 5 named in body plus header word
line("INC-059", "PASS" if ok else "FAIL", f"describe_head={desc59[:120]!r}")

# INC-060
a60 = Alert(identity="a", dataset="ds", fault=Fault.ARRIVAL, what="the feed did not arrive", consequence="FINREP line 23 is downstream", likely_cause="vendor mapping changed at 05:30")
msg60 = a60.compose()
ok = "the feed did not arrive" in msg60 and "FINREP line 23 is downstream" in msg60 and "Likeliest cause: vendor mapping changed at 05:30" in msg60
line("INC-060", "PASS" if ok else "FAIL", f"message={msg60!r}")

# INC-061
a61 = Alert(identity="a", dataset="ds", fault=Fault.ARRIVAL, what="x", covers=400)
msg61 = a61.compose()
ok = "(400 findings, one incident)" in msg61
line("INC-061", "PASS" if ok else "FAIL", f"message={msg61!r}")

# INC-062
a62 = Alert(identity="a", dataset="ds", fault=Fault.CALIBRATION, what="x", disclosure="this monitor has degraded")
msg62 = a62.compose()
ok = "⚠ this monitor has degraded." in msg62
line("INC-062", "PASS" if ok else "FAIL", f"message={msg62!r}")

# INC-063
a63 = Alert(identity="a", dataset="ds", fault=Fault.ARRIVAL, what="the feed failed.", consequence="downstream fails.", likely_cause="vendor issue.")
msg63 = a63.compose()
ok = ".." not in msg63
line("INC-063", "PASS" if ok else "FAIL", f"message={msg63!r}")

# INC-064
policy = Policy.of("EU")
gate64 = Gate(policy, tenant_id="t1")
router64 = Router({("ds64", Role.CUSTODIAN): "cust1"}, channels={Role.CUSTODIAN:"pager"}, channel_regions={"pager":"US"}, gate=gate64)
a64 = Alert(identity="a", dataset="ds64", fault=Fault.ARRIVAL, what="x", jurisdiction="EU", at=base)
d64 = router64.dispatch(a64)
ok = d64.delivery == Delivery.QUIET and "cust1" in d64.reason
line("INC-064", "PASS" if ok else "FAIL", f"delivery={d64.delivery} reason={d64.reason!r}")

# INC-065
ok = "The alert body quotes failing values, so sending it moves the tenant's data" in d64.reason
line("INC-065", "PASS" if ok else "FAIL", f"reason={d64.reason!r}")

# INC-066
router66 = Router({("ds66", Role.CUSTODIAN): "cust"}, gate=None)
a66 = Alert(identity="a", dataset="ds66", fault=Fault.ARRIVAL, what="x", severity=0.6, at=base)
d66 = router66.dispatch(a66)
ok = d66.delivery in (Delivery.IMMEDIATE, Delivery.DIGEST)
line("INC-066", "PASS" if ok else "FAIL", f"delivery={d66.delivery}")

# INC-067
policy67 = Policy.of("EU")
gate67 = Gate(policy67, tenant_id="t1")
router67a = Router({("ds67", Role.STEWARD): "stew"}, channels={Role.STEWARD:"chat"}, channel_regions={"chat":"EU"}, gate=gate67)
router67b = Router({("ds67", Role.STEWARD): "stew"}, channels={Role.STEWARD:"pager"}, channel_regions={"pager":"US"}, gate=gate67)
a67 = Alert(identity="a", dataset="ds67", fault=Fault.VALUE, what="x", jurisdiction="EU", at=base)
d67a = router67a.dispatch(a67)
d67b = router67b.dispatch(a67)
ok = d67a.delivery != Delivery.QUIET and d67b.delivery == Delivery.QUIET
line("INC-067", "PASS" if ok else "FAIL", f"eu_chan_delivery={d67a.delivery} us_chan_delivery={d67b.delivery}")

# INC-068
router68 = Router({("ds68", Role.CUSTODIAN): "cust"}, gate=gate67)
a68a = Alert(identity="a", dataset="ds68", fault=Fault.ARRIVAL, what="x", severity=0.5, jurisdiction="EU", at=base)
router68.dispatch(a68a)  # first dispatch establishes sent state
a68b = Alert(identity="a", dataset="ds68", fault=Fault.ARRIVAL, what="x", severity=0.5, jurisdiction="EU", at=base+timedelta(minutes=5))
d68 = router68.dispatch(a68b)
ok = d68.delivery == Delivery.QUIET and "residency" in d68.reason and "already open and unchanged" not in d68.reason
line("INC-068", "PASS" if ok else "FAIL", f"delivery={d68.delivery} reason={d68.reason!r}")

# INC-069
router69 = Router({("ds69", Role.CUSTODIAN): "cust"})
a69 = Alert(identity="a", dataset="ds69", fault=Fault.ARRIVAL, what="x", severity=0.1, at=base)
router69.dispatch(a69)  # digested (low severity)
d69 = router69.resolve(a69)
ok = d69.change == Change.RESOLVED and len(d69.recipients) > 0 and d69.sent
line("INC-069", "PASS" if ok else "FAIL", f"change={d69.change} recipients={len(d69.recipients)} sent={d69.sent}")

# INC-070
router70 = Router({("ds70", Role.CUSTODIAN): "cust"})
a70 = Alert(identity="a", dataset="ds70", fault=Fault.ARRIVAL, what="x", severity=0.6, at=base)
router70.dispatch(a70)
router70.resolve(a70)
a70b = Alert(identity="a", dataset="ds70", fault=Fault.ARRIVAL, what="x", severity=0.6, at=base+timedelta(minutes=5))
d70 = router70.dispatch(a70b)
ok = d70.change == Change.OPENED and d70.sent
line("INC-070", "PASS" if ok else "FAIL", f"change={d70.change} sent={d70.sent}")

# INC-071
gate71 = Gate(Policy.of("EU"), tenant_id="t1")
router71 = Router({("ds71", Role.CUSTODIAN): "cust"}, channels={Role.CUSTODIAN:"pager"}, channel_regions={"pager":"US"}, gate=gate71)
a71 = Alert(identity="a", dataset="ds71", fault=Fault.ARRIVAL, what="x", jurisdiction="EU", at=base)
d71 = router71.resolve(a71)
ok_bypasses = d71.delivery != Delivery.QUIET  # resolve doesn't check gate -> goes through despite residency issue
line("INC-071", "FAIL" if ok_bypasses else "PASS", f"resolve_delivery={d71.delivery} recipients={[r.identity for r in d71.recipients]} (resolve does not call _residency_refusals -- gate bypassed)")

# INC-072
router72 = Router({("dsA", Role.CUSTODIAN): "custA"})  # shared router, note: contacts keyed only by dataset name, not tenant
a72_t1 = Alert(identity="same_id", dataset="dsA", fault=Fault.ARRIVAL, what="x", severity=0.6, at=base)
d72_t1 = router72.dispatch(a72_t1)
a72_t2 = Alert(identity="same_id", dataset="dsA", fault=Fault.ARRIVAL, what="x", severity=0.6, at=base+timedelta(minutes=1))  # "different tenant" but identical dataset/fault/identity -- no tenant field exists
d72_t2 = router72.dispatch(a72_t2)
ok = d72_t2.change != Change.UNCHANGED  # expect NOT deduplicated if truly different tenants
line("INC-072", "FAIL" if d72_t2.change == Change.UNCHANGED else "PASS", f"t1_change={d72_t1.change} t2_change={d72_t2.change} (Alert/Router carry no tenant field; a shared Router instance across tenants collides on identical dataset+fault+identity)")

# INC-073
combos = []
for delivery in Delivery:
    for change in Change:
        d = Dispatch(alert=Alert(identity="a",dataset="d",fault=Fault.ARRIVAL,what="x"), delivery=delivery, change=change)
        combos.append((delivery, change, d.sent))
ok = all((sent == False) if (delivery==Delivery.QUIET or change==Change.UNCHANGED) else (sent==True) for delivery,change,sent in combos)
line("INC-073", "PASS" if ok else "FAIL", f"combos={combos}")
