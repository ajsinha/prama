import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from datetime import date
from prama.classify import codelists as cl
from prama.core.errors import ValidationError

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

@block("CLS-058")
def _():
    a = cl.ISO_4217.contains('EUR')
    b = cl.ISO_4217.contains('EUR', when=date(2021,6,1))
    c = cl.ISO_4217.contains('EUR', when=date(2026,1,1))
    R("CLS-058", a and b and c, f"a={a} b={b} c={c}")

@block("CLS-059")
def _():
    a = cl.ISO_4217.contains('ZWL', when=date(2023,6,1))
    b = cl.ISO_4217.contains('ZWL', when=date(2024,4,4))
    c = cl.ISO_4217.contains('ZWL', when=date(2024,4,5))
    d = cl.ISO_4217.contains('ZWL', when=date(2025,1,1))
    ok = a and b and not c and not d
    R("CLS-059", ok, f"2023-06-01={a} 2024-04-04={b} 2024-04-05={c} 2025-01-01={d}")

@block("CLS-060")
def _():
    a = cl.ISO_4217.contains('ZWG', when=date(2024,4,4))
    b = cl.ISO_4217.contains('ZWG', when=date(2024,4,5))
    ok = not a and b
    R("CLS-060", ok, f"04-04={a} 04-05={b}")

@block("CLS-061")
def _():
    a1 = cl.ISO_4217.contains('ANG', when=date(2025,3,30))
    a2 = cl.ISO_4217.contains('ANG', when=date(2025,3,31))
    b1 = cl.ISO_4217.contains('XCG', when=date(2025,3,30))
    b2 = cl.ISO_4217.contains('XCG', when=date(2025,3,31))
    ok = a1 and not a2 and not b1 and b2
    R("CLS-061", ok, f"ANG:03-30={a1} 03-31={a2}; XCG:03-30={b1} 03-31={b2}")

@block("CLS-062")
def _():
    v2024 = cl.ISO_4217.as_of(date(2024,4,5))
    zwl_present = 'ZWL' in v2024
    zwg_present = 'ZWG' in v2024
    # the comment above _ISO4217_2024 claims outgoing code is NOT removed in the same step
    # but code does (_ISO4217_2023 | {"ZWG"}) - {"ZWL"}
    matches_comment = zwl_present  # if comment true, ZWL should still be present when ZWG appears
    R("CLS-062", matches_comment, f"in the version introducing ZWG: ZWL_present={zwl_present} ZWG_present={zwg_present} -- comment claims outgoing code kept for a transition period; code removes it in the same step (ZWL_present should be True per comment, is {zwl_present})")

@block("CLS-063")
def _():
    a = cl.ISO_4217.contains('SLL', when=date(2023,6,1))
    b = cl.ISO_4217.contains('SLE', when=date(2023,6,1))
    ok = a and b
    R("CLS-063", ok, f"SLL={a} SLE={b}")

@block("CLS-064")
def _():
    a = cl.ISO_4217.contains('HRK', when=date(2022,12,31))
    b = cl.ISO_4217.contains('HRK', when=date(2023,1,1))
    v = cl.ISO_4217.as_of(date(2023,1,1))
    ok = a and not b and 'HRK' in v.note
    R("CLS-064", ok, f"2022-12-31={a} 2023-01-01={b} note={v.note!r}")

@block("CLS-065")
def _():
    v21 = cl.ISO_4217.as_of(date(2021,6,1)).codes
    v23 = cl.ISO_4217.as_of(date(2023,6,1)).codes
    removed = v21 - v23
    added = v23 - v21
    note = cl.ISO_4217.as_of(date(2023,6,1)).note
    unexplained = [c for c in removed if c not in note]
    ok = 'CUC' not in note
    R("CLS-065", ok, f"removed={sorted(removed)} added={sorted(added)} note={note!r} (CUC removed but not mentioned in note: {'CUC' not in note})")

@block("CLS-066")
def _():
    try:
        cl.ISO_4217.as_of(date(2020,12,31))
        R("CLS-066", False, "no exception")
    except ValidationError as e:
        ok = 'earliest' in str(e).lower() or '2021' in str(e)
        R("CLS-066", ok, f"{e}")

@block("CLS-067")
def _():
    a = cl.ISO_4217.as_of()
    b = cl.ISO_4217.as_of(date.today())
    ok = a is b or a==b
    R("CLS-067", ok, f"as_of()==as_of(today): {a==b}")

