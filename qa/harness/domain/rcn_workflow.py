import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from datetime import date, timedelta
from decimal import Decimal
from prama.recon.workflow import Item, State, BreakQueue, Certificate, certify, STALE_DAYS
from prama.recon.classify import Break, BreakKind

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

def mkbreak(key, kind=BreakKind.GENUINE, diff='100'):
    return Break(key=key, kind=kind, left=Decimal('0'), right=Decimal(diff), because='x')

D0 = date(2026,1,1)

@block("RCN-073")
def _():
    q = BreakQueue()
    d = D0
    for i in range(40):
        q.observe([mkbreak('K1')], when=d+timedelta(days=i))
    item = q.get('K1')
    age = item.age(d+timedelta(days=39))
    ok = age in (39,40)
    R("RCN-073", ok, f"age={age}")

@block("RCN-074")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1')], when=D0)
    q.observe([], when=D0+timedelta(days=1))
    item = q.get('K1')
    ok = item.state==State.CLEARED and item.last_seen==D0+timedelta(days=1)
    still_in_queue = q.get('K1') is not None
    R("RCN-074", ok and still_in_queue, f"state={item.state} last_seen={item.last_seen} still_present={still_in_queue}")

@block("RCN-075")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1'),mkbreak('K2'),mkbreak('K3')], when=D0)
    q.observe([mkbreak('K1')], when=D0+timedelta(days=1))
    k2 = q.get('K2'); k3=q.get('K3'); k1=q.get('K1')
    ok = k2.state==State.CLEARED and k3.state==State.CLEARED and k1.state==State.OPEN
    R("RCN-075", ok, f"K1={k1.state} K2={k2.state} K3={k3.state}")

@block("RCN-076")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1')], when=D0)
    for i in range(1,90):
        q.observe([], when=D0+timedelta(days=i))
    q.observe([mkbreak('K1')], when=D0+timedelta(days=91))
    item = q.get('K1')
    age = item.age(D0+timedelta(days=91))
    ok = item.state==State.OPEN
    R("RCN-076", None, f"state={item.state} first_seen={item.first_seen} age_now={age} -- first_seen unchanged at day0, so a break recurring after 90 days enters the '90+' bucket immediately")

@block("RCN-077")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1')], when=D0)
    item = q.get('K1').accepted(by='alice', at='t', reason='known FX timing')
    q.update(item)
    for i in range(1,11):
        q.observe([], when=D0+timedelta(days=i))
    item2 = q.get('K1')
    still_accepted_forever = item2.state==State.ACCEPTED
    R("RCN-077", not still_accepted_forever, f"state_after_10_absent_runs={item2.state} (Expected: clears or is distinguishable from a live accepted item; got: still plain ACCEPTED with no distinguishing signal)")

@block("RCN-078")
def _():
    open_states = {s for s in State if s.is_open}
    ok = open_states == {State.OPEN, State.ASSIGNED, State.EXPLAINED}
    R("RCN-078", ok, f"{open_states}")

@block("RCN-079")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1')], when=D0)
    item = q.get('K1')
    item = item.assigned_to('alice','t1')
    item = item.explained('alice','t2','looked into it')
    item = item.accepted('bob','t3','confirmed timing')
    ok = len(item.comments)==3 and item.state==State.ACCEPTED
    R("RCN-079", ok, f"comments={[ (c.by,c.text) for c in item.comments]} state={item.state}")

@block("RCN-080")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1')], when=D0)
    item = q.get('K1')
    try:
        item.accepted('bob','t','   ')
        R("RCN-080", False, "no exception")
    except ValueError as e:
        R("RCN-080", True, f"{e}")

@block("RCN-081")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K29'),mkbreak('K30'),mkbreak('K31')], when=D0)
    as_of = D0+timedelta(days=30)
    # ages: K29->30, K30->30, K31->30 all same since observed same day; need different first_seen
    q2 = BreakQueue()
    q2.observe([mkbreak('A')], when=D0)
    q2.observe([mkbreak('A'),mkbreak('B')], when=D0+timedelta(days=1))
    as_of2 = D0+timedelta(days=31)  # A age=31, B age=30
    stale = q2.stale(as_of2)
    ok = len(stale)==2 and stale[0].key=='A'
    R("RCN-081", ok, f"stale=[{[ (s.key,s.age(as_of2)) for s in stale]}]")

@block("RCN-082")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1')], when=D0)
    item = q.get('K1').accepted('bob','t','known')
    q.update(item)
    as_of = D0+timedelta(days=90)
    stale = q.stale(as_of)
    ok = len(stale)==0
    R("RCN-082", ok, f"stale={[s.key for s in stale]}")

@block("RCN-083")
def _():
    q = BreakQueue()
    as_of = D0+timedelta(days=91)
    ages = {'a0':0,'a7':7,'a8':8,'a30':30,'a31':31,'a90':90,'a91':91}
    for key, age in ages.items():
        q.update(Item(key=key, kind=BreakKind.GENUINE, difference=Decimal('100'),
                       first_seen=as_of-timedelta(days=age), last_seen=as_of, state=State.OPEN))
    buckets = q.ageing(as_of)
    ok = sum(buckets.values())==len(q.open_items())
    exp = {"0-7":2,"8-30":2,"31-90":2,"90+":1}
    ok2 = buckets==exp
    R("RCN-083", ok and ok2, f"buckets={buckets} expected={exp}")

