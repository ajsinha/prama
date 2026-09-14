# Platform Ops — QA execution log, round 4

`prama.monitor.drift` · `prama.monitor.detectors` · `prama.monitor.seasonality` · `prama.monitor.cards` ·
`prama.monitor.tournament` · `prama.monitor.coldstart` · `prama.incident.correlate` · `prama.alert.route` ·
`prama.report.rdarr` · `prama.report.attest` · `prama.report.charts` · `prama.report.contrast` ·
`prama.report.themes` · `prama.report.palette` · `prama.report.rate` · `prama.bench.corpus` ·
`prama.bench.baselines` · `prama.bench.scoring` · `prama.bench.shadow` · `deploy/helm/prama` ·
`deploy/Dockerfile` · `scripts/gate.sh` · `scripts/check_file_length.py` · `scripts/generate_docs.py` ·
`scripts/verify_evidence.py` · `run_prama_web.py` · `prama.telemetry.trace` · `prama.telemetry.lineage` ·
`prama.core.ids` · `prama.cli.base` · `prama.cli.main` · `.github/workflows/gate.yml`.

**Re-run of round 3** (`qa/logs-round3/platform-ops.md`: 425 PASS / 16 FAIL / 2 BLOCKED, 95.9%) against the tree after batches **A-D** (`bbe48af`..`a23f385`), a small, specifically-scoped delta: `core/ids.py` (ULID minting now reads the clock inside its lock), `cli/base.py`/`cli/main.py` (pack installation moved from `main()` into `Application.run`), typed refusals in `bench/corpus.py`, `cli/pack.py`, `cli/control.py`, `cli/contract.py`, `cli/bench.py`, `core/log.py` (Batch B), and — the case this round exists to re-verify — `incident/correlate.py::_shared_ancestor`'s tiebreak, changed from `(vote count, len(key))` to `(vote count, depth from the lineage graph)` (Batch D, closing `Q-65`'s equal-vote half).

All 443 cases in `MON-001..140`, `INC-001..073`, `RPT-001..095`, `BCH-001..061` and `OPS-001..074` were executed against the live codebase. The 369 `MON-`/`INC-`/`RPT-`/`BCH-` cases are real Python objects driven directly with fixed seeds via round 3's saved harness scripts in `qa/harness/platform-ops/` (`mon_001_030.py` through `bch_001_061.py`), re-run against the current tree. One correction was required and is documented below (`bch_001_061.py`, `BCH-015`/`BCH-016`); every other script needed none. The 74 `OPS-` cases have no saved script (round 2's method, continued in round 3) — each was independently re-executed by hand: a real `helm` v3.16.3 binary on `PATH`, a real Docker image rebuilt from the current `deploy/Dockerfile` (`prama:qa-r4`) and run as a real container, `scripts/gate.sh`'s individual mechanisms reproduced directly, `run_prama_web.py` run as a real subprocess against a fresh scratch copy of the repository and the live PostgreSQL 16 container at `127.0.0.1:55432`, real POSIX signals sent to a real running server, a real evidence bundle verified by `scripts/verify_evidence.py -I` in a Prama-uninstalled interpreter, the real git history scanned with `git log --all --grep` and `git fsck --unreachable`, and the product's own new regression test (`qa/regression-suite/platform/test_incident_ancestor_depth.py`) and split chart test (`tests/deploy/test_helm_chart.py`) run directly. No `src/`, `tests/`, `schema/`, `config/`, `qa/catalogue/` or `qa/regression-suite/` file was modified.

## `INC-010` — the case this round exists to re-verify

**The fix is real, and it is narrower than `INC-010`'s own catalogue case.** `_shared_ancestor`'s tiebreak changed from `(vote count, len(key))` to `(vote count, self._depth(key))`, where `_depth` asks the real lineage graph how many sources a candidate column has (`len(self._graph.sources_of(...))`) — genuine depth, not a name-length proxy for it.

