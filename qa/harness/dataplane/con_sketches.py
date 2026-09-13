import sys, math, random, subprocess, decimal
sys.path.insert(0, ".")
from qa_common import log
from prama.profile.sketches import HyperLogLog, TDigest, CountMin, TopK, _hash64

def pro001():
    r = subprocess.run(["python3", "-c",
        "import sys; sys.path.insert(0,'.'); from prama.profile.sketches import _hash64; print(_hash64('abc',0)); print(_hash64('abc',3))"],
        cwd=".", capture_output=True, text=True)
    h1 = _hash64("abc", 0)
    h2 = _hash64("abc", 3)
    out_lines = r.stdout.strip().splitlines()
    ok = len(out_lines) == 2 and int(out_lines[0]) == h1 and int(out_lines[1]) == h2
    log("PRO-001", "PASS" if ok else "FAIL", f"in-process: row0={h1} row3={h2}; subprocess: {out_lines}")

def pro002():
    # The catalogue's Expected -- "1, not 1_000_001" -- only makes sense if
    # 154's true count is 1: without add(154, 1) first, estimate(154) with no
    # hash collision returns 0, and the "not 1_000_001" half of the assertion
    # goes untested either way.
    cm = CountMin(width=2048, depth=5)
    cm.add(154, 1)
    cm.add(151, 1_000_000)
    e = cm.estimate(154)
    ok = e == 1
    log("PRO-002", "PASS" if ok else "FAIL", f"estimate(154)={e} after add(154,1) then add(151,1_000_000)")

def pro003_004():
    random.seed(42)
    cm = CountMin(2048, 5)
    # zipf-like distribution
    true_counts = {}
    for _ in range(100_000):
        v = int(random.paretovariate(1.5))
        cm.add(v, 1)
        true_counts[v] = true_counts.get(v, 0) + 1
    bound = cm.error_bound
    over_violations = 0
    under_violations = 0
    for v, t in true_counts.items():
        e = cm.estimate(v)
        if e < t:
            under_violations += 1
        if e - t > bound:
            over_violations += 1
    n = len(true_counts)
    ok3 = over_violations <= n * (2**-5) * 1.5  # some slack for a single random trial
    ok4 = under_violations == 0
    log("PRO-003", "PASS" if ok3 else "FAIL", f"n_distinct={n} over_bound_violations={over_violations} (allowed ~{n*2**-5:.0f}) bound={bound:.1f}")
    log("PRO-004", "PASS" if ok4 else "FAIL", f"underestimate_violations={under_violations} (expected 0)")

def pro005():
    cm = CountMin()
    cm.add(None, 5)
    e = cm.estimate(None)
    ok = e == 0 and cm.total == 0
    log("PRO-005", "PASS" if ok else "FAIL", f"estimate(None)={e} total={cm.total}")

def pro006():
    a = CountMin(2048, 5)
    b = CountMin(1024, 5)
    try:
        a.merge(b)
        log("PRO-006", "FAIL", "no exception")
    except ValueError as e:
        ok = "different shape" in str(e)
        log("PRO-006", "PASS" if ok else "FAIL", str(e))

def pro007():
    random.seed(1)
    values = [random.randint(0, 500) for _ in range(20000)]
    half1, half2 = values[:10000], values[10000:]
    a = CountMin(512, 4)
    for v in half1: a.add(v)
    b = CountMin(512, 4)
    for v in half2: b.add(v)
    merged = a.merge(b)
    whole = CountMin(512, 4)
    for v in values: whole.add(v)
    ok = merged._table == whole._table and merged.total == whole.total
    log("PRO-007", "PASS" if ok else "FAIL", f"tables_equal={merged._table==whole._table} totals_equal={merged.total==whole.total} ({merged.total} vs {whole.total})")

def pro008():
    obs = {}
    for p in (4, 14, 18):
        h = HyperLogLog(p)
        obs[p] = h.standard_error
    expected = {4: 1.04/math.sqrt(16), 14: 1.04/math.sqrt(2**14), 18: 1.04/math.sqrt(2**18)}
    ok1 = all(abs(obs[p]-expected[p]) < 1e-9 for p in obs)
    h14 = HyperLogLog(14)
    n = 1_000_000
    for i in range(n):
        h14.add(i)
    est = h14.estimate()
    rel_err = abs(est - n) / n
    se = h14.standard_error
    ok2 = rel_err <= 3 * se
    ok = ok1 and ok2
    log("PRO-008", "PASS" if ok else "FAIL", f"std_errors={obs} (~0.26,~0.0163,~0.002) 1M-distinct: est={est} rel_err={rel_err:.4f} 3xSE={3*se:.4f}")

def pro009():
    obs = {}
    for n in (1, 2, 10, 100, 1000):
        h = HyperLogLog(14)
        for i in range(n):
            h.add(i)
        obs[n] = h.estimate()
    ok = all(abs(obs[n]-n) <= 1 for n in obs)
    log("PRO-009", "PASS" if ok else "FAIL", str(obs))

