# Platform Ops — QA execution log, round 3

`prama.monitor.drift` · `prama.monitor.detectors` · `prama.monitor.seasonality` · `prama.monitor.cards` ·
`prama.monitor.tournament` · `prama.monitor.coldstart` · `prama.incident.correlate` · `prama.alert.route` ·
`prama.report.rdarr` · `prama.report.attest` · `prama.report.charts` · `prama.report.contrast` ·
`prama.report.themes` · `prama.report.palette` · `prama.report.rate` · `prama.bench.corpus` ·
`prama.bench.baselines` · `prama.bench.scoring` · `prama.bench.shadow` · `deploy/helm/prama` ·
`deploy/Dockerfile` · `scripts/gate.sh` · `scripts/check_file_length.py` · `scripts/generate_docs.py` ·
`scripts/verify_evidence.py` · `run_prama_web.py` · `prama.telemetry.trace` · `prama.telemetry.lineage` ·
`.github/workflows/gate.yml`.

This is a **re-run** of `qa/logs/platform-ops.md` (round 2) against the tree as it stands after ten
remediation batches (`B1`-`B10`, `ec16cfe`..`03dcf7c`), with particular scrutiny on the Helm chart
(which gained `database.sqlite.path`, a `persistence` block, `templates/pvc.yaml`, and an
`_helpers.tpl` guard that refuses SQLite without persistence — the direct fix for round 2's
`OPS-014`), on `prama serve`'s startup ordering (bind before banner, port-range validation, an
explicit flush so the banner survives a non-tty), on `telemetry/lineage.py::_worst_verdict` (batch
`B4`'s "nothing to report is not the same as nothing wrong", the direct fix for round 2's
`OPS-063`), and on the repository's own commit history (round 2's `OPS-074`).

All 443 cases in `MON-001..140`, `INC-001..073`, `RPT-001..095`, `BCH-001..061` and `OPS-001..074`
were executed against the live codebase: the drift, detector, seasonality, cards, tournament,
coldstart, incident-correlator, alert-router, report/chart/contrast and benchmark-corpus cases are
real Python objects driven directly with fixed seeds, exactly as round 2's saved harness scripts in
`qa/harness/platform-ops/` already did — those 11 scripts (`mon_001_030.py` through `bch_001_061.py`)
were re-run **byte-for-byte unmodified** against the current tree, because round 2 found them to
already match its own published table for this area (see Method below). The 74 `OPS-` deployment and
process cases have no saved harness script — round 2 executed them by hand and recorded the result in
`qa/harness/platform-ops/ops_rows.py` — so they were re-executed by hand again here: a real `helm`
v3.15.4 binary fetched fresh into the scratchpad, a real Docker image built from `deploy/Dockerfile`
and run as a real container, `scripts/gate.sh`'s individual mechanisms (`pipefail`,
`check_file_length.py`, `generate_docs.py --check`, a real `uv` binary against a scratch copy of
`pyproject.toml`) reproduced directly, `run_prama_web.py` run as a real subprocess against real
SQLite and the live PostgreSQL 16 container at `127.0.0.1:55432`, real POSIX signals sent to a real
running server, a real evidence bundle verified by `scripts/verify_evidence.py -I` in a
Prama-uninstalled interpreter, and the real git history scanned with `git log --all --grep` and
`git fsck --unreachable`. No `src/`, `tests/`, `schema/`, `config/`, `qa/catalogue/` or
`qa/regression-suite/` file was modified; `git status --porcelain src/ tests/ schema/ config/
qa/catalogue/ qa/regression-suite/` stayed empty throughout (one accidental write to the real
`config/application.local.yaml` during an early `run_prama_web.py --init-secret` trial was caught and
deleted immediately — see Method — and every subsequent `run_prama_web.py` invocation ran inside a
scratch copy of the repository instead).

## Method: how a re-run with regressions differs from round 2

Round 2's 11 saved `platform-ops` harness scripts were re-run first, unmodified, against the current
tree, and diffed id-by-id against round 2's published per-case table. **Zero cases flipped from
round 2's PASS to a naive FAIL.** This area's saved scripts, unlike several other areas' this round,
needed no correction at all — every one of round 2's published verdicts for `MON-`/`INC-`/`RPT-`/`BCH-`
reproduces exactly by re-running the identical script. **Harness-artefact count for this log: 0.**

