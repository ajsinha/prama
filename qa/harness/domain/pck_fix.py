import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.packs.banking import fix

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

SOH = fix.SOH

def build(pairs, delim=SOH):
    """pairs: list of (tag,value) excluding 8,9,10. Build a full valid message."""
    body_pairs = [(35, pairs_dict.get(35,'D'))] if False else None
    # body = everything after 9=xxx up to (not incl) 10=
    body_fields = delim.join(f"{t}={v}" for t,v in pairs) + delim
    prefix = f"8=FIX.4.4{delim}9={len(body_fields)}{delim}"
    partial = prefix + body_fields
    chksum = sum(partial.encode('latin-1')) % 256
    full = partial + f"10={chksum:03d}{delim}"
    return full

@block("PCK-067")
def _():
    pairs = [(35,'D'),(11,'ORD1'),(55,'AAPL'),(54,'1'),(38,'100'),(40,'2')]
    msg = build(pairs)
    m = fix.parse(msg)
    ok = m.is_well_formed and m.msg_type=='D' and all(t in m.tags for t in (11,55,54,38,40)) and m.delimiter==SOH
    R("PCK-067", ok, f"defects={m.defects} msg_type={m.msg_type} delim_is_soh={m.delimiter==SOH}")

@block("PCK-068")
def _():
    pairs = [(35,'D'),(11,'ORD1'),(55,'AAPL'),(54,'1'),(38,'100'),(40,'2')]
    msg_pipe = build(pairs, delim='|')
    m = fix.parse(msg_pipe)
    ok = m.arrived_display_delimited is True and m.named().get('display_delimited') is True
    msg_caret = build(pairs, delim='^')
    m2 = fix.parse(msg_caret)
    ok2 = m2.arrived_display_delimited is True
    R("PCK-068", m.is_well_formed and ok and m2.is_well_formed and ok2, f"pipe: defects={m.defects} disp={m.arrived_display_delimited}; caret: defects={m2.defects} disp={m2.arrived_display_delimited}")

@block("PCK-069")
def _():
    # SOH msg whose tag 58 free text contains a pipe
    pairs = [(35,'D'),(11,'ORD1'),(55,'AAPL'),(54,'1'),(38,'100'),(40,'2'),(58,'a|b')]
    msg = build(pairs)
    m = fix.parse(msg)
    ok = m.delimiter == SOH and m.tags.get(58) == 'a|b'
    R("PCK-069", ok, f"delimiter is SOH: {m.delimiter==SOH}; tag58={m.tags.get(58)!r}")

@block("PCK-070")
def _():
    pairs = [(35,'D'),(11,'ORD1'),(55,'AAPL'),(54,'1'),(38,'100'),(40,'2')]
    msg = build(pairs)
    m1 = fix.parse(msg)
    ok1 = not any(d.tag==9 for d in m1.defects)
    # decrement 9= by one
    import re
    m2text = re.sub(r'9=(\d+)\x01', lambda mo: f"9={int(mo.group(1))-1}\x01", msg, count=1)
    m2 = fix.parse(m2text)
    has_defect9 = any(d.tag==9 for d in m2.defects)
    R("PCK-070", ok1 and has_defect9, f"orig defects on 9: {[d for d in m1.defects if d.tag==9]}; decremented defects: {[d.render() for d in m2.defects if d.tag==9]}")

@block("PCK-071")
def _():
    found = None
    for suffix in range(2000):
        pairs = [(35,'D'),(11,f'O{suffix}'),(55,'A'),(54,'1'),(38,'1'),(40,'2')]
        msg = build(pairs)
        cs = msg.split('10=')[-1].rstrip(SOH)
        if int(cs) < 100:
            found = (msg, cs)
            break
    assert found is not None, "could not find a low-checksum message in 2000 tries"
    m1 = fix.parse(found[0])
    padded_ok = len(found[1])==3
    bad = found[0].replace(f"10={found[1]}", "10=999")
    m2 = fix.parse(bad)
    has_defect10 = any(d.tag==10 for d in m2.defects)
    R("PCK-071", padded_ok and m1.is_well_formed and has_defect10, f"checksum={found[1]!r} padded_len3={padded_ok}; bad msg defects10={[d.render() for d in m2.defects if d.tag==10]}")

@block("PCK-072")
def _():
    pairs = [(35,'D'),(49,'Renée'),(11,'O1'),(55,'A'),(54,'1'),(38,'1'),(40,'2')]
    try:
        msg = build(pairs)
        m = fix.parse(msg)
        R("PCK-072", True, f"no exception; defects={[d.render() for d in m.defects]}; is_well_formed={m.is_well_formed}")
    except Exception as e:
        R("PCK-072", False, f"EXCEPTION during build/parse: {type(e).__name__}: {e}")

@block("PCK-073")
def _():
    pairs = [(35,'AE'),(571,'T1'),(55,'A'),(32,'10'),(31,'1.0'),
             (555,'2'),(600,'LEG1'),(600,'LEG2')]
    msg = build(pairs)
    m = fix.parse(msg)
    legs = m.groups.get(555, ())
    ok = len(legs)==2 and m.named().get('no_legs_entries')==2
    R("PCK-073", ok, f"legs={legs} named_entries={m.named().get('no_legs_entries')} defects={[d.render() for d in m.defects]}")