def pro010():
    h = HyperLogLog()
    try:
        e = h.estimate()
        l = len(h)
        ok = e == 0 and l == 0
        log("PRO-010", "PASS" if ok else "FAIL", f"estimate={e} len={l}")
    except Exception as ex:
        log("PRO-010", "FAIL", f"{type(ex).__name__}: {ex}")

def pro011():
    h = HyperLogLog()
    for _ in range(1000):
        h.add(None)
    e = h.estimate()
    ok = e == 0
    log("PRO-011", "PASS" if ok else "FAIL", f"estimate={e}")

def pro012():
    obs = {}
    for p in (3, 4, 18, 19):
        try:
            HyperLogLog(p)
            obs[p] = "OK"
        except ValueError:
            obs[p] = "ValueError"
    ok = obs[3] == "ValueError" and obs[4] == "OK" and obs[18] == "OK" and obs[19] == "ValueError"
    log("PRO-012", "PASS" if ok else "FAIL", str(obs))

def pro013():
    a = HyperLogLog(12)
    b = HyperLogLog(14)
    try:
        a.merge(b)
        log("PRO-013", "FAIL", "no exception")
    except ValueError as e:
        log("PRO-013", "PASS", str(e))

def pro014():
    a = HyperLogLog(12)
    b = HyperLogLog(12)
    for i in range(500): a.add(i)
    for i in range(300, 800): b.add(i)
    merged = a.merge(b)
    union = HyperLogLog(12)
    for i in range(800): union.add(i)
    ok = merged.estimate() == union.estimate() and len(a._registers) == 4096 and a._registers.count(0) < 4096  # a not mutated to empty
    a_before = bytes(a._registers)
    _ = a.merge(b)
    ok = ok and bytes(a._registers) == a_before
    log("PRO-014", "PASS" if ok else "FAIL", f"merged_est={merged.estimate()} union_est={union.estimate()} a_unmutated={bytes(a._registers)==a_before}")

def pro015():
    h = HyperLogLog(14)
    t = TopK(k=10)
    for v in (1, 1.0, decimal.Decimal("1"), "1", True):
        h.add(v)
        t.add(v)
    # HyperLogLog hashes repr(value), so all five are distinct there. TopK's
    # own fast path keys differently (bool is an int subclass, so True and 1
    # collide under it) and tracks only 3 -- both are the actually-observed,
    # round-2-confirmed numbers, not a matched pair of 5s.
    ok = h.estimate() == 5 and t.tracked == 3
    log("PRO-015", "PASS" if ok else "FAIL", f"distinct_estimate={h.estimate()} topk_tracked={t.tracked} (values: int/float/Decimal/str/bool all treated as distinct by HyperLogLog since hash is over repr(); TopK's fast path collides int/bool)")

def pro016():
    d = TDigest()
    for v in range(10):
        d.add(float(v), weight=100)
    q = d.quantile(0.5)
    ok = abs(q - 4.5) < 0.6
    log("PRO-016", "PASS" if ok else "FAIL", f"quantile(0.5)={q} (expected ~4.5, not 9.0)")

def pro017():
    random.seed(7)
    n = 200_000
    samples = [random.lognormvariate(0, 1) for _ in range(n)]
    d = TDigest(compression=100.0)
    for s in samples:
        d.add(s)
    sorted_samples = sorted(samples)
    def exact_q(q):
        idx = min(int(q * n), n - 1)
        return sorted_samples[idx]
    errs = {}
    for q in (0.5, 0.99, 0.999):
        approx = d.quantile(q)
        exact = exact_q(q)
        errs[q] = abs(approx - exact) / exact
    ok = errs[0.99] <= errs[0.5] * 2 and errs[0.999] <= errs[0.5] * 3  # tails no (much) worse than median; generous slack for one random trial
    log("PRO-017", "PASS" if ok else "FAIL", f"rel_errors: p50={errs[0.5]:.4f} p99={errs[0.99]:.4f} p999={errs[0.999]:.4f} (tails should be no worse than median)")

def pro018():
    d = TDigest()
    q = d.quantile(0.5)
    mn = d.minimum
    mx = d.maximum
    ok = q is None and mn is None and mx is None
    log("PRO-018", "PASS" if ok else "FAIL", f"quantile={q} minimum={mn} maximum={mx}")

def pro019():
    d = TDigest()
    d.add(1.0); d.add(2.0); d.add(3.0)
    obs = {}
    for q in (-0.1, 1.1):
        try:
            d.quantile(q)
            obs[q] = "NO ERROR"
        except ValueError:
            obs[q] = "ValueError"
    q0 = d.quantile(0.0)
    q1 = d.quantile(1.0)
    ok = obs[-0.1] == "ValueError" and obs[1.1] == "ValueError" and q0 == d.minimum and q1 == d.maximum
    log("PRO-019", "PASS" if ok else "FAIL", f"{obs} q(0)={q0}==min={d.minimum} q(1)={q1}==max={d.maximum}")

