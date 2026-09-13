import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.packs.banking import fpml

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

def leg_xml(payer, receiver, notional, ccy, kind='fixed', rate='0.05', index='USD-LIBOR-BBA', payer_as_text=False):
    if payer_as_text:
        payer_el = f"<payerPartyReference>{payer}</payerPartyReference>" if payer else ""
    else:
        payer_el = f'<payerPartyReference href="{payer}"/>' if payer else ""
    receiver_el = f'<receiverPartyReference href="{receiver}"/>' if receiver else ""
    rate_el = f"<fixedRateSchedule><initialValue>{rate}</initialValue></fixedRateSchedule>" if kind=='fixed' else ""
    float_el = f"<floatingRateCalculation><floatingRateIndex>{index}</floatingRateIndex></floatingRateCalculation>" if kind=='floating' else ""
    notional_el = ""
    if notional is not None:
        notional_el = f"<notionalSchedule><notionalStepSchedule><initialValue>{notional}</initialValue><currency>{ccy}</currency></notionalStepSchedule></notionalSchedule>"
    return f"""<swapStream>
      {payer_el}
      {receiver_el}
      <calculationPeriodAmount><calculation>
        {notional_el}
        {rate_el}{float_el}
      </calculation></calculationPeriodAmount>
    </swapStream>"""

def trade_xml(legs_xml, parties=(('PartyA','PARTYA'),('PartyB','PARTYB')), trade_id='T1', ns='http://www.fpml.org/FpML-5/confirmation', version_attr='5-10', on_behalf_of=None):
    parties_xml = "".join(f'<party id="{pid}"/>' for pid,name in parties)
    behalf_xml = f'<onBehalfOf href="{on_behalf_of}"/>' if on_behalf_of else ""
    attrs = ""
    if ns:
        attrs += f' xmlns="{ns}"'
    if version_attr:
        attrs += f' version="{version_attr}"'
    root_open = f'<dataDocument{attrs}>'
    return f"""{root_open}
    <trade><tradeHeader><partyTradeIdentifier><tradeId>{trade_id}</tradeId></partyTradeIdentifier><tradeDate>2026-01-01</tradeDate></tradeHeader>
    <swap>{"".join(legs_xml)}</swap>
    </trade>
    {parties_xml}
    {behalf_xml}
    </dataDocument>"""

@block("PCK-101")
def _():
    legs = [leg_xml('PartyA','PartyB',1000000,'USD',kind='fixed'), leg_xml('PartyB','PartyA',1000000,'USD',kind='floating')]
    xml = trade_xml(legs)
    t = fpml.parse(xml)
    ok = len(t.legs)==2 and t.is_two_sided and any(l.kind=='fixed' and l.rate is not None for l in t.legs) and any(l.kind=='floating' and l.index for l in t.legs) and len(t.defects)==0
    R("PCK-101", ok, f"legs={len(t.legs)} is_two_sided={t.is_two_sided} defects={t.defects} legdetail={[l.to_dict() for l in t.legs]}")

@block("PCK-102")
def _():
    legs = [leg_xml('PartyA','PartyB',1000000,'USD'), leg_xml(None,'PartyA',1000000,'USD')]
    xml = trade_xml(legs)
    t = fpml.parse(xml)
    d = [x for x in t.defects if 'leg 2' in x]
    ok = len(d)==1 and t.has_two_legs and not t.is_two_sided
    R("PCK-102", ok, f"defects={t.defects} has_two_legs={t.has_two_legs} is_two_sided={t.is_two_sided}")

@block("PCK-103")
def _():
    legs = [leg_xml('PartyA','PartyB',1000000,'USD',payer_as_text=True)]
    xml = trade_xml(legs)
    t = fpml.parse(xml)
    ok = t.legs[0].payer == 'PartyA'
    R("PCK-103", ok, f"payer={t.legs[0].payer!r}")

@block("PCK-104")
def _():
    legs = [leg_xml('PartyA','PartyB',1000000,'USD')]
    xml = trade_xml(legs)
    t = fpml.parse(xml)
    leg = t.legs[0]
    a = leg.signed_for('PartyA')
    b = leg.signed_for('PartyB')
    c = leg.signed_for('PartyC')
    # leg with no notional
    legs2 = [leg_xml('PartyA','PartyB',None,'')]
    t2 = fpml.parse(trade_xml(legs2))
    d = t2.legs[0].signed_for('PartyA')
    ok = a == -1000000 and b == 1000000 and c is None and d is None
    R("PCK-104", ok, f"payer(PartyA)={a} receiver(PartyB)={b} uninvolved(PartyC)={c} no_notional={d}")