@block("RCN-084")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1'),mkbreak('K2'),mkbreak('K3')], when=D0)
    counts = q.by_owner()
    ok = counts.get('unassigned')==3
    R("RCN-084", ok, f"{counts}")

@block("RCN-085")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1',diff='100'),mkbreak('K2',diff='200'),mkbreak('K3',diff='300'),mkbreak('K4',diff='400')], when=D0)
    q.update(q.get('K1').accepted('bob','t','known'))
    q.update(q.get('K2').accepted('bob','t','known'))
    cert = certify('recon', q, period_end=D0, signed_by='alice', signed_at='t', matched_rate=0.9)
    ok = len(cert.outstanding)==4 and cert.accepted_total==Decimal('300') and cert.unexplained_total==Decimal('700')
    each_has_state_or_reason = all(('accepted' in cert.render() or True) for _ in [1])
    R("RCN-085", ok, f"outstanding={len(cert.outstanding)} accepted_total={cert.accepted_total} unexplained_total={cert.unexplained_total}")

@block("RCN-086")
def _():
    q = BreakQueue()
    cert1 = certify('recon', q, period_end=D0, signed_by='alice', signed_at='t', matched_rate=1.0)
    q2 = BreakQueue()
    q2.observe([mkbreak('K1')], when=D0)
    q2.observe([], when=D0+timedelta(days=1))
    cert2 = certify('recon', q2, period_end=D0+timedelta(days=1), signed_by='alice', signed_at='t', matched_rate=1.0)
    ok = 'Nothing was outstanding at period end.' in cert1.render() and 'Nothing was outstanding at period end.' in cert2.render()
    ok2 = f"{1.0:.2%}" in cert1.render()
    R("RCN-086", ok and ok2, f"cert1_clean={cert1.is_clean} cert2_clean={cert2.is_clean}")

@block("RCN-087")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1')], when=D0)
    cert = certify('recon', q, period_end=D0, signed_by='alice', signed_at='t', matched_rate=0.9)
    h1 = cert.content_hash
    import dataclasses
    cert2 = dataclasses.replace(cert, signed_by='bob')
    h2 = cert2.content_hash
    cert3 = dataclasses.replace(cert, unexplained_total=cert.unexplained_total+1)
    h3 = cert3.content_hash
    ok = h1==h2 and h1!=h3
    R("RCN-087", ok, f"h1==h2(after signed_by change)={h1==h2}; h1!=h3(after unexplained_total change)={h1!=h3}")

@block("RCN-088")
def _():
    q1 = BreakQueue()
    q1.observe([mkbreak('K1',diff='100'),mkbreak('K2',diff='200')], when=D0)
    q2 = BreakQueue()
    q2.observe([mkbreak('K2',diff='200'),mkbreak('K1',diff='100')], when=D0)
    c1 = certify('recon', q1, period_end=D0, signed_by='a', signed_at='t', matched_rate=0.9)
    c2 = certify('recon', q2, period_end=D0, signed_by='a', signed_at='t', matched_rate=0.9)
    ok = c1.content_hash==c2.content_hash
    R("RCN-088", ok, f"hashes_equal={ok}")

@block("RCN-089")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1',diff='-100'),mkbreak('K2',diff='200')], when=D0)
    q.update(q.get('K1').accepted('b','t','known'))
    cert = certify('recon', q, period_end=D0, signed_by='a', signed_at='t', matched_rate=0.9)
    ok = cert.accepted_total + cert.unexplained_total == cert.outstanding_total
    R("RCN-089", ok, f"accepted={cert.accepted_total} unexplained={cert.unexplained_total} sum={cert.accepted_total+cert.unexplained_total} total={cert.outstanding_total}")

@block("RCN-090")
def _():
    q = BreakQueue()
    q.observe([mkbreak('KA',diff='100'),mkbreak('KB',diff='100'),mkbreak('KC',diff='100')], when=D0)
    c1 = certify('recon', q, period_end=D0, signed_by='a', signed_at='t', matched_rate=0.9)
    c2 = certify('recon', q, period_end=D0, signed_by='a', signed_at='t', matched_rate=0.9)
    ok = [i.key for i in c1.outstanding]==[i.key for i in c2.outstanding]
    R("RCN-090", ok, f"order1={[i.key for i in c1.outstanding]} order2={[i.key for i in c2.outstanding]}")

@block("RCN-091")
def _():
    q = BreakQueue()
    q.observe([mkbreak('K1')], when=D0)
    try:
        cert = certify('recon', q, period_end=D0, signed_by='', signed_at='t', matched_rate=0.9)
        R("RCN-091", False, f"no refusal for signed_by=''; certificate produced and hash={cert.content_hash[:16]}")
    except Exception as e:
        R("RCN-091", True, f"refused: {e}")

print("=== RCN workflow 073-091 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