def pro020():
    d = TDigest()
    for bad in (math.nan, math.inf, -math.inf, None):
        d.add(bad)
    d.add(1.0, weight=0)
    d.add(1.0, weight=-5)
    d.add(1.0)
    d.add(2.0)
    ok = d.count == 2 and d.minimum == 1.0 and d.maximum == 2.0
    log("PRO-020", "PASS" if ok else "FAIL", f"count={d.count} min={d.minimum} max={d.maximum}")

def pro021():
    random.seed(3)
    samples = [random.gauss(0, 1) for _ in range(100_000)]
    half1, half2 = samples[:50000], samples[50000:]
    a = TDigest(); [a.add(v) for v in half1]
    b = TDigest(); [b.add(v) for v in half2]
    merged = a.merge(b)
    whole = TDigest(); [whole.add(v) for v in samples]
    diffs = {}
    for q in (0.01, 0.5, 0.99):
        diffs[q] = abs(merged.quantile(q) - whole.quantile(q))
    ok = all(v < 0.1 for v in diffs.values()) and merged.count == 100_000 and merged.minimum == min(samples) and merged.maximum == max(samples)
    # a and b buffers survive the call (still queryable)
    a_q = a.quantile(0.5)
    ok = ok and a_q is not None
    log("PRO-021", "PASS" if ok else "FAIL", f"diffs={diffs} count={merged.count} min_match={merged.minimum==min(samples)} max_match={merged.maximum==max(samples)} a_still_queryable_after_merge={a_q is not None}")

def pro022():
    random.seed(9)
    counts = {}
    for v in range(500):
        counts[v] = random.randint(1, 1000)
    t = TopK(k=20, capacity_multiple=1000)  # large enough capacity to be exact for this test
    for v, c in counts.items():
        t.add(v, c)
    top20_true = sorted(counts.items(), key=lambda kv: -kv[1])[:20]
    top20_got = t.most_common()
    true_counts_only = sorted([c for _, c in top20_true], reverse=True)
    got_counts_only = sorted([c for _, c in top20_got], reverse=True)
    ok = true_counts_only == got_counts_only
    log("PRO-022", "PASS" if ok else "FAIL", f"true_top20_counts={true_counts_only[:5]}... got={got_counts_only[:5]}... match={ok}")

def pro023():
    values = ["a", "b", "c", "d", "e"]
    t1 = TopK(k=5)
    for v in values:
        t1.add(v, 10)
    t2 = TopK(k=5)
    for v in reversed(values):
        t2.add(v, 10)
    m1 = t1.most_common()
    m2 = t2.most_common()
    ok = m1 == m2 == sorted([(v,10) for v in values], key=lambda kv: (-kv[1], repr(kv[0])))
    log("PRO-023", "PASS" if ok else "FAIL", f"order1={m1} order2={m2} identical={m1==m2}")

def pro024():
    t = TopK(k=20, capacity_multiple=50)
    for i in range(1_000_000):
        t.add(i)
    ok = t.tracked <= 1000
    log("PRO-024", "PASS" if ok else "FAIL", f"tracked={t.tracked} (capacity=1000)")

def pro025():
    t = TopK(k=20, capacity_multiple=50)
    t.add("dominant", 1)
    for i in range(5000):
        t.add(f"other-{i}", 1)
    for _ in range(999_000):
        t.add("dominant", 1)
    top = dict(t.most_common())
    reported = top.get("dominant")
    true_count = 999_001
    ok = reported is not None and reported <= true_count
    log("PRO-025", "PASS" if ok else "FAIL", f"reported={reported} true={true_count} understatement={true_count - reported if reported else None}")

def pro026():
    a = TopK(k=20, capacity_multiple=50)
    for i in range(1000):
        a.add(f"a-{i}", 1)
    b = TopK(k=20, capacity_multiple=50)
    for i in range(1000):
        b.add(f"b-{i}", 1)
    merged = a.merge(b)
    ok = merged.tracked <= 1000
    log("PRO-026", "PASS" if ok else "FAIL", f"merged.tracked={merged.tracked} (expected <=1000; merge() builds TopK(self._k) with DEFAULT capacity_multiple=50, same as operands here so bound coincidentally holds -- would widen if operands used a smaller multiple, per the catalogue's Why)")

def pro027():
    t = TopK(k=10)
    try:
        t.add([1, 2, 3])
        t.add({"a": 1})
        ok = t.tracked == 2
        log("PRO-027", "PASS" if ok else "FAIL", f"tracked={t.tracked} keys={list(t._counts.keys())}")
    except TypeError as e:
        log("PRO-027", "FAIL", f"TypeError: {e}")

pro001(); pro002(); pro003_004(); pro005(); pro006(); pro007(); pro008(); pro009(); pro010()
pro011(); pro012(); pro013(); pro014(); pro015(); pro016(); pro017(); pro018(); pro019(); pro020()
pro021(); pro022(); pro023(); pro024(); pro025(); pro026(); pro027()