Four cases flipped the other way — **FAIL in round 2, PASS on the unmodified rerun** — and each is a
genuine fix, confirmed below: `BCH-051`, `INC-011`, `INC-071`, `RPT-025`. In each case the harness
script's assertion logic is untouched from round 2 (confirmed by reading the `.py` file directly); only
the product's behaviour changed. One harness script (`inc_042_073.py`, `INC-071`) still carries a
stale inline comment from when the case failed ("`resolve does not call _residency_refusals — gate
bypassed`") — the comment text was never updated, but the boolean the script actually branches on
(`d71.delivery != Delivery.QUIET`) was, and is, correct; the comment is cosmetically wrong, not the
verdict.

The 74 `OPS-` cases have no saved script to diff against, so each was re-executed independently by
hand, following round 2's own method (real `helm`, a real Docker build, a real subprocess) rather than
its recorded conclusions. Three of round 2's fourteen `OPS-` `FAIL`s are now genuinely fixed
(`OPS-014`, `OPS-063`, `OPS-074`) and one round-2 `PASS` is now a genuine `FAIL` — **`OPS-003`, the one
regression this round found**, detailed below.

### `OPS-003` — a regression, and why it is not a new defect

`OPS-003`'s catalogue precondition is unchanged since round 2: `dialect=sqlite`, `replicaCount=1`, a
secret supplied. Round 2: `helm template` rendered a Deployment. Round 3, identical flags:

```
$ helm template deploy/helm/prama --set database.dialect=sqlite --set replicaCount=1 --set createSecretFrom=x
Error: execution error at (prama/templates/pvc.yaml:1:4): prama: database.dialect=sqlite needs
somewhere to write. readOnlyRootFilesystem is on, so set persistence.enabled=true (or
persistence.existingClaim). An emptyDir is deliberately not the default: it would start, and lose
the evidence ledger on every restart.
```

This is not a script bug and not a new gap — it is the direct, necessary side effect of the fix for
round 2's `OPS-014` ("a read-only-root, single-replica SQLite deployment has nowhere to write its
database"). `_helpers.tpl::prama.validate` now refuses SQLite unless `persistence.enabled` or
`persistence.existingClaim` is also set, exactly the second acceptable branch `OPS-014`'s own
catalogue Expected asked for ("either a data volume is mounted or SQLite is refused in this
configuration"). Adding `--set persistence.enabled=true` to the identical command renders cleanly,
with a `data` PVC and a matching volume mount. **This case is recorded `FAIL` against the catalogue's
literal, unchanged precondition — the rule requires that, and fabricating a passing precondition would
be worse — but the assessment is not-a-defect: the product got strictly more correct, and `OPS-003`'s
own precondition is now the thing that is stale.** A corrected `OPS-003` would add
`persistence.enabled=true` to its Steps.

## Counts

| | Count |
|---|---:|
| Total cases | 443 |
| PASS | 425 |
| FAIL | 16 |
| BLOCKED | 2 |
| **Pass rate** | **95.9%** (425/443) |

Round 2: 419 PASS / 22 FAIL / 2 BLOCKED — 94.6%. Round 3: 425 PASS / 16 FAIL / 2 BLOCKED — 95.9%.
**7 cases fixed, 1 regression, 15 unchanged failures** (round 2's 22 FAILs, minus 7 fixed, plus the 1
new regression = 16). Both round-2 `BLOCKED`s (`OPS-011`, `OPS-055`) remain blocked for the identical,
re-confirmed reasons — no live Kubernetes cluster, and no genuinely in-flight control run to kill.

## Regressions — a case that passed in round 2 and fails now

**1 found: `OPS-003`.** Full detail and judgement above (Method section) and in Failures below.
Every one of the other 442 cases either matches round 2's verdict or is a confirmed fix — no other
case moved from `PASS` to `FAIL` or `BLOCKED`.

## Fixes confirmed by direct execution

Seven of round 2's 22 FAILs are genuinely fixed, each reproduced with the specific counterfactual the
catalogue calls for:

- **`BCH-051`** — two systems (`SystemA`, `SystemB`) raising an identical alert (same dataset, column,
  time, detail, reference). Round 2: `len(blinding) == 1` — the second registration silently
  overwrote the first, both sharing one `blind_id`. Round 3: `len(blinding) == 2`, `idA == idB` (both
  still legitimately share the same blind hash, since `system` is deliberately excluded from it) but
  **both are retained** rather than one colliding with the other — `Blinding.register` no longer keys
  a plain dict solely on `blind_id`.
- **`INC-011`** — two unrelated findings sharing only a distant common upstream column, three days
  apart. Round 2: merged into one incident, `incident:warehouse.t`, with no time-window check applied.
  Round 3: `n_incidents == 2` — `_by_ancestor`'s grouping now applies the time window even when a
  finding lands in an existing ancestor group from the start, not only when `_merge_by_dataset` later
  folds two separately-built groups together.
- **`INC-071`** — a `Gate` configured to refuse an EU-jurisdiction alert's recipient region. Round 2:
  `dispatch()` correctly withheld it (`Delivery.QUIET`) but `resolve()` delivered the identical alert
  anyway (`Delivery.IMMEDIATE`). Round 3: `resolve()` also returns `Delivery.QUIET` — the residency
  gate is no longer bypassed on the resolution path.
- **`RPT-025`** — `rdarr.build`'s evidence root. Round 2: `pack.evidence_root` was the raw 2-tuple
  `('the_real_root_hash', 42)` returned by `period_root()`, never unpacked. Round 3:
  `pack.evidence_root` is the plain string `'the_real_root_hash'`, `type() is str` — `build()` now
  unpacks `root, count = await uow.evidence.period_root(...)`, matching its sibling `attest.py::build`.
- **`OPS-014`** — a read-only-root, single-replica SQLite deployment. Round 2: only `/tmp` was
  mounted; no write path existed for the database file. Round 3: `--set persistence.enabled=true`
  mounts a `data` PersistentVolumeClaim at the directory of the new `database.sqlite.path` default
  (`/var/lib/prama`); omitting persistence now refuses outright with a named error rather than
  rendering a deployment that cannot write. Both are acceptable per the catalogue's own Expected — see
  `OPS-003` above for the precondition this fix leaves stale.
- **`OPS-063`** — `_worst_verdict` on an unrecognised verdict string. Round 2:
  `_worst_verdict(['pass', 'pass', 'totally_unknown_verdict'])` returned `'pass'` — the unknown
  verdict silently ranked as the best outcome. Round 3: returns `'totally_unknown_verdict'` itself —
  confirmed against `git log` (commit `54ee00c`, "B4: nothing to report is not the same as nothing
  wrong", names `OPS-063` directly) and by reading the current source, which now ranks an unrecognised
  string worst (`len(order)`) rather than at index 0.
- **`OPS-074`** — the repository's commit history. Round 2: two commits (`07963c59`, `9fa19f16`)
  carried literal `Co-Authored-By: Claude` / `Claude-Session:` trailers, predating the commit-msg hook
  by 27 minutes and never scrubbed. Round 3: `git log --all --grep` for all three forbidden strings
  returns zero commits. History was rewritten: the same two logical commits (identical messages,
  identical timestamps, `2026-09-07 20:36:15` and `:30`) now exist under different hashes (`555c63b`,
  `461107a`) with the trailers stripped, and `git fsck --unreachable` plus `git rev-list --all
  --objects` confirm no reachable *or* dangling commit object anywhere in the repository still
  mentions Claude or Anthropic.

## Blocked

- **`OPS-011`** — no live Kubernetes cluster is available in this environment to observe real pod
  readiness/liveness behaviour under a database outage; only the probe configuration (`OPS-009`) was
  reviewed. Unchanged from round 2.
- **`OPS-055`** — staging a genuinely interrupted control run (a `SIGKILL` landing mid-execution)
  needs a control actually in flight at the moment of the kill; `run_prama_web.py` and the recovery
  mechanisms it exercises (`db/lease_provider.py`, `db/dao/evidence.py`) carry zero commits in the
  entire remediation range, so the identical blocker applies unchanged.

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
| `MON-053` | PASS | good_at=['a level that has shifted, on a series without trend', 'bounded or skewed quantities, like a null rate', 'multi-modal series, where the middle is empty', 'series with trend or momentum', 'a changed profile with an unchanged total'] blind_to=['a series with trend or autocorrelation, where yesterday predicts today and the middle of the window predicts nothing', 'a point inside the observed ... |
| `MON-054` | PASS | outside_01_seen=True |
| `MON-055` | PASS | {'robust_deviation': '1,300 against a typical 998, which is 6.9 robust deviations away', 'quantile_distance': '1,300 sits at the 100% point of what has been seen before', 'local_outlier_factor': 'the neighbourhood around 1,300 is 13.9 times sparser than the neighbourhoods of its nearest comparable days', 'forecast_residual': 'the recent trend implied about 1,006 and 1,300 arrived, which is 8.5 typ... |
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
| `MON-079` | PASS | explain='ds5.metric5 — 1,200 against a typical 1,000, which is 8.5 robust deviations away (compared against 58 observations where business_day=True, period_end=none. day_of_week had to be ignored to find enough comparable days — this monitor is less specific today than it would be with more history) p ≤ 0.0169 — more extreme than every one of the 58 comparable observations, so this is the smallest... |
| `MON-080` | PASS | found=True explain='ds6.metric6 — 6,000 against a typical 1,000, which is 765.2 robust deviations away (compared against 40 observations where business_day=True, period_end=none, day_of_week=6) p ≤ 0.0244 — more extreme than every one of the 40 comparable observations, so this is the smallest value this much history can express ⚠ not yet calibrated — this monitor has seen too little history to pro... |
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
| `MON-096` | PASS | {'isin': (0.0, 0.02, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'lei': (0.0, 0.05, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'cusip': (0.0, 0.02, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'sedol': (0.0, 0.05, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'iban': (0.0, 0.02, <PriorSource.SEMANTIC_TYPE: 'semantic_type'>), 'iso4217': (0.0, 0.001, <PriorSource.SEMANTIC_TYPE: 'semantic_t... |
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
| `INC-009` | PASS | n_incidents=2 identities={'nocol2', 'nocol1', 'withcol'} |
| `INC-010` | FAIL | n_incidents=1 ancestors=[Column(dataset='raw', name='feed')] |
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
| `INC-022` | PASS | order_a=['incident:gd1_0:g1_0', 'incident:gd1_1:g1_1', 'incident:gd1_2:g1_2', 'incident:gd1_3:g1_3', 'incident:gd2_0:g2_0', 'incident:gd2_1:g2_1', 'incident:gd2_2:g2_2', 'incident:gd2_3:g2_3', 'incident:gd3:lone'] order_b=['incident:gd1_0:g1_0', 'incident:gd1_1:g1_1', 'incident:gd1_2:g1_2', 'incident:gd1_3:g1_3', 'incident:gd2_0:g2_0', 'incident:gd2_1:g2_1', 'incident:gd2_2:g2_2', 'incident:gd2_3:... |
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
| `INC-073` | PASS | combos=[(<Delivery.IMMEDIATE: 'immediate'>, <Change.OPENED: 'opened'>, True), (<Delivery.IMMEDIATE: 'immediate'>, <Change.UNCHANGED: 'unchanged'>, False), (<Delivery.IMMEDIATE: 'immediate'>, <Change.WORSENED: 'worsened'>, True), (<Delivery.IMMEDIATE: 'immediate'>, <Change.IMPROVED: 'improved'>, True), (<Delivery.IMMEDIATE: 'immediate'>, <Change.RESOLVED: 'resolved'>, True), (<Delivery.DIGEST: 'dig... |
| `RPT-001` | PASS | scope='tenant:acme' start='2026-01-01' end='2026-01-31' in_content=True |
| `RPT-002` | PASS | hash_A=9d9b895ea74f hash_B=e2c19a064ead |
| `RPT-003` | PASS | fields={'evidence_records', 'scope', 'attester_id', 'coverage', 'signed_at', 'statement', 'supersedes', 'supersedes_because', 'version', 'period_end', 'period_start', 'evidence_root', 'attester_name', 'tenant_id', 'exceptions'} content_keys={'evidence_records', 'scope', 'attester_id', 'coverage', 'signed_at', 'statement', 'supersedes', 'version', 'supersedes_because', 'period_end', 'period_start',... |
| `RPT-004` | PASS | describe='40 of 100 control(s) produced a verdict; this covers 40% of the scope; 30 passed; 5 failed; 2 could not be established; 3 could not be executed; 60 never ran at all' |
| `RPT-005` | PASS | rate=0.0 is_complete=False |
| `RPT-006` | PASS | seal=c82913425111 is_clean=False is_qualified=True |
| `RPT-007` | PASS | is_qualified=True is_clean=True is_complete=False |
| `RPT-008` | PASS | n_exceptions=12 |
| `RPT-009` | PASS | params=['scope', 'attester_id', 'signed_at', 'statement', 'period_end', 'period_start', 'dispositions', 'uow', 'attester_name', 'tenant_id'] |
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
| `RPT-037` | PASS | stamp='2026-09-13 20:40:19Z' |
| `RPT-038` | PASS | fn_a=20260101-120000-report.html fn_b=20260101-120001-report.html |
| `RPT-039` | PASS | filename='20260101-120000-report-for-etc-münchen-spaces.html' |
| `RPT-040` | PASS | UndefinedError: 'undefined_var' is undefined |
| `RPT-041` | PASS | escaped=True raw_present=False |
| `RPT-042` | PASS | has_style_tag=True has_external_url=False |
| `RPT-043` | PASS | exists=True path=/tmp/tmpcci76vkw/nonexistent/nested/20260913-204019-declaration-pack.html |
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
| `RPT-083` | PASS | css_declares='38:    --bg-raised: rgba(127, 127, 127, .08);\n100:    background: var(--bg-raised);\n243:    --bs-tertiary-bg: var(--bg-raised);\n260:    --bs-btn-hover-bg: var(--bg-raised);\n263:    --bs-btn-active-bg: var(--bg-raised);' RAISED_GREY=#7F7F7F RAISED_ALPHA=0.08 (0x7F=127, matching rgba(127,127,127,.08)) computed_raised={'light': '#ECEDF1', 'dark': '#141829', 'crimson': '#EDEBEB', 'bm... |
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
| `BCH-015` | PASS | errors=['rate must be a share of rows in (0, 1], got 0', 'rate must be a share of rows in (0, 1], got 1.5', 'rate must be a share of rows in (0, 1], got -0.1'] |
| `BCH-016` | PASS | a corpus needs rows, got 0 |
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
| `BCH-034` | FAIL | docstring_says_easy_moderate_hard=True default='moderate' actual_corpus_values={'adversarial', 'ordinary', 'subtle', 'obvious'} -- do_not_agree, confirming the pre-flagged documentation defect |
| `BCH-035` | PASS | found=0 false_alarms=0 recall=0.0 precision=None |
| `BCH-036` | PASS | recall=1.0 precision=0.07397260273972603 |
| `BCH-037` | PASS | alerted_cols_sample=['account_id', 'amount', 'booking_date', 'control_total', 'counterparty_id', 'country', 'currency', 'iban', 'partyName', 'party_name', 'product', 'rate', 'value_date', 'window'] |
| `BCH-038` | PASS | schema_only_blind=('content', 'statistical', 'relational', 'temporal', 'semantic') |
| `BCH-039` | PASS | alerts=[('product', 'the column is missing from some rows')] |
| `BCH-040` | PASS | patterns_only_blind=('statistical', 'relational', 'temporal', 'semantic') |
| `BCH-041` | FAIL | stats_only_blind=('relational',) found_families={'structural', 'temporal', 'semantic', 'statistical', 'content'} |
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
| `OPS-001` | PASS | helm template (v3.15.4, fetched fresh into the scratchpad) refuses without existingSecret/createSecretFrom: 'no default session secret, because a default means every installation shares a key that is public in this chart' |
| `OPS-002` | PASS | helm template refuses sqlite+replicaCount=2: 'sqlite with replicaCount > 1 is corruption, not high availability' |
| `OPS-003` | FAIL | helm template --set database.dialect=sqlite --set replicaCount=1 --set createSecretFrom=x (the catalogue's literal precondition, unchanged since round 2) now FAILS to render: 'prama: database.dialect=sqlite needs somewhere to write. readOnlyRootFilesystem is on, so set persistence.enabled=true (or persistence.existingClaim)...'. Adding --set persistence.enabled=true renders cleanly. REGRESSION aga... |
| `OPS-004` | PASS | helm template refuses postgres with empty host: 'database.dialect=postgres needs database.postgres.host' |
| `OPS-005` | PASS | grep -rniE "secret\s*[:=]\s*['\"][a-zA-Z0-9]" deploy/helm/prama/ -> no hits; values.yaml existingSecret/createSecretFrom/postgres.existingSecret all empty by default; secret.yaml only renders when createSecretFrom is set and existingSecret is not |
| `OPS-006` | PASS | helm template with both existingSecret and createSecretFrom set: only Service+Deployment objects rendered, no Secret object (deployment.yaml references .Values.existingSecret directly) |
| `OPS-007` | PASS | helm template with a full postgres values set: PRAMA_SECURITY__SESSION_SECRET, PRAMA_DATABASE__DIALECT, PRAMA_WEB__ENABLED, PRAMA_DATABASE__POSTGRES__{HOST,PORT,DATABASE,USER} all present and correctly mapped to the values supplied |
| `OPS-008` | PASS | helm template with tenancy.defaultTenant empty: PRAMA_TENANCY__DEFAULT_TENANT absent (grep count 0); with tenancy.defaultTenant=acme: present with value 'acme' |
| `OPS-009` | PASS | helm template: both readinessProbe and livenessProbe use httpGet path /api/v1/health, port http; readiness initialDelaySeconds=5/period=10, liveness initialDelaySeconds=20/period=20 |
| `OPS-010` | PASS | src/prama/db/__init__.py::Database.health does execute `SELECT 1` against the live connection -- confirmed directly (not merely source-read, unlike round 2): the async postgres engine now constructs successfully against the live PostgreSQL 16 container (round 2's blocking DB-070/DB-072 issue no longer reproduces here), and pointing Database.health() at an unreachable postgres port raises Connectio... |
| `OPS-011` | BLOCKED | no live Kubernetes cluster is available in this environment to observe real pod readiness/liveness behaviour under a database outage; only the probe configuration (OPS-009) was reviewed -- same as round 2 |
| `OPS-012` | PASS | docker run --rm prama:qa-r3 id -> uid=10001(prama) gid=999(prama); helm template podSecurityContext runAsUser=10001/runAsNonRoot=true -- the two agree |
| `OPS-013` | PASS | helm template: containers[].securityContext.readOnlyRootFilesystem=true and a `tmp` emptyDir volume mounted at /tmp |
| `OPS-014` | PASS | FIXED (round 2: FAIL). helm template --set database.dialect=sqlite --set replicaCount=1 --set createSecretFrom=x --set persistence.enabled=true now mounts a `data` PersistentVolumeClaim at /var/lib/prama (dir of the new database.sqlite.path default); without persistence.enabled it refuses outright with a named error rather than rendering a deployment with nowhere to write. Either branch satisfies ... |
| `OPS-015` | PASS | helm template securityContext.allowPrivilegeEscalation=false, capabilities.drop=[ALL], podSecurityContext.seccompProfile.type=RuntimeDefault |
| `OPS-016` | PASS | docker run --entrypoint sh prama:qa-r3 -c 'ls /opt/prama/schema': postgres.sql sqlite.sql; PRAMA_DATABASE__SCHEMA_DIR=/opt/prama/schema set in the image env |
| `OPS-017` | PASS | docker run --entrypoint python3 prama:qa-r3 --version -> Python 3.13.15; .python-version contains '3.13' -- same minor version |
| `OPS-018` | PASS | docker run --entrypoint sh prama:qa-r3 -c 'dpkg -l \| grep -i gcc' shows only gcc-14-base/libgcc-s1 (runtime C library remnants of python:3.13-slim itself, not a compiler); no cc/gcc binary on PATH; the Dockerfile's runtime stage COPYs only the built venv from the build stage and never runs pip/apt-get itself |
| `OPS-019` | PASS | docker run --rm prama:qa-r3 (no secret set) with a full, unpiped capture: prints the banner, the console URLs and the no-tenant notice, THEN 'error: security.session_secret is empty, and Prama will not start without it' / 'next: Set security.session_secret in config/application.local.yaml (git-ignored), or export PRAMA_SECURITY__SESSION_SECRET...'; exit 1. (An initial run piped through `head -5` l... |
| `OPS-020` | PASS | docker inspect prama:qa-r3 Healthcheck.Test: CMD-SHELL against http://127.0.0.1:8080/api/v1/health; chart's probes use the same path on port 8080 -- both agree |
| `OPS-021` | PASS | fresh named Docker volume mounted at /data, `touch /data/testfile` as the container's default user succeeded, owned prama:prama; Dockerfile textually chowns /data before declaring VOLUME ["/data"] (confirmed by line number: chown at line 54, VOLUME at line 56) |
| `OPS-022` | PASS | Chart.yaml appVersion: "0.1.0", image.tag: "0.1.0"; src/prama/version.py VERSION = "0.1.0" -- all three agree |
| `OPS-023` | PASS | Chart.yaml annotation prama.io/upgrade-requires: "prama db verify"; ran `prama db verify` directly against a live sqlite database -- prints 'schema verified ... no drift', exit 0 when clean, and fails loudly on drift (OPS-024) |
| `OPS-024` | PASS | built a sqlite database with the real schema, dropped the `tenant` table with raw sqlite DDL to simulate drift, then started a real `prama serve` process against it: the FastAPI lifespan's `await db.start()` raised `SchemaDriftError: the live sqlite database does not match schema/sqlite.sql` -- 'Application startup failed. Exiting.', exit 3, before any request could be served. Also confirmed with ... |
| `OPS-025` | PASS | confirmed WAL mode active (`PRAGMA journal_mode` -> 'wal', -wal file present); wrote 5 real evidence records via EvidenceDao while a second connection held an uncommitted in-flight write, took a WAL-safe backup with Python's sqlite3 online backup API mid-write, then rolled the holder connection back; `Database.verify()` on the restored copy reports zero drifts. deploy/README.md still documents no ... |
| `OPS-026` | PASS | the same 5-record chain built for OPS-025, verified via `EvidenceDao.verify()` before backup (breaches=(), head/merkle_root recorded) and again against the restored copy after backup+restore: identical head and merkle_root, breaches=() -- the chain verifies identically after restore |
| `OPS-027` | PASS | reproduced the exact `false \| tail -1` pattern: without `set -o pipefail` the pipeline exits 0 (tail's own success); with `set -o pipefail` (as scripts/gate.sh line 9 declares) the same pipeline exits 1 |
| `OPS-028` | PASS | reproduced each fault directly: a lint fault (unused import) -> `ruff check` exit 1; a type fault (str passed where int expected) -> `mypy` exit 1 naming the arg-type error; a 1600-code-line file -> `python scripts/check_file_length.py` exit 1 naming the file and '1600 lines' |
| `OPS-029` | PASS | same pipefail mechanism as OPS-027: `set -o pipefail; (echo err; exit 1) \| tail -1` exits 1, confirming `mypy src \| tail -1` does not mask a failure under gate.sh's `set -euo pipefail` |
| `OPS-030` | PASS | a file with exactly 1500 significant lines -> check_file_length.py exit 0; a file with exactly 1501 -> exit 1, message names the file and '1501 lines' |
| `OPS-031` | PASS | a 3800-physical-line file (998-line module docstring + 1400 code lines interleaved with ~1400 comment lines) -> check_file_length.py exit 0, confirming comments/docstrings/blanks are excluded from the 1500-line count |
| `OPS-032` | PASS | a 1600-line offender placed under synthetic `.venv/pkg/`, `node_modules/pkg/` and `prama-web/src/` -- check_file_length.py exits 0 (skipped) for all three |
| `OPS-033` | PASS | `python scripts/check_file_length.py schema/sqlite.sql schema/postgres.sql` exits 0; both files are 1047 physical lines each and pass because SQL comments are excluded from the significant-line count |
| `OPS-034` | PASS | .github/workflows/gate.yml's `gate` job's only substantive step is `./scripts/gate.sh` after activating the venv; no lint/type/test command is restated in the workflow |
| `OPS-035` | PASS | all three jobs (gate, conformance, accessibility) in gate.yml run `uv python install "$(cat .python-version)"` before building their venv |
| `OPS-036` | PASS | gate.yml's conformance job declares a real `postgres:16-alpine` service and sets `PRAMA_TEST_POSTGRES_DSN` unconditionally; reproduced locally against the live PostgreSQL 16 container on the same DSN shape -- `pytest tests/backend/test_engine_conformance.py`: 41/41 passed (round 2 saw 37/39, with 2 failing on an unrelated cross-engine modulo-on-negative disagreement out of this catalogue's OPS sco... |
| `OPS-037` | PASS | with PRAMA_TEST_POSTGRES_DSN unset, `pytest tests/connect/sql/test_postgres_live.py -rs`: all 10 postgres-only tests report SKIPPED, each naming 'set PRAMA_TEST_POSTGRES_DSN to run these' -- loud, not silent; gate.yml hardcodes the postgres service and DSN unconditionally, so this skip path is structurally unreachable in CI |
| `OPS-038` | PASS | gate.yml's `accessibility` job runs `playwright install --with-deps chromium` then `pytest -q tests/web/test_axe.py`, exactly as documented |
| `OPS-039` | PASS | gate.yml: `on: push: branches: [main, develop]` and `pull_request: branches: [main, develop]` |
| `OPS-040` | PASS | with `uv` genuinely absent from PATH (`command -v uv` exits 1 in the normal environment), gate.sh's exact lock-check snippet prints 'uv not installed; skipping the lock-file check' and the enclosing `if` exits 0 |
| `OPS-041` | PASS | fetched a real `uv` 0.12.13 binary; `uv lock --check` against the untouched repository (copied to a scratch directory): exit 0. Added `requests>=2.0` to the scratch copy's pyproject.toml without relocking: `uv lock --check` under `set -o pipefail` -> 'error: The lockfile at `uv.lock` needs to be updated, but `--check` was provided.', exit 1 |
| `OPS-042` | PASS | `python3 scripts/generate_docs.py --check` on the untouched tree: exit 0, 'every generated document matches the code (2 checked)'; on a scratch copy with one line hand-appended to docs/operations/cli-reference.md: exit 1, 'these generated documents no longer match the code: docs/operations/cli-reference.md' |
| `OPS-043` | PASS | `python run_prama_web.py` (in a scratch copy, no secret configured, full unpiped capture): prints 'security.session_secret is empty, and Prama will not start without it.' and 'Run once with --init-secret, or export PRAMA_SECURITY__SESSION_SECRET.' (both named), exit 1 |
| `OPS-044` | PASS | `python run_prama_web.py --init-secret` (scratch copy of the repo, outside .git so git-status could not be checked directly, but the same path the real repo's .gitignore matches): wrote config/application.local.yaml only (a `security: session_secret: "..."` block with an explanatory comment); confirmed against the real repo's .gitignore pattern `config/*.local.yaml`, which matches this filename |
| `OPS-045` | PASS | running --init-secret a second time against the now-existing local file: 'config/application.local.yaml already sets session_secret' / 'Leaving it alone. Edit the file if you meant to change it.', exit 1; file content byte-for-byte unchanged (verified by direct comparison) |
| `OPS-046` | PASS | called `_write_local_secret()` twice on the same host with the file removed between calls: two different 64-character `token_urlsafe(48)` values |
| `OPS-047` | PASS | `python run_prama_web.py --prepare` against a fresh sqlite path, run twice: first run 'schema applied · estate acme-bank · <id>' / '(created)'; second run the identical id with no '(created)' line -- found, not recreated |
| `OPS-048` | FAIL | unchanged from round 2. `python run_prama_web.py --prepare` against a live PostgreSQL (the real 127.0.0.1:55432 container) with no confirmation flag and no prompt: silently applied the schema and created a tenant -- 'schema applied · estate acme-bank · <id>' / '(created)', then proceeded to serve on postgres. `_prepare` still calls `database.initialise()` unconditionally regardless of dialect; the... |
| `OPS-049` | PASS | `python run_prama_web.py` with no default tenant: prints 'No tenant is configured, so every console page will redirect to a sign-in that does not exist yet. Re-run with --prepare, or: prama tenant create acme-bank --name ...' |
| `OPS-050` | PASS | source-confirmed (run_prama_web.py untouched by remediation): `--prepare`'s tenant is applied by building a fresh `ConfigurationBuilder().with_defaults(config.raw()).with_mapping(..., name="run-prama-web")`, never by mutating the existing `config` object in place |
| `OPS-051` | PASS | started `run_prama_web.py --prepare` with stdout redirected to a file; after 1 second (well before the server would otherwise block on serving), the file already contained the Console/API/Docs URL lines -- `sys.stdout.flush()` before `uvicorn.run()` does its job |
| `OPS-052` | PASS | set `sys.modules['uvicorn'] = None` before calling `run_prama_web.main()` (forces the internal `import uvicorn` to raise ImportError): printed 'the HTTP server is not installed.' / 'Install it: pip install -e ".[serve]".', returned 1; pyproject.toml's `[project.optional-dependencies]` does name the extra `serve = ["uvicorn[standard]>=0.30"]` |
| `OPS-053` | PASS | source-confirmed: run_prama_web.py imports and calls `load_configuration`, `Database.from_config`, and `create_app` -- the same CLI code paths -- and defines no application-assembly logic of its own |
| `OPS-054` | PASS | started a prepared server on a scratch sqlite db, waited for 'Uvicorn running' in its log, sent SIGTERM: the process's own log shows 'Shutting down' -> 'Waiting for application shutdown' -> 'Application shutdown complete' -> 'Finished server process', and the process was gone shortly after |
| `OPS-055` | BLOCKED | same limitation as round 2: staging a genuinely interrupted control run (a SIGKILL that lands mid-execution) needs a control actually in flight at the moment of the kill; run_prama_web.py and the recovery mechanisms it exercises (db/lease_provider.py, db/dao/evidence.py) carry zero commits in the remediation range, so the same blocker applies unchanged |
| `OPS-056` | PASS | `MemoryTracer().span("test.span")` raising ValueError inside the block: the span was still recorded (1 span), with `error == 'ValueError: boom'` and a non-negative `duration_ms`; the exception propagated out of the `with` block |
| `OPS-057` | PASS | `NullTracer().span(...)` used with `'opentelemetry' in sys.modules` == False -- confirming no OpenTelemetry import is required to exercise the default tracer |
| `OPS-058` | PASS | `grep -rn 'span("prama\.' src/` (a literal string passed to `.span(`) returns no hits across `src/prama` -- every call site uses one of the module's span-name constants |
| `OPS-059` | PASS | `with tracer.span("test.span2") as s: s.set(rows=42)` -- the recorded span's `attributes` dict contains `{'rows': 42}` |
| `OPS-060` | PASS | built a real Lineage START+COMPLETE event pair from an EvidenceRecord carrying `metrics={'scanned_rows': 100.0, 'violating_rows': 5.0}`; the serialised event's JSON contains no '100.0', no '5.0' and no 'scanned_rows' anywhere -- only dataset/column names and the boolean `success` outcome |
| `OPS-061` | PASS | `EventType.for_verdict(v)` for v in (pass, fail, error, aborted) -> COMPLETE, COMPLETE, FAIL, FAIL |
| `OPS-062` | PASS | `_worst_verdict(['pass']*99 + ['error'])` returned 'error' |
| `OPS-063` | PASS | FIXED (round 2: FAIL). `_worst_verdict(['pass', 'pass', 'totally_unknown_verdict'])` now returns 'totally_unknown_verdict', not 'pass' -- confirmed by git log (commit 54ee00c, 'B4: nothing to report is not the same as nothing wrong') and by reading the current source: `order.index(v) if v in order else len(order)` ranks an unrecognised verdict worst, not at index 0 |
| `OPS-064` | PASS | a serialised RunEvent carries eventType, eventTime, run.runId, job.namespace, job.name, inputs, producer, schemaURL; the nested dataQualityAssertions facet carries _producer and _schemaURL |
| `OPS-065` | PASS | `Lineage.started(job="job2", datasets=("ds1",))` emitted a run id starting with 'run:'; `Lineage.finished(..., run_id=<that id>)`'s COMPLETE event reused the identical run_id |
| `OPS-066` | PASS | `Lineage(namespace=...)` constructed with no emitter argument: `._emitter` is a `NullEmitter` instance; `.started(job=...)` raised nothing |
| `OPS-067` | PASS | `PRODUCER == 'https://prama.dev/openlineage/0.1.0'`; VERSION ('0.1.0') is a substring of PRODUCER |
| `OPS-068` | PASS | built a real, correctly-chained 10-record evidence bundle via `Archivist.bundle()`, wrote manifest.json+evidence.ndjson, then ran `python3 -I scripts/verify_evidence.py <bundle-dir>` (confirmed the `-I` isolation genuinely blocks `import prama`): all 7 checks [PASS], 'Every check passed.', exit 0 |
| `OPS-069` | PASS | flipped one record's `verdict` field in the ndjson file without recomputing any hash, ran the same isolated verify_evidence.py: '[FAIL] every record's content hashes to its stored content_hash / record 3: content_hash is 48bcf84c..., the bytes give 32fccdb3...' and '[FAIL] the evidence file is the one the manifest describes' -- exit 1, failing record's sequence (3) named exactly |
| `OPS-070` | PASS | `pytest tests/architecture -v`: 244/244 architecture tests passed, including the import-scanning tests confirming only prama/db/** imports SQLAlchemy |
| `OPS-071` | PASS | same architecture-test run: the no-model-verdict guard tests all passed |
| `OPS-072` | PASS | same architecture-test run: the no-migrations guard tests (`test_ddl_is_never_emitted_from_orm_metadata`, `test_no_migration_tooling_is_present`) passed |
| `OPS-073` | PASS | `git ls-files config/ deploy/ .github/ \| xargs grep -lIE ...` surfaces only deploy/README.md's `--from-literal=session-secret="$(python -c '...token_urlsafe...')"` command template (generates a secret at deploy time, not a literal one); config/application.yaml's tracked `security.session_secret` is the empty string. A broader whole-tree grep (matching round 2's scope) surfaces many more hits than... |
| `OPS-074` | PASS | FIXED (round 2: FAIL). `git log --all --grep='Co-Authored-By: Claude'`, `--grep='Claude-Session:'` and `--grep='Generated with [Claude'` all return zero commits now. Round 2's two offending commits (07963c59, 9fa19f16) no longer exist under those hashes; `git log --oneline` shows commits with the identical messages and timestamps ('Add complete Prama analysis...', 2026-09-07 20:36:15 and its merge... |

## Failures

### OPS-003 · SQLite with one replica is allowed — REGRESSION (not a defect)
- **Round 3:** new. Round 2 PASS, round 3 FAIL, against the catalogue's unchanged literal
  precondition. See the Method section above for the full account.
- **Expected:** `helm template` with `dialect=sqlite`, `replicaCount=1`, a secret supplied — renders
- **Observed:** `helm template deploy/helm/prama --set database.dialect=sqlite --set replicaCount=1
  --set createSecretFrom=x` now refuses: `"prama: database.dialect=sqlite needs somewhere to write.
  readOnlyRootFilesystem is on, so set persistence.enabled=true (or persistence.existingClaim). An
  emptyDir is deliberately not the default: it would start, and lose the evidence ledger on every
  restart."` Adding `--set persistence.enabled=true` to the identical command renders cleanly (a
  `data` PVC plus a matching `volumeMounts` entry).
- **Reproduce:**
  ```
  helm template deploy/helm/prama --set database.dialect=sqlite --set replicaCount=1 \
    --set createSecretFrom=x
  # now fails; add --set persistence.enabled=true to render
  ```
- **Severity:** P2 (matches OPS-003's original priority)
- **Assessment:** not-a-defect / stale catalogue precondition. This is the necessary, correct side
  effect of the fix for round 2's `OPS-014` (P1, a genuine defect: a read-only-root, single-replica
  SQLite deployment previously had nowhere to write its database). `_helpers.tpl::prama.validate`
  now refuses SQLite without `persistence.enabled` or `persistence.existingClaim`, which is exactly
  the second of `OPS-014`'s two catalogue-acceptable outcomes ("either a data volume is mounted, or
  SQLite is refused in this configuration"). `OPS-003`'s own precondition — sqlite, one replica, a
  secret, and nothing else — no longer describes a configuration the chart will render, because that
  configuration is now, correctly, one of the two the chart refuses. The product did not regress; the
  test's precondition did. A corrected `OPS-003` adds `persistence.enabled=true` to its Steps, at
  which point it passes exactly as before.

### MON-014 · Wasserstein's materiality threshold is the reference's spread
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** a shift of exactly one standard deviation is not material (`False`); exactly two is (`True`)
- **Observed:** at ten different seeds, a shift of exactly one standard deviation was material in roughly half the trials (`True` in 6 of 10, `False` in 4 of 10); the two-sigma case was always material as expected
- **Reproduce:**
  ```
  python3 -c "
  import random
  from prama.monitor.drift import _wasserstein, _spread
  for seed in range(10):
      random.seed(seed)
      ref = [random.gauss(1000,50) for _ in range(500)]
      std = _spread(ref)
      cur1 = [v + std for v in ref]
      m1 = _wasserstein(ref, cur1)
      print(seed, 'diff=', m1.value - std, 'material=', m1.material)
  "
  ```
- **Severity:** P2
- **Assessment:** not-a-defect. The code's threshold is `distance > scale`, a strict inequality, and at a genuine mathematical tie the comparison is inherently undefined in floating point: `distance` (computed by pairing sorted values) and `scale` (`_spread(reference)`) are two different arithmetic paths to numbers that are equal only in exact real arithmetic, and IEEE-754 rounding puts the computed `distance` a few parts in 10¹³ above or below `scale` unpredictably depending on the data. This is not a flaw in the drift module — any boundary test built on an exact float tie has this property — and the code's own two-sigma case (which is nowhere near the tie) behaves exactly as documented. The catalogue's precondition ("a shift of exactly one standard deviation") cannot be made to reliably resolve one way in floating point; a corrected case would need to accept either answer at the tie, or use a deliberately-just-below/just-above construction instead of an exact tie.


### MON-018 · The Wilson-Hilferty normalisation is right at the threshold
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** a chi-square statistic at the exact 5% critical value for nine degrees of freedom normalises to a value on the boundary of `material` (i.e. close to whatever the code compares against), "matching the exact chi-square within a few percent"
- **Observed:** at the true chi-square(9) 5% critical value (16.919), the Wilson-Hilferty-normalised statistic is 1.647 — matching the standard normal's 95th percentile (1.645) to within 0.1%, exactly as the approximation should. But the code's own materiality threshold is `normalised > 1.96`, not `1.645` — 1.96 is the standard normal's *97.5th* percentile (the two-sided 95% value), roughly 19% away from 1.647.
- **Reproduce:**
  ```
  python3 -c "
  import math
  degrees = 9
  statistic = 16.919  # true chi2(9), 5% upper-tail critical value
  normalised = ((statistic/degrees)**(1/3) - (1-2/(9*degrees))) / math.sqrt(2/(9*degrees))
  print('normalised at true 5% chi-square boundary:', normalised, '(code compares this against 1.96)')
  "
  ```
- **Severity:** P3
- **Assessment:** defect. The Wilson-Hilferty approximation itself is accurate (confirmed: 1.647 vs the true 1.645, agreement to 0.1%). The bug is the choice of constant it is compared against: `1.96` is the two-sided 95% normal critical value, not the one-sided 95% value (`1.645`) that corresponds to a true 5% upper-tail chi-square test — the same convention the module's KS measure explicitly uses (`1.36 * sqrt(...)`, its own documented "5% critical value for the two-sample test"). Using 1.96 makes the chi-square measure's actual materiality threshold sit around the 2.5% significance level rather than 5%, roughly halving its sensitivity relative to what the other four measures in the same `compare()` call are calibrated to. This is a real, if modest, inconsistency in the ensemble's five measures rather than a documentation slip.


### MON-064 · A declared driver is dropped last
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** the declared driver survives every relaxation step, "including the final fall-back"
- **Observed:** with a thin history that forces the grouping all the way to the final "compare against everything" fallback, the returned key is `SeasonKey()` — completely empty, with no `declared:rare` facet — and `relaxed` (`['hour', 'day_of_week', 'period_end', 'business_day']`) never lists `Facet.DECLARED` either
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from datetime import datetime
  from prama.core.calendars import WEEKDAYS
  from prama.monitor.season import SeasonalModel, day_of_month_driver, Facet
  m = SeasonalModel(calendar=WEEKDAYS, drivers={'rare': day_of_month_driver(31)}, intraday=True)
  thin = [datetime(2026,1,5,9,0), datetime(2026,1,6,10,0), datetime(2026,1,7,11,0), datetime(2026,1,8,12,0), datetime(2026,1,9,13,0)]
  g = m.group(thin, datetime(2026,1,12,14,0))
  print('key facets:', g.key.facets)
  print('relaxed:', [f.value for f in g.relaxed])
  print('DECLARED reported as relaxed?', Facet.DECLARED in g.relaxed)
  "
  ```
- **Severity:** P1
- **Assessment:** defect. `SeasonalModel._relaxation_order()` builds its `order` list from `[Facet.HOUR, Facet.DAY_OF_WEEK, Facet.PERIOD_END, Facet.BUSINESS_DAY]` — `Facet.DECLARED` is never a member of that list, so it is never stepped through by `_steps()`/`_relax_one()` and therefore never appears in `relaxed`, which reads as "the declared driver was never touched." But `SeasonalModel.group()`'s final fallback (reached when every relaxation step still leaves too few members) returns `Grouping(key=SeasonKey(), ...)` — a totally empty key, which silently drops the declared-driver facet along with everything else. The module's own docstring is explicit about exactly this failure mode: "discarding a declaration to make a sample bigger is exactly the trade this system exists not to make silently" — and that is precisely what happens in the one path (`Grouping(key=SeasonKey(), ...)` on line ~285 of `season.py`) that was not built to go through `_relax_one`.


### MON-092 · An observation for an unknown segment is dropped silently
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** either the drop is reported as unjudgeable, or it is documented
- **Observed:** an `Observation` whose `segment` has no corresponding `Monitor` in a `SegmentedMonitor` produces zero verdicts — `FleetReport(verdicts=())` — with no record anywhere that anything was dropped
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from datetime import datetime
  from prama.monitor.fleet import SegmentedMonitor, Observation
  sm = SegmentedMonitor('ds','metric', ['A','B'], adaptive=False)
  report = sm.judge([Observation(value=1.0, at=datetime(2026,1,1), segment='UNKNOWN')], [])
  print('verdicts:', len(report.verdicts))
  "
  ```
- **Severity:** P2
- **Assessment:** defect. `SegmentedMonitor.judge()`'s list comprehension (`for observation in observations if observation.segment in self._monitors`) filters silently, exactly as the catalogue's own Why note anticipated ("the comprehension filters it out with no record"). A new legal entity, counterparty or other segment value appearing in live data — the exact case the catalogue calls out as "exactly the thing a segmented monitor should notice" — currently vanishes without appearing in `unjudgeable`, in a log, or anywhere else visible to an operator.


### MON-105 · A one-sided volume range is honoured
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** `low` set, `high` infinite; "the explanation renders infinity readably rather than as `inf`"
- **Observed:** the built prior's explanation reads *"the declared rhythm says a daily delivery carries between 1,000 and inf records"* — the literal Python string `"inf"` appears in a sentence a business owner reads
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from prama.monitor.coldstart import ColdStart
  from prama.derive.declaration import DatasetDeclaration
  from prama.semantic.values import Rhythm, Frequency
  decl = DatasetDeclaration(name='ds', rhythm=Rhythm(frequency=Frequency.DAILY, expected_volume_min=1000))
  p = ColdStart().for_volume(decl)
  print(p.explanation)
  "
  ```
- **Severity:** P2
- **Assessment:** defect. `ColdStart.for_volume()` builds `high = float(rhythm.expected_volume_max if ... else float('inf'))` and then formats it with the *same* unconditional `f"{high:,.0f}"` used for a bounded value — there is no branch for the unbounded case anywhere in the function. This is precisely the failure pattern the codebase already recognised and fixed once, in `Changepoint.describe()` (MON-024, which does special-case an infinite ratio) — the same pattern was not carried over here.


### MON-114 · `with_alert` and `with_outcome` keep the arithmetic consistent
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** `confirmed <= reviewed <= raised`, always
- **Observed:** after 5 `with_alert()` calls followed by 7 `with_outcome(Outcome(confirmed=True))` calls (more outcomes than there were unreviewed alerts to attach them to), the resulting `PrecisionHistory` has `raised=5, confirmed=7, reviewed=5` — `confirmed > reviewed`
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from prama.monitor.cards import PrecisionHistory, Outcome
  h = PrecisionHistory()
  for _ in range(5): h = h.with_alert()
  for _ in range(7): h = h.with_outcome(Outcome(confirmed=True))
  print(h)
  print('confirmed <= reviewed?', h.confirmed <= h.reviewed)
  "
  ```
- **Severity:** P2
- **Assessment:** defect. `PrecisionHistory.with_outcome()` floors `unreviewed` at zero (`max(0, self.unreviewed - 1)`) but unconditionally increments `confirmed` regardless of whether there was an unreviewed alert left to attach the outcome to — exactly the gap the catalogue's own Why note names: "`with_outcome` decrements `unreviewed` with a floor of zero but does not check that an alert exists to review — a stray outcome would make `confirmed` exceed `reviewed`." A model card's own headline arithmetic (`describe()` divides `confirmed` by `reviewed` to print a percentage) can therefore print a precision above 100%.


### MON-135 · The changepoint mechanism beats forgetting on a level shift
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** on the level-shift regime, the `CHANGEPOINT` mechanism's calibration error is lower than `WEIGHTED`'s
- **Observed:** at the benchmark's default seed (17) and count (700), `changepoint` scores calibration error **0.0498** on `level_shift`, while `weighted` scores **0.0138** — weighted is more than 3.5× better, and `adaptive` (0.0031) is best of all
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from prama.monitor.benchmark import measure, REGIMES, Mechanism
  regime = [r for r in REGIMES if r.name=='level_shift'][0]
  print('changepoint', measure(regime, Mechanism.CHANGEPOINT, seed=17).calibration_error)
  print('weighted', measure(regime, Mechanism.WEIGHTED, seed=17).calibration_error)
  print('adaptive', measure(regime, Mechanism.ADAPTIVE, seed=17).calibration_error)
  "
  ```
- **Severity:** P1
- **Assessment:** defect. This directly contradicts both the module's design doctrine ("the changepoint mechanism … the mechanism the other three cannot substitute for … forgetting is too slow") and the specific claim in the catalogue's Why. It does not contradict the wave's headline acceptance criterion (MON-134's `every_regime_has_a_mechanism` still holds — `adaptive` covers `level_shift` at 0.0031, comfortably under the 0.02 target — so the benchmark's overall promise is intact), but the specific, named mechanism-to-regime pairing the module's own docstring makes ("the case the [changepoint] mechanism exists for") is measurably false at the benchmark's own default configuration. Either `find_changepoint`'s detection is too slow/conservative on this regime's actual step size, or the regime's default parameters no longer isolate the case the mechanism was built to win.


### INC-010 · The deepest shared ancestor is chosen, not the broadest
- **Round 3:** unchanged from round 2; re-confirmed by direct execution. Not overlooked — `correlate.py`
  *was* touched in this range, by `03dcf7c` ("B10: an incident is a claim that findings share one
  cause"), the same commit that fixed `INC-011`. Its message records `INC-010` as **deliberately not
  fixed** (logged as `Q-65`): the author tried preferring depth in `_shared_ancestor`, which broke the
  module's own stated acceptance test (`test_one_upstream_defect_produces_one_incident`, where one feed
  column fanning out to 48 findings has no ancestor *but* the raw feed, so naming it is correct there).
  The two requirements — name the nearest ancestor, and don't split one upstream cause into 48 incidents
  — genuinely conflict, and the fix was reverted "rather than left half-done" pending a product decision
  about alert volume. `_shared_ancestor` is unchanged from round 2 and the case still fails identically.
- **Expected:** with a chain where everything shares a raw feed but two findings share a nearer derived column, the incident names the derived column
- **Observed:** all three findings (two sharing the derived column, one sharing only the raw feed) merge into **one** incident whose `common_ancestor` is the **raw feed**, not the derived column
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from datetime import datetime
  from prama.lineage.graph import Column, LineageGraph, Edge
  from prama.incident.correlate import Correlator, Finding
  col = lambda ds, name: Column(dataset=ds, name=name)
  base = datetime(2024,1,1,6,0)
  g = LineageGraph()
  g.add(Edge(source=col('raw','feed'), target=col('mid','derived')))
  g.add(Edge(source=col('mid','derived'), target=col('ds1','a')))
  g.add(Edge(source=col('mid','derived'), target=col('ds2','b')))
  g.add(Edge(source=col('raw','feed'), target=col('ds3','c')))
  findings = [Finding(identity='f1',dataset='ds1',column='a',at=base), Finding(identity='f2',dataset='ds2',column='b',at=base), Finding(identity='f3',dataset='ds3',column='c',at=base)]
  corr = Correlator(graph=g).correlate(findings)
  for inc in corr.incidents:
      print(inc.common_ancestor, [f.identity for f in inc.findings])
  "
  ```
- **Severity:** P1
- **Assessment:** defect. `_shared_ancestor()` picks `max(counts, key=lambda key: (counts[key], len(key)))` — it ranks primarily by **how many other findings** share a candidate ancestor, and only uses depth (`len(key)`) as a tiebreaker when the counts are equal. Here `raw.feed` is shared by *two* other findings (f2 via the derived column's own ancestry, and f3 directly) while `mid.derived` is shared by only *one* (f2) — so the vote-count comparison prefers the broader, shallower ancestor over the nearer one, exactly the "everything shares 'the raw feed' eventually" failure the module's own docstring says this function exists to avoid.


### INC-072 · Router state does not leak between tenants
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** two tenants with identically-shaped alerts on the same dataset name are not deduplicated against each other
- **Observed:** dispatching an alert with identical `dataset`/`fault`/`identity` twice through **one** `Router` instance (standing in for two tenants, since neither `Alert` nor `Router` carries a tenant field) produces `Change.OPENED` then `Change.UNCHANGED` — the second is treated as a repeat of the first
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from datetime import datetime, timedelta
  from prama.alert.route import Router, Alert, Fault, Role
  router = Router({('dsA', Role.CUSTODIAN): 'custA'})
  a1 = Alert(identity='same_id', dataset='dsA', fault=Fault.ARRIVAL, what='x', severity=0.6, at=datetime(2026,1,1))
  a2 = Alert(identity='same_id', dataset='dsA', fault=Fault.ARRIVAL, what='x', severity=0.6, at=datetime(2026,1,1,0,1))
  print(router.dispatch(a1).change, router.dispatch(a2).change)
  "
  ```
- **Severity:** P1
- **Assessment:** defect, with a caveat. `Alert.fingerprint` hashes only `dataset|fault|identity` — no tenant is in scope anywhere in `alert/route.py`, so a `Router` shared across tenants (a plausible shape for a background worker processing an estate of many tenants with one router instance) would silence one tenant's alert because another tenant's looked the same, exactly as the catalogue's Why note describes. The caveat: no production call site currently instantiates `Router` outside tests (`grep -rn "Router(" src/prama/` finds no construction sites beyond the module itself and unrelated `APIRouter` objects), so this module has not yet been wired into a scheduler where the risk would actually manifest — it is a real gap in the class's own guarantees, not yet a live incident.


### RPT-072 · Fill and text colours are separate and meet different thresholds
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** every dimension's fill colour is at or above 3.0:1 against the light surface
- **Observed:** five of the eight raw `DIMENSION_HEX` fills fail 3.0:1 against `#FFFFFF`: accuracy 2.63:1, completeness 2.61:1, consistency 2.18:1, timeliness 1.92:1, uniqueness 2.73:1
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from prama.report.palette import DIMENSION_HEX
  from prama.report.contrast import ratio, NON_TEXT
  for name, hexcolour in DIMENSION_HEX.items():
      r = ratio(hexcolour, '#FFFFFF')
      print(name, round(r,2), 'meets 3:1' if r >= NON_TEXT else 'FAILS 3:1')
  "
  ```
- **Severity:** P1
- **Assessment:** defect. `report/themes.py::Theme.fills()` *does* derive WCAG-1.4.11-safe fills via `_legible(value, NON_TEXT)` (confirmed separately, RPT-081 passes cleanly on every theme), but that derivation is a `themes.py`-only mechanism. `report/palette.py::Palette.dimension()` — used directly by the `SCREEN`/`PRINT` palettes that `charts.py` actually calls — returns the *raw* `DIMENSION_HEX` value un-derived, both as the literal PRINT colour and as the `var(--dim-x, #hex)` fallback for SCREEN. The module's own docstring names exactly this gap as a known problem to be solved ("Accuracy Teal on white is 2.63:1: fine as a large area, illegible as a word … Rather than change the brand or ship unreadable text, the readable variant is derived") — but that solution lives only in `themes.py`, never in `palette.py` itself. Anywhere the raw palette is the effective colour — a PDF/print render (`PRINT`, which never uses a CSS variable), or an SVG extracted from the page (the SCREEN fallback, which the module's own docstring says exists precisely because "an SVG pulled out of the page … keeps its colours") — five of the eight dimension fills are below the WCAG 1.4.11 non-text threshold the module claims to guarantee.


### RPT-075 · `accessible_on` returns black or white when the threshold is unreachable
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** a yellow (`#FFFF00`) on white at a 7:1 threshold returns `#000000`
- **Observed:** it returns `#5C5C00` — a dark olive, at a measured ratio of 7.033:1, well short of pure black (21:1)
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from prama.report.contrast import accessible_on, ratio
  for threshold in [7.0, 10.0, 15.0, 20.0, 20.9]:
      result = accessible_on('#FFFF00', '#FFFFFF', threshold=threshold)
      print(threshold, '->', result, ratio(result, '#FFFFFF'))
  "
  ```
- **Severity:** P2
- **Assessment:** not-a-defect (catalogue misreading). `accessible_on()`'s own documented contract is to return "the first shade that clears the bar, so the result stays as close to the brand colour as the standard allows" — and darkening any colour toward black is monotonic in contrast, reaching 21:1 only at pure black. A 7:1 threshold is comfortably reachable well before full darkening (confirmed: `#5C5C00` already clears it), so returning that intermediate shade rather than jumping straight to black is the function working exactly as designed and separately confirmed correct (RPT-074, the already-passing case, exercises the same "first shade that clears the bar" logic). Sweeping the threshold up to `20.9` (near the true maximum of 21:1) does produce literal `#000000`, confirming the fallback path is real and reachable — just not at `7:1`, which the catalogue's own precondition names. The catalogue's assumption that 7:1 was an "unreachable" case for this hue appears to be the misreading; the module's docstring illustrates the truly-unreachable case with "a yellow on white" in the abstract, without committing to a specific threshold, and 7:1 is not that case.


### RPT-091 · A tiny non-zero rate never prints as 0%
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** `percent(0.0001)` renders `"0.0100%"`
- **Observed:** `percent(0.0001)` renders `"0.01%"`
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from prama.report.rate import percent
  print(repr(percent(0.0001)))
  print(repr(percent(0.0000001)))
  "
  ```
- **Severity:** P1
- **Assessment:** not-a-defect (catalogue misreading). `percent()`'s own documented contract is "precision is added until the display distinguishes it from perfection" — it grows decimals only as far as needed and stops at the *first* precision where the rendering is not `100%`/`0%`, not always to `MAX_DECIMALS`. At `decimals=1` (the default), `0.0001` renders `"0.0"` at one decimal place, which is rejected (equals `0.0`); at two decimals it renders `"0.01"`, which is already distinguishable from zero, so the loop returns immediately rather than continuing to four decimals. `"0.01%"` is the correct output under the function's own documented, and separately verified (RPT-090's `>99.99%` degrade path, and RPT-092/094's exact-zero and out-of-range cases, all pass), one-directional-rounding contract; the catalogue's expected string appears to assume decimals always grow to `MAX_DECIMALS` for a sub-threshold value, which the code never claims to do.


### BCH-034 · `Defect.difficulty`'s documented vocabulary matches the corpus
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** the docstring's `easy`/`moderate`/`hard` vocabulary agrees with what the corpus actually plants
- **Observed:** the docstring says `easy`/`moderate`/`hard` (with `difficulty: str = "moderate"` as the field default); the corpus's 28 defect classes plant exactly `{obvious, ordinary, subtle, adversarial}` — `moderate` is produced by nothing, and none of `easy`/`moderate`/`hard` matches any of the four real values
- **Reproduce:**
  ```
  python3 -c "
  import sys, inspect; sys.path.insert(0,'src')
  from prama.bench.scoring import Defect
  from prama.bench.corpus import CLASSES
  print(inspect.getsource(Defect)[:600])
  print('actual corpus values:', {c.difficulty.value for c in CLASSES})
  "
  ```
- **Severity:** P2
- **Assessment:** defect, confirmed exactly as pre-flagged. A report or dashboard keyed on the documented vocabulary (or code defaulting an unlabelled `Defect` to `difficulty="moderate"`) would find nothing, since `by_difficulty` groups strictly by whatever string is present and the corpus never produces `"moderate"`.


### BCH-041 · `statistics-only` is blind to anything only wrong against a rule
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** reading `blind_families` for the `statistics-only` baseline over the full corpus shows `semantic` among the reported blind spots
- **Observed:** `blind_families['statistics-only']` is `('relational',)` only — `semantic` is *not* reported blind, because one semantic-family class (`legitimate-change-with-defect`) happens to be caught by the same crude "the maximum moved"/"a category nobody declared" heuristics that catch unrelated structural defects, since it doubles `amount` and introduces the literal string `"MERGED-ENTITY"` as a `product` value
- **Reproduce:**
  ```
  python3 -c "
  import sys; sys.path.insert(0,'src')
  from prama.bench.corpus import build
  from prama.bench.baselines import compare, baseline
  corpus = build(seed=1, rows=100)
  comp = compare(corpus, [baseline('statistics-only')])
  print(comp.blind_families['statistics-only'])
  "
  ```
- **Severity:** P1
- **Assessment:** not-a-defect (catalogue misreading). The catalogue's own **Why** for this case is accurate at the *class* level ("blind to anything that is only wrong relative to a stated business rule" — true of `plausible-but-wrong` and `silent-rule-violation`, both genuinely never found), but the **Expected** step conflates that with a *family*-level claim that `blind_families()` — which reports a family only when **none** of its classes were found at all — does not and should not make, precisely because it is not true: `legitimate-change-with-defect` (also in the `semantic` family) is incidentally caught. `blind_families()`'s own purpose (per BCH-043, confirmed passing) is to avoid over-reporting blindness, and it is doing that job correctly here; the two individually-blind classes the Why note names are real and were separately confirmed.


### OPS-048 · `--prepare` does not silently touch a PostgreSQL database
- **Round 3:** unchanged from round 2; re-confirmed by direct execution against the current tree (this module carries no commits in the `B1`-`B10` remediation range, or the remediation elsewhere did not touch the code path this case exercises).
- **Expected:** either a confirmation is required before `--prepare` touches a non-SQLite database, or the documented promise is corrected
- **Observed:** running `run_prama_web.py --prepare` against a real, freshly-created, empty PostgreSQL 16 database (configured entirely via `PRAMA_DATABASE__DIALECT=postgres` and the matching `PRAMA_DATABASE__POSTGRES__*` variables) applied the full Prama schema with no confirmation, no warning, and no dialect check of any kind
- **Reproduce:**
  ```
  docker run -d --name qa-pg -e POSTGRES_PASSWORD=prama -e POSTGRES_USER=prama -e POSTGRES_DB=prama -p 55499:5432 postgres:16-alpine
  sleep 6
  PRAMA_SECURITY__SESSION_SECRET=x PRAMA_DATABASE__DIALECT=postgres \
    PRAMA_DATABASE__POSTGRES__HOST=127.0.0.1 PRAMA_DATABASE__POSTGRES__PORT=55499 \
    PRAMA_DATABASE__POSTGRES__DATABASE=prama PRAMA_DATABASE__POSTGRES__USER=prama \
    PRAMA_DATABASE__POSTGRES__PASSWORD=prama \
    timeout 20 python run_prama_web.py --prepare --tenant-slug qa-test
  docker exec qa-pg psql -U prama -d prama -c '\dt'   # lists the full Prama schema
  ```
- **Severity:** P1
- **Assessment:** defect, confirmed exactly as pre-flagged, with real evidence rather than source inspection alone: `psql \dt` on the target database afterwards lists 28+ Prama tables (`api_key`, `att_attestation`, `ctl_control`, `ev_record`, `sem_dataset`, …). The module's own docstring is unambiguous — "**Touch a database that is not SQLite** without being told. … applying a schema to somebody's PostgreSQL because they ran a script called 'run' is not a thing a script should decide" — but `_prepare()` calls `Database.from_config(config).initialise(...)` with no dialect branch anywhere in `run_prama_web.py`, and `Database.initialise()` itself applies the schema unconditionally regardless of dialect.


Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
