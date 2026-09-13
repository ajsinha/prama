import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from decimal import Decimal
from prama.recon.classify import Classifier, BreakKind, Break, Population, attribute_to_fx, MULTIPLE_TOLERANCE, FX_POPULATION
from prama.semantic.relationships import Tolerance

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

D = Decimal
TOL = Tolerance(absolute=0.01, relative=0.0001)

@block("RCN-045")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('100.00'), D('100.005'))
    R("RCN-045", b is None, f"{b}")

@block("RCN-046")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('1000000'), D('1000000.02'))
    R("RCN-046", b is None, f"{b}")

@block("RCN-047")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('1000'), D('-1000'))
    ok = b is not None and b.kind==BreakKind.SIGN and b.kind.is_configuration
    R("RCN-047", ok, f"{b}")

@block("RCN-048")
def _():
    c = Classifier(TOL)
    for mult, left, right in [(2,'1000','2000'),(3,'1000','3000'),(4,'1000','4000')]:
        b = c.classify('k', D(left), D(right))
        if b is None or b.kind!=BreakKind.DUPLICATE or str(mult) not in b.because:
            R("RCN-048", False, f"mult={mult} -> {b}")
            return
    R("RCN-048", True, "2x,3x,4x all DUPLICATE")

@block("RCN-049")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('1000'), D('5000'))
    ok = b is not None and b.kind==BreakKind.GENUINE
    R("RCN-049", ok, f"{b}")

@block("RCN-050")
def _():
    c = Classifier(TOL)
    b1 = c.classify('k', D('1000.00'), D('2000.05'))
    b2 = c.classify('k', D('1000.00'), D('2000.5'))
    ok = b1 is not None and b1.kind==BreakKind.DUPLICATE and b2 is not None and b2.kind!=BreakKind.DUPLICATE
    R("RCN-050", ok, f"2000.05={b1.kind if b1 else None} 2000.5={b2.kind if b2 else None}")

@block("RCN-051")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('0'), D('1000'))
    ok = b is not None and b.kind!=BreakKind.DUPLICATE
    R("RCN-051", ok, f"{b}")

@block("RCN-052")
def _():
    c = Classifier(Tolerance(absolute=0.0001), rounding_places=2)
    b = c.classify('k', D('100.00'), D('100.01'))
    ok = b is not None and b.kind==BreakKind.ROUNDING and '2' in b.because
    R("RCN-052", ok, f"{b}")

@block("RCN-053")
def _():
    c = Classifier(Tolerance(absolute=0.0001), rounding_places=None)
    b = c.classify('k', D('100.00'), D('100.01'))
    ok = b is not None and b.kind==BreakKind.GENUINE
    R("RCN-053", ok, f"{b}")

@block("RCN-054")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('100'), D('105'), timing=True)
    ok = b is not None and b.kind==BreakKind.TIMING and b.kind.clears_itself
    R("RCN-054", ok, f"{b}")

@block("RCN-055")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('1000'), D('-1000'), timing=True)
    ok = b is not None and b.kind==BreakKind.TIMING
    R("RCN-055", ok, f"{b} (timing checked before sign)")

@block("RCN-056")
def _():
    only_timing = [k for k in BreakKind if k.clears_itself]
    ok = only_timing==[BreakKind.TIMING]
    R("RCN-056", ok, f"{only_timing}")

@block("RCN-057")
def _():
    config = {k for k in BreakKind if k.is_configuration}
    ok = config == {BreakKind.SIGN, BreakKind.DUPLICATE, BreakKind.FX}
    R("RCN-057", ok, f"{config}")

@block("RCN-058")
def _():
    c = Classifier(TOL)
    b_missing = c.classify('k', D('100'), None)
    b_extra = c.classify('k', None, D('100'))
    ok = b_missing.kind==BreakKind.MISSING and b_extra.kind==BreakKind.EXTRA
    reasons_ok = 'late or absent' in b_missing.because and 'late or absent' in b_extra.because
    R("RCN-058", ok and reasons_ok, f"missing={b_missing.kind} extra={b_extra.kind}")

@block("RCN-059")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('100'), None, normalisation=("the right side has 3 rows that carry no amount",))
    ok = b.kind==BreakKind.GENUINE and 'carry no' in b.because
    R("RCN-059", ok, f"{b}")

@block("RCN-060")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('100'), None, normalisation=("nothing relevant here, but text says the phrase 'carry no' by coincidence",))
    ok = b.kind==BreakKind.GENUINE
    R("RCN-060", ok, f"{b} (substring match on unrelated text produces wrong classification -- confirms brittle coupling)")

@block("RCN-061")
def _():
    c = Classifier(TOL)
    import decimal
    breaks = []
    ratio = D('1.0873')
    for i in range(25):
        left = D('1000')+i
        right = (left*ratio*(1+D('0.0001'))).quantize(D('0.01'))
        b = c.classify(f'k{i}', left, right)
        breaks.append(b)
    assert all(b.kind==BreakKind.GENUINE for b in breaks), [b.kind for b in breaks]
    out = attribute_to_fx(breaks)
    ok = all(b.kind==BreakKind.FX for b in out) and all(str(ratio) in b.because or '1.087' in b.because for b in out)
    R("RCN-061", ok, f"kinds={[b.kind for b in out]}")

def make_ratio_breaks(n, ratio):
    c = Classifier(TOL)
    out = []
    for i in range(n):
        left = D('1000')+i
        right = (left*ratio).quantize(D('0.0001'))
        b = c.classify(f'k{i}', left, right)
        out.append(b)
    return out