**Verified on the shape that actually distinguishes the two rankings.** A scenario where the deeper column also happens to have the longer name proves nothing (both rankings agree there — this is exactly the mistake round 4's own first attempt made and had to redo). Built instead a graph where a long-named shallow column feeds a short-named deep one, with the vote count genuinely **tied** between the two candidates (three findings all downstream of the same derived column, so every "other" finding that shares the raw feed also shares the derived column — count 2 each):
```
LONG_SHALLOW = Column('raw', 'a_very_long_staging_ingestion_feed_name')   # depth 0, 43 chars
SHORT_DEEP   = Column('mid', 'b')                                        # depth 1, 5 chars
edges: LONG_SHALLOW -> SHORT_DEEP -> {ds0.x, ds1.y, ds2.z}
findings: f0=ds0.x, f1=ds1.y, f2=ds2.z

counts = {'raw.a_very_long_staging_ingestion_feed_name': 2, 'mid.b': 2}   # a genuine tie
old tiebreak (len(key))          would choose: raw.a_very_long_staging_ingestion_feed_name
new tiebreak (graph depth)       chooses:       mid.b
Correlator(graph).correlate(...).incidents[0].common_ancestor == mid.b   # CONFIRMED
```
This is exactly the shape the product's own new regression test uses (`qa/regression-suite/platform/test_incident_ancestor_depth.py`, `test_the_nearest_shared_column_wins_even_when_the_raw_feed_has_a_longer_name` and `test_depth_comes_from_the_graph_and_not_from_the_name`), independently constructed before reading it and confirmed to match; both tests pass (`pytest qa/regression-suite/platform/test_incident_ancestor_depth.py` — 2 passed). **The equal-vote tiebreak fix is real and directly confirmed.**

**`INC-010`'s own catalogue case is unchanged: still `FAIL`.** Its precondition ("a chain where everything shares a raw feed but two findings share a nearer derived column") is round 3's own reproduction — `raw.feed` -> `mid.derived` -> `{ds1.a, ds2.b}`, plus `raw.feed` -> `ds3.c` directly. There, the vote counts genuinely **differ** (`raw.feed`=2 votes from f2 and f3; `mid.derived`=1 vote from f2 alone) — no tie, so the tiebreak this round fixed is not what decides it. Re-run byte-for-byte against the current tree: still one incident, still named `raw.feed`. This is `Q-65`'s still-open question — *"which wins when the vote counts genuinely differ, broadest or deepest"* — named explicitly, and left open, in the new regression test's own docstring ("What this test does not settle"). **Not a new defect and not newly discovered — it is the identical, previously-logged gap, and this round's fix does not touch it.**

## Regressions — a case that passed in round 3 and fails now

**2 found: `BCH-015`, `BCH-016`.**

Both are the same defect, on the two boundary values `BCH-015`/`BCH-016` probe: Batch B (`53b9043`, "the fourteen commands that answered a person with a stack trace") retyped `bench/corpus.py`'s `rate`/`rows` refusals from a bare `ValueError` to `prama.core.errors.ValidationError` — deliberately, as part of routing every CLI-reachable refusal through the typed error taxonomy instead of a traceback. `ValidationError` is a `PramaError`, **not** a `ValueError` subclass. Both catalogue cases' literal `Expected` is the specific type `ValueError` (`BCH-015`: "`ValueError` naming the value"; `BCH-016`: `"ValueError"`). The refusal messages are byte-identical to round 3 (`git show 53b9043` confirms the commit message's own claim — "only the type changed") and still name the offending value, but the exception type genuinely changed, so the literal catalogue `Expected` no longer holds.

**Attribution:** commit `53b9043` (Batch B), `src/prama/bench/corpus.py`. **Judgement: same shape as round 3's own `OPS-003`** — a deliberate, documented, correct improvement (a data owner gets a named taxonomy code and remedy instead of a raw `ValueError`) whose side effect is that two catalogue cases' literal precondition text is now stale. Recorded `FAIL` against the literal, unchanged catalogue `Expected`, because the rule requires that and fabricating a passing precondition would be worse — but this is not a new gap in the product, it is the catalogue text that needs `ValidationError` written into its `Expected` now that the taxonomy migration has reached `bench/corpus.py` too. The harness script `qa/harness/platform-ops/bch_001_061.py` was corrected (broadened its `except ValueError` to also catch `ValidationError`, so the run does not crash before reaching `BCH-017`..`BCH-061`) with the correction documented inline and the verdict still checked against the literal `ValueError` type, not silently passed.

## Fixes confirmed by direct execution

**None.** Every one of round 3's 16 FAILs and 2 BLOCKEDs reproduces identically this round (including `INC-010` — see the dedicated section above). Batches A-D's four in-scope fixes (`Q-70` ULID monotonicity, `Q-67`/`Q-66` scope grants, the fourteen typed CLI refusals, `Q-63` plugin-install ordering, and `Q-65`'s equal-vote tiebreak half) either address code this catalogue's `MON-`/`INC-`/`RPT-`/`BCH-`/`OPS-` cases do not exercise (the scope/role and language-route fixes are `SEC-`/`CFG-`/interface-area concerns), or — for `Q-65` — address only the tied-vote half of `INC-010`, which round 3's own reproduction does not exercise (see above).

## Counts

| | Count |
|---|---:|
| Total cases | 443 |
| PASS | 423 |
| FAIL | 18 |
| BLOCKED | 2 |
| **Pass rate** | **95.5%** (423/443) |

Round 3: 425 PASS / 16 FAIL / 2 BLOCKED — 95.9%. Round 4: 423 PASS / 18 FAIL / 2 BLOCKED — 95.5%.
**0 of round 3's failures fixed, 2 regressions (`BCH-015`, `BCH-016`), round 3's 16 FAILs all still fail
unchanged, both round 3 BLOCKEDs unchanged (16 + 2 = 18 FAIL this round).**

## Blocked

- **`OPS-011`** — no live Kubernetes cluster is available in this environment (`kubectl` is not even on `PATH`) to observe real pod readiness/liveness behaviour under a database outage; only the probe configuration (`OPS-009`) was reviewed. Unchanged from round 2 and round 3.
- **`OPS-055`** — staging a genuinely interrupted control run (a `SIGKILL` landing mid-execution) needs a control actually in flight at the moment of the kill; `run_prama_web.py` and the recovery mechanisms it exercises (`db/lease_provider.py`, `db/dao/evidence.py`) carry zero commits in batches A-D, so the identical blocker applies unchanged.

## Per-case results (id order, 443 rows)

| Id | Result | Observed |
|---|---|---|
| `MON-001` | PASS | measures=() refusal='no drift measure is reported below 50 observations a side (49 against 50); PSI in particular will report a shift between two draws from the same distribution' |
| `MON-002` | PASS | n_measures=5 refusal='' |
| `MON-003` | PASS | is_material=False material=('chi_square',) |
| `MON-004` | PASS | is_material=True material=('psi', 'ks', 'wasserstein', 'jensen_shannon', 'chi_square') |
| `MON-005` | PASS | material_count=2 is_material=False |
| `MON-006` | PASS | disagreement='m0, m1, m2 see a shift and m3, m4 do not, which usually means the change is in a part of the distribution only some of them look at' |
| `MON-007` | PASS | d1='' d2='' |
| `MON-008` | PASS | psi_value=26.244726754808656 |
| `MON-009` | PASS | psi_value=0.0 material=False |
| `MON-010` | PASS | at0.2=True at0.19999=False |
| `MON-011` | PASS | DEFAULT_BINS=10 edges=9 buckets=10 |
| `MON-012` | PASS | ks_same=0.0 ks_dis=1.0 crit_small=0.272 crit_large=0.027 |
| `MON-013` | PASS | wasserstein=4101.053131569189 explanation='the distribution moved by about 4,101.1 in its own units' |
| `MON-014` | FAIL | 1sd_material=True val=49.355734768613345 scale~49.355734768612734 2sd_material=True val=98.7114695372244 |
| `MON-015` | PASS | js=0.8325546111576977 |
| `MON-016` | PASS | m1=0.5185426920543056 m2=0.5185426920543056 |
| `MON-017` | PASS | small=1.6666666666666659,False large=166.6666666666666,True |
| `MON-018` | FAIL | normalised=1.6474271474295212 (expect near 1.96) |
| `MON-019` | PASS | allfinite=True to_dict_ok=True |
| `MON-020` | PASS | refusal='no drift measure is reported below 50 observations a side (0 against 60); PSI in particular will report a shift between two draws from the same distribution' |
| `MON-021` | PASS | cp=None |
| `MON-022` | PASS | cp=Changepoint(index=100, before=1000.5103451552541, after=1600.0942958803917, strength=1.9949448548001576) |
| `MON-023` | PASS | cp.strength=0.45924092997952226 |
| `MON-024` | PASS | ratio=inf desc='the level rose from about 0 to 5 at observation 10, a inf% change' dict_ratio=None |
| `MON-025` | PASS | errs=['accepting a new normal requires a reason. Without one the record cannot distinguish a business change from somebody silencing an alert, which is the only question anybody asks about it later', 'accepting a new normal requires a reason. Without one the record cannot distinguish a business change from somebody silencing an alert, which is the only question anybody asks about it later'] |
| `MON-026` | PASS | annotation='2026-01-01: new normal accepted by alice (1,000 → 1,400) — Q1 seasonal reset' |
| `MON-027` | PASS | len=80 start=120 |
| `MON-028` | PASS | len=200 equal=True |
| `MON-029` | PASS | len=100 |
| `MON-030` | PASS | len=1 h=[99] |
| `MON-031` | PASS | {'robust_deviation': None, 'quantile_distance': None, 'local_outlier_factor': None, 'forecast_residual': None, 'shape_distance': None} |
| `MON-032` | PASS | rd10=True rd9=True lof6=True lof5=True fr8=True fr7=True sd12=True sd11=True |
| `MON-033` | PASS | score_full=0.008576720536219093 score_manual=0.008576720536219093 n_cal=300 |
| `MON-034` | PASS | mean_loo=0.9630 mean_full=0.8947 |
| `MON-035` | PASS | without_outlier=5.4660 with_outlier=5.3256 |
| `MON-036` | PASS | score=6.7449075947659525 expected=6.7449075947659525 |
| `MON-037` | PASS | with_factor_order=[1000, 1100, 900, 1300, 700, 1500] without_factor_order=[1000, 1100, 900, 1300, 700, 1500] |
| `MON-038` | PASS | low=1.000 high=1.000 mid=0.000 |
| `MON-039` | PASS | null_rate=QuantileDistance distribution=QuantileDistance |
| `MON-040` | PASS | 10000=1136.464 19500=3.433 |
| `MON-041` | PASS | score=Score(value=0.29500000000000004, detector='local_outlier_factor', explanation='the neighbourhood around 10 is 0.3 times sparser than the neighbourhoods of its nearest comparable days', expected=None, observed=10.0) |
| `MON-042` | PASS | score=30.0 explanation_excerpt=100,000,000,000,000,001,097,906,362,944,045,541,740,492,309, |
| `MON-043` | PASS | fr_score=1.000 fr_percentile=0.12 rd_score=1.950 rd_percentile=1.00 |
| `MON-044` | PASS | first_third_mean=15.2203 last_third_mean=3.2399 |
| `MON-045` | PASS | _relative(5,0)=5.0 |
| `MON-046` | PASS | smooth=0.642 spiky=5.541 |
| `MON-047` | PASS | score=0.0 |
| `MON-048` | PASS | standardise=[0.0, 0.0, 0.0] score=0.0 |
| `MON-049` | PASS | ensemble_detectors=['robust_deviation', 'quantile_distance', 'local_outlier_factor', 'forecast_residual'] module_docstring_claims_five=True |
| `MON-050` | PASS | scored=['robust_deviation', 'quantile_distance', 'forecast_residual'] |
| `MON-051` | PASS | Ensemble public methods: ['calibration_for', 'describe', 'detectors', 'score_all'] -- score_all returns per-detector dict, calibration_for returns one detector's list, neither combines |
| `MON-052` | PASS | result=[] |
| `MON-053` | PASS | good_at=['a level that has shifted, on a series without trend', 'bounded or skewed quantities, like a null rate', 'multi-modal series, where the middle is empty', 'series with trend or momentum', 'a changed profile with an unchanged total'] blind_to=['a series with trend or autocorrelation, where yesterday predicts today and the middle of the window predicts nothing', 'a point inside the observed range that is nonetheless in the wrong place — between two clusters, say', 'gradual drift, which moves every point together', 'a change that arrives gradually enough for the forecast to follow it, which is exactly what a slow leak looks like', 'a level change that preserves the shape'] |
| `MON-054` | PASS | outside_01_seen=True |
| `MON-055` | PASS | {'robust_deviation': '1,300 against a typical 998, which is 6.9 robust deviations away', 'quantile_distance': '1,300 sits at the 100% point of what has been seen before', 'local_outlier_factor': 'the neighbourhood around 1,300 is 13.9 times sparser than the neighbourhoods of its nearest comparable days', 'forecast_residual': 'the recent trend implied about 1,006 and 1,300 arrived, which is 8.5 typical residuals away', 'shape_distance': 'the most recent 6 observations form a pattern whose closest match in the history is 1.36 away'} |
| `MON-056` | PASS | month_end_sunday=2020-05-31 friday=2020-05-29 pe_friday=month pe_sunday=none |
| `MON-057` | PASS | dec31=year mar31=quarter apr30=month |
| `MON-058` | PASS | sat_end=2020-02-29 pe=none |
| `MON-059` | PASS | facet_names=['business_day', 'period_end', 'day_of_week', 'hour', 'declared:payroll', 'declared:rebalance'] |
| `MON-060` | PASS | ka=(('business_day', 'True'), ('period_end', 'none'), ('day_of_week', '3'), ('declared:aaa', 'False'), ('declared:zzz', 'False')) kb=(('business_day', 'True'), ('period_end', 'none'), ('day_of_week', '3'), ('declared:aaa', 'False'), ('declared:zzz', 'False')) |
| `MON-061` | PASS | group_size=24 key=business_day=True, period_end=any relaxed=['day_of_week'] |
| `MON-062` | PASS | relaxed=['day_of_week'] period_end_key=any |
| `MON-063` | PASS | order=['hour', 'day_of_week', 'period_end', 'business_day'] |
| `MON-064` | FAIL | final_key=() declared_survives_in_key=False relaxed=['hour', 'day_of_week', 'period_end', 'business_day'] declared_in_relaxed=False (expected the driver to survive the fallback; it does not, and its loss is not reported in `relaxed` either) |
| `MON-065` | PASS | g19_size=19 g19_relaxed=['day_of_week', 'period_end', 'business_day'] g20_size=20 g20_relaxed=[] |
| `MON-066` | PASS | size=25 relaxed=['hour', 'day_of_week', 'period_end', 'business_day'] describe='compared against 25 observations where every observation, which is enough for a p-value no finer than 0.038. hour, day_of_week, period_end, business_day had to be ignored to find enough comparable days — this monitor is less specific today than it would be with more history' |
| `MON-067` | PASS | resolution=0.04 describe='compared against 24 observations where every observation, which is enough for a p-value no finer than 0.040' |
| `MON-068` | PASS | resolution=1.0 |
| `MON-069` | PASS | describe='compared against 15 observations where business_day=True, which is enough for a p-value no finer than 0.062. hour, day_of_week had to be ignored to find enough comparable days — this monitor is less specific today than it would be with more history' |
| `MON-070` | PASS | results=[True, True, True, False] |
| `MON-071` | PASS | count=12 days=[datetime.date(2026, 1, 30), datetime.date(2026, 2, 27), datetime.date(2026, 3, 31), datetime.date(2026, 4, 30), datetime.date(2026, 5, 29), datetime.date(2026, 6, 30), datetime.date(2026, 7, 31), datetime.date(2026, 8, 31), datetime.date(2026, 9, 30), datetime.date(2026, 10, 30), datetime.date(2026, 11, 30), datetime.date(2026, 12, 31)] |
| `MON-072` | PASS | count=12 days=[datetime.date(2026, 1, 16), datetime.date(2026, 2, 20), datetime.date(2026, 3, 20), datetime.date(2026, 4, 17), datetime.date(2026, 5, 15), datetime.date(2026, 6, 19), datetime.date(2026, 7, 17), datetime.date(2026, 8, 21), datetime.date(2026, 9, 18), datetime.date(2026, 10, 16), datetime.date(2026, 11, 20), datetime.date(2026, 12, 18)] |
| `MON-073` | PASS | count=7 feb_count=0 |
| `MON-074` | PASS | type=<class 'bool'> value=True |
| `MON-075` | PASS | alerted=False reason=no history for this metric yet |
| `MON-076` | PASS | v1=False,Uncalibrated(reason='no history for this metric yet', n=0) v2=False,Uncalibrated(reason='3 comparable observations is too few for robust_deviation to compute a score', n=0) v3=False,Uncalibrated(reason='15 calibration points is below the minimum of 20; the coarsest p-value available would be 0.062, which cannot honour any useful budget', n=0) |
| `MON-077` | PASS | clean_size=58 polluted_size=58 |
| `MON-078` | PASS | group_size=59 (expect 59, i.e. index0..58) |
| `MON-079` | PASS | explain='ds5.metric5 — 1,200 against a typical 1,000, which is 8.5 robust deviations away (compared against 58 observations where business_day=True, period_end=none. day_of_week had to be ignored to find enough comparable days — this monitor is less specific today than it would be with more history) p ≤ 0.0169 — more extreme than every one of the 58 comparable observations, so this is the smallest value this much history can express ⚠ not yet calibrated — this monitor has seen too little history to promise a false-alarm rate, so 1.0% is an intention rather than a measurement' |
| `MON-080` | PASS | found=True explain='ds6.metric6 — 6,000 against a typical 1,000, which is 765.2 robust deviations away (compared against 40 observations where business_day=True, period_end=none, day_of_week=6) p ≤ 0.0244 — more extreme than every one of the 40 comparable observations, so this is the smallest value this much history can express ⚠ not yet calibrated — this monitor has seen too little history to promise a false-alarm rate, so 1.0% is an intention rather than a measurement' |
| `MON-081` | PASS | explain='ds7.metric7 could not be judged: no history for this metric yet' |
| `MON-082` | PASS | hypothesis=None |
| `MON-083` | PASS | hX=ds8.metric8[X] hY=ds8.metric8[Y] |
| `MON-084` | PASS | last_level=0.007099999999999996 configured_alpha=0.01 |
| `MON-085` | PASS | half_life=None |
| `MON-086` | PASS | bounded=['null_rate', 'distribution'] |
| `MON-087` | PASS | detector=ForecastResidual |
| `MON-088` | PASS | detector_is_custom=True |
| `MON-089` | PASS | alerting=2 unjudgeable=1 degraded=1 |
| `MON-090` | PASS | describe='0 monitors ran; 0 exceeded their level before selection, 0 could not be judged, 0 are no longer calibrated' |
| `MON-091` | PASS | alerting_segments=['C'] |
| `MON-092` | FAIL | verdicts_count=0 (unknown segment silently dropped, no record/unjudgeable entry produced) |
| `MON-093` | PASS | n_hyps=40 parents={'ds93.metric93'} |
| `MON-094` | PASS | verdicts=[('low', None), ('high', None)] |
| `MON-095` | PASS | low=0.0 high=0.0 source=PriorSource.DECLARATION explanation='acct_id was declared mandatory, so any missing value at all is a departure from what was declared' |
| `MON-096` | PASS | {'isin': (0.0, 0.02, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'lei': (0.0, 0.05, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'cusip': (0.0, 0.02, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'sedol': (0.0, 0.05, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'iban': (0.0, 0.02, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'iso4217': (0.0, 0.001, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'iso3166': (0.0, 0.02, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'uuid': (0.0, 0.0, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'iso_date': (0.0, 0.01, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>)} |
| `MON-097` | PASS | admits(0.0)=True admits(0.001)=False |
| `MON-098` | PASS | source=PriorSource.DECLARATION |
| `MON-099` | PASS | two_source=PriorSource.DEFAULT three_source=PriorSource.SIBLINGS |
| `MON-100` | PASS | low=0.2 high=1.0 |
| `MON-101` | PASS | source=PriorSource.DEFAULT explanation='nothing is known about this attribute yet, so the estate default applies — this is the weakest kind of expectation and is here only because the alternative is no monitoring at all' |
| `MON-102` | PASS | is_calibrated=False |
| `MON-103` | PASS | disclosure='this is a prior, not a measurement: nothing is known about this attribute yet, so the estate default applies — this is the weakest kind of expectation and is here only because the alternative is no monitoring at all. No false-alarm rate is promised until this monitor has its own history' |
| `MON-104` | PASS | p104a=None p104b=None |
| `MON-105` | FAIL | low=1000.0 high=inf explanation='the declared rhythm says a daily delivery carries between 1,000 and inf records' |
| `MON-106` | PASS | n=4 first_kind=MetricKind.VOLUME |
| `MON-107` | PASS | describe='row_count now has 45 of its own observations and is calibrated against them. Until now it was judged against a prior: nothing is known about this attribute yet, so the estate default applies — this is the weakest kind of expectation and is here only because the alternative is no monitoring at all' |
| `MON-108` | PASS | c1.detector=robust_deviation c2.detector=quantile_distance |
| `MON-109` | PASS | blind_to_present=True |
| `MON-110` | PASS | expressible=False rendered_excerpt=['**The promise cannot currently be kept.** This much history can express no p-value finer than 0.0400, and the declared budget needs 0.0100.'] |
| `MON-111` | PASS | alpha=0.04 resolution=0.04 expressible=True |
| `MON-112` | PASS | precision=1.0 reviewed=29 describe='34 alerts raised, 29 of the 29 reviewed were confirmed (100%); 5 still unreviewed' |
| `MON-113` | PASS | precision=None describe='10 alerts raised, none of them reviewed yet' |
| `MON-114` | FAIL | raised=5 confirmed=7 reviewed=5 unreviewed=0 (confirmed<=reviewed=False) |
| `MON-115` | PASS | has_version_line=True |
| `MON-116` | PASS | comparison_group=nothing yet resolution=1.0 expressible=False |
| `MON-117` | PASS | j199=Decision.HOLD reason='199 shadow observations of 200; below that the comparison is between two samples of noise' j200=Decision.PROMOTE reason='precision 83% to 89% with nothing lost that the champion caught' |
| `MON-118` | PASS | decision=Decision.HOLD reason='no alert from the challenger has been reviewed, so there is nothing to compare its precision against' |
| `MON-119` | PASS | decision=Decision.REFER reason='the challenger missed 1 incident(s) the champion caught. It may still be the better monitor, and that is a judgement about which failures matter rather than an average somebody can compute' |
| `MON-120` | PASS | j120=Decision.PROMOTE imp=0.06; j749=Decision.HOLD imp~0.0749; j751=Decision.PROMOTE imp~0.0751 |
| `MON-121` | PASS | decision=Decision.HOLD reason='the difference (+3%) is inside the margin that would make it an improvement rather than luck; promoting on this would mean promoting whichever challenger was luckiest' |
| `MON-122` | PASS | decision=Decision.RETIRE reason='the challenger is materially worse (60% against 80%)' |
| `MON-123` | PASS | decision=Decision.PROMOTE reason='the champion has no reviewed alerts to defend and the challenger is running at 80% precision' (catalogue's 'nothing to defend' is a paraphrase; code says 'no reviewed alerts to defend' -- same meaning) |
| `MON-124` | PASS | rb19='' rb20='p is running at 50% precision against the 90% the monitor it replaced was achieving. Rolling back; the promotion was decided on 20 reviewed alerts and production disagrees' |
| `MON-125` | PASS | rb_09='' rb_11='p is running at 79% precision against the 90% the monitor it replaced was achieving. Rolling back; the promotion was decided on 100 reviewed alerts and production disagrees' |
| `MON-126` | PASS | reviewed=2 confirmed=1 |
| `MON-127` | PASS | alert_rate=0.0 |
| `MON-128` | PASS | stat_ok=True seasonal_ok=True level_ok=True switch_ok=True bursty_ok=True |
| `MON-129` | PASS | identical=True |
| `MON-130` | PASS | n_cells=25 all_5_levels=True |
| `MON-131` | PASS | error=0.01 |
| `MON-132` | PASS | is_liberal=True describe='! r              m         error 0.0300  (fires more often than promised)' |
| `MON-133` | PASS | error=1.0 meets_target=False |
| `MON-134` | PASS | every_regime_has_mechanism=True best_errors={'stationary': 0.0013333333333333363, 'seasonal': 0.012000000000000004, 'level_shift': 0.003111111111111112, 'regime_switch': 0.006222222222222224, 'bursty': 0.0031111111111111144} |
| `MON-135` | FAIL | changepoint_error=0.04977777777777777 weighted_error=0.013777777777777772 |
| `MON-136` | PASS | seasonal=0.02577777777777778 weighted=0.06666666666666668 plain=0.064 |
| `MON-137` | PASS | adaptive=0.006222222222222224 weighted=0.013777777777777781 |
| `MON-138` | PASS | len_result=110 len_orig=110 unchanged=True |
| `MON-139` | PASS | unchanged=True |
| `MON-140` | PASS | confirmed by source read: _stationary/_seasonal/_level_shift/_regime_switch/_bursty draw only from the regime's own distribution, no injected anomaly |
| `INC-001` | PASS | n_incidents=1 n_findings=400 ancestor=staging.x |
| `INC-002` | PASS | reduction=0.9975 describe='400 findings became 1 incident (100% fewer things to look at)' |
| `INC-003` | PASS | incidents=() reduction=0.0 |
| `INC-004` | PASS | confidence=1.0 |
| `INC-005` | PASS | confidence=0.8300000000000001 expected=0.83 |
| `INC-006` | PASS | is_speculative=True describe='2 findings across 2 datasets, one incident. Grouped on timing alone, which is usually right and occasionally merges two unrelated problems' |
| `INC-007` | PASS | is_speculative=False |
| `INC-008` | PASS | n_incidents=3 datasets=[('d1',), ('d2',), ('d3',)] |
| `INC-009` | PASS | n_incidents=2 identities={'nocol1', 'nocol2', 'withcol'} |
| `INC-010` | FAIL | n_incidents=1 ancestors=[Column(dataset='raw', name='feed')] -- catalogue's own vote-count-differs shape (f1,f2 share mid.derived=1 vote; f3 shares raw.feed alone, so raw.feed=2 votes vs mid.derived=1) still merges into ONE incident naming raw.feed. UNCHANGED from round 3, not fixed by this round's Q-65 tiebreak repair -- see the INC-010 write-up below for the separate, positive verification that the tiebreak itself (equal-vote case) is now correctly depth-based, not length-based. |
| `INC-011` | PASS | n_incidents=2 |
| `INC-012` | PASS | n_incidents=1 ancestor=raw.* |
| `INC-013` | PASS | n_incidents=1 incidents=[(Column(dataset='raw', name='*'), ['f_amt', 'f_other'])] |
| `INC-014` | PASS | n_incidents=2 |
| `INC-015` | PASS | n_incidents=1 sizes=[2] |
| `INC-016` | PASS | n59=1 n61=2 |
| `INC-017` | PASS | change=Change(identity='dep1', at=datetime.datetime(2024, 1, 1, 6, 0), what='deploy', by='alice', touched=('d1.c',)) signals=['change'] |
| `INC-018` | PASS | change=None |
| `INC-019` | PASS | 11h_attached=True 13h_attached=False |
| `INC-020` | PASS | attached_change=c1 |
| `INC-021` | PASS | change=None |
| `INC-022` | PASS | order_a=['incident:gd1_0:g1_0', 'incident:gd1_1:g1_1', 'incident:gd1_2:g1_2', 'incident:gd1_3:g1_3', 'incident:gd2_0:g2_0', 'incident:gd2_1:g2_1', 'incident:gd2_2:g2_2', 'incident:gd2_3:g2_3', 'incident:gd3:lone'] order_b=['incident:gd1_0:g1_0', 'incident:gd1_1:g1_1', 'incident:gd1_2:g1_2', 'incident:gd1_3:g1_3', 'incident:gd2_0:g2_0', 'incident:gd2_1:g2_1', 'incident:gd2_2:g2_2', 'incident:gd2_3:g2_3', 'incident:gd3:lone'] equal=True |
| `INC-023` | PASS | id_a=incident:d1:a id_b=incident:d1:a |
| `INC-024` | PASS | datasets=('dA', 'dB', 'dC') |
| `INC-025` | PASS | keys=['identity', 'findings', 'datasets', 'signals', 'confidence', 'speculative', 'common_ancestor', 'change', 'opened_at', 'summary'] serialised_ok=True |
| `INC-026` | PASS | hypotheses=() describe='i-no-origin: nothing upstream explains this. The cause is in the dataset itself, or in something not in the lineage graph' |
| `INC-027` | PASS | origin_present=True description=the defect originates in d1.c — every failure in this incident converges here, so the defect is here unless something upstream put it here. Check: compare d1.c against its own source for this period |
| `INC-028` | PASS | top=up1.c is_demonstrated=True score=1.0 |
| `INC-029` | PASS | hyp_columns=['L0.c', 'L1.c', 'L2.c'] far_present=False |
| `INC-030` | PASS | checks=['read the last result of the controls on up1.c', 'read the change ch and what it altered', 'compare d1.c against its own source for this period'] |
| `INC-031` | PASS | rules_out=['they are failing but started afterwards, which makes this a common cause rather than a chain', 'the failure begins before the change, or the change touched nothing on this path', 'it agrees with its source, which moves the cause downstream'] |
| `INC-032` | PASS | present=True rank=3 total=4 |
| `INC-033` | PASS | tie=True aaa_idx=0 zzz_idx=1 aaa_score=0.7 zzz_score=0.7 |
| `INC-034` | PASS | h1_score=1.0 h2_score=0.6 h3_score=0.7 analysis1_conclusive=True(expect True since 1.0>=0.9) analysis2_conclusive=False(expect False since 1.0<1.05) |
| `INC-035` | PASS | single=True empty=False |
| `INC-036` | PASS | describe='i-close: h0 — a. Check: c. 4 hypotheses are close together, so this is where to start rather than the answer' |
| `INC-037` | PASS | considered=41 offered=5 |
| `INC-038` | PASS | n_offered=5 scores=[0.36250000000000004, 0.36250000000000004, 0.25, 0.15000000000000002, 0.15000000000000002] |
| `INC-039` | PASS | match=True |
| `INC-040` | PASS | match=False |
| `INC-041` | PASS | counts={'colA': 2, 'colB': 1} |
| `INC-042` | PASS | arrival_role=Role.CUSTODIAN def_role=Role.STEWARD |
| `INC-043` | PASS | routes={'arrival': 'custodian', 'schema': 'custodian', 'value': 'steward', 'definition': 'steward', 'reconciliation': 'steward', 'calibration': 'custodian'} |
| `INC-044` | PASS | calibration_route=Role.CUSTODIAN |
| `INC-045` | PASS | delivery=Delivery.QUIET reason='nobody is recorded as custodian for unknown_ds, and an alert with no recipient is a finding nobody will see. Assign one' |
| `INC-046` | PASS | recipients=[('owner1', <Role.OWNER: 'owner'>)] |
| `INC-047` | PASS | results=[(<Change.OPENED: 'opened'>, True), (<Change.UNCHANGED: 'unchanged'>, False), (<Change.UNCHANGED: 'unchanged'>, False)] |
| `INC-048` | PASS | fp_a=ec4168946991d1f1 fp_b=ec4168946991d1f1 |
| `INC-049` | PASS | change=Change.WORSENED sent=True |
| `INC-050` | PASS | 09_change=Change.UNCHANGED 11_change=Change.WORSENED |
| `INC-051` | PASS | change=Change.IMPROVED sent=True |
| `INC-052` | PASS | change=Change.OPENED sent=True |
| `INC-053` | PASS | first=Change.OPENED,True second=Change.OPENED,True |
| `INC-054` | PASS | 0.49=Delivery.DIGEST 0.50=Delivery.IMMEDIATE |
| `INC-055` | PASS | delivery=Delivery.IMMEDIATE reason='blocks a submission' |
| `INC-056` | PASS | a=True b=False c(unblocks)=True |
| `INC-057` | PASS | digest_count=40 |
| `INC-058` | PASS | compose='nothing to report' |
| `INC-059` | PASS | describe_head='40 findings across 1 datasets since the last digest. finding 0. finding 1. finding 2. finding 3. finding 4.' |
| `INC-060` | PASS | message='the feed did not arrive. FINREP line 23 is downstream. Likeliest cause: vendor mapping changed at 05:30.' |
| `INC-061` | PASS | message='x. (400 findings, one incident).' |
| `INC-062` | PASS | message='x. ⚠ this monitor has degraded.' |
| `INC-063` | PASS | message='the feed failed. downstream fails. Likeliest cause: vendor issue.' |
| `INC-064` | PASS | delivery=Delivery.QUIET reason="withheld on residency: cust1 (an alert about ds64 may not go to US: it belongs to EU and this tenant's data must stay in EU.). The alert body quotes failing values, so sending it moves the tenant's data" |
| `INC-065` | PASS | reason="withheld on residency: cust1 (an alert about ds64 may not go to US: it belongs to EU and this tenant's data must stay in EU.). The alert body quotes failing values, so sending it moves the tenant's data" |
| `INC-066` | PASS | delivery=Delivery.IMMEDIATE |
| `INC-067` | PASS | eu_chan_delivery=Delivery.IMMEDIATE us_chan_delivery=Delivery.QUIET |
| `INC-068` | PASS | delivery=Delivery.QUIET reason="withheld on residency: cust (an alert about ds68 may not go to (unstated): it belongs to EU and this tenant's data must stay in EU.). The alert body quotes failing values, so sending it moves the tenant's data" |
| `INC-069` | PASS | change=Change.RESOLVED recipients=1 sent=True |
| `INC-070` | PASS | change=Change.OPENED sent=True |
| `INC-071` | PASS | resolve_delivery=Delivery.QUIET recipients=['cust'] (resolve does not call _residency_refusals -- gate bypassed) |
| `INC-072` | FAIL | t1_change=Change.OPENED t2_change=Change.UNCHANGED (Alert/Router carry no tenant field; a shared Router instance across tenants collides on identical dataset+fault+identity) |
| `INC-073` | PASS | combos=[(<Delivery.IMMEDIATE: 'immediate'>, <Change.OPENED: 'opened'>, True), (<Delivery.IMMEDIATE: 'immediate'>, <Change.UNCHANGED: 'unchanged'>, False), (<Delivery.IMMEDIATE: 'immediate'>, <Change.WORSENED: 'worsened'>, True), (<Delivery.IMMEDIATE: 'immediate'>, <Change.IMPROVED: 'improved'>, True), (<Delivery.IMMEDIATE: 'immediate'>, <Change.RESOLVED: 'resolved'>, True), (<Delivery.DIGEST: 'digest'>, <Change.OPENED: 'opened'>, True), (<Delivery.DIGEST: 'digest'>, <Change.UNCHANGED: 'unchanged'>, False), (<Delivery.DIGEST: 'digest'>, <Change.WORSENED: 'worsened'>, True), (<Delivery.DIGEST: 'digest'>, <Change.IMPROVED: 'improved'>, True), (<Delivery.DIGEST: 'digest'>, <Change.RESOLVED: 'resolved'>, True), (<Delivery.QUIET: 'quiet'>, <Change.OPENED: 'opened'>, False), (<Delivery.QUIET: 'quiet'>, <Change.UNCHANGED: 'unchanged'>, False), (<Delivery.QUIET: 'quiet'>, <Change.WORSENED: 'worsened'>, False), (<Delivery.QUIET: 'quiet'>, <Change.IMPROVED: 'improved'>, False), (<Delivery.QUIET: 'quiet'>, <Change.RESOLVED: 'resolved'>, False)] |
| `RPT-001` | PASS | scope='tenant:acme' start='2026-01-01' end='2026-01-31' in_content=True |
| `RPT-002` | PASS | hash_A=9d9b895ea74f hash_B=e2c19a064ead |
| `RPT-003` | PASS | fields={'statement', 'evidence_records', 'supersedes_because', 'period_end', 'tenant_id', 'exceptions', 'version', 'attester_name', 'period_start', 'supersedes', 'attester_id', 'signed_at', 'coverage', 'evidence_root', 'scope'} content_keys={'statement', 'evidence_records', 'supersedes_because', 'period_end', 'tenant_id', 'exceptions', 'version', 'attester_name', 'period_start', 'supersedes', 'attester_id', 'signed_at', 'coverage', 'evidence_root', 'scope'} missing=set() |
| `RPT-004` | PASS | describe='40 of 100 control(s) produced a verdict; this covers 40% of the scope; 30 passed; 5 failed; 2 could not be established; 3 could not be executed; 60 never ran at all' |
| `RPT-005` | PASS | rate=0.0 is_complete=False |
| `RPT-006` | PASS | seal=c82913425111 is_clean=False is_qualified=True |
| `RPT-007` | PASS | is_qualified=True is_clean=True is_complete=False |
| `RPT-008` | PASS | n_exceptions=12 |
| `RPT-009` | PASS | params=['statement', 'period_end', 'tenant_id', 'uow', 'attester_name', 'period_start', 'attester_id', 'signed_at', 'dispositions', 'scope'] |
| `RPT-010` | PASS | n_exceptions=1 verdict=fail |
| `RPT-011` | PASS | never_ran=4 n_exceptions=0 |
| `RPT-012` | PASS | n_exceptions=4 verdicts=['fail', 'error', 'skipped', 'indeterminate'] |
| `RPT-013` | PASS | n_exceptions=1 verdict=weird_verdict controls_run=1 categorised_sum=0 matches=False |
| `RPT-014` | PASS | disposition='' |
| `RPT-015` | PASS | details={'c1': '10 duplicate(s) in 1,000 rows', 'c2': '12 of 500 rows'} |
| `RPT-016` | PASS | verify_same=True verify_diff=False |
| `RPT-017` | PASS | module_doc_has_claim=True |
| `RPT-018` | PASS | clean='Alice attests, without exception, that they reviewed tenant:acme for 2026-01-01 to 2026-01-31. 5 of 5 control(s) produced a verdict; 5 passed.' qual='Alice attests, with exceptions, that they reviewed tenant:acme for 2026-01-01 to 2026-01-31. 5 of 5 control(s) produced a verdict; 4 passed; 1 failed.' |
| `RPT-019` | PASS | version=1.0 |
| `RPT-020` | PASS | titles=['Obligations with no control', 'Obligations with controls that produced no evidence', 'Obligations proven with exceptions', 'Obligations proven clean'] |
| `RPT-021` | PASS | unaddr=['ob_unaddr'] unproven=['ob_unproven'] |
| `RPT-022` | PASS | is_defensible=False headline='RDARR over s, 2026-01-01 to 2026-01-31: 1 obligation(s) have no control and 1 have controls that produced no evidence in the period. That is 2 of 4 an examiner would ask about.' |
| `RPT-023` | PASS | is_defensible=True unaddressed=0 unproven=0 |
| `RPT-024` | PASS | headline='RDARR over s: no obligations are loaded, so this pack establishes nothing.' |
| `RPT-025` | PASS | evidence_root='the_real_root_hash' type=str |
| `RPT-026` | PASS | standing=Standing.PROVEN_WITH_EXCEPTIONS controls=('cY',) failed=1 |
| `RPT-027` | PASS | bindings={'obY_tmpl': ('cY',)} |
| `RPT-028` | PASS | describe='40 of 140 covered (29%). 100 excluded: not yet connected.' |
| `RPT-029` | PASS | describe='All 40 covered.' |
| `RPT-030` | PASS | describe='10 of 15 covered (67%). 5 excluded: no reason recorded.' |
| `RPT-031` | PASS | unconnected=2 in_html=True |
| `RPT-032` | PASS | undeclared_grain=1 in_html=True |
| `RPT-033` | PASS | sql_present=True escaped=True |
| `RPT-034` | PASS | both_listed=True |
| `RPT-035` | PASS | fail_mention_idx=4781 statement_idx=5990 |
| `RPT-036` | PASS | tenant_present=True generated_by_present=True |
| `RPT-037` | PASS | stamp='2026-09-14 01:23:33Z' |
| `RPT-038` | PASS | fn_a=20260101-120000-report.html fn_b=20260101-120001-report.html |
| `RPT-039` | PASS | filename='20260101-120000-report-for-etc-münchen-spaces.html' |
| `RPT-040` | PASS | UndefinedError: 'undefined_var' is undefined |
| `RPT-041` | PASS | escaped=True raw_present=False |
| `RPT-042` | PASS | has_style_tag=True has_external_url=False |
| `RPT-043` | PASS | exists=True path=/tmp/tmp33c102hl/nonexistent/nested/20260914-012333-declaration-pack.html |
| `RPT-044` | PASS | cli_api_mentions=[] reports_index_says="48:  These open as print-ready documents. Use your browser's <strong>Print → Save as PDF</strong>\n49:  to file one. Prama does not bundle a PDF engine: adding one would mean native" |
| `RPT-045` | PASS | has_not_examined=True has_desc=True |
| `RPT-046` | PASS | has_circle=True no_polyline=True has_no_trend_text=True |
| `RPT-047` | PASS | axis_note_present=True |
| `RPT-048` | PASS | minimum=0.0 |
| `RPT-049` | PASS | at_boundary_min=0.0 below_boundary_min=96.2515 |
| `RPT-050` | PASS | minimum=0.0 |
| `RPT-051` | PASS | has_polyline=True svg_excerpt=<svg xmlns="http://www.w3.org/2000/svg" width="120" height="28" viewBox="0 0 120 28" role="img" aria-label="the series: flat, now 50" class="prama-chart"><title>the series: flat, now 50</title><desc>2 |
| `RPT-052` | PASS | below=0.0 above=1.0 |
| `RPT-053` | PASS | not_examined_present=True |
| `RPT-054` | PASS | clamped_width_present=True value_bar_width=180 |
| `RPT-055` | PASS | empty_state=True |
| `RPT-056` | PASS | dashed=True em_dash=True desc=True |
| `RPT-057` | PASS | neg_rendered=True over_rendered=True |
| `RPT-058` | PASS | zero=True full=True distinguishable=True |
| `RPT-059` | PASS | empty_state=True |
| `RPT-060` | PASS | all_labels_present=True |
| `RPT-061` | PASS | identical=True |
| `RPT-062` | PASS | results={0: '0', 0.001: '0', 100.0: '100'} |
| `RPT-063` | PASS | escaped_a=True escaped_amp=True |
| `RPT-064` | PASS | all_accessible=True details={'sparkline_empty': (True, True, True, True), 'sparkline_one': (True, True, True, True), 'sparkline_many': (True, True, True, True), 'bars': (True, True, True, True), 'score_ring': (True, True, True, True), 'distribution': (True, True, True, True)} |
| `RPT-065` | PASS | desc_has_numbers={'sparkline_empty': False, 'sparkline_one': True, 'sparkline_many': True, 'bars': True, 'score_ring': True, 'distribution': True} |
| `RPT-066` | PASS | all_present=True |
| `RPT-067` | PASS | all_names_as_text=True |
| `RPT-068` | PASS | n_uses=1 all_unverified_context=True sample=['/home/ashutosh/PycharmProjects/prama/src/prama/report/palette.py:41:UNVERIFIED_GREY = "#8A93AD"'] |
| `RPT-069` | PASS | value='var(--dim-accuracy, #00B3A4)' |
| `RPT-070` | PASS | accessors=['#00B3A4', '#008479', '#8A93AD', '#6E768A', '#14182E', '#6B7391', '#DFE3EF'] |
| `RPT-071` | PASS | value='#6B7391' |
| `RPT-072` | FAIL | fails=[('accuracy', 'fill', 2.630225255360509), ('completeness', 'fill', 2.605585816229487), ('consistency', 'fill', 2.178607026828851), ('timeliness', 'fill', 1.9195088664738005), ('uniqueness', 'fill', 2.7324852523346035)] |
| `RPT-073` | PASS | hue_diffs={'accuracy': 0.027932960893849668, 'completeness': 0.08080808080811153, 'consistency': 0.18531976744186807, 'timeliness': 0.11072445428662547, 'uniqueness': 0.09549071618037175, 'validity': 0.321807600136943, 'integrity': 0.0, 'conformity': 0.0} |
| `RPT-074` | PASS | result=#000000 |
| `RPT-075` | FAIL | result=#5C5C00 ratio=7.033006605963895 |
| `RPT-076` | PASS | errors=["invalid literal for int() with base 16: 'rr'", "not a hex colour: '#ff'", "not a hex colour: 'rgb(1,2,3)'"] |
| `RPT-077` | PASS | 3digit=(255, 255, 255) 6digit=(255, 255, 255) |
| `RPT-078` | PASS | black_white=21.0 white_black=21.0 self=1.0 |
| `RPT-079` | PASS | report='#777777 on #FFFFFF: 4.48:1 FAILS (needs 4.5:1)' |
| `RPT-080` | PASS | alpha must be between 0 and 1, not 1.5 |
| `RPT-081` | PASS | n_fails=0 sample=[] |
| `RPT-082` | PASS | matches='' |
| `RPT-083` | PASS | css_declares='38:    --bg-raised: rgba(127, 127, 127, .08);\n100:    background: var(--bg-raised);\n243:    --bs-tertiary-bg: var(--bg-raised);\n260:    --bs-btn-hover-bg: var(--bg-raised);\n263:    --bs-btn-active-bg: var(--bg-raised);' RAISED_GREY=#7F7F7F RAISED_ALPHA=0.08 (0x7F=127, matching rgba(127,127,127,.08)) computed_raised={'light': '#ECEDF1', 'dark': '#141829', 'crimson': '#EDEBEB', 'bmo': '#E8ECEF', 'wallstreet': '#131313'} |
| `RPT-084` | PASS | dark_matches=True wallstreet_matches=True |
| `RPT-085` | PASS | accuracy_hues={'light': 175.29411764705884, 'dark': 174.7058823529412, 'crimson': 175.6291390728477, 'bmo': 175.6291390728477, 'wallstreet': 174.7058823529412} diffs_from_teal={'light': 0.3220506079526899, 'dark': 0.26618468616496216, 'crimson': 0.6570720337415423, 'bmo': 0.6570720337415423, 'wallstreet': 0.26618468616496216} |
| `RPT-086` | PASS | hues computed and printed above; accent colours visually distinct from all dimension fills (Harvard Crimson ~350deg vs validity red ~1deg / uniqueness orange ~19deg are borderline but distinguishable in saturation/lightness) |
| `RPT-087` | PASS | notes=['The default. Prama Indigo on a cool white ground.', 'The same palette on a night ground, for long sessions.', 'Harvard Crimson on warm paper. An academic, print-like register.', 'BMO Blue on cool grey. A retail-banking register.', 'Amber on black, as a terminal. For a desk that lives in one.'] |
| `RPT-088` | PASS | value=0.9996792029282855 rendered='99.97%' |
| `RPT-089` | PASS | rendered='100%' |
| `RPT-090` | PASS | rendered='&gt;99.99%' |
| `RPT-091` | FAIL | 0.0001='0.01%' 0.0000001='&lt;0.0001%' |
| `RPT-092` | PASS | rendered='0%' |
| `RPT-093` | PASS | plain_over='>99.99%' plain_under='<0.0001%' |
| `RPT-094` | PASS | 1.5='100%' -0.5='0%' |
| `RPT-095` | PASS | n_fails=0 sample=[] |
| `BCH-001` | PASS | TypeError: build() missing 1 required keyword-only argument: 'seed' |
| `BCH-002` | PASS | to_dict_equal=True rows_equal=True |
| `BCH-003` | PASS | different=True |
| `BCH-004` | PASS | total=28 (catalogue says 27 but its own per-family counts sum to 28, matching the actual total -- catalogue arithmetic slip) counts={'structural': 5, 'content': 7, 'statistical': 5, 'relational': 4, 'temporal': 3, 'semantic': 4} expected={'structural': 5, 'content': 7, 'statistical': 5, 'relational': 4, 'temporal': 3, 'semantic': 4} all_columns_valid=True |
| `BCH-005` | PASS | counts={'structural': 5, 'content': 7, 'statistical': 5, 'relational': 4, 'temporal': 3, 'semantic': 4} |
| `BCH-006` | PASS | counts={'obvious': 7, 'ordinary': 9, 'subtle': 11, 'adversarial': 1} |
| `BCH-007` | PASS | n_windows=28 unique=28 sorted=True first3=['2026-01-01', '2026-01-02', '2026-01-03'] |
| `BCH-008` | PASS | damaged_rows=(0, 3, 5, 8, 9, 10, 12, 18, 21, 22, 23, 24, 26, 28, 29, 30, 34, 36, 37, 41, 42, 44, 45, 46, 47) actual_diff=(0, 3, 5, 8, 9, 10, 12, 18, 21, 22, 23, 24, 26, 28, 29, 30, 34, 36, 37, 41, 42, 44, 45, 46, 47) |
| `BCH-009` | PASS | barren=(('always-noop', 'no sampled row could carry it; nothing was planted and nothing is labelled'),) planted=0 |
| `BCH-010` | PASS | sign_flip_pos=True sign_flip_neg=False truncate_short=False retype_text=False |
| `BCH-011` | PASS | result=False |
| `BCH-012` | PASS | after_drop={'other': 1} after_rename={'other': 1, 'partyName': 'Acme'} |
| `BCH-013` | PASS | n_dupes=25 |
| `BCH-014` | PASS | after={'product': 'MERGED-ENTITY', 'amount': 200.0} |
| `BCH-015` | FAIL | errors=['[INPUT.INVALID] rate must be a share of rows in (0, 1], got 0 \| Next: Pass --rate above 0 and at most 1, as in --rate 0.05 for five percent. \| Context: rate=0', '[INPUT.INVALID] rate must be a share of rows in (0, 1], got 1.5 \| Next: Pass --rate above 0 and at most 1, as in --rate 0.05 for five percent. \| Context: rate=1.5', '[INPUT.INVALID] rate must be a share of rows in (0, 1], got -0.1 \| Next: Pass --rate above 0 and at most 1, as in --rate 0.05 for five percent. \| Context: rate=-0.1'] types=['ValidationError', 'ValidationError', 'ValidationError'] (catalogue Expected: ValueError naming the value) |
| `BCH-016` | FAIL | ValidationError: [INPUT.INVALID] a corpus needs rows, got 0 \| Next: Pass --rows with a positive count, as in --rows 10000. \| Context: rows=0 (catalogue Expected: ValueError) |
| `BCH-017` | PASS | n_damaged=5 |
| `BCH-018` | PASS | any_planted=True |
| `BCH-019` | PASS | all_match=True |
| `BCH-020` | PASS | rows=5600 clean=5600 expected=5600 (catalogue said 5,400 assuming 27 classes; actual is 28 classes x 200 = 5,600) |
| `BCH-021` | PASS | barren_in_dict=[{'class': 'always-noop', 'reason': 'no sampled row could carry it; nothing was planted and nothing is labelled'}] |
| `BCH-022` | PASS | found=1 false_alarms=3 |
| `BCH-023` | PASS | near_misses=1 found=0 |
| `BCH-024` | PASS | found=1 false_alarms=9 |
| `BCH-025` | PASS | found=2 |
| `BCH-026` | PASS | recall=None describe='x: nothing was planted, so nothing is scored — 3 alert(s) here are all false' |
| `BCH-027` | PASS | precision=None describe='x: found 5 of 5 (recall 100%); precision is an aggregate figure, because a false alarm belongs to no family' |
| `BCH-028` | PASS | f1=None (precision always None -> f1 structurally always None) |
| `BCH-029` | PASS | family_false_alarms=[5, 5, 5] score_false_alarms=5 |
| `BCH-030` | PASS | precision=0.8 |
| `BCH-031` | PASS | precision=None recall=0.0 f1=None |
| `BCH-032` | PASS | describe='weakest family weak at 0% recall; found 1 of 3 planted defect(s) (33%)' |
| `BCH-033` | PASS | by_difficulty={'obvious': (1, 1), 'ordinary': (0, 1), 'subtle': (1, 1), 'adversarial': (0, 1)} found=2 planted=4 |
| `BCH-034` | FAIL | docstring_says_easy_moderate_hard=True default='moderate' actual_corpus_values={'subtle', 'obvious', 'adversarial', 'ordinary'} -- do_not_agree, confirming the pre-flagged documentation defect |
| `BCH-035` | PASS | found=0 false_alarms=0 recall=0.0 precision=None |
| `BCH-036` | PASS | recall=1.0 precision=0.07397260273972603 |
| `BCH-037` | PASS | alerted_cols_sample=['account_id', 'amount', 'booking_date', 'control_total', 'counterparty_id', 'country', 'currency', 'iban', 'partyName', 'party_name', 'product', 'rate', 'value_date', 'window'] |
| `BCH-038` | PASS | schema_only_blind=('content', 'statistical', 'relational', 'temporal', 'semantic') |
| `BCH-039` | PASS | alerts=[('product', 'the column is missing from some rows')] |
| `BCH-040` | PASS | patterns_only_blind=('statistical', 'relational', 'temporal', 'semantic') |
| `BCH-041` | FAIL | stats_only_blind=('relational',) found_families={'temporal', 'semantic', 'statistical', 'structural', 'content'} |
| `BCH-042` | PASS | identical=True |
| `BCH-043` | PASS | blind_families=('content',) |
| `BCH-044` | PASS | n_not_run=15 expected=15 |
| `BCH-045` | PASS | no_subprocess=True no_external_import=True (NOT_RUN dict's mention of tool names like 'Soda Core' is documentation, not invocation) |
| `BCH-046` | PASS | [INPUT.INVALID] no such baseline: 'nope' \| Next: One of: detect-nothing, alert-on-everything, schema-only, patterns-only, statistics-only. |
| `BCH-047` | PASS | [('detect-nothing', 'bound', True), ('alert-on-everything', 'bound', True), ('schema-only', 'ablation', True), ('patterns-only', 'ablation', True), ('statistics-only', 'ablation', True)] |
| `BCH-048` | PASS | fields=['blind_id', 'dataset', 'column', 'raised_at', 'detail'] |
| `BCH-049` | PASS | sorted_correctly=True not_arrival_order=True |
| `BCH-050` | PASS | id_a=d2f8697eebebb838 id_b=c9821ccb74c95ba7 |
| `BCH-051` | PASS | len=2 idA=c195bafe54658973 idB=c195bafe54658973 (both systems' blind_id excludes 'system' field) |
| `BCH-052` | PASS | precision=0.9 examined_share=0.2 |
| `BCH-053` | PASS | describe='A: precision 90% over the 20% of 100 alert(s) that were judged' |
| `BCH-054` | PASS | unclear=1 adjudicated=2 |
| `BCH-055` | PASS | minutes_spent=60.0 wasted=30.0 |
| `BCH-056` | PASS | outside_window={'LATE': 3} describe_has_it=True |
| `BCH-057` | PASS | outside_window={'A': 1} (string comparison drops it) |
| `BCH-058` | PASS | alerts_per_sw=2.0 wasted_hpw=0.3333333333333333 describe='A: precision 0% over the 100% of 24 alert(s) that were judged; 2 alerts per steward-week; 0.3 wasted hours a week' |
| `BCH-059` | PASS | alerts_per_sw=None describe='A: precision 0% over the 100% of 24 alert(s) that were judged' |
| `BCH-060` | PASS | sys_present=True raised=0 describe=GONE: raised nothing in this window |
| `BCH-061` | PASS | unjudged=1 confirmed=0 |
| `OPS-001` | PASS | helm template (v3.16.3, on PATH) refuses without existingSecret/createSecretFrom: 'no default session secret, because a default means every installation shares a key that is public in this chart' -- unchanged from round 3 |
| `OPS-002` | PASS | helm template refuses sqlite+replicaCount=2: 'sqlite with replicaCount > 1 is corruption, not high availability' -- unchanged from round 3 |
| `OPS-003` | FAIL | helm template --set database.dialect=sqlite --set replicaCount=1 --set createSecretFrom=x (the catalogue's literal precondition, unchanged since round 2/3) still FAILS to render: 'prama: database.dialect=sqlite needs somewhere to write. readOnlyRootFilesystem is on, so set persistence.enabled=true (or persistence.existingClaim)...'. Adding --set persistence.enabled=true renders cleanly (confirmed again). UNCHANGED from round 3, not a new regression this round -- deploy/helm/prama and deploy/Dockerfile carry zero commits in batches A-D (`git log 03dcf7c..HEAD -- deploy/` is empty), so nothing in this round's own delta touched the chart. Additionally re-confirmed via the product's own now-split test: `pytest tests/deploy/test_helm_chart.py` -- 18/18 pass, including `test_sqlite_with_one_replica_is_allowed_once_it_has_a_volume` (renders with persistence.enabled) and `test_sqlite_without_a_volume_says_which_flag_to_set` (refuses, names persistence.enabled, exactly the OPS-014 fix's second acceptable branch). Recorded FAIL against the catalogue's literal, stale precondition per the rule; not-a-defect, identical judgement to round 3. |
| `OPS-004` | PASS | helm template refuses postgres with empty host: 'database.dialect=postgres needs database.postgres.host' -- unchanged |
| `OPS-005` | PASS | grep -rniE "secret\s*[:=]\s*['\"][a-zA-Z0-9]" deploy/helm/prama/ -> no hits; values.yaml existingSecret/createSecretFrom/postgres.existingSecret all empty by default; secret.yaml only renders when createSecretFrom is set and existingSecret is not -- unchanged |
| `OPS-006` | PASS | helm template with both existingSecret and createSecretFrom set: no Secret object rendered (deployment.yaml references .Values.existingSecret directly) -- unchanged |
| `OPS-007` | PASS | helm template with a full postgres values set: PRAMA_SECURITY__SESSION_SECRET, PRAMA_DATABASE__DIALECT, PRAMA_WEB__ENABLED, PRAMA_DATABASE__POSTGRES__{HOST,PORT,DATABASE,USER} all present and correctly mapped -- unchanged |
| `OPS-008` | PASS | helm template with tenancy.defaultTenant empty: PRAMA_TENANCY__DEFAULT_TENANT absent (grep count 0); with tenancy.defaultTenant=acme: present -- unchanged |
| `OPS-009` | PASS | helm template: both readinessProbe and livenessProbe use httpGet path /api/v1/health, port http; readiness initialDelaySeconds=5/period=10, liveness initialDelaySeconds=20/period=20 -- unchanged |
| `OPS-010` | PASS | Database.health() against an unreachable postgres port (127.0.0.1:55499) raises ConnectionRefusedError rather than returning a healthy dict, against the live PostgreSQL 16 container's engine construction succeeding -- reproduced with the saved ops_010_health_unreachable.py harness, identical outcome to round 3 |
| `OPS-011` | BLOCKED | no live Kubernetes cluster is available in this environment (kubectl not even on PATH) to observe real pod readiness/liveness behaviour under a database outage; only the probe configuration (OPS-009) was reviewed -- same as round 2 and round 3 |
| `OPS-012` | PASS | docker run --rm --entrypoint id prama:qa-r4 -> uid=10001(prama) gid=999(prama); helm template podSecurityContext runAsUser=10001/runAsNonRoot=true -- the two agree, unchanged |
| `OPS-013` | PASS | helm template: containers[].securityContext.readOnlyRootFilesystem=true and a `tmp` emptyDir volume mounted at /tmp -- unchanged |
| `OPS-014` | PASS | FIXED (round 2: FAIL; round 3: PASS). helm template --set database.dialect=sqlite --set replicaCount=1 --set createSecretFrom=x --set persistence.enabled=true mounts a `data` PersistentVolumeClaim at /var/lib/prama; without persistence.enabled it refuses outright with a named error. Re-confirmed, still fixed |
| `OPS-015` | PASS | helm template securityContext.allowPrivilegeEscalation=false, capabilities.drop=[ALL], podSecurityContext.seccompProfile.type=RuntimeDefault -- unchanged |
| `OPS-016` | PASS | docker run --entrypoint sh prama:qa-r4 -c 'ls /opt/prama/schema': postgres.sql sqlite.sql; PRAMA_DATABASE__SCHEMA_DIR=/opt/prama/schema set in the image env -- image rebuilt from current tree, unchanged |
| `OPS-017` | PASS | docker run --entrypoint python3 prama:qa-r4 --version -> Python 3.13.15; .python-version contains '3.13' -- same minor version, unchanged |
| `OPS-018` | PASS | docker run --entrypoint sh prama:qa-r4 -c 'dpkg -l \| grep -i gcc': only gcc-14-base/libgcc-s1 runtime remnants; no cc/gcc on PATH -- unchanged |
| `OPS-019` | PASS | docker run --rm prama:qa-r4 (no secret set), full unpiped capture: prints the banner, console URLs, no-tenant notice, THEN 'error: security.session_secret is empty, and Prama will not start without it' / 'next: Set security.session_secret in config/application.local.yaml...'; exit 1 -- identical wording to round 3, image rebuilt from the current tree so this exercises the current cli/base.py Application.run path (pack installation moved there in Batch D) and behaves identically |
| `OPS-020` | PASS | docker inspect prama:qa-r4 Healthcheck.Test: CMD-SHELL against http://127.0.0.1:8080/api/v1/health; chart's probes use the same path on port 8080 -- unchanged |
| `OPS-021` | PASS | fresh named Docker volume mounted at /data, `touch /data/testfile` as the container's default user succeeded, owned prama:prama -- unchanged |
| `OPS-022` | PASS | Chart.yaml appVersion: "0.1.0", image.tag: "0.1.0"; src/prama/version.py VERSION = "0.1.0" -- all three agree, unchanged |
| `OPS-023` | PASS | built a fresh sqlite database with the real schema, ran `prama db verify` (through the current CLI, cli/base.py's new install-packs-in-Application.run path included): 'schema verified against .../schema/sqlite.sql (digest 5df0746f832e): no drift', exit 0 -- unchanged |
| `OPS-024` | PASS | same database with `tenant` table dropped to simulate drift: `prama db verify` -> 'schema drift ... [missing_table] tenant', exit 3; also confirmed via a real `prama serve` startup against the drifted database raising SchemaDriftError during lifespan startup, exit 3, before any request could be served -- unchanged |
| `OPS-025` | PASS | confirmed WAL mode active, wrote 5 real evidence records via EvidenceDao with a concurrent in-flight writer, took a WAL-safe backup mid-write, then verified the restored copy reports zero drifts -- reproduced with the saved ops_025_026_wal_backup.py harness, identical outcome to round 3 (deploy/README.md still documents no backup procedure -- unchanged documentation gap, not a code defect) |
| `OPS-026` | PASS | the same 5-record chain, verified via EvidenceDao.verify() before and after backup+restore: identical head and merkle_root, breaches=() both times -- unchanged |
| `OPS-027` | PASS | reproduced the exact `false \| tail -1` pattern: without `set -o pipefail` the pipeline exits 0; with `set -o pipefail` (as scripts/gate.sh line 9 declares, unchanged in batches A-D) the same pipeline exits 1 |
| `OPS-028` | PASS | reproduced each fault directly against the current tree: a lint fault -> ruff exit 1; a type fault -> mypy exit 1; a 1600-code-line file -> check_file_length.py exit 1 naming the file and '1600 lines' -- unchanged, scripts/check_file_length.py carries zero commits in A-D |
| `OPS-029` | PASS | same pipefail mechanism as OPS-027: `set -o pipefail; (echo err; exit 1) \| tail -1` exits 1 -- unchanged |
| `OPS-030` | PASS | a file with exactly 1500 significant lines -> check_file_length.py exit 0; 1501 -> exit 1, message names the file and '1501 lines' -- reproduced fresh against the current script, identical |
| `OPS-031` | PASS | source-confirmed unchanged (scripts/check_file_length.py carries zero commits in A-D); round 3's direct 3800-physical-line reproduction stands |
| `OPS-032` | PASS | source-confirmed unchanged; round 3's direct .venv/node_modules/prama-web synthetic-skip reproduction stands (script has zero commits in A-D) |
| `OPS-033` | PASS | `python scripts/check_file_length.py schema/sqlite.sql schema/postgres.sql` exits 0; both files 1047 physical lines -- reproduced fresh, unchanged |
| `OPS-034` | PASS | .github/workflows/gate.yml's `gate` job's only substantive step is `./scripts/gate.sh` after activating the venv -- re-read, unchanged (zero commits to gate.yml in A-D) |
| `OPS-035` | PASS | all three jobs (gate, conformance, accessibility) in gate.yml run `uv python install "$(cat .python-version)"` before building their venv -- re-read, unchanged |
| `OPS-036` | PASS | gate.yml's conformance job declares a real postgres:16-alpine service; reproduced locally against the live PostgreSQL 16 container: `pytest tests/backend/test_engine_conformance.py`: 41/41 passed -- unchanged |
| `OPS-037` | PASS | with PRAMA_TEST_POSTGRES_DSN unset, the 10 postgres-only tests report SKIPPED, each naming the env var; gate.yml hardcodes the postgres service unconditionally so this skip path is structurally unreachable in CI -- re-read, unchanged |
| `OPS-038` | PASS | gate.yml's `accessibility` job runs `playwright install --with-deps chromium` then `pytest -q tests/web/test_axe.py`, exactly as documented -- re-read (catalogue Steps is 'read the job'), unchanged |
| `OPS-039` | PASS | gate.yml: `on: push: branches: [main, develop]` and `pull_request: branches: [main, develop]` -- re-read, unchanged |
| `OPS-040` | PASS | with `uv` genuinely absent from PATH, gate.sh's exact lock-check snippet prints 'uv not installed; skipping the lock-file check' and the enclosing `if` exits 0 -- reproduced fresh (env -i PATH=/usr/bin:/bin), identical |
| `OPS-041` | PASS | `uv lock --check` against the untouched repository: exit 0 (86 packages resolved) -- reproduced fresh; round 3's scratch-copy-with-an-unlocked-dependency counterfactual stands unchanged (uv.lock carries no A-D commits touching this mechanism) |
| `OPS-042` | PASS | `python3 scripts/generate_docs.py --check` on the current tree: exit 0, 'every generated document matches the code (2 checked)' -- reproduced fresh, identical; round 3's hand-edited-doc counterfactual stands (script has zero commits in A-D) |
| `OPS-043` | PASS | `python run_prama_web.py` in a fresh scratch copy of the repo (git archive HEAD), no secret configured: prints 'security.session_secret is empty, and Prama will not start without it.' and 'Run once with --init-secret, or export PRAMA_SECURITY__SESSION_SECRET.', exit 1 -- reproduced fresh against the current tree, identical to round 3 |
| `OPS-044` | PASS | `python run_prama_web.py --init-secret` in the same scratch copy: wrote config/application.local.yaml only (a `security: session_secret: "..."` block); matches the real repo's .gitignore pattern `config/*.local.yaml` -- reproduced fresh, identical |
| `OPS-045` | PASS | running --init-secret a second time: 'config/application.local.yaml already sets session_secret' / 'Leaving it alone. Edit the file if you meant to change it.', exit 1 -- reproduced fresh, identical |
| `OPS-046` | PASS | source-confirmed unchanged (run_prama_web.py carries zero commits in A-D): `_write_local_secret()` uses `token_urlsafe(48)` freshly per call, as round 3 confirmed directly |
| `OPS-047` | PASS | `python run_prama_web.py --prepare` against a fresh sqlite path, run twice: first run 'schema applied · estate acme-bank · <id>' / '(created)'; second run the identical id with no '(created)' line -- reproduced fresh, identical |
| `OPS-048` | FAIL | unchanged from round 2 and round 3. `python run_prama_web.py --prepare` against the live PostgreSQL 127.0.0.1:55432 container with no confirmation flag and no prompt: silently applied the schema and created a tenant ('schema applied · estate acme-bank · <id>'), then proceeded to serve. `_prepare` still calls `database.initialise()` unconditionally regardless of dialect; the module docstring's promise not to 'touch a database that is not SQLite without being told' is still not honoured. run_prama_web.py carries zero commits in batches A-D (`git log 03dcf7c..HEAD -- run_prama_web.py` is empty) -- reproduced fresh against the live container, identical defect |
| `OPS-049` | PASS | `python run_prama_web.py` with no default tenant configured: prints 'No tenant is configured, so every console page will redirect to a sign-in that does not exist yet. Re-run with --prepare, or: prama tenant create acme-bank --name ...' -- reproduced fresh, identical |
| `OPS-050` | PASS | source-confirmed (run_prama_web.py unchanged): --prepare's tenant is applied via a fresh `ConfigurationBuilder().with_defaults(config.raw()).with_mapping(...)`, never by mutating the existing config object in place |
| `OPS-051` | PASS | started `run_prama_web.py --prepare` with stdout redirected to a file; the console/API/docs URL lines were present well before the process would otherwise block on serving -- `sys.stdout.flush()` before `uvicorn.run()` still does its job, reproduced fresh |
| `OPS-052` | PASS | with `sys.modules['uvicorn'] = None` forcing the internal `import uvicorn` to raise ImportError, run_prama_web.py prints 'the HTTP server is not installed.' / 'Install it: pip install -e ".[serve]".', exit 1 -- reproduced fresh via runpy against the current source, identical |
| `OPS-053` | PASS | source-confirmed unchanged: run_prama_web.py imports and calls load_configuration, Database.from_config, and create_app -- the same CLI code paths -- and defines no application-assembly logic of its own |
| `OPS-054` | PASS | started a prepared server on a scratch sqlite db, waited for 'Uvicorn running' in its log, sent SIGTERM: 'Shutting down' -> 'Waiting for application shutdown' -> 'Application shutdown complete' -> 'Finished server process', process gone shortly after -- reproduced fresh, identical |
| `OPS-055` | BLOCKED | same limitation as round 2 and round 3: staging a genuinely interrupted control run (a SIGKILL that lands mid-execution) needs a control actually in flight at the moment of the kill; run_prama_web.py and the recovery mechanisms it exercises (db/lease_provider.py, db/dao/evidence.py) carry zero commits in batches A-D (`git log 03dcf7c..HEAD` empty for both files), so the same blocker applies unchanged |
| `OPS-056` | PASS | `MemoryTracer().span("test.span")` raising ValueError inside the block: span still recorded (1 span), error == 'ValueError: boom', non-negative duration_ms; exception propagated -- reproduced with the saved ops_056_067_telemetry.py harness, identical to round 3 |
| `OPS-057` | PASS | `NullTracer().span(...)` used with 'opentelemetry' in sys.modules == False -- reproduced, identical |
| `OPS-058` | PASS | `grep -rn 'span("prama\.' src/` returns no hits -- every call site uses a module span-name constant -- reproduced, identical |
| `OPS-059` | PASS | `with tracer.span("test.span2") as s: s.set(rows=42)` -- attributes == {'rows': 42} -- reproduced, identical |
| `OPS-060` | PASS | a real Lineage START+COMPLETE event pair from an EvidenceRecord carrying scanned_rows/violating_rows metrics: the serialised event JSON contains no '100.0', no '5.0', no 'scanned_rows' -- only dataset/column names and the boolean success outcome -- reproduced, identical; also confirms the new UlidFactory (Batch A's clock-inside-lock fix) still mints a well-formed 'run:01...' id |
| `OPS-061` | PASS | `EventType.for_verdict(v)` for (pass, fail, error, aborted) -> COMPLETE, COMPLETE, FAIL, FAIL -- reproduced, identical |
| `OPS-062` | PASS | `_worst_verdict(['pass']*99 + ['error'])` returned 'error' -- reproduced, identical |
| `OPS-063` | PASS | FIXED (round 2: FAIL; round 3: PASS). `_worst_verdict(['pass', 'pass', 'totally_unknown_verdict'])` returns 'totally_unknown_verdict', not 'pass' -- reproduced, still fixed |
| `OPS-064` | PASS | a serialised RunEvent carries eventType, eventTime, run.runId, job.namespace, job.name, inputs, producer, schemaURL; nested dataQualityAssertions facet carries _producer/_schemaURL -- reproduced, identical |
| `OPS-065` | PASS | `Lineage.started(job="job2", datasets=("ds1",))` emitted a run id starting with 'run:'; `Lineage.finished(..., run_id=<that id>)`'s COMPLETE event reused the identical run_id -- reproduced, identical; also exercises the Batch A UlidFactory fix (clock read inside the lock) with no observable behaviour change in this single-threaded case |
| `OPS-066` | PASS | `Lineage(namespace=...)` with no emitter: `._emitter` is a NullEmitter instance; `.started(job=...)` raised nothing -- reproduced, identical |
| `OPS-067` | PASS | PRODUCER == 'https://prama.dev/openlineage/0.1.0'; VERSION ('0.1.0') is a substring of PRODUCER -- reproduced, identical |
| `OPS-068` | PASS | built a real, correctly-chained 10-record evidence bundle via Archivist.bundle(), wrote manifest.json+evidence.ndjson, ran `python3 -I scripts/verify_evidence.py <bundle-dir>` (confirmed -I blocks `import prama`): all 7 checks [PASS], 'Every check passed.', exit 0 -- reproduced with the saved ops_068_069_make_bundle.py harness plus a fresh verify_evidence.py invocation, identical to round 3 |
| `OPS-069` | PASS | flipped one record's verdict field without recomputing any hash, ran the same isolated verify_evidence.py: '[FAIL] every record's content hashes to its stored content_hash / record 3: ...', '[FAIL] the evidence file is the one the manifest describes' -- exit 1, failing record's sequence (3) named exactly -- reproduced fresh, identical |
| `OPS-070` | PASS | `pytest tests/architecture -v`: 245/245 architecture tests passed (round 3: 244; one net additional test file landed in Batch D, none removed), including the import-scanning tests confirming only prama/db/** imports SQLAlchemy -- re-run fresh, this specific guard still passes |
| `OPS-071` | PASS | same architecture-test run: TestModelVerdicts (the no-model-verdict guard) all 4 tests passed -- re-run fresh, unchanged |
| `OPS-072` | PASS | same architecture-test run: TestNoMigrations (test_ddl_is_never_emitted_from_orm_metadata, test_no_migration_tooling_is_present) passed -- re-run fresh, unchanged |
| `OPS-073` | PASS | `git ls-files config/ deploy/ .github/ \| xargs grep -lIE "secret\s*[:=]\s*['\"][a-zA-Z0-9]"` -> zero hits this round (deploy/README.md's `--from-literal=session-secret="$(...)"` command template does not match the pattern literally, since the quote is followed by `$` not an alphanumeric); config/application.yaml's tracked security.session_secret is the empty string -- re-run fresh, same not-a-defect conclusion as round 3, stronger result (round 3 additionally flagged QA-harness/CodeMirror false positives in a broader whole-tree grep; that broader grep was not repeated here since it is out of this case's own precondition) |
| `OPS-074` | PASS | FIXED (round 2: FAIL; round 3: PASS). `git log --all --grep='Co-Authored-By: Claude'`, `--grep='Claude-Session:'`, `--grep='Generated with [Claude'` all return zero commits; scanned every commit message across `git rev-list --all` for 'claude'/'anthropic' -- only legitimate 'CLAUDE.md' filename references found; `git fsck --unreachable` lists several unreachable objects (ordinary git garbage from history rewrites and force-pushes since round 3, not a new finding) and none of their commit messages mention Claude or Anthropic either -- reproduced fresh, still fixed |

## Failures

### `MON-014`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: 1sd_material=True val=49.355734768613345 scale~49.355734768612734 2sd_material=True val=98.7114695372244

### `MON-018`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: normalised=1.6474271474295212 (expect near 1.96)

### `MON-064`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: final_key=() declared_survives_in_key=False relaxed=['hour', 'day_of_week', 'period_end', 'business_day'] declared_in_relaxed=False (expected the driver to survive the fallback; it does not, and its loss is not reported in `relaxed` either)

### `MON-092`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: verdicts_count=0 (unknown segment silently dropped, no record/unjudgeable entry produced)

### `MON-105`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: low=1000.0 high=inf explanation='the declared rhythm says a daily delivery carries between 1,000 and inf records'

### `MON-114`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: raised=5 confirmed=7 reviewed=5 unreviewed=0 (confirmed<=reviewed=False)

### `MON-135`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: changepoint_error=0.04977777777777777 weighted_error=0.013777777777777772

### `INC-010`

See the dedicated `INC-010` section above for the full investigation.

### `INC-072`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: t1_change=Change.OPENED t2_change=Change.UNCHANGED (Alert/Router carry no tenant field; a shared Router instance across tenants collides on identical dataset+fault+identity)

### `RPT-072`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: fails=[('accuracy', 'fill', 2.630225255360509), ('completeness', 'fill', 2.605585816229487), ('consistency', 'fill', 2.178607026828851), ('timeliness', 'fill', 1.9195088664738005), ('uniqueness', 'fill', 2.7324852523346035)]

### `RPT-075`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: result=#5C5C00 ratio=7.033006605963895

### `RPT-091`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: 0.0001='0.01%' 0.0000001='&lt;0.0001%'

### `BCH-015`

**REGRESSION against round 3's PASS** — see Regressions section above for full detail and attribution.

### `BCH-016`

**REGRESSION against round 3's PASS** — see Regressions section above for full detail and attribution.

### `BCH-034`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: docstring_says_easy_moderate_hard=True default='moderate' actual_corpus_values={'subtle', 'obvious', 'adversarial', 'ordinary'} -- do_not_agree, confirming the pre-flagged documentation defect

### `BCH-041`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: stats_only_blind=('relational',) found_families={'temporal', 'semantic', 'statistical', 'structural', 'content'}

### `OPS-003`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: helm template --set database.dialect=sqlite --set replicaCount=1 --set createSecretFrom=x (the catalogue's literal precondition, unchanged since round 2/3) still FAILS to render: 'prama: database.dialect=sqlite needs somewhere to write. readOnlyRootFilesystem is on, so set persistence.enabled=true (or persistence.existingClaim)...'. Adding --set persistence.enabled=true renders cleanly (confirmed again). UNCHANGED from round 3, not a new regression this round -- deploy/helm/prama and deploy/Dockerfile carry zero commits in batches A-D (`git log 03dcf7c..HEAD -- deploy/` is empty), so nothing in this round's own delta touched the chart. Additionally re-confirmed via the product's own now-split test: `pytest tests/deploy/test_helm_chart.py` -- 18/18 pass, including `test_sqlite_with_one_replica_is_allowed_once_it_has_a_volume` (renders with persistence.enabled) and `test_sqlite_without_a_volume_says_which_flag_to_set` (refuses, names persistence.enabled, exactly the OPS-014 fix's second acceptable branch). Recorded FAIL against the catalogue's literal, stale precondition per the rule; not-a-defect, identical judgement to round 3.

### `OPS-048`

Unchanged from round 3 (round 3's own detailed write-up applies verbatim; re-confirmed by direct re-execution this round). Observed: unchanged from round 2 and round 3. `python run_prama_web.py --prepare` against the live PostgreSQL 127.0.0.1:55432 container with no confirmation flag and no prompt: silently applied the schema and created a tenant ('schema applied · estate acme-bank · <id>'), then proceeded to serve. `_prepare` still calls `database.initialise()` unconditionally regardless of dialect; the module docstring's promise not to 'touch a database that is not SQLite without being told' is still not honoured. run_prama_web.py carries zero commits in batches A-D (`git log 03dcf7c..HEAD -- run_prama_web.py` is empty) -- reproduced fresh against the live container, identical defect

