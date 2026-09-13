import sys, asyncio, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
from prama.execute.preview import Preview, Trial, Backtest, business_dates, plain_identifier, _restricted
from prama.core.errors import ValidationError
from prama.pql import parse_control
from prama.pql.ast import Control

CLEAN = "CHECK t.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'x'"
SCREENED = "CHECK t.lei IS VALID 'lei' SEVERITY major DIMENSION validity BECAUSE 'x'"

def exe139():
    import dataclasses
    trial_fields = {f.name for f in dataclasses.fields(Trial)}
    forbidden = {"plan_id", "snapshot", "chain_position"}
    ok1 = trial_fields.isdisjoint(forbidden)
    import inspect
    sig = inspect.signature(Preview.__init__)
    ok2 = "uow" not in sig.parameters and "unit_of_work" not in sig.parameters

    import db_harness as h
    async def try_append():
        db = h.new_database(); await h.start(db)
        tenant = await h.make_tenant(db)
        trial = Trial(label="now", verdict="pass", scanned_rows=10, violating_rows=0)
        try:
            async with db.unit_of_work() as uow:
                await uow.evidence.append(trial, tenant_id=tenant, run_id="r1")
            result = "NO ERROR -- accepted a Trial as evidence"
        except Exception as e:
            result = f"refused: {type(e).__name__}: {e}"
        await h.stop(db)
        return result
    append_result = asyncio.run(try_append())
    ok3 = "refused" in append_result
    ok = ok1 and ok2 and ok3
    log("EXE-139", "PASS" if ok else "FAIL", f"Trial_fields_exclude_ledger_identity={ok1} Preview.__init___has_no_uow_param={ok2} passing_a_Trial_to_evidence.append={append_result}")

def fake_execute(rows_by_label=None, default=None, error_labels=()):
    rows_by_label = rows_by_label or {}
    def execute(query):
        return execute._next
    execute._next = default or []
    return execute

def exe140():
    def execute(query):
        return []  # no rows at all
    p = Preview(execute=execute, engine="duckdb")
    trial = p.once(CLEAN)
    ok = trial.verdict == "no_data" and trial.has_data is False and trial.detail == "no rows were in scope, so the control tested nothing"
    log("EXE-140", "PASS" if ok else "FAIL", f"verdict={trial.verdict} has_data={trial.has_data} detail={trial.detail!r}")

def exe141():
    call = [0]
    def execute(query):
        call[0] += 1
        i = call[0]
        if i <= 10:
            return []  # empty periods
        elif i <= 14:
            return [{"scanned_rows": 100, "violating_rows": 5}]  # alerting (fail)
        else:
            return [{"scanned_rows": 100, "violating_rows": 0}]  # pass
    p = Preview(execute=execute, engine="duckdb")
    periods = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(30)]
    bt = p.backtest(CLEAN, period_column="as_of_date", periods=periods)
    ok = bt.alert_rate == 0.2 and "excluded from the rate rather than counted as quiet" in bt.describe()
    log("EXE-141", "PASS" if ok else "FAIL", f"alert_rate={bt.alert_rate} (expected 0.2 = 4/20) describe={bt.describe()!r}")

def exe142():
    def execute(query):
        raise RuntimeError("source unreachable")
    p = Preview(execute=execute, engine="duckdb")
    periods = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(30)]
    bt = p.backtest(CLEAN, period_column="as_of_date", periods=periods)
    ok = bt.alert_rate is None and bt.per_period(30) is None and "none of the 30 period(s) could be evaluated" in bt.describe()
    log("EXE-142", "PASS" if ok else "FAIL", f"alert_rate={bt.alert_rate} per_period={bt.per_period(30)} describe={bt.describe()!r}")

def exe143():
    obs = {}
    for v in ("pass", "fail", "indeterminate", "error", "no_data"):
        if v == "error":
            t = Trial(label="x", error="boom")
        else:
            t = Trial(label="x", verdict=v)
        obs[v] = t.would_alert
    ok = obs == {"pass": False, "fail": True, "indeterminate": True, "error": False, "no_data": False}
    log("EXE-143", "PASS" if ok else "FAIL", str(obs))

