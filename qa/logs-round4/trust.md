# Evidence, security and scoring — QA execution log, round 4

`prama.evidence.ledger` · `prama.evidence.record` · `prama.evidence.recorder` · `prama.evidence.replay` ·
`prama.evidence.retention` · `scripts/verify_evidence.py` · `prama.security.scopes` · `prama.security.residency` ·
`prama.security.egress` · `prama.security.cmk` · `prama.security.oidc` · `prama.security.scim` ·
`prama.security.siem` · `prama.security.soc2` · `prama.security.bundle` · `prama.cli.bundle` ·
`prama.secrets.reference` · `prama.secrets.providers` · `prama.secrets.resolver` · `prama.secrets.vault` ·
`prama.secrets.value` · `prama.core.log` · `prama.score.composite` · `prama.score.trust` ·
`prama.calibrate.conformal` · `prama.calibrate.validity` · `prama.calibrate.select`.

This is a **re-run** of `qa/logs-round3/trust.md` (round 3, 464/496, 93.5%) against the tree as it stands
after batches **A–D** (`0968874`..`a23f385`), the baseline named in `qa/logs-round4/README.md`. Only two
files in this area's dependency graph changed at all across those four batches — `git log --oneline
0968874..HEAD -- <file>` is empty for every other module this log names:

- **`src/prama/core/ids.py`** (batch A, `Q-70`/`CFG-168`) — `UlidFactory.new()` read the clock *outside*
  the lock guarding `_last_ms`, so a descheduled thread could present a stale millisecond, take the `else`
  branch, and write it back over a later one, emitting an id that sorts before one already issued. The clock
  read now happens inside the lock, and a reading at or below the high-water mark clamps to it instead of
  regressing it. This is the minting path for every identifier in the system, and this area was named as the
  one most exposed to collateral damage: the evidence ledger is a *sequence*, `record_hash` chains in id
  order, and `Archivist.bundle()` exports a *range*.
- **`src/prama/cli/base.py`** (batches A and D, `Q-63`) — `Application.run` now calls `install_shipped(...)`
  before every command executes, so `prama control check` resolves the same functions `prama pack list`
  advertises. Every `h_bundle*.py`/`h_soc2.py` harness in this area drives the real `prama` CLI as a
  subprocess and is therefore a live probe of this change.

`retention.py`, `ledger.py`, `record.py`, `replay.py`, `bundle.py` (security), `score/trust.py`,
`score/composite.py` and `calibrate/*.py` — every module this catalogue actually exercises with its own
cases — are **byte-identical** to round 3 (`git log 0968874..HEAD` empty for all of them). Any movement in
this round's verdicts has exactly one possible source in `core/ids.py`, and one in `cli/base.py`; nothing
else could have moved.

All 496 cases in `qa/catalogue/trust.md` were re-executed against the live codebase: round 3's 47 saved
scripts in `qa/harness/trust/` were copied to a fresh scratch directory and re-run byte-for-byte (one had a
stale `sys.path` entry left over from round 3's own transient run — see **Harness note** below; it changed
nothing about the verdict, only where the row landed on disk, and is fixed in place). Real `EvidenceRecord`/
`Ledger` chains were built and tampered with by hand, `scripts/verify_evidence.py` was run as a real
subprocess against real bundle directories, a real `prama` CLI was invoked as a subprocess (`bundle seal`,
`bundle verify`, `pack soc2`, `config show`), real RSA/EC/Ed25519 keys came from `cryptography`, and
`ConformalCalibrator`/`HierarchicalSelector`/`TrustPropagator`/`CalibrationCurve` were constructed directly
with hand-computed expected values — same method as round 3, nothing skipped.

Beyond re-running the saved harnesses, this round did the specific extra scrutiny the brief asked for on the
one file that changed with estate-wide reach:

1. **The product's own counterfactual, run both ways.** `qa/regression-suite/platform/test_ulid_monotonicity.py`
   (added by batch A) exercises the real `UlidFactory` — not a reimplementation — with a scripted clock that
   forces a reading below the high-water mark deterministically, plus 16 real threads racing 4,000 mints
   against a clock stepping across a boundary. Run against the current tree: **4 passed in 0.06s.** Run again
   with `src/prama/core/ids.py` swapped for the pre-batch-A version (`git show 3926ed9^:src/prama/core/ids.py`,
   nothing else changed) via `PYTHONPATH`: **all 4 fail**, the concurrent-minting one on
   `assert len(set(minted)) == len(minted)` and the others on the ordering/clamping assertions directly — the
   fix is real and the test that proves it is not a tautology.
2. **`EVD-052`'s 8-thread/4,000-record concurrent-append counterfactual, repeated 5 more times** (with random
   micro-jitter added between appends to widen the race window, beyond round 3's own already-real 8-thread
   run), against the real `Ledger.append`: **0 duplicate sequences, chain intact, all 5 trials**, on top of
   the 1 trial already recorded for `EVD-052` itself. `Ledger.append`'s lock (batch `B2`, round 3's own fix)
   is unrelated to `core/ids.py` and was not touched by batches A–D — this reconfirms it holds, it does not
   newly test anything the ids.py change could have broken, because the ledger's `sequence` field is a plain
   integer counter, never a `UlidFactory` output (confirmed by reading `evidence/ledger.py` and
   `evidence/retention.py`: no `ulid`/`UlidFactory` import in either).
3. **A hand-built range export against the real `Archivist.bundle()`**, not a round-3 case: 250 real records
   appended, a bundle taken over an arbitrary interior window (`records[137:191]`, not touching either end),
   and `manifest.from_sequence == 137`, `manifest.to_sequence == 190` confirmed to be *exactly* the requested
   boundary, no off-by-one either side, payload sequences `== list(range(137, 191))` exactly.
4. **Tampering the windowed bundle, not just checking a clean one**: a byte inside the range (record at
   sequence 147, well inside the window and not at either boundary) was flipped after export.
   `Bundle.check()` caught it (`ok=False, "the records do not match the digest in the manifest"`), and
   `evidence.ledger.verify()` over the same tampered payload independently reported a `content` breach at
   sequence 147 — two independent detectors, both real, both fired.
5. **Replay**, via the real `compare`/`Cause`/`ReplayReport`/`Divergence` objects from `prama.evidence.replay`
   (not reimplemented) — `EVD-089` (exact replay reported `IDENTICAL`), `EVD-096` (inexact snapshot excuses
   a divergence and says the run was never replayable), `EVD-101`/`EVD-102` (sequence numbers and timings
   excluded from the diff, escalations counted by cause) all re-verified against the current tree, unchanged.

One finding fell out of step 4 that is **not** a regression and **not** covered by any case's `Expected` in
this catalogue, so it changes no verdict, but is recorded because it was found doing exactly the exercise the
brief asked for: a fifth, separate test — replacing `manifest.to_sequence` alone with a value larger than the
payload actually holds, leaving `manifest.records` and `payload_digest` untouched — was **not** caught by
`Bundle.check()`. Reading `Bundle.check()`'s source shows why: it validates line count against
`manifest.records`, the payload's SHA-256 against `manifest.payload_digest`, chain integrity, and
`manifest.chain_head` — `from_sequence`/`to_sequence` are descriptive fields it never cross-checks against the
payload's own first/last sequence. `retention.py` is untouched across `0968874..HEAD`, so this is not
collateral damage from this round's batches; `EVD-116` (the one case that inspects these fields) only checks
that they are populated correctly *at construction time*, which they are — nothing in the catalogue's
`Expected` for any case asks `Bundle.check()` to defend against a falsified range after the fact. Recorded
here as a scope gap worth a future case, not scored against any id.

**Harness note.** `h_secrets4.py` (`SEC-212`) carried a `sys.path.insert` pointing at
`.../scratchpad/r3/trust` — a stale reference to round 3's own transient scratch copy, not round 3's saved
`.../scratchpad/trust` (the pattern every other harness had and which this round's setup correctly rewrote).
Because that directory still existed and still held its own `reclib.py`, the script ran correctly and printed
the correct answer to stdout every time — the row just landed in a leftover round-3 file instead of this
round's `results.tsv`. Confirmed by reading `run_log.txt` (SEC-212 printed `PASS` there, first run) against
the stray file (same exact PASS, filed under the wrong path). Fixed in `qa/harness/trust/h_secrets4.py` and
re-run for a clean result. Zero effect on the verdict — this is a `(a)` harness artefact in the sense of the
brief's rubric, but note that unlike round 2→3's thirteen, it never produced a wrong verdict at all, only a
misfiled one.

## Counts

| | Count |
|---|---:|
| Total cases | 496 |
| PASS | 464 |
| FAIL | 32 |
| BLOCKED | 0 |
| **Pass rate** | **93.5%** (464/496) |

Round 3: 464 PASS / 32 FAIL — 93.5%. Round 4: 464 PASS / 32 FAIL — 93.5%. **Zero cases moved in either
direction.** The FAIL set is set-identical to round 3's, id for id (diffed programmatically, not by eye).

## Regressions — a case that passed in round 3 and fails now

**0 found.** Every one of round 3's 464 PASSes is a PASS again; every one of round 3's 32 FAILs is a FAIL
again, for the same underlying reason (three of the 32 — `CAL-011`, `SCR-042`, `SEC-144` — differ from round
3's recorded text only in wall-clock timing or a run timestamp; see their entries below). This was verified
by programmatic diff against `qa/logs-round3/trust.md`'s own 496-row table, id by id, result by result — not
by re-reading the table by eye.

This is a real, checked answer, not an assumption resting on "`core/ids.py` changed and nothing broke on
`git log`": every one of `EVD-039` through `EVD-055` and the whole EVD-1xx bundle/replay range (concurrency,
range export, tamper detection, Merkle, replay) was re-run against live code this round, and the five
deliberate extra checks above (items 1–5) went further than any single round-3 case does on its own,
specifically because this is the area the brief named as most exposed. None of it moved.

## Fixes confirmed by direct execution

**None new.** Round 3's six fixes (`EVD-049`, `EVD-052`, `SEC-014`, and three others recorded in round 3's
own "Fixes confirmed" section) remain fixed — reconfirmed by direct execution this round, not carried
forward on trust. Batches A–D touched no code path any of the 32 remaining FAILs exercise (confirmed per-file
above), so none of the 32 could have been fixed by these four batches, and none was.

## `SEC-144` and `SCR-042` — carried forward unchanged

Both keep round 3's classification for the same reason round 3 gave, because `src/prama/security/bundle.py`
and `src/prama/score/trust.py` are byte-identical to round 3 (`git log 0968874..HEAD` empty for both):

- **`SEC-144`** — the Q-19 defect (a stripped publisher signature silently downgrading to a pass) is fixed;
  the message still reads *"the bundle was altered, or signed by somebody else"* rather than naming a missing
  signature specifically, which is what the catalogue's `Expected` asks for word-for-word. Re-run this round,
  same code path, same gap.
- **`SCR-042`** — this round's single measurement landed at **30.13s against the 30s budget** — over, again,
  by the same margin round 3's flakiest runs showed (round 3 saw 26.6s–49.9s on unchanged code). `git log`
  confirms zero commits to `score/trust.py` across `0968874..HEAD` too, so this is the same unbounded `6**8`
  enumeration straddling its own budget line, not a regression and not a fix. Recorded `FAIL` to match round
  3 rather than credit a measurement that happened to land on the fail side of a coin.

## Harness-artefact count

**1** (not counted as a regression or a flip, since the verdict it produced was correct in every run):
`h_secrets4.py`'s stray `sys.path` entry, described above.


## Per-case results (id order, 496 rows)

| Id | Result | Observed |
|---|---|---|
| `CAL-001` | PASS | p_value(90)=0.1 hand_computed=(1+9)/100=0.1 |
| `CAL-002` | PASS | pytest tests/calibrate/test_conformal.py::test_a_normal_observation_alerts_at_most_alpha_of_the_time -> ['tests/calibrate/test_conformal.py::test_a_normal_observation_alerts_at_most_alpha_of_the_time[0.01] PASSED [  4%]', 'tests/calibrate/test_conformal.py::test_a_normal_observation_alerts_at_mos... |
| `CAL-003` | PASS | pytest tests/calibrate/test_conformal.py::test_the_plus_one_is_the_guarantee_and_not_rounding -> ['tests/calibrate/test_conformal.py::test_the_plus_one_is_the_guarantee_and_not_rounding PASSED [ 26%]'] |
| `CAL-004` | PASS | pytest tests/calibrate/test_conformal.py::test_a_p_value_cannot_be_finer_than_the_history_supports -> ['tests/calibrate/test_conformal.py::test_a_p_value_cannot_be_finer_than_the_history_supports PASSED [ 30%]'] |
| `CAL-005` | PASS | resolution=0.0196 honours(0.001)=False honours(0.05)=True |
| `CAL-006` | PASS | pytest tests/calibrate/test_conformal.py::test_a_saturated_p_value_says_at_most_rather_than_equals -> ['tests/calibrate/test_conformal.py::test_a_saturated_p_value_says_at_most_rather_than_equals PASSED [ 34%]'] |
| `CAL-007` | PASS | pytest tests/calibrate/test_conformal.py::test_too_little_history_produces_no_p_value_and_says_why -> ['tests/calibrate/test_conformal.py::test_too_little_history_produces_no_p_value_and_says_why PASSED [ 60%]'] |
| `CAL-008` | PASS | u1='10 calibration points is below the minimum of 20; the coarsest p-value available would be 0.091, which cannot honour any useful budget' u2='the observed score is not a finite number' u3='every calibration point has zero weight, which happens when the whole window is older than the decay allow... |
| `CAL-009` | PASS | pytest tests/calibrate/test_conformal.py::test_a_non_finite_observation_is_refused_rather_than_ranked -> ['tests/calibrate/test_conformal.py::test_a_non_finite_observation_is_refused_rather_than_ranked PASSED [ 65%]'] |
| `CAL-010` | PASS | n=25 (25 finite + 5 nan dropped) |
| `CAL-011` | FAIL | 100k calib points, 10k p_value() calls: elapsed=49.019s budget=10.0s |
| `CAL-012` | PASS | p_value(50)=0.84 at_least=20 expected=0.84 |
| `CAL-013` | PASS | p_value(below_all)=1.0 |
| `CAL-014` | PASS | w[-1]=1.0 w[-51]=0.500000 (age 50 == half_life) ascending=True |
| `CAL-015` | PASS | recency_weights(0)=() recency_weights(10, half_life=0)_all_finite=True |
| `CAL-016` | PASS | pytest tests/calibrate/test_conformal.py::test_recency_weighting_costs_resolution_and_the_cost_is_reported -> ['tests/calibrate/test_conformal.py::test_recency_weighting_costs_resolution_and_the_cost_is_reported PASSED [ 43%]'] |
| `CAL-017` | PASS | n=40 effective_n=40.0 |
| `CAL-018` | PASS | pytest tests/calibrate/test_conformal.py::test_a_weighted_p_value_does_not_claim_to_be_exact -> ['tests/calibrate/test_conformal.py::test_a_weighted_p_value_does_not_claim_to_be_exact PASSED [ 47%]'] |
| `CAL-019` | PASS | describe()='p = 0.1274 against 60 comparable observations; weighted for recency, so validity is approximate — coverage may depart from nominal by up to 0.534' to_dict={'p_value': 0.127393, 'n': 60, 'effective_n': 27.98, 'resolution': 0.03451, 'exact': False, 'coverage_gap': 0.533712, 'saturated':... |
| `CAL-020` | PASS | coverage_gap=0.0 exact=True |
| `CAL-021` | PASS | pytest tests/calibrate/test_conformal.py::test_a_window_older_than_its_decay_says_so -> ['tests/calibrate/test_conformal.py::test_a_window_older_than_its_decay_says_so PASSED [ 69%]'] |
| `CAL-022` | PASS | pytest tests/calibrate/test_conformal.py::test_mismatched_weights_are_refused -> ['tests/calibrate/test_conformal.py::test_mismatched_weights_are_refused PASSED [ 56%]'] |
| `CAL-023` | PASS | pytest tests/calibrate/test_conformal.py::test_a_threshold_can_be_shown_instead_of_a_p_value -> ['tests/calibrate/test_conformal.py::test_a_threshold_can_be_shown_instead_of_a_p_value PASSED [ 73%]'] |
| `CAL-024` | PASS | pytest tests/calibrate/test_conformal.py::test_no_threshold_is_offered_for_a_level_the_history_cannot_express -> ['tests/calibrate/test_conformal.py::test_no_threshold_is_offered_for_a_level_the_history_cannot_express PASSED [ 78%]'] |
| `CAL-025` | PASS | pytest tests/calibrate/test_conformal.py::test_a_target_that_is_not_a_probability_is_refused -> ['tests/calibrate/test_conformal.py::test_a_target_that_is_not_a_probability_is_refused PASSED [100%]'] |
| `CAL-026` | PASS | pytest tests/calibrate/test_conformal.py::test_the_adaptive_level_tightens_when_alerts_exceed_the_budget -> ['tests/calibrate/test_conformal.py::test_the_adaptive_level_tightens_when_alerts_exceed_the_budget PASSED [ 82%]'] |
| `CAL-027` | PASS | pytest tests/calibrate/test_conformal.py::test_the_adaptive_level_loosens_when_nothing_has_alerted_in_a_long_time -> ['tests/calibrate/test_conformal.py::test_the_adaptive_level_loosens_when_nothing_has_alerted_in_a_long_time PASSED [ 86%]'] |
| `CAL-028` | PASS | min_level=0.0001 max_level=0.5 floor=1e-4 ceiling=0.5 all_within_bounds=True |
| `CAL-029` | PASS | pytest tests/calibrate/test_conformal.py::test_the_long_run_alert_rate_converges_to_the_budget_under_drift -> ['tests/calibrate/test_conformal.py::test_the_long_run_alert_rate_converges_to_the_budget_under_drift PASSED [ 91%]'] |
| `CAL-030` | PASS | levels_after_identical_alert_sequences_but_via_two_separately_constructed_calibrators: a=0.11010000000000013 b=0.11010000000000013 equal=True (observe() signature only accepts a bool 'alerted', confirming by inspection that p-value magnitude cannot enter the update) |
| `CAL-031` | PASS | pytest tests/calibrate/test_conformal.py::test_adapting_cannot_help_when_every_p_value_is_at_its_floor -> ['tests/calibrate/test_conformal.py::test_adapting_cannot_help_when_every_p_value_is_at_its_floor PASSED [ 95%]'] |
| `CAL-032` | PASS | saturated=0.49 -> is_powerless=False; saturated=0.50 -> is_powerless=True |
| `CAL-033` | PASS | len(_recent)=100 len(_saturated)=100 realised=0.1 expected(over_last_100)=0.1 |
| `CAL-034` | PASS | judge()_records_saturation=True separate_test+observe_loses_it=True |
| `CAL-035` | PASS | current_level=0.00010 target=0.05 p_between=0.02505 test()_result=False (expected: False -- tested against current, not target) |
| `CAL-036` | PASS | descs=['testing at the declared level of 0.0500', 'testing at 0.0200 rather than the declared 0.0500, because 15.0% of recent observations alerted — the data has moved and the level is being held to the budget', 'testing at 0.0800 rather than the declared 0.0500: recent alerting has run below bud... |
| `CAL-037` | PASS | pytest tests/calibrate/test_validity.py::test_a_calibrated_monitor_reports_that_it_is -> ['tests/calibrate/test_validity.py::test_a_calibrated_monitor_reports_that_it_is PASSED [  6%]'] |
| `CAL-038` | PASS | pytest tests/calibrate/test_validity.py::test_a_monitor_whose_data_moved_reports_uncalibrated_and_keeps_running -> ['tests/calibrate/test_validity.py::test_a_monitor_whose_data_moved_reports_uncalibrated_and_keeps_running PASSED [ 13%]'] |
| `CAL-039` | PASS | pytest tests/calibrate/test_validity.py::test_sampling_noise_does_not_trip_the_validity_monitor -> ['tests/calibrate/test_validity.py::test_sampling_noise_does_not_trip_the_validity_monitor PASSED [ 26%]'] |
| `CAL-040` | PASS | DEGRADATION_CONFIDENCE=0.999 reasoning_documented=True |
| `CAL-041` | PASS | pytest tests/calibrate/test_validity.py::test_a_new_monitor_has_not_earned_the_promise_yet -> ['tests/calibrate/test_validity.py::test_a_new_monitor_has_not_earned_the_promise_yet PASSED [ 33%]'] |
| `CAL-042` | PASS | pytest tests/calibrate/test_validity.py::test_firing_less_often_than_promised_is_not_a_broken_promise -> ['tests/calibrate/test_validity.py::test_firing_less_often_than_promised_is_not_a_broken_promise PASSED [ 40%]'] |
| `CAL-043` | PASS | pytest tests/calibrate/test_validity.py::test_a_departure_that_is_not_yet_meaningless_is_called_drifting -> ['tests/calibrate/test_validity.py::test_a_departure_that_is_not_yet_meaningless_is_called_drifting PASSED [ 46%]'] |
| `CAL-044` | PASS | interval=[0.08,0.12] nominal=0.05 -> is_liberal=True |
| `CAL-045` | PASS | interval=[0.01,0.03] nominal=0.05 -> is_liberal=False |
| `CAL-046` | PASS | pytest tests/calibrate/test_validity.py::test_the_curve_covers_three_orders_of_magnitude -> ['tests/calibrate/test_validity.py::test_the_curve_covers_three_orders_of_magnitude PASSED [ 73%]'] |
| `CAL-047` | PASS | pytest tests/calibrate/test_validity.py::test_the_calibration_error_meets_the_wave_target_on_honest_data -> ['tests/calibrate/test_validity.py::test_the_calibration_error_meets_the_wave_target_on_honest_data PASSED [ 60%]'] |
| `CAL-048` | FAIL | empty CalibrationCurve: calibration_error=0.0 meets_target=True -- expected either meets_target guarded to False for zero observations, or a documented UNKNOWN qualification on the curve itself; as read, meets_target is UNGUARDED and reports True for a curve that has seen nothing |
| `CAL-049` | PASS | pytest tests/calibrate/test_validity.py::test_the_interval_stays_an_interval_at_small_rates -> ['tests/calibrate/test_validity.py::test_the_interval_stays_an_interval_at_small_rates PASSED [ 80%]'] |
| `CAL-050` | PASS | pytest tests/calibrate/test_validity.py::test_no_observations_admits_everything -> ['tests/calibrate/test_validity.py::test_no_observations_admits_everything PASSED [ 93%]'] |
| `CAL-051` | PASS | _z_for(0.95)=1.95996 _z_for(0.99)=2.57583 _z_for(0.999)=3.29053 |
| `CAL-052` | PASS | pytest tests/calibrate/test_validity.py::test_the_degradation_appears_on_every_alert_not_only_a_status_page -> ['tests/calibrate/test_validity.py::test_the_degradation_appears_on_every_alert_not_only_a_status_page PASSED [ 20%]'] |
| `CAL-053` | PASS | observations=500 (expected 500) oldest_retained=0.9500 (expected 0.9500, the 500 most recent) |
| `CAL-054` | PASS | docstring_acknowledges_weak_point=True docstring_excerpt='Watches a monitor\'s own false-alarm rate against what it promised.\n\nFed the p-values of observations *believed to be normal*. That belief is\nthe weak point and is worth naming: on live data nobody knows which\nobservations were normal,... |
| `CAL-055` | PASS | pytest tests/calibrate/test_select.py::test_bh_takes_the_largest_k_and_not_the_first_failure -> ['tests/calibrate/test_select.py::test_bh_takes_the_largest_k_and_not_the_first_failure PASSED [  5%]'] |
| `CAL-056` | PASS | pytest tests/calibrate/test_select.py::test_bh_controls_the_false_discovery_rate -> ['tests/calibrate/test_select.py::test_bh_controls_the_false_discovery_rate PASSED [ 21%]'] |
| `CAL-057` | PASS | pytest tests/calibrate/test_select.py::test_by_is_strictly_more_conservative_than_bh -> ['tests/calibrate/test_select.py::test_by_is_strictly_more_conservative_than_bh PASSED [ 15%]'] |
| `CAL-058` | PASS | 999: exact=7.48447086 approx=7.48447086 diff=0.00e+00; 1000: diff=8.33e-08; 1001: diff=8.32e-08 |
| `CAL-059` | PASS | _harmonic(0)=1.0 _harmonic(1)=1.0 |
| `CAL-060` | PASS | pytest tests/calibrate/test_select.py::test_simes_summarises_a_family_without_testing_each_member -> ['tests/calibrate/test_select.py::test_simes_summarises_a_family_without_testing_each_member PASSED [ 26%]'] |
| `CAL-061` | PASS | simes([])=1.0 |
| `CAL-062` | PASS | pytest tests/calibrate/test_select.py::test_a_quiet_family_is_never_opened -> ['tests/calibrate/test_select.py::test_a_quiet_family_is_never_opened PASSED [ 63%]'] |
| `CAL-063` | PASS | families_unopened=16 (expected 16 of 20) thresholds_seen={0.010000000000000002} expected_scaled_level=0.010000000000000002 matches=True |
| `CAL-064` | PASS | pytest tests/calibrate/test_select.py::test_a_wholesale_failure_becomes_one_finding_rather_than_four_hundred -> ['tests/calibrate/test_select.py::test_a_wholesale_failure_becomes_one_finding_rather_than_four_hundred PASSED [ 31%]'] |
| `CAL-065` | PASS | pytest tests/calibrate/test_select.py::test_roll_up_is_decided_on_the_shape_of_the_failure_not_the_correction -> ['tests/calibrate/test_select.py::test_roll_up_is_decided_on_the_shape_of_the_failure_not_the_correction PASSED [ 47%]'] |
| `CAL-066` | PASS | pytest tests/calibrate/test_select.py::test_a_partial_failure_is_not_rolled_up -> ['tests/calibrate/test_select.py::test_a_partial_failure_is_not_rolled_up PASSED [ 57%]'] |
| `CAL-067` | PASS | pytest tests/calibrate/test_select.py::test_a_small_family_is_never_rolled_up -> ['tests/calibrate/test_select.py::test_a_small_family_is_never_rolled_up PASSED [ 52%]'] |
| `CAL-068` | PASS | pytest tests/calibrate/test_select.py::test_the_roll_up_carries_the_family_p_value_not_the_worst_child -> ['tests/calibrate/test_select.py::test_the_roll_up_carries_the_family_p_value_not_the_worst_child PASSED [ 42%]'] |
| `CAL-069` | PASS | _parent_level(CHECK)=Level.ATTRIBUTE _parent_level(DOMAIN)=Level.DOMAIN |
| `CAL-070` | PASS | order1=['estate'] order2=['estate'] identical=True |
| `CAL-071` | PASS | empty_findings=0 describe='0 findings from 0 monitors at FDR 0.050 using BH, which assumes independence or positive regression dependency between the tests' non_rejecting_findings=0 |
| `CAL-072` | PASS | pytest tests/calibrate/test_select.py::test_which_procedure_ran_and_what_it_assumes_is_on_the_result -> ['tests/calibrate/test_select.py::test_which_procedure_ran_and_what_it_assumes_is_on_the_result PASSED [ 68%]'] |
| `CAL-073` | PASS | pytest tests/calibrate/test_select.py::test_a_business_budget_becomes_a_statistical_level -> ['tests/calibrate/test_select.py::test_a_business_budget_becomes_a_statistical_level PASSED [ 78%]'] |
| `CAL-074` | PASS | Budget(false_alarms=2, tests_per_period=0).alpha=0.0 |
| `CAL-075` | PASS | Budget(false_alarms=100, tests_per_period=10).alpha=1.0 |
| `CAL-076` | PASS | pytest tests/calibrate/test_select.py::test_a_budget_the_history_cannot_honour_is_refused_with_the_arithmetic -> ['tests/calibrate/test_select.py::test_a_budget_the_history_cannot_honour_is_refused_with_the_arithmetic PASSED [ 89%]'] |
| `CAL-077` | PASS | pytest tests/calibrate/test_select.py::test_an_achievable_budget_reports_no_shortfall -> ['tests/calibrate/test_select.py::test_an_achievable_budget_reports_no_shortfall PASSED [ 94%]'] |
| `CAL-078` | PASS | power_at docstring mentions approximation: True docstring='Rough power of a conformal test against a shifted alternative.\n\nAn approximation, and labelled as one wherever it surfaces. It exists so\nthe sensitivi' |
| `CAL-079` | PASS | power_by_effect(0,1,2,3)=[0.050000000000000155, 0.25951102284144445, 0.6387600313123355, 0.9123145367502966] power_by_alpha(0.01,0.05)=[0.3720805854354955, 0.6387600313123355] monotone_effect=True monotone_alpha=True bounded=True zero_effect~alpha=True |
| `CAL-080` | PASS | power_at(alpha=0.05, effect=2, n=0)=0.0 power_at(alpha=0, effect=2, n=1000)=0.0 |
| `EVD-001` | PASS | dataclass_fields-2=['binding', 'control_id', 'control_version', 'coverage', 'criticality', 'dataset', 'detail', 'dimensions', 'duration_ms', 'engine', 'evidence_version', 'finished_at', 'metrics', 'parameters', 'plan_id', 'sample_count', 'samples_digest', 'sequence', 'snapshot', 'started_at', 'te... |
| `EVD-002` | PASS | fields excluded from content(): ['previous_hash', 'tombstone']; docstring covers previous_hash ('it is a hash') and tombstone ('sealed separately') -- checked by inspection |
| `EVD-003` | PASS | record_hash=96a6eac00cce3c2e016653f068cb698ebb158dfacb9f17031a56b0c79ac787ca handcomputed=96a6eac00cce3c2e016653f068cb698ebb158dfacb9f17031a56b0c79ac787ca |
| `EVD-004` | PASS | ca0cb5341eab14d8375b46bd62e551bc8432a6ac207cbf3e8ef2a5f17f1a7542 vs ca0cb5341eab14d8375b46bd62e551bc8432a6ac207cbf3e8ef2a5f17f1a7542 |
| `EVD-005` | PASS | with_orjson=(True,c61f8c2e39bc14b7885d1e8ce752bfed939ae4874faabb3965afaa27201a3907) without_orjson=(False,c61f8c2e39bc14b7885d1e8ce752bfed939ae4874faabb3965afaa27201a3907) stderr_with='' stderr_without='' |
| `EVD-006` | FAIL | prama_content_hash=6cf4caa4b80d6c0525c344c012f18fd3be842a10ed3e15fab7f7aca7bcd28f72 verifier_recompute=463eb2aca6f977b4680f7bf1fe99950cb1b8e6335110dd61bfc6340c32611d65 equal=False |
| `EVD-007` | PASS | 302fc1c54cafddf0a92e1a775b2bcae9ad927a41393dc2daaf640509d49f6259 vs 302fc1c54cafddf0a92e1a775b2bcae9ad927a41393dc2daaf640509d49f6259 |
| `EVD-008` | PASS | nan_hash=91a9d76bedec4be5eb3229cc399e8073cf7eb2892d76ddab8834ff16015494f8 inf_hash=91a9d76bedec4be5eb3229cc399e8073cf7eb2892d76ddab8834ff16015494f8 collide=True content_nan={'ratio': nan} content_inf={'ratio': inf} |
| `EVD-009` | PASS | hash_eq=True to_dict_detail_len=300 truncated_matches_x300=True |
| `EVD-010` | PASS | recomputed=696a3800828cd7b37aa8b2c10b40198174a889521455340773de51e0dcc9a420 stored=696a3800828cd7b37aa8b2c10b40198174a889521455340773de51e0dcc9a420 content_keys=['binding', 'control_id', 'control_version', 'coverage', 'dataset', 'detail', 'duration_ms', 'engine', 'evidence_version', 'finished_at'... |
| `EVD-011` | PASS | content_dimensions=['completeness', 'accuracy'] content_criticality=2 |
| `EVD-012` | PASS | _version_tuple('1.10')=(1, 10) _version_tuple('1.9')=(1, 9) |
| `EVD-013` | PASS | _version_tuple('banana')=(0, 0) content_keys=['binding', 'control_id', 'control_version', 'coverage', 'dataset', 'detail', 'duration_ms', 'engine', 'evidence_version', 'finished_at', 'metrics', 'parameters', 'plan_id', 'sample_count', 'samples_digest', 'sequence', 'snapshot', 'started_at', 'tenan... |
| `EVD-014` | FAIL | prama_verify_intact=True (breaches=[]) independent_exit=1 independent_ok=False -- expected both to report a breach |
| `EVD-015` | PASS | breaches=[('content', 0, 'the content does not match its hash; this record has been altered'), ('link', 0, 'the record hash does not match its own contents')] |
| `EVD-016` | PASS | full='pass' incremental='pass over the rows examined' forward_only='fail over the rows examined' |
| `EVD-017` | PASS | breaches=[('content', 0, 'the content does not match its hash; this record has been altered'), ('link', 0, 'the record hash does not match its own contents')] |
| `EVD-018` | PASS | equal_dict=True content_hash_eq=True record_hash_eq=True |
| `EVD-019` | PASS | verdict=error criticality=4 coverage=full triggered_by=schedule previous_hash=0000000000000000000000000000000000000000000000000000000000000000 evidence_version=1.1 |
| `EVD-020` | FAIL | raised a raw ValueError, not a typed/named failure: ValueError("could not convert string to float: 'eight'") |
| `EVD-021` | PASS | size_bytes=1136 |
| `EVD-022` | PASS | GENESIS='0000000000000000000000000000000000000000000000000000000000000000' ve.GENESIS='0000000000000000000000000000000000000000000000000000000000000000' |
| `EVD-023` | PASS | intact=True erased=1 breaches=[] |
| `EVD-024` | PASS | before=37deda42d64963ce4337b0dfb85d303289cafe44ec7e7b025e5179daea402af3 after=37deda42d64963ce4337b0dfb85d303289cafe44ec7e7b025e5179daea402af3 tombstone_orig=37deda42d64963ce4337b0dfb85d303289cafe44ec7e7b025e5179daea402af3 |
| `EVD-025` | PASS | cleared_ok=True snapshot_cleared=True plan_id='' control_id='' dataset='' binding='' parameters={} metrics={} samples_digest='' sample_count=0 detail='' dimensions=() verdict_survives='pass' tenant_id_survives='t1' criticality_survives=1 |
| `EVD-026` | PASS | e2==e1:True erased_by=dpo authority=A1 |
| `EVD-027` | PASS | seal=0e45328c28f3dda0220857a67fa615ee1a05b7c2f9bd98afa5806be78c8aa1ba handcomputed=0e45328c28f3dda0220857a67fa615ee1a05b7c2f9bd98afa5806be78c8aa1ba |
| `EVD-028` | PASS | exit=1 output_excerpt="Bundle:   /tmp/tmpw17b4_pp\nTenant:   t1\nPeriod:   sequence 0 to 4, written 2026-01-01T00:00:00Z\nRecords:  5\n\n  [PASS] every record's content hashes to its stored content_hash\n  [PASS] every record links to the one before it\n  [PASS] sequence numbers are contiguous\n ... |
| `EVD-029` | PASS | exit=1 output_excerpt="Bundle:   /tmp/tmp0vjyzf7q\nTenant:   t1\nPeriod:   sequence 0 to 4, written 2026-01-01T00:00:00Z\nRecords:  5\n\n  [PASS] every record's content hashes to its stored content_hash\n  [PASS] every record links to the one before it\n  [PASS] sequence numbers are contiguous\n ... |
| `EVD-030` | PASS | exit=1 output_excerpt="Bundle:   /tmp/tmptjp6v3bb\nTenant:   t1\nPeriod:   sequence 0 to 4, written 2026-01-01T00:00:00Z\nRecords:  5\n\n  [PASS] every record's content hashes to its stored content_hash\n  [FAIL] every record links to the one before it\n         record 3: record_hash is 8775aa7a6... |
| `EVD-031` | PASS | prama_verify_intact=True independent_exit=1 -- expected both report a breach |
| `EVD-032` | PASS | erased_by=dpo@bank authority=DSAR-2026-114 reason='right to erasure' erased_at=2026-09-01T00:00:00Z |
| `EVD-033` | PASS | tombstone fields=['original_content_hash', 'erased_at', 'erased_by', 'authority', 'reason'] -- none is a subject/customer identifier field by name |
| `EVD-034` | PASS | forged_seal=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff recomputed_seal=e8d8187411f39cf8263e30c0b12935db5e3fd3d0f441536f06da5274ecb51e8a differs=True |
| `EVD-035` | PASS | erased=2 rendered='5 record(s) verified. Chain head dd12780efcc92e15…, Merkle root d60638856effeef7… 2 record(s) have been erased under a right-to-erasure request; their place in the chain is verified, their contents are gone.' |
| `EVD-036` | FAIL | no exception raised; returned list identical_to_original=True; caller receives no statement that nothing was erased (bare list of 5 records) |
| `EVD-037` | PASS | bundle_check_before_erase=(True,5 record(s), chain intact, Merkle root d60638856effeef7…) bundle_check_after_hot_erase=(True,5 record(s), chain intact, Merkle root d60638856effeef7…) |
| `EVD-038` | PASS | intact=True erased=5 rendered='5 record(s) verified. Chain head dd12780efcc92e15…, Merkle root d60638856effeef7… 5 record(s) have been erased under a right-to-erasure request; their place in the chain is verified, their contents are gone.' |
| `EVD-039` | PASS | sequence=0 previous_hash==GENESIS:True head==record_hash:True |
| `EVD-040` | PASS | caller_supplied sequence=0 previous_hash=ff*32; actual sequence=3 previous_hash=4e8ae00fe280d013812a0663868a76ada380b995f94b647581307f7ff47bc4f3 |
| `EVD-041` | PASS | len=1000 first5=[0, 1, 2, 3, 4] last5=[995, 996, 997, 998, 999] contiguous=True |
| `EVD-042` | PASS | head=0000000000000000000000000000000000000000000000000000000000000000 next_sequence=0 verify_intact=True verify_records=0 merkle_root=0000000000000000000000000000000000000000000000000000000000000000 |
| `EVD-043` | PASS | breaches_at_4=['content', 'link'] all_breaches=[('content', 4), ('link', 4), ('link', 5)] |
| `EVD-044` | PASS | breaches_at_4=[] breaches_at_5=['link'] |
| `EVD-045` | PASS | intact=True root_changed=True head_changed=True |
| `EVD-046` | PASS | breaches=[('gap', 5, 'expected sequence 4 and found 5; 1 record(s) are missing'), ('link', 5, 'this record does not follow the one before it; the chain is broken here')] |
| `EVD-047` | PASS | breaches=[('gap', 5, 'expected sequence 4 and found 5; 1 record(s) are missing'), ('link', 5, 'this record does not follow the one before it; the chain is broken here'), ('gap', 4, 'records are out of order'), ('link', 4, 'this record does not follow the one before it; the chain is broken here'),... |
| `EVD-048` | PASS | verify_over_truncated_lines_intact=True bundle_check_ok=False bundle_check_msg='the manifest says 10 record(s) and the file holds 7; this bundle is incomplete' |
| `EVD-049` | PASS | window seq 100..109; verify intact=True breaches=[] |
| `EVD-050` | PASS | breaches=[('genesis', 0, 'the first record does not start the chain')] |
| `EVD-051` | PASS | lone record of arbitrary content verifies intact=True (T11: proves its own content hash and nothing about position) breaches=[] |
| `EVD-052` | PASS | total_records=4000 expected=4000 duplicate_sequences=0 contiguous=True chain_intact=True errors=[] |
| `EVD-053` | PASS | public_surface=['append', 'export', 'extend', 'find', 'head', 'merkle_root', 'next_sequence', 'records', 'since', 'verify'] |
| `EVD-054` | PASS | since(10)_len=10 since(10)_first_seqs=[10, 11, 12] find('plan-0')_count=7 find_seqs=[0, 3, 6, 9, 12, 15, 18] |
| `EVD-055` | PASS | num_lines_when_split_on_newline=2 parse_each_as_json_ok=True error=None detail_repr='line one\nline two üñî' |
| `EVD-056` | PASS | no_trailing_nonblank=10 one_trailing_nl=10 two_trailing_nl=10 all_10=True |
| `EVD-057` | PASS | rendered={'content': 'record 4: the content does not match its hash; this record has been altered', 'link': 'record 5: this record does not follow the one before it; the chain is broken here', 'gap': 'record 6: expected sequence 5 and found 6; 1 record(s) are missing', 'order': 'record 4: records... |
| `EVD-058` | PASS | keys=['breaches', 'erased', 'head', 'intact', 'merkle_root', 'records'] intact=False n_breaches=5 |
| `EVD-059` | PASS | verify().head=195e2666ca36d6c15b71c74c27340703b4871d4bf49fb573afb4b55e2e8ed9dc ledger.head=195e2666ca36d6c15b71c74c27340703b4871d4bf49fb573afb4b55e2e8ed9dc |
| `EVD-060` | PASS | content_breach_sequences=[2, 7] |
| `EVD-061` | PASS | SCALED PROBE (20000 records, not the stated 1,000,000): verify_intact=True time_s=1.00 -- completed without error; did not instrument memory to confirm streaming/no materialisation of the full chain, so this only confirms correctness at reduced scale, not the performance claim |
| `EVD-062` | PASS | hashseed1_out='{"records": 10, "intact": true, "head": "195e2666ca36d6c15b71c74c27340703b4871d4bf49fb573afb4b55e2e8ed9dc", "merkle_root": "624bca090cc4956d105abb8fcd52f5a2d0cb6ca03454dc89f819b115b3b49319", "erased":' hashseed999999_out='{"records": 10, "intact": true, "head": "195e2666ca36d6c15b7... |
| `EVD-063` | PASS | merkle_root([])=0000000000000000000000000000000000000000000000000000000000000000 |
| `EVD-064` | PASS | merkle_root([h])=2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881 h=2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881 |
| `EVD-065` | PASS | merkle_root=62af5c3cb8da3e4f25061e829ebeea5c7513c54949115b1acc225930a90154da handcomputed=62af5c3cb8da3e4f25061e829ebeea5c7513c54949115b1acc225930a90154da |
| `EVD-066` | PASS | root([a,b,c])=d71dc32fa2cd95be60b32dbb3e63009fa8064407ee19f457c92a09a5ff841a8a root([a,b,c,c])=0bdf27bf7ec894ca7cadfe491ec1a3ece840f117989e8c5e9bd7086467bf6c38 different=True |
| `EVD-067` | PASS | orig=862532e6a3c9aafc2016810598ed0cc3025af5640db73224f586b6f1138385f4 swapped=a48572b1744e5e3f3473c9eaa91f73be774712d2b207c34eb537023af0ec6528 |
| `EVD-068` | PASS | mismatches_at_n=[] |
| `EVD-069` | PASS | sign()=6331f8754128a1772a2f97cf116f3cba522ae027434c32cfeb96c1b20bd3e890 manual_rfc2104=6331f8754128a1772a2f97cf116f3cba522ae027434c32cfeb96c1b20bd3e890 |
| `EVD-070` | PASS | {'wrong_key': False, 'wrong_head': False, 'truncated_sig': False, 'altered_one_char': False} |
| `EVD-071` | PASS | source='def verify_signature(head: str, key: bytes, signature: str) -> bool:\n    return hmac.compare_digest(sign(head, key), signature)' |
| `EVD-072` | FAIL | no refusal; sign(head, b'') returned 'a2b06ab139723730c894df6027a0dd71fe29655185867dc6157134d3a8ef0a25' |
| `EVD-073` | FAIL | evidence.ledger.sign()/verify_signature() called outside evidence/ledger.py+__init__.py: False -- other 'sign('/'verify_signature' hits are unrelated mechanisms (CLI bundle manifest Ed25519 signing, attestation.sign): ['/home/ashutosh/PycharmProjects/prama/src/prama/cli/bundle.py:149:            ... |
| `EVD-074` | PASS | forged_head=07bc5fccf289086f9bf8bfb28076937386b315edbe8d4af3c9cfd249a427924a original_head=195e2666ca36d6c15b71c74c27340703b4871d4bf49fb573afb4b55e2e8ed9dc verify_signature(forged_head, key, original_sig)=False |
| `EVD-075` | PASS | sequence=0 previous_hash==GENESIS:True verify_intact=True len=1 |
| `EVD-076` | PASS | control_id=cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe pql_hash=cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe |
| `EVD-077` | PASS | signature=(plan: 'ControlPlan', result: 'ControlResult', *, snapshot: 'Any' = None, parameters: 'dict[str, str] \| None' = None, started_at: 'Any' = None, rows: 'list[dict[str, Any]] \| None' = None, masked: 'tuple[str, ...]' = (), triggered_by: 'str' = 'schedule', control_id: 'str' = '', control_v... |
| `EVD-078` | PASS | criticality_1_record=1 criticality_4_record=4 -- caller CAN choose criticality; asymmetry with dimensions documented in recorder.py docstring |
| `EVD-079` | PASS | kind=none identifier='' exact=False |
| `EVD-080` | PASS | kind=file_digest identifier=sha256:abcd exact=True |
| `EVD-081` | PASS | duration_ms=0 |
| `EVD-082` | PASS | metrics={'scanned_rows': 10.0} |
| `EVD-083` | PASS | samples_digest='' sample_count=0 store_len=0 |
| `EVD-084` | FAIL | same_digest=True digest=sha256:db2610d342583a001c4eaa4ef57e8be3 forgetting_one_also_forgets_other=True (content-addressed sharing, not reference-counted) documented_in_SampleStore_docstrings=False |
| `EVD-085` | PASS | digest=sha256:b713f6d2a989e907c58516a7c8bb4877 len_hex_part=32 |
| `EVD-086` | PASS | verify_intact=True sample_count=50 rows_gone=True |
| `EVD-087` | FAIL | EvidenceRecord fields do not include which columns were masked (['binding', 'control_id', 'control_version', 'coverage', 'criticality', 'dataset', 'detail', 'dimensions', 'duration_ms', 'engine', 'evidence_version', 'finished_at', 'metrics', 'parameters', 'plan_id', 'previous_hash', 'sample_count... |
| `EVD-088` | PASS | caller_ledger_len=1 recorder.ledger_is_callers_object=True |
| `EVD-089` | PASS | cause=Cause.IDENTICAL answer_held=True differences=() |
| `EVD-090` | PASS | cause=Cause.STABLE is_divergence=False render='Replay of sequence 0 reached the same conclusion about changed data: pass.' |
| `EVD-091` | PASS | cause=Cause.CONTROL_CHANGED |
| `EVD-092` | PASS | cause=Cause.CONTROL_CHANGED |
| `EVD-093` | PASS | cause=Cause.PARAMETERS_CHANGED |
| `EVD-094` | PASS | cause=Cause.COVERAGE_CHANGED |
| `EVD-095` | PASS | cause=Cause.DATA_CHANGED needs_escalation=False |
| `EVD-096` | PASS | cause=Cause.SNAPSHOT_NOT_EXACT explanation='the source could not identify its own state exactly, so this run was never replayable and the original record said so' |
| `EVD-097` | PASS | cause=Cause.SNAPSHOT_NOT_EXACT (expected the engine change to be reported, or report to say both are true) render="Replay of sequence 0 diverged: pass → fail.\nCause: the source could not identify its own state exactly, so this run was never replayable and the original record said so.\nWhat diffe... |
| `EVD-098` | PASS | cause=Cause.ENGINE_CHANGED needs_escalation=True render="Replay of sequence 0 diverged: pass → fail.\nCause: the same control ran on a different engine and disagreed — a portability failure, and the conformance suite should have caught it.\nWhat differs:\n  engine: 'postgresql' → 'snowflake'\n  v... |
| `EVD-099` | PASS | cause=Cause.UNEXPLAINED needs_escalation=True all_accounted_for=False |
| `EVD-100` | PASS | answer_held=False verdict_changed=False render_headline='Replay of sequence 0 diverged: fail, with different numbers.' |
| `EVD-101` | PASS | cause=Cause.IDENTICAL differences=() |
| `EVD-102` | PASS | held=80 identical=60 all_accounted_for=False n_escalations=5 by_cause={'data_changed': 15, 'engine_changed': 4, 'identical': 60, 'stable': 20, 'unexplained': 1} |
| `EVD-103` | PASS | ValidationError: [INPUT.INVALID] the retention tiers are out of order \| Next: Hot must be no longer than warm, and warm no longer than cold. Evidence moves outward as it ages; it does not move back. \| Context: cold=2555, hot=400, warm=100 context={'hot': 400, 'warm': 100, 'cold': 2555} |
| `EVD-104` | PASS | accepted: RetentionPolicy(hot_days=90, warm_days=90, cold_days=90, expire=False) |
| `EVD-105` | PASS | 90.0->Tier.HOT 90.0001->Tier.WARM 365.0->Tier.WARM 365.0001->Tier.COLD |
| `EVD-106` | PASS | tier_at(10000)=Tier.COLD |
| `EVD-107` | PASS | tier_at(cold_days)=Tier.COLD tier_at(cold_days+1)=Tier.EXPIRED |
| `EVD-108` | PASS | tier_of=Tier.HOT |
| `EVD-109` | PASS | tier_of=Tier.HOT |
| `EVD-110` | FAIL | TypeError (naive vs aware datetime subtraction): can't subtract offset-naive and offset-aware datetimes |
| `EVD-111` | PASS | plan_counts={k: len(v) for k,v in plan.items()} total=3 len_ledger=3 |
| `EVD-112` | PASS | expire=True: 'Queryable for 90 days, online for 365, in WORM storage thereafter, and deleted after 2,555 days.' expire=False: 'Queryable for 90 days, online for 365, in WORM storage thereafter, and kept indefinitely beyond 2,555 days.' |
| `EVD-113` | PASS | ValidationError: [INPUT.INVALID] there is nothing to bundle \| Next: Bundle a period that contains evidence. An empty bundle would look like a period in which nothing ran, which is a different and much more alarming claim. |
| `EVD-114` | PASS | ResidencyRefused: [RESIDENCY.REFUSED] the evidence bundle for acme-eu may not go to US: it belongs to EU and this tenant's data must stay in EU. \| Next: Send this to a destination inside the tenant's residency, or change the tenant's residency rule if the obligation has changed. \| Context: destin... |
| `EVD-115` | PASS | whole call refused (no partial bundle object exists): [RESIDENCY.REFUSED] the evidence bundle for acme-eu may not go to US: it belongs to MIXED-EU-US and this tenant's data must stay in EU. \| Next: Send this to a destination inside the tenant's residency, or change the tenant's residency rule if ... |
| `EVD-116` | PASS | records=10 erased=2 from_seq=0 to_seq=9 digest_ok=True chain_head_ok=True bundle_version=1.0 evidence_version=1.1 |
| `EVD-117` | PASS | check()=True msg='10 record(s), chain intact, Merkle root 624bca090cc4956d…' |
| `EVD-118` | PASS | check()=False msg='the manifest says 10 record(s) and the file holds 8; this bundle is incomplete' |
| `EVD-119` | PASS | check()=False msg='the records do not match the digest in the manifest' |
| `EVD-120` | PASS | check()=False msg='the chain head does not match the manifest' |
| `EVD-121` | PASS | files=['evidence.ndjson', 'manifest.json'] |
| `EVD-122` | FAIL | prose="Each line is one JSON record. Recompute each record's content_hash as SHA-256 of its fields excluding previous_hash, content_hash and record_hash, serialised as JSON with keys sorted at every level and no insignificant whitespace. Recompute record_hash as SHA-256 of the ASCII concatenation... |
| `EVD-123` | PASS | bundle_version=1.0 |
| `EVD-124` | FAIL | grep -rn 'Archivist(' src/prama/cli src/prama/api -> (no hits: nothing in cli or api constructs an Archivist or calls .bundle()) |
| `EVD-125` | PASS | imports=['__future__', 'hashlib', 'json', 'pathlib', 'sys'] non_stdlib=[] |
| `EVD-126` | PASS | exit=0 stdout_tail=' that this file is the one the manifest describes. It does not say\nthe records are true: a false record, honestly written and correctly\nchained, produces a bundle that verifies exactly like this one.\n' stderr='' |
| `EVD-127` | PASS | exit=0 checks_found=['content hash', 'links to the one', 'sequence numbers', 'evidence file is the one', 'Merkle root', 'chain head'] missing=[] |
| `EVD-128` | PASS | exit=1 tail='ac6e8…, file is f4cab721a0bdbfcf…\n  [PASS] the Merkle root matches the records\n  [PASS] the chain head matches the last record\n\nAt least one check FAILED. This bundle is not what its manifest claims.\n' |
| `EVD-129` | PASS | exits=[2, 2, 2, 2] stderrs=['not a directory: /tmp/tmpwfwbpa2c/does-not-exist', 'no such file: /tmp/tmpf6lki7_w/manifest.json', 'manifest.json is not JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)', 'evidence line 2 is not JSON: Expecting property name enclosed ... |
| `EVD-130` | PASS | exit=2 stderr="could not read the bundle: [Errno 13] Permission denied: '/tmp/tmp112yb9w1/evidence.ndjson'" |
| `EVD-131` | PASS | zero_args_exit=2 stderr0='usage:  python3 verify_evidence.py <bundle-directory>\n        python3 verify_evidence.py manifest.json evidence.ndjson\n' three_args_exit=2 stderr3='usage:  python3 verify_evidence.py <bundle-directory>\n        python3 verify_evidence.py manifest.json evidence.ndjson\n' |
| `EVD-132` | PASS | dir_form_exit=0 files_form_exit=0 outputs_identical=True |
| `EVD-133` | PASS | exit=1 excerpt=['         record 4: content_hash is e8628f0abba4…, the bytes give 56add68a1b0f…'] |
| `EVD-134` | PASS | exit=1 fail_checks=['  [FAIL] every record links to the one before it', '  [FAIL] sequence numbers are contiguous'] |
| `EVD-135` | PASS | exit=1 link_pass=True seq_fail=True |
| `EVD-136` | PASS | tampered_erased_by_exit=1 missing_seal_exit=1 |
| `EVD-137` | PASS | exit=1 excerpt=['         record 2: the tombstone names a different original content hash than the record carries'] |
| `EVD-138` | PASS | exit=0 tombstone_line=['  [PASS] 2 record(s) carry a tombstone whose seal holds'] |
| `EVD-139` | PASS | exit=1 excerpt=["  [FAIL] the manifest's record count (10) matches the file (7)", '         A truncated file is the failure an archive actually suffers, and only the count reveals it — the remaining chain is perfectly valid.'] |
| `EVD-140` | PASS | exit=1 fail_lines=['  [FAIL] the evidence file is the one the manifest describes'] |
| `EVD-141` | PASS | exit=1 merkle_fail=True head_fail=True |
| `EVD-142` | FAIL | exit=0 says_every_check_passed=True -- an empty bundle (0 records) verifies green with no distinguishing statement that there was nothing to check |
| `EVD-143` | PASS | exit=0 tail='Every check passed.\n\nThis says the records have not been altered since they were written,\nand that this file is the one the manifest describes. It does not say\nthe records are true: a false record, honestly written and correctly\nchained, produces a bundle that verifies exactly l... |
| `EVD-144` | FAIL | disagreements(name,prama_intact,independent_ok)=[('erased_tampered', True, False), ('extra_key', True, False)] -- predicted by EVD-006(non_ascii, not in this corpus fn but same canonical bug applies to any record if dataset made non-ascii and prama also passes it through differently -- see EVD-00... |
| `EVD-145` | PASS | NOT_CONTENT=('previous_hash', 'content_hash', 'record_hash') (tombstone is popped separately in verify_chain, not via NOT_CONTENT -- confirmed correct by inspection) |
| `EVD-146` | PASS | lines_shown=5 (expected 5, out of 20 failing records) |
| `EVD-147` | PASS | exit=1 no_crash=True reported_as_failure=True stderr='' |
| `EVD-148` | PASS | tombstone_check_shown_when_no_erasures=False (expected: absent, not shown as passing) |
| `SCR-001` | PASS | composites={<Method.MEAN: 'mean'>: 0.9500000000000001, <Method.MINIMUM: 'minimum'>: 0.9, <Method.WEIGHTED: 'weighted'>: 0.95} composite()_default=0.95 weighted=0.95 |
| `SCR-002` | PASS | mean=0.75 (expected ~0.75, i.e. equal weight per dimension not per control) |
| `SCR-003` | PASS | minimum=0.62 worst=Dimension.TIMELINESS |
| `SCR-004` | PASS | pytest tests/score/test_composite.py::test_the_weighted_score_is_not_dominated_by_column_count -> ['tests/score/test_composite.py::test_the_weighted_score_is_not_dominated_by_column_count PASSED [  5%]'] |
| `SCR-005` | PASS | pytest tests/score/test_composite.py::test_rows_weight_within_a_tier_and_never_across_one -> ['tests/score/test_composite.py::test_rows_weight_within_a_tier_and_never_across_one PASSED [ 11%]'] |
| `SCR-006` | PASS | weights={<Criticality.TIER_1: 1>: 16.0, <Criticality.TIER_2: 2>: 8.0, <Criticality.TIER_3: 3>: 2.0, <Criticality.TIER_4: 4>: 1.0} |
| `SCR-007` | PASS | pytest tests/score/test_composite.py::test_a_control_that_did_not_run_is_not_a_pass -> ['tests/score/test_composite.py::test_a_control_that_did_not_run_is_not_a_pass PASSED [ 38%]'] |
| `SCR-008` | PASS | pytest tests/score/test_composite.py::test_an_empty_scan_is_not_a_pass -> ['tests/score/test_composite.py::TestScanningNothingIsNotPassing::test_an_empty_scan_is_not_a_pass PASSED [ 72%]'] |
| `SCR-009` | PASS | pytest tests/score/test_composite.py::test_an_empty_scan_is_not_counted_as_measured -> ['tests/score/test_composite.py::TestScanningNothingIsNotPassing::test_an_empty_scan_is_not_counted_as_measured PASSED [ 77%]'] |
| `SCR-010` | PASS | pytest tests/score/test_composite.py::test_nothing_measured_is_not_a_perfect_score -> ['tests/score/test_composite.py::test_nothing_measured_is_not_a_perfect_score PASSED [ 44%]'] |
| `SCR-011` | PASS | coverage=0.7 controls=10 not_run=2 scanned_nothing=1 |
| `SCR-012` | PASS | coverage(no measurements)=0.0 |
| `SCR-013` | PASS | pytest tests/score/test_composite.py::test_the_three_composites_answer_different_questions -> ['tests/score/test_composite.py::test_the_three_composites_answer_different_questions PASSED [ 22%]'] |
| `SCR-014` | PASS | at_0.1_disagree=False at_0.1000001_disagree=True |
| `SCR-015` | PASS | single_composite_disagree=False |
| `SCR-016` | PASS | pytest tests/score/test_composite.py::test_dimensions_come_before_composites -> ['tests/score/test_composite.py::test_dimensions_come_before_composites PASSED [ 33%]'] |
| `SCR-017` | PASS | scanned=1000 violations=5 controls=2 tier_weighted_score=0.5294117647058824 naive_raw_ratio=0.995 |
| `SCR-018` | PASS | order_a=[<Dimension.COMPLETENESS: 'completeness'>, <Dimension.TIMELINESS: 'timeliness'>, <Dimension.VALIDITY: 'validity'>] order_b=[<Dimension.COMPLETENESS: 'completeness'>, <Dimension.TIMELINESS: 'timeliness'>, <Dimension.VALIDITY: 'validity'>] |
| `SCR-019` | FAIL | rate(scanned=10,violations=15)=-0.5 (expected: refusal or a visibly-flagged clamp, not a silent negative) weighted_composite=-0.5 |
| `SCR-020` | PASS | composites={<Method.MEAN: 'mean'>: 1.0, <Method.MINIMUM: 'minimum'>: 1.0, <Method.WEIGHTED: 'weighted'>: 1.0} methods_disagree=False |
| `SCR-021` | PASS | keys=['composites', 'controls', 'coverage', 'dataset', 'dimensions', 'methods_disagree', 'not_run', 'scanned_nothing', 'summary'] composite_keys=['mean', 'minimum', 'weighted'] |
| `SCR-022` | FAIL | round(0.9999996, 6)=1.0 -- to_dict()['composites']['weighted']=1.0 (a failing/near-failing dataset renders as a clean 1.0 via to_dict's round-to-6-places, and nothing documents this as lossy) |
| `SCR-023` | PASS | record.criticality=1 -> Measurement.criticality=1 (read straight from the record, no live tier lookup) |
| `SCR-024` | PASS | pytest tests/score/test_composite.py::test_an_objective_without_a_budget_is_a_wish -> ['tests/score/test_composite.py::test_an_objective_without_a_budget_is_a_wish PASSED [ 50%]'] |
| `SCR-025` | PASS | consumed(1e6 rows, 2500 violations, objective=0.995)=0.49999999999999956 |
| `SCR-026` | PASS | objective=1.0: consumed(1000,0)=0.0 consumed(1000,1)=1.0 |
| `SCR-027` | PASS | consumed(0,0)=0.0 describe(0,0)="ds completeness: 0% of the month's budget used, comfortably inside 99.5%" claims_objective_met=False |
| `SCR-028` | PASS | 0.5->"ds completeness: 50% of the month's budget used, comfortably inside 99.0%" 0.8->"ds completeness: 80% of the month's budget used, 20 rows of allowance left. At this rate the objective is missed before the period ends" 1.2->"ds completeness: the month's budget is spent and then some — 120 ro... |
| `SCR-029` | PASS | describe(999 scanned, 4 violations)="ds completeness: 80% of the month's budget used, 0 rows of allowance left. At this rate the objective is missed before the period ends" (budget=0.005*999=4.995, int()->4, so allowed-violations=0 not negative) |
| `SCR-030` | PASS | EvidenceRecord fields=['binding', 'control_id', 'control_version', 'coverage', 'criticality', 'dataset', 'detail', 'dimensions', 'duration_ms', 'engine', 'evidence_version', 'finished_at', 'metrics', 'parameters', 'plan_id', 'previous_hash', 'sample_count', 'samples_digest', 'sequence', 'snapshot... |
| `SCR-031` | PASS | pytest tests/score/test_trust.py::test_a_column_with_nothing_upstream_scores_on_its_own_evidence -> ['tests/score/test_trust.py::test_a_column_with_nothing_upstream_scores_on_its_own_evidence PASSED [ 40%]'] |
| `SCR-032` | PASS | trust(column_absent_from_local_map)=1.0 |
| `SCR-033` | PASS | score=0.7200000000000001 hand_computed(0.9*0.8)=0.7200000000000001 derivation=['a.x (0.90) → b.y: 0.90 in, 0.90 out (copied unchanged)', 'b.y (0.80) → c.z: 0.90 in, 0.72 out (copied unchanged)'] |
| `SCR-034` | PASS | pytest tests/score/test_trust.py::test_the_default_treats_inputs_as_complementary -> ['tests/score/test_trust.py::test_the_default_treats_inputs_as_complementary PASSED [  6%]'] |
| `SCR-035` | PASS | redundant_score=0.98775 (healthy path governs, > corrupt feed's 0.4) no_auto_selection_logic_found=True |
| `SCR-036` | PASS | pytest tests/score/test_trust.py::test_every_semiring_can_say_what_it_means -> ['tests/score/test_trust.py::test_every_semiring_can_say_what_it_means PASSED [ 20%]'] |
| `SCR-037` | PASS | WEAKEST_LINK score=0.8 (expected ~0.8, min across chain-of-3-at-0.9 and single-hop-at-0.8) |
| `SCR-038` | PASS | pytest tests/score/test_trust.py::test_an_aggregate_makes_a_column_more_trustworthy_than_its_source -> ['tests/score/test_trust.py::test_an_aggregate_makes_a_column_more_trustworthy_than_its_source PASSED [ 73%]'] |
| `SCR-039` | PASS | _attenuate(0.9, attenuation=2.5)=0.75 _attenuate(-0.5, attenuation=0.7)=0.0 _attenuate(0.0, attenuation=10.0)=0.0 all_in_[0,1]=True |
| `SCR-040` | PASS | pytest tests/score/test_trust.py::test_a_cycle_does_not_hang_the_propagation -> ['tests/score/test_trust.py::test_a_cycle_does_not_hang_the_propagation PASSED [100%]'] |
| `SCR-041` | FAIL | n_hops_in_derivation=8 reached_all_the_way_to_t0=False explanation_mentions_truncation=False score=1.0 explanation='t15.x scores 1.00. Its own controls say 1.00. trust multiplies along a path and the weakest path governs, because a derived value needs every one of its inputs. t7.x (1.00) → t8.x: ... |
| `SCR-042` | FAIL | 6-wide x 8-level graph: completed=True elapsed_s=30.13 budget_s=30  |
| `SCR-043` | PASS | pytest tests/score/test_trust.py::test_the_derivation_shows_the_path_that_decided_the_score -> ['tests/score/test_trust.py::test_the_derivation_shows_the_path_that_decided_the_score PASSED [ 26%]'] |
| `SCR-044` | PASS | pytest tests/score/test_trust.py::test_the_alternatives_considered_are_counted -> ['tests/score/test_trust.py::test_the_alternatives_considered_are_counted PASSED [ 33%]'] |
| `SCR-045` | PASS | pytest tests/score/test_trust.py::test_a_control_that_caught_the_problem_stops_it_propagating -> ['tests/score/test_trust.py::test_a_control_that_caught_the_problem_stops_it_propagating PASSED [ 53%]'] |
| `SCR-046` | PASS | pytest tests/score/test_trust.py::test_a_control_that_did_not_run_contains_nothing -> ['tests/score/test_trust.py::test_a_control_that_did_not_run_contains_nothing PASSED [ 60%]'] |
| `SCR-047` | PASS | local=0.4 with perfect upstream(1.0) -> score=0.4 (expected 0.4, min(own, combined)) |
| `SCR-048` | PASS | score=local-1e-12: is_inherited=False (expect False); score=local-1e-7: is_inherited=True (expect True) |
| `SCR-049` | PASS | explanation='d.w scores 0.90. Its own controls say 1.00, and upstream brings it down to 0.90. trust multiplies along a path and the weakest path governs, because a derived value needs every one of its inputs. a.x (0.70) → b.y: 0.70 in, 0.70 out (copied unchanged) b.y (0.90) → c.z: 0.70 in, 0.74 o... |
| `SCR-050` | PASS | pytest tests/score/test_trust.py::test_the_queue_is_least_trustworthy_first -> ['tests/score/test_trust.py::test_the_queue_is_least_trustworthy_first PASSED [ 93%]'] |
| `SCR-051` | PASS | pytest tests/score/test_trust.py::test_trust_ranks_the_consequence_where_severity_ranks_the_finding -> ['tests/score/test_trust.py::test_trust_ranks_the_consequence_where_severity_ranks_the_finding PASSED [ 86%]'] |
| `SCR-052` | PASS | n_columns=30 mismatches=[] |
| `SEC-001` | PASS | pytest tests/architecture/test_scopes.py::TestThereIsOneVocabulary::test_every_granted_permission_is_a_declared_scope -> tests/architecture/test_scopes.py::TestThereIsOneVocabulary::test_every_granted_permission_is_a_declared_scope PASSED [ 63%] |
| `SEC-002` | PASS | pytest ...::test_every_scope_a_route_requires_can_be_held -> tests/architecture/test_scopes.py::TestThereIsOneVocabulary::test_every_scope_a_route_requires_can_be_held PASSED [ 81%] |
| `SEC-003` | PASS | n_scopes=16 bad=[] |
| `SEC-004` | PASS | exact_match=True different_scope=False |
| `SEC-005` | PASS | control:*->control:approve=True control:*->incident:read=False con:*->control:approve=False |
| `SEC-006` | PASS | all_true=True failures=[] |
| `SEC-007` | PASS | all_false=True unexpected_true=[] |
| `SEC-008` | PASS | unknown(['semantic:read','control:read'])=['semantic:read'] |
| `SEC-009` | PASS | unknown(['*','control:*','nonsense:*'])=[] -- nonsense:* silently accepted, confirming the catalogue's concern that unknown() does not catch a typo in a wildcard prefix |
| `SEC-010` | PASS | case_mismatch_permits=False leading_space_permits=False |
| `SEC-011` | PASS | grep for a second wildcard matcher outside security/scopes.py -> [] |
| `SEC-012` | PASS | tested 15 mutating routes with a declaration:read-only key -- non-403 results: [] |
| `SEC-013` | FAIL | POST invalid body to POST /api/v1/datasets with read-only key -> 422 (expected 403, not 422) |
| `SEC-014` | PASS | signed_in=True POST /reconciliation/breaks/.../assign -> 500; .../explain -> 500 (steward holds break:* per BUILTIN_ROLES; route registered via self.page() with no explicit scope=, so it defaults to auto->declaration:write for a POST, which steward does NOT hold -- steward's grants: ['control:pro... |
| `SEC-015` | PASS | verdict=Verdict.UNRESTRICTED may_proceed=True describe='this data may go to US: this tenant declares no residency rule, so nothing is restricted. That is an absence of a rule, not an approval.' |
| `SEC-016` | PASS | verdict=Verdict.PERMITTED describe="this data may go to EU: the tenant's data must stay in EEA, EU, and EU is among them." |
| `SEC-017` | PASS | verdict=Verdict.REFUSED describe="this data may not go to US: it belongs to EU and this tenant's data must stay in EU." |
| `SEC-018` | PASS | dest=EU,jur=US -> Verdict.REFUSED may_proceed=False; dest=US,jur=EU -> Verdict.REFUSED may_proceed=False |
| `SEC-019` | PASS | verdict=Verdict.UNDECLARED may_proceed=False is_undeclared=True |
| `SEC-020` | PASS | undeclared_remedy='Declare the jurisdiction this data belongs to. Undeclared is not unrestricted: treating it as unrestricted is how the one table nobody got round to declaring is the one that leaves the region.' dest_refused_remedy="Send this to a destination inside the tenant's residency, or ch... |
| `SEC-021` | PASS | verdict=Verdict.REFUSED destination='(unstated)' destination_unstated=True |
| `SEC-022` | PASS | verdict=Verdict.UNRESTRICTED destination='(unstated)' -- asymmetry with SEC-021 confirmed: unrestricted branch runs before the missing-destination branch |
| `SEC-023` | PASS | p1.allowed=('EEA', 'EU') p2.allowed=('EEA', 'EU') equal=True |
| `SEC-024` | PASS | Policy.of('').is_unrestricted=True Policy.of(' , ').is_unrestricted=True Policy.of([]).is_unrestricted=True |
| `SEC-025` | PASS | verdict=Verdict.PERMITTED |
| `SEC-026` | PASS | n_distinct=4 all_name_subject=True |
| `SEC-027` | PASS | refusals=[<Verdict.REFUSED: 'refused'>, <Verdict.UNDECLARED: 'undeclared'>] expected=[REFUSED, UNDECLARED] |
| `SEC-028` | PASS | keys=['destination', 'jurisdiction', 'may_proceed', 'message', 'rule', 'subject', 'verdict'] |
| `SEC-029` | PASS | grep hits: (none) |
| `SEC-030` | PASS | unrestricted='no residency rule: data may go anywhere' with_rule='data must stay in EEA, EU' |
| `SEC-031` | PASS | pytest tests/architecture/test_egress.py -> returncode=0 passed=34 failed=0 |
| `SEC-032` | PASS | src/ untouched (mutation applied only to a scratch copy at /tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/r4/trust/rest_mutated.py); reaches_the_gate() on the real file=True, on the mutated scratch copy=False (expected: real file True, mutate... |
| `SEC-033` | PASS | refused_per_point={'model-inference': True, 'catalog-write-back': True, 'siem-export': True, 'evidence-export': True, 'secret-fetch': True, 'source-read': True, 'alert-delivery': True} (tested Gate.require directly for all 7 registered points, not by driving each real connector/provider end to en... |
| `SEC-034` | PASS | ValidationError: [INPUT.INVALID] no such egress point: 'siem_export' \| Next: Register it in prama.security.egress.EGRESS_POINTS. An egress the registry does not name is an egress nobody reviews. Known: model-inference, catalog-write-back, siem-export, evidence-export, secret-fetch, source-read, a... |
| `SEC-035` | PASS | decide()_returns_refused_without_raising=True require()_raises=True |
| `SEC-036` | PASS | type=<class 'prama.security.egress.ResidencyRefused'> code=RESIDENCY.REFUSED isinstance_ValidationError=False |
| `SEC-037` | PASS | context={'egress': 'evidence-export', 'tenant': 'acme', 'destination': 'EU', 'jurisdiction': '(undeclared)'} |
| `SEC-038` | PASS | n_points=7 incomplete=[] |
| `SEC-039` | FAIL | EGRESS_POINTS['source-read'].jurisdiction_from still documented as "the dataset's declared jurisdiction": True; connect/sources/rest.py:gate.require('source-read', ...) still passes jurisdiction=self._region (the connector-configured region, same as destination): True; RestSource now has a genuin... |
| `SEC-040` | PASS | secrets/vault.py gate.require('secret-fetch', destination=self._region, jurisdiction=self._region, ...) present: True; EGRESS_POINTS['secret-fetch'].jurisdiction_from documents exactly this as deliberate ('the same region: a credential belongs wherever its store is, and there is no separate subje... |
| `SEC-041` | PASS | unregistered scratch module using httpx.post() found by network_modules() scan and flagged as unaccounted: True -- this is exactly what test_every_module_that_can_reach_the_network_is_accounted_for would fail on; real modules besides the injected scratch one that the scan currently misses: [] (em... |
| `SEC-042` | PASS | context={'egress': 'evidence-export', 'tenant': '01ACME', 'destination': 'US', 'jurisdiction': 'EU'} |
| `SEC-043` | PASS | message=[RESIDENCY.REFUSED] evidence-export may not go to US: it belongs to EU and this tenant's data must stay in EU. \| Next: Send this to a destination inside the tenant's residency, or change the tenant's residency rule if the obligation has changed. \| Context: destination='US', egress='eviden... |
| `SEC-044` | PASS | security/egress.py mentions audit logging at refusal: True |
| `SEC-045` | PASS | decrypted=b'the quick brown fox' |
| `SEC-046` | PASS | ciphertext_differs=True nonce_differs=True wrapped_key_differs=True |
| `SEC-047` | PASS | signature=(plaintext: 'bytes', *, provider: 'KeyProvider', tenant_id: 'str', purpose: 'str') -> 'Envelope' has_nonce_param=False NONCE_BYTES=12 actual_nonce_len=12 |
| `SEC-048` | PASS | DATA_KEY_BYTES=32 config_references=(none) |
| `SEC-049` | PASS | KeyRevoked: [CMK.UNWRAP_REFUSED] this envelope belongs to a different estate \| Next: The ciphertext is sealed to the tenant it was written for. Read it as that tenant, or investigate how a row from one estate came to be read as another's. \| Context: expected='tenant-B', sealed_for='tenant-A' unwr... |
| `SEC-050` | PASS | decrypt(envelope, provider=p) with tenant_id=None decrypts_without_cross_tenant_check=True; real call sites of cmk.decrypt outside cmk.py itself: [] |
| `SEC-051` | PASS | KeyRevoked: [CMK.UNWRAP_REFUSED] this envelope was sealed for a different purpose \| Next: A key scoped to one purpose must not open another's data. Use the purpose the envelope was written under. \| Context: expected='evidence', sealed_for='samples' |
| `SEC-052` | PASS | KeyRevoked: [CMK.UNWRAP_REFUSED] the customer key did not unwrap this data key \| Next: Either the key was rotated out and the old version is gone, or this envelope belongs to a different tenant or purpose — the context is authenticated, so it cannot decrypt into the wrong one. |
| `SEC-053` | PASS | KeyRevoked: [CMK.UNWRAP_REFUSED] the envelope did not decrypt under its own data key \| Next: The ciphertext or its context was altered. The context is authenticated, so a tenant or purpose changed after the fact breaks decryption rather than quietly changing what this is. |
| `SEC-054` | PASS | KeyRevoked: [CMK.UNWRAP_REFUSED] the customer key did not unwrap this data key \| Next: Either the key was rotated out and the old version is gone, or this envelope belongs to a different tenant or purpose — the context is authenticated, so it cannot decrypt into the wrong one. |
| `SEC-055` | PASS | KeyRevoked: [CMK.UNWRAP_REFUSED] the customer key did not unwrap this data key \| Next: Either the key was rotated out and the old version is gone, or this envelope belongs to a different tenant or purpose — the context is authenticated, so it cannot decrypt into the wrong one. |
| `SEC-056` | PASS | results=['KeyRevoked', 'KeyRevoked', 'KeyRevoked'] |
| `SEC-057` | PASS | KeyRevoked: [CMK.UNWRAP_REFUSED] this key has been revoked and cannot wrap \| Next: Provision a new key. The revoked one is not coming back. |
| `SEC-058` | PASS | module_docstring_states_irreversible_and_not_selective=True docs_mentioning_revocation=['/home/ashutosh/PycharmProjects/prama/docs/22-distributed-execution.md', '/home/ashutosh/PycharmProjects/prama/docs/13-security-governance-compliance.md', '/home/ashutosh/PycharmProjects/prama/docs/reviews/202... |
| `SEC-059` | PASS | envelope.key_id='key-1' (present, so a provider CAN select by it) decrypted_with_old_key=True |
| `SEC-060` | PASS | PramaError code=CMK.BAD_CONTEXT: [CMK.BAD_CONTEXT] an encryption context value contains a null byte \| Next: Context keys and values are text. A null byte would let one field forge another. |
| `SEC-061` | PASS | a1=b'purpose\x00samples\x01tenant\x00acme' a2=b'purpose\x00samples\x01tenant\x00acme' |
| `SEC-062` | PASS | PramaError code=CMK.NO_TENANT: [CMK.NO_TENANT] an envelope needs a tenant \| Next: The tenant is authenticated into the ciphertext. Without it, an envelope moved between tenants would decrypt cleanly into the wrong one. |
| `SEC-063` | PASS | subprocess with cryptography masked -> stdout='CmkUnavailable CMK.UNAVAILABLE True' stderr_tail='' |
| `SEC-064` | PASS | fields_match=True decrypted=b'round trip me' |
| `SEC-065` | PASS | grep hits for the 'no cloud KMS exercised' disclosure: ['/home/ashutosh/PycharmProjects/prama/docs/03-business-semantic-layer.md:42:model has not been exercised against an estate of the size §6 describes.', '/home/ashutosh/PycharmProjects/prama/docs/13-security-governance-compliance.md:22:**not m... |
| `SEC-066` | PASS | grep -rln LocalTestKeyProvider src/ config/ -> ['/home/ashutosh/PycharmProjects/prama/src/prama/security/__pycache__/cmk.cpython-313.pyc', '/home/ashutosh/PycharmProjects/prama/src/prama/security/cmk.py'] (excluding its own definition file, hits: []) |
| `SEC-067` | PASS | pytest tests/security/test_oidc.py::test_it_verifies_and_returns_the_claims -> ['tests/security/test_oidc.py::TestAGoodToken::test_it_verifies_and_returns_the_claims PASSED [  3%]'] |
| `SEC-068` | PASS | pytest tests/security/test_oidc.py::test_an_es256_token_verifies -> ['tests/security/test_oidc.py::TestEllipticCurve::test_an_es256_token_verifies PASSED [ 81%]'] |
| `SEC-069` | PASS | pytest tests/security/test_oidc.py::test_alg_none_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_alg_none_is_refused PASSED [ 15%]'] |
| `SEC-070` | PASS | pytest tests/security/test_oidc.py::test_hmac_signed_with_the_public_key_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_hmac_signed_with_the_public_key_is_refused PASSED [ 18%]'] |
| `SEC-071` | PASS | InvalidToken: [SSO.TOKEN_INVALID] algorithm 'ES256' is not accepted \| Next: Accepted: RS256. Symmetric algorithms are refused outright: with a public verification key they make the signature forgeable by anyone. |
| `SEC-072` | PASS | pytest tests/security/test_oidc.py::test_an_unknown_kid_is_refused_rather_than_tried_against_every_key -> ['tests/security/test_oidc.py::TestForgeries::test_an_unknown_kid_is_refused_rather_than_tried_against_every_key PASSED [ 25%]'] |
| `SEC-073` | PASS | pytest tests/security/test_oidc.py::test_a_token_with_no_kid_against_several_keys_is_refused -> ['tests/security/test_oidc.py::TestKeySetHygiene::test_a_token_with_no_kid_against_several_keys_is_refused PASSED [ 78%]'] |
| `SEC-074` | PASS | verified subject=user-42 |
| `SEC-075` | PASS | pytest tests/security/test_oidc.py::test_an_empty_key_set_verifies_nothing -> ['tests/security/test_oidc.py::TestForgeries::test_an_empty_key_set_verifies_nothing PASSED [ 71%]'] |
| `SEC-076` | PASS | pytest tests/security/test_oidc.py::test_an_encryption_key_is_not_a_signing_key -> ['tests/security/test_oidc.py::TestKeySetHygiene::test_an_encryption_key_is_not_a_signing_key PASSED [ 75%]'] |
| `SEC-077` | PASS | pytest tests/security/test_oidc.py::test_an_altered_payload_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_an_altered_payload_is_refused PASSED [ 28%]'] |
| `SEC-078` | PASS | InvalidToken: [SSO.TOKEN_INVALID] the signature does not verify against the provider's key \| Next: The token was not signed by this provider, or was altered in transit. Nothing about the claims inside it can be believed. (expected: signature failure reported, not the payload-not-JSON failure) |
| `SEC-079` | PASS | pytest tests/security/test_oidc.py::test_a_token_from_another_issuer_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_a_token_from_another_issuer_is_refused PASSED [ 34%]'] |
| `SEC-080` | PASS | pytest tests/security/test_oidc.py::test_a_token_for_another_client_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_a_token_for_another_client_is_refused PASSED [ 31%]'] |
| `SEC-081` | PASS | pytest tests/security/test_oidc.py::test_an_audience_list_containing_us_is_accepted -> ['tests/security/test_oidc.py::TestAGoodToken::test_an_audience_list_containing_us_is_accepted PASSED [  6%]'] |
| `SEC-082` | PASS | pytest tests/security/test_oidc.py::test_an_expired_token_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_an_expired_token_is_refused PASSED [ 37%]'] |
| `SEC-083` | PASS | pytest tests/security/test_oidc.py::test_a_token_from_the_future_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_a_token_from_the_future_is_refused PASSED [ 40%]'] |
| `SEC-084` | PASS | pytest tests/security/test_oidc.py::test_a_not_yet_valid_token_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_a_not_yet_valid_token_is_refused PASSED [ 43%]'] |
| `SEC-085` | PASS | pytest tests/security/test_oidc.py::test_a_missing_required_claim_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_a_missing_required_claim_is_refused[sub] PASSED [ 56%]', 'tests/security/test_oidc.py::TestForgeries::test_a_missing_required_claim_is_refused[iss] PASSED [ 59%]', 't... |
| `SEC-086` | PASS | pytest tests/security/test_oidc.py::test_an_empty_subject_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_an_empty_subject_is_refused PASSED [ 53%]'] |
| `SEC-087` | PASS | pytest tests/security/test_oidc.py::test_a_replayed_token_without_our_nonce_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_a_replayed_token_without_our_nonce_is_refused PASSED [ 46%]'] |
| `SEC-088` | PASS | pytest tests/security/test_oidc.py::test_a_nonce_is_unpredictable -> ['tests/security/test_oidc.py::TestNonces::test_a_nonce_is_unpredictable PASSED [100%]'] |
| `SEC-089` | PASS | pytest tests/security/test_oidc.py::test_a_malformed_token_is_refused -> ['tests/security/test_oidc.py::TestForgeries::test_a_malformed_token_is_refused PASSED [ 68%]'] |
| `SEC-090` | PASS | InvalidToken: [SSO.TOKEN_INVALID] the signature does not verify against the provider's key \| Next: The token was not signed by this provider, or was altered in transit. Nothing about the claims inside it can be believed. |
| `SEC-091` | PASS | P-521 curve: PASS: [SSO.TOKEN_INVALID] unsupported elliptic curve 'P-521' \| Next: Only P-256 is accepted. Ask the provider for RS256 or ES256.; kty=oct: PASS: [SSO.TOKEN_INVALID] unsupported key type 'oct' \| Next: Only RSA and EC keys are accepted. |
| `SEC-092` | FAIL | files under src/prama/web or src/prama/api referencing OIDC verification machinery: [] -- no console or API route calls prama.security.oidc at all; the module ships tested and standalone (docs/19 W10.3) but sign-in (auth_routes.py) is local-password-only, so this case's Steps (drive a failed sign... |
| `SEC-093` | PASS | digest(idp-a,user-42)=7b4659f140faba5db39248b0410841a32f1de1536f3e2a841a4be54f318f9840 digest(idp-b,user-42)=62f09677503341449f1ee2ae53d4fd1e1943c70c547f213f0021e6cc369cdb9f differ=True |
| `SEC-094` | PASS | pytest tests/security/test_oidc.py::test_an_unmapped_group_grants_nothing -> ['tests/security/test_oidc.py::TestClaimMapping::test_an_unmapped_group_grants_nothing PASSED [ 84%]'] |
| `SEC-095` | PASS | groups_as_string=('owners',) roles_as_list=('owners',) absent=() |
| `SEC-096` | PASS | subprocess with cryptography masked -> stdout='SsoUnavailable SSO.UNAVAILABLE True' stderr='' |
| `SEC-097` | PASS | imports=['__future__', 'base64', 'collections.abc', 'cryptography.hazmat.primitives', 'cryptography.hazmat.primitives.asymmetric', 'cryptography.hazmat.primitives.asymmetric.utils', 'dataclasses', 'hashlib', 'json', 'prama.core.errors', 'secrets', 'typing'] network_hits=set() |
| `SEC-098` | PASS | change=Change.CREATE roles=('owner',) reason='the directory has somebody Prama does not' |
| `SEC-099` | PASS | change=Change.NONE reason='the directory sent an inactive user Prama has never held' |
| `SEC-100` | PASS | change=Change.DEACTIVATE reason='the directory says this person has left. The account is deactivated and kept: they signed things, and deleting them leaves an attestation signed by a principal that does not exist' |
| `SEC-101` | PASS | change=Change.REFUSED reason='this is the last active administrator, and deactivating them locks everybody out of the tenant with no way back in that does not involve the database' |
| `SEC-102` | PASS | decisions=[('admin-0', <Change.DEACTIVATE: 'deactivate'>), ('admin-1', <Change.DEACTIVATE: 'deactivate'>), ('admin-2', <Change.DEACTIVATE: 'deactivate'>), ('admin-3', <Change.REFUSED: 'refused'>)] n_deactivate=3 n_refused=1 |
| `SEC-103` | PASS | change=Change.UPDATE roles=('steward',) fields=(('roles', 'owner, steward', 'steward'),) |
| `SEC-104` | PASS | fields=() (expected: no 'email' field change) |
| `SEC-105` | PASS | change=Change.REFUSED reason='the directory sent no external id, and without one this cannot be matched to an account — a create would make a duplicate on every sync' |
| `SEC-106` | PASS | change=Change.REACTIVATE roles=('owner',) |
| `SEC-107` | PASS | change=Change.NONE applies=False |
| `SEC-108` | PASS | REFUSED.applies=False NONE.applies=False distinct=True |
| `SEC-109` | PASS | groups_display=('Owners',) groups_value=('owners-id',) groups_string=('owners',) primary_email=b@x.com formatted_name=Full Name displayName=Display Only |
| `SEC-110` | PASS | active=True docstring_has_warning=True |
| `SEC-111` | PASS | describe="update jill: email 'old@bank.com' to 'new@bank.com', display_name 'Old Name' to 'New Name', roles 'owner' to 'steward' [roles: steward]" |
| `SEC-112` | PASS | no_http_routes_found=True module_docstring_says_not_written=True docs_confirm=True docs_hits=['/home/ashutosh/PycharmProjects/prama/docs/19-implementation-roadmap.md:898:W10.3 ✅ SSO/SCIM, vault, CMK (local sign-in, RBAC, OIDC ID-token verification refusing eight forgery classes, SCIM reconciliati... |
| `SEC-113` | PASS | n_lines=3 sample_keys=['@timestamp', 'event', 'observer', 'organization', 'prama', 'source', 'trace', 'user'] |
| `SEC-114` | PASS | one_line=True has_escapes=True rendered='CEF:0\|Prama\|Prama\|0.1.0\|control.approve\|control.approve\|2\|rt=2026-01-01T00:00:00Z suid=alice suser=principal src=10.0.0.1 outcome=success cs1Label=tenant cs1=t1 cs2Label=objectKind cs2=control cs3Label=objectId cs3=a\\=b\|c\\\\d\\ne\\rf cs4Label=correlation... |
| `SEC-115` | PASS | header_line='CEF:0\|Prama\|Prama\|0.1.0\|cont\\\|rol.approve\|cont\\\|rol.approve\|2\|rt=2026-01-01T00:00:00Z suid=alice suser=principal src=10.0.0.1 outcome=success cs1Label=tenant cs1=t1 cs2Label=objectKind cs2=control cs3Label=objectId cs3=ctl-1 cs4Label=correlationId cs4=01COR' |
| `SEC-116` | PASS | denied=8 failure=6 success=2 |
| `SEC-117` | PASS | role.grant/success=7 report.read/failure=6 |
| `SEC-118` | PASS | evidence.erase=8 max_of_others_at_denied=8 |
| `SEC-119` | PASS | severity_of(unknown_action, 'partial')=2 |
| `SEC-120` | PASS | prama_detail={'dataset': 'positions_eod', 'object_id': 'ctl-1', 'object_kind': 'control'} dropped=1 |
| `SEC-121` | PASS | describe='1 event(s) rendered; 1 detail field(s) were not exported because they are not on the allow-list, which is not the same as there having been none' |
| `SEC-122` | PASS | results=[(0, 'ok'), (0, 'ok'), (0, 'ok')] |
| `SEC-123` | FAIL | cs1Label='tenant' (fixed to 'tenant', not a detail key) cs5Label=control cs6Label=control_id cs7_present=False -- of 8 detail keys offered, only 2 were carried via cs5/cs6 because cs1..cs4 are reserved for tenant/objectKind/objectId/correlationId, not available for arbitrary detail keys as the ca... |
| `SEC-124` | PASS | ResidencyRefused: [RESIDENCY.REFUSED] the audit event stream may not go to US: it belongs to EU and this tenant's data must stay in EU. \| Next: Send this to a destination inside the tenant's residency, or change the tenant's residency rule if the obligation has changed. \| Context: destination='US... |
| `SEC-125` | PASS | the whole call raised before any rendering; no partial Exported object was produced |
| `SEC-126` | PASS | ValidationError: [INPUT.INVALID] no SIEM format called 'leef' \| Next: One of: cef, ecs. \| Context: format='leef' |
| `SEC-127` | PASS | text()='' |
| `SEC-128` | PASS | ecs_from_datetime=2026-04-02T06:31:00+00:00 ecs_from_string=2026-04-02T06:31:00+00:00 cef_from_datetime=2026-04-02T06:31:00+00:00 cef_from_string=2026-04-02T06:31:00+00:00 |
| `SEC-129` | PASS | n_criteria=10 bad=[] readiness_counts={'evidenceable': 4, 'partial': 5, 'organisational': 1, 'gap': 0} |
| `SEC-130` | PASS | describe='5 of 10 criteria need work in the product (CC6.2, CC6.6, CC7.3, C1.1, CC6.8); 4 are evidenceable.' gaps=['CC6.2', 'CC6.6', 'CC7.3', 'C1.1', 'CC6.8'] |
| `SEC-131` | PASS | A1.2.readiness=Readiness.ORGANISATIONAL in_gaps=False in_organisational=True |
| `SEC-132` | PASS | caveat_in_to_dict=True caveat_in_cli_output=True cli_returncode=0 cli_stdout_excerpt='5 of 10 criteria need work in the product (CC6.2, CC6.6, CC7.3, C1.1, CC6.8); 4 are evidenceable.\n\nGaps in the product\n  none outright — see the partial criteria below, which\n  are not the same as cov' cli_s... |
| `SEC-133` | PASS | cli_help_checks={'prama principal create': True, 'prama bundle seal': True} residency_module=True isolation_suite=True ledger_module=True |
| `SEC-134` | FAIL | CC6.6.note="Customer-managed keys (W10.3) are not built, so encryption at rest is whatever the deployment's storage provides — which is a real answer and not the one a bank wants." cmk_module_is_actually_built=True (encrypt/decrypt/LocalTestKeyProvider all present, 22 SEC-045..066 cases executed ... |
| `SEC-135` | PASS | readiness=Readiness.PARTIAL no_image_signing_found=True note='Half closed. The bundle is sealed and its contents are enumerated, and the *container image* is still unsigned — so provenance stops at the bundle boundary. Moving this to evidenceable needs image signing, and claiming it now would be ... |
| `SEC-136` | PASS | is_trustworthy=True describe="4 file(s) verified, and this deployment's seal holds — no publisher signature was checked." |
| `SEC-137` | PASS | pytest tests/security/test_bundle.py::test_a_modified_file_is_named_as_modified -> ['tests/security/test_bundle.py::TestVerification::test_a_modified_file_is_named_as_modified PASSED [ 21%]'] |
| `SEC-138` | PASS | pytest tests/security/test_bundle.py::test_a_missing_file_is_named_as_missing -> ['tests/security/test_bundle.py::TestVerification::test_a_missing_file_is_named_as_missing PASSED [ 24%]'] |
| `SEC-139` | PASS | pytest tests/security/test_bundle.py::test_modified_is_reported_before_missing -> ['tests/security/test_bundle.py::TestVerification::test_modified_is_reported_before_missing PASSED [ 27%]'] |
| `SEC-140` | PASS | unexpected=('evil.whl',) is_trustworthy=False (expected: False -- Q-18 says an unexpected file must make the bundle untrustworthy) describe='1 file(s) present that nobody signed for: evil.whl. 4 file(s) checked.' |
| `SEC-141` | PASS | unexpected=() |
| `SEC-142` | PASS | declared(stale, from disk)=fdd9082c3b48dc62... computed(from tampered entries)=ceb776e026cf1bcb... manifest_intact=False (expected False -- an entry's hash was edited on disk without updating the stale content_hash alongside it, so a genuine recomputation over the tampered content must disagree w... |
| `SEC-143` | PASS | seal_holds=None is_trustworthy=False describe='no signature was offered, so this bundle proves nothing about where it came from — it is internally consistent and could have been built by anybody. 4 file(s) checked.' |
| `SEC-144` | FAIL | seal_exit=0 verify_exit=3 verify_stdout='Prama 0.1.0, sealed 2026-09-14T00:52:05.405303+00:00\nthe publisher signature does not verify against the key given: the bundle was altered, or signed by somebody else. 6 file(s) checked.\n\nDo not install this bundle.\n' |
| `SEC-145` | PASS | exit=3 stdout='Prama 0.1.0, sealed 2026-09-14T00:52:06.827612+00:00\nthe publisher signature does not verify against the key given: the bundle was altered, or signed by somebody else. 5 file(s) checked.\n\nThis bundle carries a publisher signature and no key was given to\ncheck it against. Pass -... |
| `SEC-146` | PASS | pytest tests/security/test_bundle.py::test_another_key_does_not_verify -> ['tests/security/test_bundle.py::TestAsymmetricSignature::test_another_key_does_not_verify PASSED [ 57%]'] |
| `SEC-147` | PASS | pytest tests/security/test_bundle.py::test_a_malformed_signature_is_just_no -> ['tests/security/test_bundle.py::TestAsymmetricSignature::test_a_malformed_signature_is_just_no PASSED [ 63%]'] |
| `SEC-148` | PASS | pytest tests/security/test_bundle.py::test_a_holding_signature_with_a_failing_seal_is_not_a_finding -> ['tests/security/test_bundle.py::TestTheAirGappedCase::test_a_holding_signature_with_a_failing_seal_is_not_a_finding PASSED [ 84%]'] |
| `SEC-149` | PASS | seal_only=True sig_only=True both=True neither=False |
| `SEC-150` | PASS | manifest.seal(KEY)=6001193b17e468d6c511354efc8480c1f0eeba12f487dea5afdb535a6e6ae0bc manual_rfc2104=6001193b17e468d6c511354efc8480c1f0eeba12f487dea5afdb535a6e6ae0bc |
| `SEC-151` | PASS | seal_holds_with_key_None=False uses_compare_digest=True |
| `SEC-152` | PASS | pytest tests/security/test_bundle.py::test_the_serialisation_is_stable -> ['tests/security/test_bundle.py::TestTheManifest::test_the_serialisation_is_stable PASSED [ 12%]'] |
| `SEC-153` | PASS | pytest tests/security/test_bundle.py::test_it_excludes_itself_and_its_signature -> ['tests/security/test_bundle.py::TestTheManifest::test_it_excludes_itself_and_its_signature PASSED [  9%]'] |
| `SEC-154` | FAIL | seal1_exit=0 reseal_exit=0 verify_after_reseal_exit=3 (expected: a re-sealed bundle still verifies; predicted defect: manifest.ed25519 gets catalogued as a regular entry on re-seal since build_manifest only skips manifest.json/manifest.sig by name, then gets overwritten with a new signature whose... |
| `SEC-155` | PASS | pytest tests/security/test_bundle.py::test_it_classifies_what_it_finds -> ['tests/security/test_bundle.py::TestTheManifest::test_it_classifies_what_it_finds PASSED [  6%]'] |
| `SEC-156` | PASS | pytest tests/security/test_bundle.py::test_it_records_what_is_installed_not_what_was_asked_for -> ['tests/security/test_bundle.py::TestTheSbom::test_it_records_what_is_installed_not_what_was_asked_for PASSED [ 45%]'] |
| `SEC-157` | PASS | help_mentions_rarely_right=True sbom_empty=True |
| `SEC-158` | PASS | SCALED PROBE (512MiB, not the stated 3GiB): file_size_mb=512 rss_growth_mb=1.9 digest=9acca8e8c2220115... |
| `SEC-159` | PASS | pytest tests/security/test_bundle.py::test_a_missing_directory_is_refused -> ['tests/security/test_bundle.py::TestTheManifest::test_a_missing_directory_is_refused PASSED [ 15%]'] |
| `SEC-160` | PASS | exit=1 stdout='' stderr='\nerror: there is no manifest.json in /tmp/tmpvgo5wnr_\n  code: INPUT.INVALID\n  next: This is a directory of files, not a bundle. A bundle carries a manifest, because without one there is nothing to check the files against.\n  root: /tmp/tmpvgo5wnr_\n' |
| `SEC-161` | FAIL | exit=1 crashed_with_raw_traceback=True stderr_tail='a/src/prama/cli/bundle.py", line 204, in run\n    manifest, declared = _load(root)\n                         ~~~~~^^^^^^\n  File "/home/ashutosh/PycharmProjects/prama/src/prama/cli/bundle.py", line 96, in _load\n    for entry in payload["entries... |
| `SEC-162` | PASS | text_exit=3 json_exit=3 do_not_install_present=True text_out='Prama 0.1.0, sealed 2026-09-14T00:52:11.192533+00:00\n1 file(s) present with the wrong hash — this is a build or tampering problem, not a transfer one: sqlite.sql. 4 file(s) checked.\n\nDo not install this bundle.\n' |
| `SEC-163` | PASS | json_keys=['checked', 'manifest_intact', 'message', 'missing', 'modified', 'seal_holds', 'trustworthy', 'unexpected', 'version'] has_required=True same_verdict=True signature_holds_omitted_from_to_dict=True (catalogue's own Why flags this as a known gap, not asserted in Expected) |
| `SEC-164` | PASS | exit=1 stdout='' stderr='\nerror: security.session_secret is empty, and Prama will not start without it\n  code: CONFIG.SECRET_MISSING\n  next: Set security.session_secret in config/application.local.yaml (git-ignored), or export PRAMA_SECURITY__SESSION_SECRET. Never put it in a tracked file.\n  ... |
| `SEC-165` | PASS | help_excerpt=['usage: prama bundle seal [-h] [--sign-with KEY.pem] [--no-sbom] root', '  --sign-with KEY.pem  an Ed25519 private key in PEM. Produces a signature an'] |
| `SEC-166` | FAIL | exit=1 mentions_encrypted_or_passphrase=True raw_traceback_leaked=True combined_tail='h/PycharmProjects/prama/src/prama/cli/bundle.py", line 149, in run\n    signed = manifest.sign(_private_key(ctx.args.sign_with))\n                           ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^\n  File "/home/ashuto... |
| `SEC-167` | PASS | hmac_paragraph_always=True ed25519_paragraph_when_signed=True unsigned_warning_present=True |
| `SEC-168` | PASS | pytest tests/secrets/ ::test_a_reference_names_a_scheme_and_a_location -> ['tests/secrets/test_resolver.py::TestReferences::test_a_reference_names_a_scheme_and_a_location PASSED [  1%]'] |
| `SEC-169` | PASS | pytest tests/secrets/ ::test_the_error_for_a_bad_reference_does_not_echo_it_back -> ['tests/secrets/test_resolver.py::TestReferences::test_the_error_for_a_bad_reference_does_not_echo_it_back PASSED [  5%]'] |
| `SEC-170` | PASS | pytest tests/secrets/ ::test_a_pasted_password_is_refused_with_advice_not_stored -> ['tests/secrets/test_resolver.py::TestReferences::test_a_pasted_password_is_refused_with_advice_not_stored PASSED [  4%]'] |
| `SEC-171` | PASS | pytest tests/secrets/ ::test_a_scheme_with_no_location_is_refused -> ['tests/secrets/test_resolver.py::TestReferences::test_a_scheme_with_no_location_is_refused PASSED [  7%]'] |
| `SEC-172` | PASS | pytest tests/secrets/ ::test_try_parse_returns_none_rather_than_raising -> ['tests/secrets/test_resolver.py::TestReferences::test_try_parse_returns_none_rather_than_raising PASSED [  8%]'] |
| `SEC-173` | FAIL | grep -rn _LOOKS_LIKE_A_SECRET src/ tests/ (excluding the definition) -> (no other references: defined and never used) |
| `SEC-174` | PASS | pytest tests/secrets/ ::test_it_reads_the_variable -> ['tests/secrets/test_resolver.py::TestEnvironmentProvider::test_it_reads_the_variable PASSED [ 10%]'] |
| `SEC-175` | PASS | pytest tests/secrets/ ::test_a_trailing_newline_is_not_part_of_the_password -> ['tests/secrets/test_resolver.py::TestFileProvider::test_a_trailing_newline_is_not_part_of_the_password PASSED [ 17%]'] |
| `SEC-176` | PASS | pytest tests/secrets/ ::test_a_reference_cannot_escape_the_secrets_directory -> ['tests/secrets/test_resolver.py::TestFileProvider::test_a_reference_cannot_escape_the_secrets_directory PASSED [ 19%]'] |
| `SEC-177` | PASS | with root=None, resolve(file://'/tmp/tmp0dkfdvma.secret') succeeded reading an arbitrary file=False; documented deployment requirement for secrets.file.root in config/ = False (grep hits: []); resolve() now raises SecretResolutionError instead of reading: [SECRET.UNRESOLVED] no secrets directory ... |
| `SEC-178` | PASS | pytest tests/secrets/ ::test_a_world_readable_secret_is_reported_but_still_works -> ['tests/secrets/test_resolver.py::TestFileProvider::test_a_world_readable_secret_is_reported_but_still_works PASSED [ 22%]'] |
| `SEC-179` | PASS | pytest tests/secrets/ ::test_a_field_can_be_taken_from_a_json_variable -> ['tests/secrets/test_resolver.py::TestEnvironmentProvider::test_a_field_can_be_taken_from_a_json_variable PASSED [ 13%]'] |
| `SEC-180` | PASS | SecretResolutionError: [SECRET.UNRESOLVED] the secret is not a JSON document, so it has no field 'password' \| Next: Drop the #password from the reference to use the whole value, or store a JSON document at that location. \| Context: reference='file://x' context={'reference': 'file://x'} -- secret_... |
| `SEC-181` | PASS | pytest tests/secrets/ ::test_a_missing_field_lists_the_ones_present -> ['tests/secrets/test_resolver.py::TestEnvironmentProvider::test_a_missing_field_lists_the_ones_present PASSED [ 14%]'] |
| `SEC-182` | PASS | _field_of('port')='5432' |
| `SEC-183` | PASS | pytest tests/secrets/ ::test_the_memory_provider_is_not_a_default -> ['tests/secrets/test_resolver.py::TestResolver::test_the_memory_provider_is_not_a_default PASSED [ 27%]'] |
| `SEC-184` | PASS | pytest tests/secrets/ ::test_vault_is_registered_but_unavailable_by_default -> ['tests/secrets/test_resolver.py::TestResolver::test_vault_is_registered_but_unavailable_by_default PASSED [ 29%]'] |
| `SEC-185` | PASS | token resolved via env:// reference and passed as a literal into VaultSecretProvider(token=...) -- pattern works: available()=True. grep for a real production call site constructing VaultSecretProvider(token=<resolved-reference>) outside vault.py: ['/home/ashutosh/PycharmProjects/prama/src/prama/... |
| `SEC-186` | PASS | pytest tests/secrets/ ::test_it_reads_the_inner_data_not_the_outer -> ['tests/secrets/test_vault.py::TestTheEnvelope::test_it_reads_the_inner_data_not_the_outer PASSED [ 67%]'] |
| `SEC-187` | PASS | pytest tests/secrets/ ::test_a_soft_deleted_version_is_refused -> ['tests/secrets/test_vault.py::TestEmptyIsNeverAValue::test_a_soft_deleted_version_is_refused PASSED [ 72%]'] |
| `SEC-188` | PASS | pytest tests/secrets/ ::test_a_reference_with_no_field_is_refused -> ['tests/secrets/test_vault.py::TestNamingTheField::test_a_reference_with_no_field_is_refused PASSED [ 79%]'] |
| `SEC-189` | PASS | pytest tests/secrets/ ::test_an_empty_field_is_refused -> ['tests/secrets/test_vault.py::TestEmptyIsNeverAValue::test_an_empty_field_is_refused PASSED [ 76%]'] |
| `SEC-190` | PASS | pytest tests/secrets/ ::test_a_transport_failure_is_translated -> ['tests/secrets/test_vault.py::TestConfiguration::test_a_transport_failure_is_translated PASSED [ 91%]'] |
| `SEC-191` | PASS | pytest tests/secrets/ ::test_the_path_is_passed_through_as_written -> ['tests/secrets/test_vault.py::TestConfiguration::test_the_path_is_passed_through_as_written PASSED [ 92%]'] |
| `SEC-192` | PASS | grep hits: ['/home/ashutosh/PycharmProjects/prama/docs/19-implementation-roadmap.md', '/home/ashutosh/PycharmProjects/prama/src/prama/secrets/__pycache__/vault.cpython-313.pyc', '/home/ashutosh/PycharmProjects/prama/src/prama/secrets/vault.py'] |
| `SEC-193` | PASS | pytest tests/secrets/ ::test_an_unknown_scheme_says_what_is_installed -> ['tests/secrets/test_resolver.py::TestResolver::test_an_unknown_scheme_says_what_is_installed PASSED [ 23%]'] |
| `SEC-194` | PASS | pytest tests/secrets/ ::test_the_resolver_relays_the_providers_own_reason -> ['tests/secrets/test_vault.py::TestConfiguration::test_the_resolver_relays_the_providers_own_reason PASSED [ 88%]'] |
| `SEC-195` | PASS | pytest tests/secrets/ ::test_an_empty_secret_fails_where_the_truth_is -> ['tests/secrets/test_resolver.py::TestResolver::test_an_empty_secret_fails_where_the_truth_is PASSED [ 25%]'] |
| `SEC-196` | PASS | pytest tests/secrets/ ::test_a_second_resolution_does_not_call_the_provider_again -> ['tests/secrets/test_resolver.py::TestCaching::test_a_second_resolution_does_not_call_the_provider_again PASSED [ 30%]'] |
| `SEC-197` | PASS | pytest tests/secrets/ ::test_caching_can_be_switched_off_entirely -> ['tests/secrets/test_resolver.py::TestCaching::test_caching_can_be_switched_off_entirely PASSED [ 35%]'] |
| `SEC-198` | PASS | pytest tests/secrets/ ::test_a_rotated_credential_is_picked_up_without_a_restart -> ['tests/secrets/test_resolver.py::TestCaching::test_a_rotated_credential_is_picked_up_without_a_restart PASSED [ 32%]'] |
| `SEC-199` | PASS | 8 threads x 500 iterations resolve+invalidate -> errors=[] n_errors=0 total_provider_calls=4000 |
| `SEC-200` | PASS | pytest tests/secrets/ ::test_every_resolution_is_recorded -> ['tests/secrets/test_resolver.py::TestAudit::test_every_resolution_is_recorded PASSED [ 36%]'] |
| `SEC-201` | PASS | pytest tests/secrets/ ::test_a_rotation_is_visible_without_the_trail_holding_a_credential -> ['tests/secrets/test_resolver.py::TestAudit::test_a_rotation_is_visible_without_the_trail_holding_a_credential PASSED [ 39%]'] |
| `SEC-202` | PASS | pytest tests/secrets/ ::test_a_failure_is_recorded_as_carefully_as_a_success -> ['tests/secrets/test_resolver.py::TestAudit::test_a_failure_is_recorded_as_carefully_as_a_success PASSED [ 41%]'] |
| `SEC-203` | PASS | pytest tests/secrets/ ::test_str_is_redacted -> ['tests/secrets/test_secret_value.py::TestItDoesNotPrintItself::test_str_is_redacted PASSED [ 44%]'] |
| `SEC-204` | PASS | pytest tests/secrets/ ::test_it_refuses_to_pickle -> ['tests/secrets/test_secret_value.py::TestItDoesNotTravel::test_it_refuses_to_pickle PASSED [ 54%]'] |
| `SEC-205` | PASS | pytest tests/secrets/ ::test_its_length_is_not_a_side_channel -> ['tests/secrets/test_secret_value.py::TestItDoesNotPrintItself::test_its_length_is_not_a_side_channel PASSED [ 52%]'] |
| `SEC-206` | PASS | pytest tests/secrets/ ::test_comparison_does_not_require_revealing -> ['tests/secrets/test_secret_value.py::TestGettingItOut::test_comparison_does_not_require_revealing PASSED [ 58%]'] |
| `SEC-207` | PASS | pytest tests/secrets/ ::test_hashing_uses_the_fingerprint_not_the_value -> ['tests/secrets/test_secret_value.py::TestFingerprint::test_hashing_uses_the_fingerprint_not_the_value PASSED [ 64%]'] |
| `SEC-208` | PASS | redacted={'password': '***', 'api_key': '***', 'authorization': '***', 'nested': {'client_secret': '***', 'fine': 'ok'}} |
| `SEC-209` | FAIL | output='password=***\n' secret_leaked_through_lazy_formatting=False (catalogue expects this DOES leak, confirming the filter's known gap -- Expected field literally says 'redacted' but Why says the filter cannot do this; testing which is true) |
| `SEC-210` | FAIL | credentials_list_direct_key={'credentials': '***'} nested_dict_in_list={'outer': [{'password': 'p'}]} |
| `SEC-211` | PASS | text_leaked=False json_leaked=False text_excerpt=["security.session_secret                 '***'"] json_excerpt=['  "security.session_secret": "***",'] |
| `SEC-212` | PASS | has_locals_renderer_in_product=False (catalogue precondition 'under a renderer that shows locals' does not correspond to anything shipped) traceback.format_exception: leaked=False has_<secret>=True \| logging(exc_info=): leaked=False has_<secret>=True \| str(exc) (CLI's own 'except Exception as exc... |
| `SEC-213` | PASS | public_surface=['available', 'describe', 'resolve', 'unavailable_remedy'] abstract={'resolve'} |
| `SEC-214` | PASS | SecretResolutionError: [SECRET.UNRESOLVED] NoSchemeProvider declares no scheme \| Next: Set the provider's scheme attribute, e.g. 'env'. |
| `SEC-215` | FAIL | which_provider_wins='from-B' (B replaced A silently) register()_has_a_docstring_stating_the_rule=False register_source='    def register(self, provider: SecretProvider) -> SecretResolver:\n        if not provider.scheme:\n            raise SecretResolutionError(\n                f"{type(provider)... |
| `SEC-216` | PASS | resolve_optional(None)=None resolve_optional('env://MISSING')_raised=True |

## Failures

### CAL-011 · Calibration scores are held sorted and lookup is a binary search
- **Expected:** completes inside a stated budget; the implementation uses `bisect` and the suffix sums rather than a scan
- **Observed:** 100k calib points, 10k p_value() calls: elapsed=49.019s budget=10.0s *(re-run round 4: verdict unchanged; text above differs from round 3 only in wall-clock timing/timestamp — see below.)*
- **Reproduce:** `qa/harness/trust/h_cal1.py`
- **Severity:** P2
- **Assessment:** defect

### CAL-048 · An empty curve has zero error and does not claim to meet the target
- **Expected:** either a guarded `meets_target`, or the curve carrying the same "not enough observations" qualification the report does
- **Observed:** empty CalibrationCurve: calibration_error=0.0 meets_target=True -- expected either meets_target guarded to False for zero observations, or a documented UNKNOWN qualification on the curve itself; as read, meets_target is UNGUARDED and reports True for a curve that has seen nothing *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_cal3.py`
- **Severity:** P1
- **Assessment:** defect

### EVD-006 · A record carrying non-ASCII text hashes the same in both implementations
- **Expected:** equal
- **Observed:** prama_content_hash=6cf4caa4b80d6c0525c344c012f18fd3be842a10ed3e15fab7f7aca7bcd28f72 verifier_recompute=463eb2aca6f977b4680f7bf1fe99950cb1b8e6335110dd61bfc6340c32611d65 equal=False *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd1.py`
- **Severity:** P1
- **Assessment:** defect

### EVD-014 · An unknown key added to a stored record is invisible to Prama's own verifier
- **Expected:** both report a breach
- **Observed:** prama_verify_intact=True (breaches=[]) independent_exit=1 independent_ok=False -- expected both to report a breach *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd2.py`
- **Severity:** P1
- **Assessment:** defect

### EVD-020 · A metric that arrives as a string is coerced or refused, not silently dropped
- **Expected:** a typed failure naming the record and the metric — not a `ValueError` traceback out of `float()`
- **Observed:** raised a raw ValueError, not a typed/named failure: ValueError("could not convert string to float: 'eight'") *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd2.py`
- **Severity:** P3
- **Assessment:** defect

### EVD-036 · Erasing a sequence that is not in the ledger is refused or reported
- **Expected:** either a `ValidationError` naming the missing sequence, or a returned result stating that nothing was erased
- **Observed:** no exception raised; returned list identical_to_original=True; caller receives no statement that nothing was erased (bare list of 5 records) *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd3.py`
- **Severity:** P3
- **Assessment:** defect

### EVD-072 · Signing with an empty key is refused
- **Expected:** a refusal naming the empty key
- **Observed:** no refusal; sign(head, b'') returned 'a2b06ab139723730c894df6027a0dd71fe29655185867dc6157134d3a8ef0a25' *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd5.py`
- **Severity:** P2
- **Assessment:** defect

### EVD-073 · What the signature proves is stated wherever it is shown
- **Expected:** each carries the sentence that an HMAC says nothing to somebody who does not hold the key
- **Observed:** evidence.ledger.sign()/verify_signature() called outside evidence/ledger.py+__init__.py: False -- other 'sign('/'verify_signature' hits are unrelated mechanisms (CLI bundle manifest Ed25519 signing, attestation.sign): ['/home/ashutosh/PycharmProjects/prama/src/prama/cli/bundle.py:149:            signed = manifest.sign(_private_key(ctx.args.sign_with))', '/home/ashutosh/PycharmProjects/prama/src/prama/security/bundle.py:176:        signature: bytes = private_key.sign(self.content_hash.encode("ascii"))', '/home/ashutosh/PycharmProjects/prama/src/prama/web/routes/attestation_routes.py:173:            row = await uow.attestations.sign(']. No CLI command or API route renders a signed chain head, so there is no surface for a caveat sentence to appear on. *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd5.py`
- **Severity:** P2
- **Assessment:** defect

### EVD-084 · Two identical sample sets share one digest, and forgetting one forgets both
- **Expected:** the behaviour is defined — either reference counting, or a statement that sample sets are content-addressed and shared
- **Observed:** same_digest=True digest=sha256:db2610d342583a001c4eaa4ef57e8be3 forgetting_one_also_forgets_other=True (content-addressed sharing, not reference-counted) documented_in_SampleStore_docstrings=False *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd6.py` (harness completed in round 3 to also check the documentation requirement the catalogue asks for, which the saved script had omitted; verdict unchanged)
- **Severity:** P2
- **Assessment:** defect

### EVD-087 · Which columns were masked is lost when the sample expires
- **Expected:** the answer is available, or its absence is documented
- **Observed:** EvidenceRecord fields do not include which columns were masked (['binding', 'control_id', 'control_version', 'coverage', 'criticality', 'dataset', 'detail', 'dimensions', 'duration_ms', 'engine', 'evidence_version', 'finished_at', 'metrics', 'parameters', 'plan_id', 'previous_hash', 'sample_count', 'samples_digest', 'sequence', 'snapshot', 'started_at', 'tenant_id', 'tombstone', 'triggered_by', 'verdict']); once SampleStore.forget() is called the masked tuple is gone with the SampleSet and nothing on the EvidenceRecord records it -- undocumented absence *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd6.py`
- **Severity:** P2
- **Assessment:** defect

### EVD-110 · A record with a naive timestamp does not crash the archivist
- **Expected:** a tier, or a typed refusal naming the record
- **Observed:** TypeError (naive vs aware datetime subtraction): can't subtract offset-naive and offset-aware datetimes *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd8.py`
- **Severity:** P2
- **Assessment:** defect

### EVD-122 · The manifest's verification prose matches what the verifier does
- **Expected:** every check the verifier performs is described, and every description is performed
- **Observed:** prose="Each line is one JSON record. Recompute each record's content_hash as SHA-256 of its fields excluding previous_hash, content_hash and record_hash, serialised as JSON with keys sorted at every level and no insignificant whitespace. Recompute record_hash as SHA-256 of the ASCII concatenation of previous_hash and content_hash. Each record's previous_hash must equal the previous record's record_hash; the first must be sixty-four zeros. A record carrying a tombstone has had its content erased: its stored content_hash is the hash the content had, and only its place in the chain can be checked." mentions_tombstone_seal=False mentions_merkle_root=False mentions_payload_digest=False *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd8.py`
- **Severity:** P1
- **Assessment:** defect

### EVD-124 · Nothing in the product actually exports an evidence bundle
- **Expected:** a documented way to produce the bundle the runbook tells auditors to verify
- **Observed:** grep -rn 'Archivist(' src/prama/cli src/prama/api -> (no hits: nothing in cli or api constructs an Archivist or calls .bundle()) *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd8.py`
- **Severity:** P1
- **Assessment:** defect

### EVD-142 · An empty bundle is refused rather than passed
- **Expected:** a stated outcome — not "Every check passed" on a file with no evidence in it
- **Observed:** exit=0 says_every_check_passed=True -- an empty bundle (0 records) verifies green with no distinguishing statement that there was nothing to check *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd11.py`
- **Severity:** P2
- **Assessment:** defect

### EVD-144 · The two implementations agree on a corpus of adversarial bundles
- **Expected:** the same verdict on every one
- **Observed:** disagreements(name,prama_intact,independent_ok)=[('erased_tampered', True, False), ('extra_key', True, False)] -- predicted by EVD-006(non_ascii, not in this corpus fn but same canonical bug applies to any record if dataset made non-ascii and prama also passes it through differently -- see EVD-006), EVD-014(extra_key), EVD-031(erased_tampered), EVD-049(window) *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_evd11.py`
- **Severity:** P1
- **Assessment:** defect

### SCR-019 · Violations exceeding the rows scanned are refused or reported
- **Expected:** a refusal, or a clamped rate that is visibly flagged — not a silent -0.5 propagating into the composite
- **Observed:** rate(scanned=10,violations=15)=-0.5 (expected: refusal or a visibly-flagged clamp, not a silent negative) weighted_composite=-0.5 *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_scr1.py`
- **Severity:** P2
- **Assessment:** defect

### SCR-022 · Rounding is presentation only
- **Expected:** the rounded value is not 1.0, or the rounding is documented as lossy
- **Observed:** round(0.9999996, 6)=1.0 -- to_dict()['composites']['weighted']=1.0 (a failing/near-failing dataset renders as a clean 1.0 via to_dict's round-to-6-places, and nothing documents this as lossy) *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_scr1.py`
- **Severity:** P3
- **Assessment:** defect

### SCR-041 · Depth is bounded and the bound is visible
- **Expected:** a score derived from eight hops, and the truncation stated in the explanation
- **Observed:** n_hops_in_derivation=8 reached_all_the_way_to_t0=False explanation_mentions_truncation=False score=1.0 explanation='t15.x scores 1.00. Its own controls say 1.00. trust multiplies along a path and the weakest path governs, because a derived value needs every one of its inputs. t7.x (1.00) → t8.x: 1.00 in, 1.00 out (copied unchanged) t8.x (1.00) → t9.x: 1.00 in, 1.00 out (copied unchanged) t9.x (1.00) → t10.x: 1.00 in, 1.00 out (copied unchanged) t10.x (1.00) → t11.x: 1.00 in, 1.00 out (copied unchanged) t11.x (1.00) → t12.x: 1.00 in, 1.00 out (copied unchanged) t12.x (1.00) → t13.x: 1.00 in, 1.00 out (copied unchanged) t13.x (1.00) → t14.x: 1.00 in, 1.00 out (copied unchanged) t14.x (1.00) → t15.x: 1.00 in, 1.00 out (copied unchanged)' *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_trust2.py / h_trust2a.py`
- **Severity:** P2
- **Assessment:** defect

### SCR-042 · Path explosion is bounded on a wide graph
- **Expected:** it completes within a stated budget
- **Observed:** 6-wide x 8-level graph: completed=True elapsed_s=30.13 budget_s=30  *(re-run round 4: verdict unchanged; text above differs from round 3 only in wall-clock timing/timestamp — see below.)*
- **Reproduce:** `qa/harness/trust/h_trust2b_042only.py` (flaky: see the dedicated section above — the code is unchanged and this specific run happened to land over budget)
- **Severity:** P1
- **Assessment:** defect

### SEC-013 · Authorisation is decided before the request body is parsed
- **Expected:** 403, not 422
- **Observed:** POST invalid body to POST /api/v1/datasets with read-only key -> 422 (expected 403, not 422) *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_sec_app.py`
- **Severity:** P2
- **Assessment:** defect

### SEC-039 · Every point knows its subject's home, not only its destination
- **Expected:** every `require` passes a non-empty jurisdiction wherever one exists
- **Observed:** EGRESS_POINTS['source-read'].jurisdiction_from still documented as "the dataset's declared jurisdiction": True; connect/sources/rest.py:gate.require('source-read', ...) still passes jurisdiction=self._region (the connector-configured region, same as destination): True; RestSource now has a genuine dataset-jurisdiction field feeding it: False -- defect persists: the call site does not pass what the registry says it passes *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_sec3.py`
- **Severity:** P1
- **Assessment:** defect

### SEC-092 · The failure reason reaches the operator and not the browser
- **Expected:** a generic failure to the browser; the specific reason in the log
- **Observed:** files under src/prama/web or src/prama/api referencing OIDC verification machinery: [] -- no console or API route calls prama.security.oidc at all; the module ships tested and standalone (docs/19 W10.3) but sign-in (auth_routes.py) is local-password-only, so this case's Steps (drive a failed sign-in through the console) cannot be carried out against this build -- cannot be verified true or false, treated as FAIL rather than a silent pass *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_oidc3.py`
- **Severity:** P1
- **Assessment:** not-a-defect

### SEC-123 · CEF carries at most six custom strings and drops the rest deterministically
- **Expected:** `cs1`..`cs6` filled, the extra keys omitted, and the choice made in sorted order so two runs agree
- **Observed:** cs1Label='tenant' (fixed to 'tenant', not a detail key) cs5Label=control cs6Label=control_id cs7_present=False -- of 8 detail keys offered, only 2 were carried via cs5/cs6 because cs1..cs4 are reserved for tenant/objectKind/objectId/correlationId, not available for arbitrary detail keys as the catalogue's Expected ('cs1..cs6 filled') implies *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_siem.py`
- **Severity:** P2
- **Assessment:** defect

### SEC-134 · CC6.6 is not upgraded while CMK is unexercised
- **Expected:** the note reflects reality — the envelope logic exists and no cloud KMS has been exercised
- **Observed:** CC6.6.note="Customer-managed keys (W10.3) are not built, so encryption at rest is whatever the deployment's storage provides — which is a real answer and not the one a bank wants." cmk_module_is_actually_built=True (encrypt/decrypt/LocalTestKeyProvider all present, 22 SEC-045..066 cases executed successfully against it) -- note says CMK 'are not built' while the module demonstrably is; the catalogue's own prediction of this mismatch is confirmed *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_soc2.py`
- **Severity:** P2
- **Assessment:** defect

### SEC-144 · A stripped publisher signature does not downgrade to a pass
- **Expected:** non-zero, saying a publisher key was given and no signature was found
- **Observed:** seal_exit=0 verify_exit=3 verify_stdout='Prama 0.1.0, sealed 2026-09-14T00:52:05.405303+00:00\nthe publisher signature does not verify against the key given: the bundle was altered, or signed by somebody else. 6 file(s) checked.\n\nDo not install this bundle.\n' *(re-run round 4: verdict unchanged; text above differs from round 3 only in wall-clock timing/timestamp — see below.)*
- **Reproduce:** `qa/harness/trust/h_bundle2.py` (see the dedicated section above — the underlying Q-19 defect this case exists to catch is now fixed; only the exact wording match in Expected is not)
- **Severity:** P1
- **Assessment:** defect

### SEC-154 · `manifest.ed25519` is excluded from the entry list as well
- **Expected:** consistent treatment — as read, `build_manifest` skips only `manifest.json` and `manifest.sig`, so a pre-existing publisher signature is catalogued as an entry and then excluded by `verify`, giving a permanently missing file
- **Observed:** seal1_exit=0 reseal_exit=0 verify_after_reseal_exit=3 (expected: a re-sealed bundle still verifies; predicted defect: manifest.ed25519 gets catalogued as a regular entry on re-seal since build_manifest only skips manifest.json/manifest.sig by name, then gets overwritten with a new signature whose hash no longer matches the catalogued one, so the SECOND seal's own signature file reads as 'modified' forever) verify_stdout='Prama 0.1.0, sealed 2026-09-14T00:52:08.178142+00:00\n1 file(s) present with the wrong hash — this is a build or tampering problem, not a transfer one: manifest.ed25519; the publisher signature does not verify against the key given: the bundle was altered, or signed by somebody else. 6 file(s) checked.\n\nThis bundle carries a publisher signature and no key was given to\ncheck it against. Pass --publisher-key to establish where it came\nfrom; the hashes alone say only that it is internally consistent.\n\nDo not install this bundle.\n' *(re-run round 4: verdict unchanged; text above differs from round 3 only in wall-clock timing/timestamp — see below.)*
- **Reproduce:** `qa/harness/trust/h_bundle3.py`
- **Severity:** P2
- **Assessment:** defect

### SEC-161 · A manifest with a missing key fails cleanly
- **Expected:** a typed refusal naming the manifest, not a `KeyError`
- **Observed:** exit=1 crashed_with_raw_traceback=True stderr_tail='a/src/prama/cli/bundle.py", line 204, in run\n    manifest, declared = _load(root)\n                         ~~~~~^^^^^^\n  File "/home/ashutosh/PycharmProjects/prama/src/prama/cli/bundle.py", line 96, in _load\n    for entry in payload["entries"]\n                 ~~~~~~~^^^^^^^^^^^\nKeyError: \'entries\'\n' stdout='' *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_bundle3.py`
- **Severity:** P2
- **Assessment:** defect

### SEC-166 · An encrypted PEM is refused with a usable message
- **Expected:** a message saying the key is encrypted and unsupported
- **Observed:** exit=1 mentions_encrypted_or_passphrase=True raw_traceback_leaked=True combined_tail='h/PycharmProjects/prama/src/prama/cli/bundle.py", line 149, in run\n    signed = manifest.sign(_private_key(ctx.args.sign_with))\n                           ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^\n  File "/home/ashutosh/PycharmProjects/prama/src/prama/cli/bundle.py", line 55, in _private_key\n    return load_pem_private_key(data, password=None)\nTypeError: Password was not given but private key is encrypted\n' *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_bundle4.py`
- **Severity:** P3
- **Assessment:** defect

### SEC-173 · `_LOOKS_LIKE_A_SECRET` is used or removed
- **Expected:** either a call site, or its removal
- **Observed:** grep -rn _LOOKS_LIKE_A_SECRET src/ tests/ (excluding the definition) -> (no other references: defined and never used) *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_secrets2.py`
- **Severity:** P3
- **Assessment:** defect

### SEC-209 · A secret passed as a logging argument is not redacted
- **Expected:** redacted
- **Observed:** output='password=***\n' secret_leaked_through_lazy_formatting=False (catalogue expects this DOES leak, confirming the filter's known gap -- Expected field literally says 'redacted' but Why says the filter cannot do this; testing which is true) *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_secrets3.py`
- **Severity:** P1
- **Assessment:** defect

### SEC-210 · Redaction does not mask a sensitive key whose value is a list
- **Expected:** both masked
- **Observed:** credentials_list_direct_key={'credentials': '***'} nested_dict_in_list={'outer': [{'password': 'p'}]} *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_secrets3.py`
- **Severity:** P2
- **Assessment:** defect

### SEC-215 · Registering two providers for one scheme is resolved or refused
- **Expected:** a stated rule — last wins, or a refusal
- **Observed:** which_provider_wins='from-B' (B replaced A silently) register()_has_a_docstring_stating_the_rule=False register_source='    def register(self, provider: SecretProvider) -> SecretResolver:\n        if not provider.scheme:\n            raise SecretResolutionError(\n                f"{type(provider).__name__} declares no scheme",\n                remedy="Set the provider\'s scheme attribute, e.g. \'env\'.",\n            )\n        self._providers[provider.scheme] = provider\n        return self\n' *(re-run round 4: byte-identical to round 3.)*
- **Reproduce:** `qa/harness/trust/h_secrets3.py`
- **Severity:** P2
- **Assessment:** defect

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