@block("RCN-062")
def _():
    b19 = make_ratio_breaks(19, D('1.05'))
    b20 = make_ratio_breaks(20, D('1.05'))
    out19 = attribute_to_fx(b19)
    out20 = attribute_to_fx(b20)
    ok = all(b.kind==BreakKind.GENUINE for b in out19) and all(b.kind==BreakKind.FX for b in out20)
    R("RCN-062", ok, f"19->{set(b.kind for b in out19)} 20->{set(b.kind for b in out20)}")

@block("RCN-063")
def _():
    b = make_ratio_breaks(25, D('1.0005'))
    out = attribute_to_fx(b)
    ok = all(x.kind==BreakKind.GENUINE for x in out)
    R("RCN-063", ok, f"kinds={set(x.kind for x in out)}")

@block("RCN-064")
def _():
    c = Classifier(TOL)
    breaks = []
    for i in range(12):
        left=D('1000')+i; right=(left*D('1.05')).quantize(D('0.0001'))
        breaks.append(c.classify(f'a{i}',left,right))
    for i in range(13):
        left=D('2000')+i; right=(left*D('1.20')).quantize(D('0.0001'))
        breaks.append(c.classify(f'b{i}',left,right))
    out = attribute_to_fx(breaks)
    ok = all(x.kind==BreakKind.GENUINE for x in out)
    R("RCN-064", ok, f"kinds={set(x.kind for x in out)}")

@block("RCN-065")
def _():
    c = Classifier(TOL)
    breaks = []
    for i in range(25):
        left=D('1000')+i; right=D(-left)  # sign-flip -> SIGN kind
        b = c.classify(f'k{i}', left, right)
        breaks.append(b)
    assert all(x.kind==BreakKind.SIGN for x in breaks)
    out = attribute_to_fx(breaks)
    ok = all(x.kind==BreakKind.SIGN for x in out)
    R("RCN-065", ok, f"kinds unchanged: {set(x.kind for x in out)}")

@block("RCN-066")
def _():
    b = make_ratio_breaks(25, D('1.05'))
    # duplicate two of the frozen breaks by value (equal fields, distinct objects)
    import dataclasses
    dup = dataclasses.replace(b[0])
    pool = b + [dup]
    out = attribute_to_fx(pool)
    both_reattributed = out[0].kind==BreakKind.FX and out[-1].kind==BreakKind.FX
    R("RCN-066", both_reattributed, f"orig={out[0].kind} dup={out[-1].kind}")

@block("RCN-067")
def _():
    c = Classifier(TOL)
    breaks = []
    for i in range(390):
        breaks.append(c.classify(f'k{i}', D('100'), D('105'), timing=True))
    for i in range(10):
        breaks.append(c.classify(f'g{i}', D('100'), D('999')))
    pop = Population(breaks=tuple(breaks))
    d = pop.describe()
    ok = 'timing' in d and 'genuine' in d and str(len(breaks)) in d.replace(',','')
    R("RCN-067", ok, f"describe={d[:300]}")

@block("RCN-068")
def _():
    c = Classifier(TOL)
    b1 = [c.classify('k1', D('1000'), D('-1000'))]  # SIGN, 1 config fault
    pop1 = Population(breaks=tuple(b1))
    d1 = pop1.describe()
    b2 = [c.classify('k1', D('1000'), D('-1000')), c.classify('k2', D('2000'), D('-2000'))]
    pop2 = Population(breaks=tuple(b2))
    d2 = pop2.describe()
    ok = '1 points at' in d1 and '2 point at' in d2
    R("RCN-068", not ok, f"1_fault: ...{d1[-120:]}; 2_faults: ...{d2[-120:]} (Expected grammatically correct '1 point at' / '2 point at', pluralisation appears inverted)")

@block("RCN-069")
def _():
    c = Classifier(TOL)
    breaks = [
        c.classify('t1', D('100'), D('105'), timing=True),
        c.classify('g1', D('100'), D('300')),
        c.classify('g2', D('100'), D('1000')),
    ]
    pop = Population(breaks=tuple(breaks))
    npl = pop.needs_a_person
    ok = all(b.kind!=BreakKind.TIMING for b in npl) and (len(npl)<2 or npl[0].magnitude>=npl[1].magnitude)
    R("RCN-069", ok, f"needs_a_person_kinds={[b.kind for b in npl]} magnitudes={[b.magnitude for b in npl]}")

@block("RCN-070")
def _():
    pop = Population(breaks=())
    d = pop.describe()
    ok = d=="the two sides agree"
    R("RCN-070", ok, f"{d!r}")

@block("RCN-071")
def _():
    c = Classifier(TOL)
    b = c.classify('k', D('1000'), None)
    ok = b.difference==D('-1000') and b.magnitude==D('1000')
    R("RCN-071", ok, f"difference={b.difference} magnitude={b.magnitude}")

@block("RCN-072")
def _():
    c = Classifier(TOL)
    b_missing = c.classify('k', D('1000'), None)
    b_extra = c.classify('k', None, D('1000'))
    d1 = b_missing.describe()
    d2 = b_extra.describe()
    ok = '1,000.00 on the left and nothing on the right' in d1 and 'nothing on the left and 1,000.00 on the right' in d2
    R("RCN-072", ok, f"missing_describe={d1[:80]!r} extra_describe={d2[:80]!r}")

print("=== RCN classify 045-072 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