def exe144():
    def mk_bt(n_evaluated, n_alerting):
        trials = [Trial(label=str(i), verdict=("fail" if i < n_alerting else "pass"), scanned_rows=10, violating_rows=1) for i in range(n_evaluated)]
        return Backtest(trials=tuple(trials))
    bt4 = mk_bt(4, 1)
    bt5 = mk_bt(5, 1)
    ok = bt4.is_trustworthy is False and bt5.is_trustworthy is True and bt4.describe().endswith("4 period(s) is too few to quote a rate from")
    log("EXE-144", "PASS" if ok else "FAIL", f"4_periods_trustworthy={bt4.is_trustworthy} describe={bt4.describe()!r}; 5_periods_trustworthy={bt5.is_trustworthy}")

def exe145():
    def execute(query):
        return [{"scanned_rows": 10_000, "violating_rows": 3}]
    p = Preview(execute=execute, engine="duckdb", max_rows=10_000)
    trial = p.once(CLEAN)
    ok = trial.was_bounded is True and "cap" in trial.detail.lower() or "floor" in trial.detail.lower()
    desc = trial.describe()
    ok = ok and "at least" in desc
    bt = Backtest(trials=(trial,))
    ok = ok and bt.is_a_lower_bound is True and "at least" in bt.describe()
    log("EXE-145", "PASS" if ok else "FAIL", f"was_bounded={trial.was_bounded} detail={trial.detail!r} describe={desc!r} backtest.is_a_lower_bound={bt.is_a_lower_bound} backtest.describe={bt.describe()!r}")

def exe146():
    def execute(query):
        return [{"scanned_rows": 10_000, "violating_rows": 0}]
    p = Preview(execute=execute, engine="duckdb", max_rows=10_000)
    trial = p.once(CLEAN)
    ok = trial.verdict == "pass" and trial.was_bounded is True and "floor" in trial.detail
    log("EXE-146", "PASS" if ok else "FAIL", f"verdict={trial.verdict} was_bounded={trial.was_bounded} detail={trial.detail!r}")

def exe147():
    captured = {}
    def execute(query):
        captured["query"] = query
        return [{"scanned_rows": 5, "violating_rows": 0}]
    p = Preview(execute=execute, engine="duckdb", max_rows=1000)
    p.once(CLEAN)
    q = captured["query"]
    # crude check: LIMIT should appear near the source relation, not wrapping the aggregate SELECT COUNT
    ok = "LIMIT 1000" in q or "limit 1000" in q.lower()
    is_outer_limit = q.strip().upper().endswith("LIMIT 1000") and "SELECT" in q.upper().split("LIMIT")[0].upper().count("SELECT") == 1
    log("EXE-147", "PASS" if ok else "FAIL", f"query={q!r}")

def exe148():
    control = parse_control(CLEAN)
    evil_period = "x'; DROP TABLE positions --"
    restricted = _restricted(control, "as_of_date", evil_period)
    from prama.ir.resolve import resolved
    from prama.backend import compile_for
    plan = resolved(restricted)
    compiled = compile_for(plan, "duckdb", table=plan.scope.dataset)
    q = compiled.metric_query
    ok = "DROP TABLE" not in q.upper().replace("''", "") or evil_period.replace("'", "''") in q
    def execute(query):
        return [{"scanned_rows": 0, "violating_rows": 0}]
    p = Preview(execute=execute, engine="duckdb")
    trial = p.over(CLEAN, period_column="as_of_date", periods=[evil_period])
    result = list(trial)[0]
    log("EXE-148", "PASS" if result.error == "" else "FAIL", f"compiled_query={q!r} trial_result={result.verdict}/{result.error}")