@block("CLS-068")
def _():
    try:
        cl.CodeList(name='x', label='x', authority='x', versions=(
            cl.CodeListVersion(effective_from=date(2024,1,1), codes=frozenset({'A'})),
            cl.CodeListVersion(effective_from=date(2023,1,1), codes=frozenset({'A','B'})),
        ))
        r1 = False
    except ValidationError:
        r1 = True
    try:
        cl.CodeList(name='y', label='y', authority='y', versions=())
        r2 = False
    except ValidationError:
        r2 = True
    R("CLS-068", r1 and r2, f"out_of_order_raises={r1} no_versions_raises={r2}")

@block("CLS-069")
def _():
    try:
        clist = cl.CodeList(name='z', label='z', authority='z', versions=(
            cl.CodeListVersion(effective_from=date(2024,1,1), codes=frozenset({'A'})),
            cl.CodeListVersion(effective_from=date(2024,1,1), codes=frozenset({'B'})),
        ))
        v = clist.as_of(date(2024,1,1))
        R("CLS-069", None, f"duplicate effective_date NOT refused at construction; as_of resolves to codes={v.codes} (last-wins by declaration order, undocumented)")
    except ValidationError as e:
        R("CLS-069", True, f"refused at construction: {e}")

@block("CLS-070")
def _():
    a = cl.SIDE.contains('buy')
    b = 'buy' in cl.SIDE.latest
    ok = a == b
    R("CLS-070", ok, f"SIDE.contains('buy')={a}; 'buy' in SIDE.latest={b} (case_sensitive=False set on CodeList, but CodeListVersion.__contains__ does no case folding)")

@block("CLS-071")
def _():
    ok = cl.ISO_4217.contains('usd') is False
    R("CLS-071", ok, f"ISO_4217.contains('usd')={cl.ISO_4217.contains('usd')}")

@block("CLS-072")
def _():
    codes = cl.ISO_4217_MINOR_UNITS.latest.codes
    present = all(c in codes for c in ('JPY','KRW','VND','CLP','ISK'))
    absent = all(c not in codes for c in ('EUR','USD','KWD'))
    R("CLS-072", present and absent, f"codes={sorted(codes)}")

@block("CLS-073")
def _():
    import re
    bad4217 = [c for c in cl._ISO4217_2025 if not re.match(r'^[A-Z]{3}$', c)]
    bad3166 = [c for c in cl._ISO3166_ALPHA2 if not re.match(r'^[A-Z]{2}$', c)]
    sizes = {'iso4217_2021': len(cl._ISO4217_2021), 'iso3166': len(cl._ISO3166_ALPHA2)}
    R("CLS-073", not bad4217 and not bad3166, f"malformed_4217={bad4217} malformed_3166={bad3166} sizes={sizes}")

@block("CLS-074")
def _():
    a = cl.ISO_3166.as_of(date(2026,1,1))
    b = cl.ISO_3166.as_of(date(2021,1,1))
    ok = a.codes == b.codes and len(cl.ISO_3166.versions)==1
    R("CLS-074", ok, f"same_set={a.codes==b.codes} version_count={len(cl.ISO_3166.versions)}")

@block("CLS-075")
def _():
    try:
        cl.REGISTRY.get('iso4127')
        R("CLS-075", False, "no exception")
    except ValidationError as e:
        ok = all(n in str(e) for n in cl.REGISTRY.names())
        R("CLS-075", ok, f"{e}")

@block("CLS-076")
def _():
    reg = cl.default_registry()
    fake = cl.CodeList(name='iso4217', label='fake', authority='x', versions=(
        cl.CodeListVersion(effective_from=date(2021,1,1), codes=frozenset({'AAA','BBB','CCC'})),
    ))
    try:
        reg.register(fake)
        got = reg.get('iso4217')
        R("CLS-076", False, f"registered without refusal; overwritten codes count={len(got.latest.codes)} (was {len(cl.ISO_4217.latest.codes)})")
    except ValidationError as e:
        R("CLS-076", True, f"refused: {e}")

@block("CLS-077")
def _():
    reg = cl.default_registry()
    r1 = reg.resolve(date(2023,6,1))
    r2 = reg.resolve()
    ok = len(r1)==4 and len(r2)==4 and ('ZWL' in r1['iso4217']) and ('ZWL' not in r2['iso4217'])
    R("CLS-077", ok, f"lists_2023={len(r1)} lists_today={len(r2)} ZWL_in_2023={'ZWL' in r1['iso4217']} ZWL_in_today={'ZWL' in r2['iso4217']}")

@block("CLS-078")
def _():
    reg = cl.default_registry()
    try:
        reg.resolve(date(2019,1,1))
        R("CLS-078", False, "no exception")
    except ValidationError as e:
        R("CLS-078", True, f"{e}")

print("=== CLS codelists 058-078 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