@block("PCK-105")
def _():
    xml = trade_xml([])
    t = fpml.parse(xml)
    got = t.net_for('PartyA')
    ok = got is None
    R("PCK-105", ok, f"net_for with no legs = {got!r} (type={type(got).__name__})")

@block("PCK-106")
def _():
    legs = [leg_xml('PartyA','PartyB',1000000,'EUR'), leg_xml('PartyB','PartyA',1200000,'USD')]
    t = fpml.parse(trade_xml(legs))
    got = t.net_for('PartyA')
    ok = got is None
    R("PCK-106", ok, f"net_for cross-currency = {got!r}")

@block("PCK-107")
def _():
    legs = [leg_xml('PartyA','PartyB',1000000,'USD'), leg_xml('PartyB','PartyA',1000000,'USD',kind='floating')]
    xml510 = trade_xml(legs, version_attr='5-10')
    t1 = fpml.parse(xml510)
    xml512 = trade_xml(legs, version_attr='5-12')
    t2 = fpml.parse(xml512)
    ok = t1.trade_id==t2.trade_id and len(t1.legs)==len(t2.legs) and t1.version=='5-10' and t2.version=='5-12'
    R("PCK-107", ok, f"v1_legs={len(t1.legs)} v2_legs={len(t2.legs)} version1={t1.version!r} version2={t2.version!r}")

@block("PCK-108")
def _():
    cases = ['<trade>', '', 'not xml at all']
    import os
    junk = os.urandom(200).decode('latin-1', errors='replace')
    cases.append(junk)
    all_ok = True
    detail = []
    for c in cases:
        try:
            t = fpml.parse(c)
            has_defect = len(t.defects) >= 1
            all_ok &= has_defect
            detail.append(f"{c[:20]!r}: defects={t.defects}")
        except Exception as e:
            all_ok = False
            detail.append(f"{c[:20]!r}: EXCEPTION {type(e).__name__}: {e}")
    R("PCK-108", all_ok, " || ".join(detail))

@block("PCK-109")
def _():
    bomb = '<?xml version="1.0"?><!DOCTYPE trade [<!ENTITY a "1234567890"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]><trade>&c;</trade>'
    import time
    t0=time.time()
    try:
        t = fpml.parse(bomb)
        dt = time.time()-t0
        R("PCK-109", dt < 5.0, f"no exception, {dt:.3f}s, defects={t.defects}")
    except Exception as e:
        R("PCK-109", False, f"EXCEPTION: {type(e).__name__}: {e}")

@block("PCK-110")
def _():
    xml = '<swap><swapStream><payerPartyReference href="A"/><receiverPartyReference href="B"/></swapStream></swap>'
    t = fpml.parse(xml)
    legs_found = len(t.legs) >= 1
    header_absence_reported = any('header' in d.lower() or 'trade_id' in d.lower() or 'trade id' in d.lower() for d in t.defects)
    ok = legs_found and header_absence_reported
    R("PCK-110", ok, f"legs={len(t.legs)} trade_id={t.trade_id!r} defects={t.defects} (legs_found={legs_found}, header_absence_reported={header_absence_reported})")

@block("PCK-111")
def _():
    legs = [leg_xml('PartyA','PartyB',1000000,'USD'), leg_xml('PartyB','PartyA',1000000,'USD',kind='floating')]
    xml = trade_xml(legs, on_behalf_of='PartyB')
    t = fpml.parse(xml)
    net_a = t.net_for('PartyA')
    net_b = t.net_for('PartyB')
    net_behalf = t.net_for(t.on_behalf_of)
    ok = t.on_behalf_of == 'PartyB' and net_behalf == -net_a
    R("PCK-111", ok, f"on_behalf_of={t.on_behalf_of!r} net(PartyA)={net_a} net(PartyB)={net_b} net(on_behalf_of)={net_behalf}")

print("=== PCK FpML 101-111 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