def exe149():
    obs = {}
    for label, ident in (
        ("valid1", "as_of_date"), ("valid2", "_x9"), ("bad1", "9x"), ("bad2", "a.b"),
        ("bad3", '"a"'), ("bad4", "a b"), ("bad5", "as_of_date; DROP TABLE positions --"),
        ("bad6", ""), ("trimmed", "  a  "),
    ):
        try:
            r = plain_identifier(ident)
            obs[label] = ("OK", r)
        except ValidationError as e:
            obs[label] = ("ValidationError", None)
    ok = (obs["valid1"][0] == "OK" and obs["valid2"][0] == "OK"
          and obs["bad1"][0] == "ValidationError" and obs["bad2"][0] == "ValidationError"
          and obs["bad3"][0] == "ValidationError" and obs["bad4"][0] == "ValidationError"
          and obs["bad5"][0] == "ValidationError" and obs["bad6"][0] == "ValidationError"
          and obs["trimmed"] == ("OK", "a"))
    log("EXE-149", "PASS" if ok else "FAIL", str(obs))

def exe150():
    pql = "CHECK t.notional IS NOT NULL WHERE ccy = 'GBP' SEVERITY critical DIMENSION completeness BECAUSE 'x'"
    control = parse_control(pql)
    original_where = control.where
    restricted = _restricted(control, "as_of_date", "2026-04-01")
    ok = (restricted.where.operator == "AND" and control.where is original_where
          and restricted is not control)
    log("EXE-150", "PASS" if ok else "FAIL", f"restricted.where.operator={restricted.where.operator} original_control_unmutated={control.where is original_where}")

def exe151():
    import time
    arrival_times = []
    call_count = [0]
    def slow_execute(query):
        call_count[0] += 1
        time.sleep(0.05)
        return [{"scanned_rows": 10, "violating_rows": 0}]
    p = Preview(execute=slow_execute, engine="duckdb")
    periods = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(30)]
    started = time.monotonic()
    gen = p.over(CLEAN, period_column="as_of_date", periods=periods)
    first = next(gen)
    time_to_first = time.monotonic() - started
    ok = time_to_first < 0.2  # much less than 30*0.05=1.5s
    log("EXE-151", "PASS" if ok else "FAIL", f"time_to_first_trial={time_to_first:.3f}s (30 periods at 50ms each would take 1.5s total if it were a list; first arrived quickly, confirming a generator)")

def exe152():
    p = Preview(execute=lambda q: [], engine="duckdb")
    periods = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(30)]
    bt = p.backtest("THIS IS NOT VALID PQL {{{", period_column="as_of_date", periods=periods)
    ok = (len(bt.trials) == 30 and all(not t.ran for t in bt.trials)
          and len({t.error for t in bt.trials}) == 1
          and len(bt.evaluated) == 0 and bt.alert_rate is None)
    log("EXE-152", "PASS" if ok else "FAIL", f"n_trials={len(bt.trials)} all_unran={all(not t.ran for t in bt.trials)} distinct_errors={len({t.error for t in bt.trials})} evaluated={len(bt.evaluated)} alert_rate={bt.alert_rate}")

def exe153():
    sunday = dt.date(2026, 4, 5)  # confirm weekday
    wednesday = dt.date(2026, 4, 8)
    obs = {}
    obs["sunday_weekday"] = sunday.weekday()
    obs["wed_weekday"] = wednesday.weekday()
    d1 = business_dates(sunday, days=5)
    d2 = business_dates(wednesday, days=5)
    d3 = business_dates(sunday, days=5, weekdays_only=False)
    d4 = business_dates(sunday, days=0)
    ok = (sunday.weekday() == 6 and all(d.weekday() < 5 for d in d1)
          and d1[-1] == dt.date(2026, 4, 3)  # Friday before
          and d1 == sorted(d1)
          and d3 == sorted(d3) and (d3[-1] - d3[0]).days == 4
          and d4 == [])
    log("EXE-153", "PASS" if ok else "FAIL", f"sunday={sunday}({sunday.weekday()}) d1(weekdays_only)={d1} d3(all_days)={d3} d4(days=0)={d4}")

exe139()
exe140()
exe141()
exe142()
exe143()
exe144()
exe145()
exe146()
exe147()
exe148()
exe149()
exe150()
exe151()
exe152()
exe153()