@block("PCK-074")
def _():
    pairs = [(35,'AE'),(571,'T1'),(55,'A'),(32,'10'),(31,'1.0'),
             (555,'3'),(600,'LEG1'),(600,'LEG2')]
    msg = build(pairs)
    m = fix.parse(msg)
    d = [x for x in m.defects if x.tag==555]
    ok = len(d)==1 and "declares 3 entr" in d[0].problem and "carries 2" in d[0].problem
    R("PCK-074", ok, f"defect={d[0].render() if d else None}")

@block("PCK-075")
def _():
    pairs = [(35,'D'),(11,'O1'),(55,'A'),(54,'1'),(38,'1'),(40,'2'),
             (453,'many'),(448,'P1'),(448,'P2')]
    msg = build(pairs)
    m = fix.parse(msg)
    d = [x for x in m.defects if x.tag==453]
    R("PCK-075", len(d)>0, f"defects_on_453={[x.render() for x in d]}; groups={m.groups.get(453)}; tags448_leaked={m.tags.get(448)}")

@block("PCK-076")
def _():
    pairs = [(35,'D'),(11,'O1'),(55,'A'),(54,'1'),(38,'1'),(40,'2'),
             (453,'2'),(448,'P1'),(448,'P2'),
             (555,'2'),(600,'LEG1'),(600,'LEG2')]
    msg = build(pairs)
    m = fix.parse(msg)
    g453 = m.groups.get(453, ())
    g555 = m.groups.get(555, ())
    ok = (len(g453)==2 and len(g555)==2 and
          g453[0].get(448)=='P1' and g453[1].get(448)=='P2' and
          g555[0].get(600)=='LEG1' and g555[1].get(600)=='LEG2')
    R("PCK-076", ok, f"g453={g453} g555={g555}")

@block("PCK-077")
def _():
    pairs_valid = [(35,'D'),(11,'O1'),(55,'A'),(54,'1'),(38,'1'),(40,'2')]
    body = SOH.join(f"{t}={v}" for t,v in pairs_valid) + SOH + "garbage" + SOH
    prefix = f"8=FIX.4.4{SOH}9={len(body)}{SOH}"
    partial = prefix + body
    cs = sum(partial.encode('latin-1')) % 256
    msg = partial + f"10={cs:03d}{SOH}"
    m = fix.parse(msg)
    d = [x for x in m.defects if x.tag is None and 'garbage' in x.problem]
    R("PCK-077", len(d)>0 and m.tags.get(11)=='O1', f"defects={[x.render() for x in m.defects]}; tag11={m.tags.get(11)}")

@block("PCK-078")
def _():
    m1 = fix.parse('')
    m2 = fix.parse('   ')
    s = fix.split('')
    ok = (m1.tags=={} and not any(True for _ in [1] if False)) and (m2.tags is not None) and s==[]
    R("PCK-078", ok, f"parse(''): tags={m1.tags} defects={m1.defects}; parse('   '): tags={m2.tags} defects={m2.defects}; split('')={s}")

@block("PCK-079")
def _():
    import os
    junk = os.urandom(4096).decode('latin-1', errors='replace')
    import time
    t0 = time.time()
    m = fix.parse(junk)
    dt = time.time()-t0
    R("PCK-079", dt < 5.0, f"no exception, took {dt:.3f}s, defects_count={len(m.defects)}")

@block("PCK-080")
def _():
    pairs = [(35,'D'),(11,'O1'),(55,'A'),(54,'1'),(38,'1'),(40,'2'),(9999,'x')]
    msg = build(pairs)
    m = fix.parse(msg)
    ok = m.named().get('tag_9999')=='x'
    R("PCK-080", ok, f"named()['tag_9999']={m.named().get('tag_9999')}")

@block("PCK-081")
def _():
    # ExecutionReport missing 39
    pairs = [(35,'8'),(37,'O1'),(17,'E1'),(150,'0'),(55,'A'),(54,'1')]
    msg = build(pairs)
    m = fix.parse(msg)
    d1 = [x for x in m.defects if x.tag==39]
    pairs2 = [(35,'AE'),(55,'A'),(32,'1'),(31,'1.0')]  # missing 571
    msg2 = build(pairs2)
    m2 = fix.parse(msg2)
    d2 = [x for x in m2.defects if x.tag==571]
    R("PCK-081", len(d1)==1 and len(d2)==1, f"exec_report missing39_defects={[x.render() for x in d1]}; AE missing571_defects={[x.render() for x in d2]}")

@block("PCK-082")
def _():
    pairs = [(35,'0')]
    msg = build(pairs)
    m = fix.parse(msg)
    ok = len(m.defects)==0
    R("PCK-082", ok, f"heartbeat defects={m.defects}; is_well_formed={m.is_well_formed} -- note: 'No structural defects found' is indistinguishable from 'all requirements met' per catalogue's own critique")

@block("PCK-083")
def _():
    pairs = [(35,'D'),(11,'O1'),(55,'A'),(54,'1'),(38,'1'),(40,'2')]
    one = build(pairs)
    three = one+one+one
    msgs = fix.split(three)
    ok1 = len(msgs)==3
    # now one whose free text field (58) contains literal '8=FIX'
    pairs2 = [(35,'D'),(11,'O1'),(55,'A'),(54,'1'),(38,'1'),(40,'2'),(58,'note 8=FIX inside')]
    msg2 = build(pairs2)
    split2 = fix.split(msg2)
    ok2 = len(split2)==1
    R("PCK-083", ok1 and ok2, f"three-concat -> {len(msgs)} messages (expect 3); literal 8=FIX inside field -> split into {len(split2)} pieces (expect 1, stated behaviour)")

print("=== PCK FIX 067-083 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
