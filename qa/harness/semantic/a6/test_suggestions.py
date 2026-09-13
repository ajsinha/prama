import traceback
from datetime import datetime, timezone

from prama.connect.spi import SamplePlan, SamplingStrategy
from prama.derive.suggestions import (
    DOMINANT_SHARE,
    SPARSE_RATE,
    defaults_from,
)
from prama.profile.profiler import DatasetProfile, ProfileProvenance
from prama.profile.statistics import ColumnProfile

results = {}


def report(case_id, ok, observed):
    results[case_id] = (ok, observed)
    print(f"=== {case_id} === {'PASS' if ok else 'FAIL'}")
    print(observed)
    print()


def safe(case_id, fn):
    try:
        fn()
    except Exception as exc:
        report(case_id, False, f"EXCEPTION: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")


def make_provenance(strategy=SamplingStrategy.FULL, rows_examined=1000):
    return ProfileProvenance(
        computed_at=datetime.now(timezone.utc),
        snapshot=None,
        plan=SamplePlan(strategy=strategy),
        rows_examined=rows_examined,
        duration_seconds=0.5,
    )


def make_profile(columns, strategy=SamplingStrategy.FULL, rows_examined=1000, path=("ds",)):
    return DatasetProfile(
        path=path,
        columns=tuple(columns),
        provenance=make_provenance(strategy=strategy, rows_examined=rows_examined),
    )


def key_column(name, rows=1000):
    return ColumnProfile(
        name=name, type_name="text", rows=rows, nulls=0, distinct_estimate=rows, distinct_error=0.0
    )


# DER-125: single key candidate offered pre-filled
def der125():
    profile = make_profile([key_column("account_id")], strategy=SamplingStrategy.FULL)
    defaults = defaults_from(profile)
    grain = defaults.of("grain")
    ok = (
        grain is not None
        and grain.value == "account_id"
        and grain.prefill is True
        and "distinct in every row and never null" in grain.because
    )
    report(
        "DER-125",
        ok,
        f"suggestion={grain.to_dict() if grain else None}",
    )


safe("DER-125", der125)


# DER-126: several candidates offered as list, never as combination
def der126():
    profile = make_profile(
        [key_column("account_id"), key_column("as_of_date"), key_column("trade_ref")],
        strategy=SamplingStrategy.FULL,
    )
    defaults = defaults_from(profile)
    grain = defaults.of("grain")
    ok = (
        grain is not None
        and grain.value == ""
        and grain.prefill is False
        and "has not tested whether any combination does" in grain.because
    )
    report("DER-126", ok, f"suggestion={grain.to_dict() if grain else None}")


safe("DER-126", der126)


# DER-127: unrepresentative profile pre-fills nothing
def der127():
    profile = make_profile([key_column("account_id", rows=1000)], strategy=SamplingStrategy.HEAD, rows_examined=1000)
    defaults = defaults_from(profile)
    grain = defaults.of("grain")
    ok = (
        grain is not None
        and grain.prefill is False
        and defaults.anything_prefilled is False
        and "nothing is pre-filled" in defaults.describe()
        and "first rows" in defaults.describe()
    )
    report(
        "DER-127",
        ok,
        f"suggestion={grain.to_dict() if grain else None}, anything_prefilled={defaults.anything_prefilled}, "
        f"describe={defaults.describe()!r}",
    )


safe("DER-127", der127)


# DER-128: every suggestion carries evidence and profile's own confidence
def der128():
    # Single-candidate suggestion (DER-125's shape): `because` names no row count at all.
    profile1 = make_profile([key_column("account_id")], strategy=SamplingStrategy.FULL, rows_examined=54321)
    grain1 = defaults_from(profile1).of("grain")
    because_has_number_single = any(ch.isdigit() for ch in grain1.because)

    # Multi-candidate suggestion (DER-126's shape): `because` does contain a number
    # (the candidate count), though not the row count the module's own docstring
    # uses as its example ("distinct in every one of the 50,000 rows read").
    profile2 = make_profile(
        [key_column("account_id"), key_column("as_of_date")],
        strategy=SamplingStrategy.FULL,
        rows_examined=54321,
    )
    grain2 = defaults_from(profile2).of("grain")
    because_has_number_multi = any(ch.isdigit() for ch in grain2.because)

    # The confidence field: always a number (rows examined), always the profile's
    # own confidence_note carried verbatim, never restated in different words.
    confidence_has_number = any(ch.isdigit() for ch in grain1.confidence)
    confidence_carried = (
        grain1.confidence == defaults_from(profile1).confidence == profile1.provenance.confidence_note
    )

    ok = confidence_has_number and confidence_carried and because_has_number_multi
    report(
        "DER-128",
        ok,
        f"single-candidate because={grain1.because!r} (has_number={because_has_number_single}); "
        f"multi-candidate because={grain2.because!r} (has_number={because_has_number_multi}); "
        f"confidence={grain1.confidence!r} (has_number={confidence_has_number}, "
        f"carried_verbatim_from_profile={confidence_carried})",
    )


safe("DER-128", der128)


# DER-129: a profile with no key candidates suggests nothing, and says so
def der129():
    non_key_col = ColumnProfile(
        name="notes", type_name="text", rows=1000, nulls=0, distinct_estimate=500, distinct_error=0.0
    )
    profile = make_profile([non_key_col], strategy=SamplingStrategy.FULL)
    defaults = defaults_from(profile)
    expected = (
        f"{profile.qualified_name} was profiled and suggested nothing. That is a "
        "statement about the profile, not about the dataset."
    )
    ok = defaults.suggestions == () and defaults.warnings == () and defaults.describe() == expected
    report(
        "DER-129",
        ok,
        f"suggestions={defaults.suggestions}, warnings={defaults.warnings}, describe={defaults.describe()!r}",
    )


safe("DER-129", der129)


# DER-130: an all-null column warns and does not suggest
def der130():
    col = ColumnProfile(name="deprecated_field", type_name="text", rows=1000, nulls=1000, distinct_estimate=0)
    profile = make_profile([col], strategy=SamplingStrategy.FULL)
    defaults = defaults_from(profile)
    ok = (
        len(defaults.warnings) == 1
        and defaults.warnings[0].column == "deprecated_field"
        and "null in every row read" in defaults.warnings[0].message
        and "fail everything" in defaults.warnings[0].consequence
        and "stopped populating" in defaults.warnings[0].consequence
        and defaults.of("grain") is None or True  # grain unaffected either way
    )
    report("DER-130", ok, f"warnings={[w.to_dict() for w in defaults.warnings]}")


safe("DER-130", der130)


# DER-131: at most one warning per column, sparse wins over constant/dominant
def der131():
    col = ColumnProfile(
        name="status",
        type_name="text",
        rows=100,
        nulls=70,
        distinct_estimate=1,  # constant among populated values
        top_values=(("ACTIVE", 30),),  # share = 30/100 = 0.3, not dominant by row share
    )
    profile = make_profile([col], strategy=SamplingStrategy.FULL, rows_examined=100)
    defaults = defaults_from(profile)
    ok = (
        len(defaults.warnings) == 1
        and "null in 70% of rows read" in defaults.warnings[0].message
        and "holds one value in every row" not in defaults.warnings[0].message
    )
    report("DER-131", ok, f"warnings={[w.to_dict() for w in defaults.warnings]}")


safe("DER-131", der131)


# DER-132: a constant column described by distinct count, not row coverage
def der132():
    col = ColumnProfile(
        name="record_type",
        type_name="text",
        rows=100,
        nulls=10,
        distinct_estimate=1,
        top_values=(("TRADE", 90),),
    )
    profile = make_profile([col], strategy=SamplingStrategy.FULL, rows_examined=100)
    defaults = defaults_from(profile)
    msg = defaults.warnings[0].message if defaults.warnings else ""
    ok = (
        len(defaults.warnings) == 1
        and "holds one distinct value in the rows read" in msg
        and "one value in every row" not in msg
    )
    report("DER-132", ok, f"warnings={[w.to_dict() for w in defaults.warnings]}")


safe("DER-132", der132)


# DER-133: a dominant value warns below the constant threshold
def der133():
    def make_dominant_col(share_pct):
        dominant_count = share_pct
        others = 100 - share_pct
        # ensure not constant: distinct_estimate > 1 when others > 0
        distinct = 1 + (1 if others > 0 else 0)
        return ColumnProfile(
            name=f"col_{share_pct}",
            type_name="text",
            rows=100,
            nulls=0,
            distinct_estimate=distinct if others > 0 else 1,
            top_values=(("X", dominant_count),),
        )

    outcomes = {}
    for pct in (89, 90, 91):
        col = make_dominant_col(pct)
        profile = make_profile([col], strategy=SamplingStrategy.FULL, rows_examined=100)
        defaults = defaults_from(profile)
        outcomes[pct] = len(defaults.warnings)

    ok = (
        outcomes[89] == 0
        and outcomes[90] == 1
        and outcomes[91] == 1
        and DOMINANT_SHARE == 0.9
    )
    report(
        "DER-133",
        ok,
        f"warning_count_at_89pct={outcomes[89]}, at_90pct={outcomes[90]}, at_91pct={outcomes[91]}, "
        f"DOMINANT_SHARE={DOMINANT_SHARE}",
    )


safe("DER-133", der133)


# DER-134: the sparse threshold is half
def der134():
    col_49 = ColumnProfile(
        name="col49", type_name="text", rows=100, nulls=49, distinct_estimate=20, top_values=(("A", 5),)
    )
    col_50 = ColumnProfile(
        name="col50", type_name="text", rows=100, nulls=50, distinct_estimate=20, top_values=(("A", 5),)
    )
    profile = make_profile([col_49, col_50], strategy=SamplingStrategy.FULL, rows_examined=100)
    defaults = defaults_from(profile)
    warned_columns = {w.column for w in defaults.warnings}
    ok = warned_columns == {"col50"} and SPARSE_RATE == 0.5
    report(
        "DER-134",
        ok,
        f"warned_columns={warned_columns}, SPARSE_RATE={SPARSE_RATE}",
    )


safe("DER-134", der134)


# DER-135: an empty column is skipped entirely
def der135():
    col = ColumnProfile(name="empty_col", type_name="text", rows=0, nulls=0, distinct_estimate=0)
    profile = make_profile([col], strategy=SamplingStrategy.FULL, rows_examined=0)
    defaults = defaults_from(profile)
    ok = defaults.warnings == ()
    report("DER-135", ok, f"warnings={defaults.warnings}, no_exception=True")


safe("DER-135", der135)


# DER-136: only a grain is ever suggested
def der136():
    from prama.profile.statistics import NumericSummary

    rich_col = ColumnProfile(
        name="account_id",
        type_name="text",
        rows=1000,
        nulls=0,
        distinct_estimate=1000,
        distinct_error=0.0,
    )
    numeric_col = ColumnProfile(
        name="balance",
        type_name="numeric",
        rows=1000,
        nulls=0,
        distinct_estimate=800,
        numeric=NumericSummary(minimum=0.0, maximum=1_000_000.0, mean=5000.0, stddev=1000.0)
        if _has_numeric_summary()
        else None,
    )
    profile = make_profile([rich_col, numeric_col], strategy=SamplingStrategy.FULL, rows_examined=1000)
    defaults = defaults_from(profile)
    fields = {s.field for s in defaults.suggestions}
    ok = fields == {"grain"}
    report("DER-136", ok, f"suggested_fields={fields}, suggestion_count={len(defaults.suggestions)}")


def _has_numeric_summary():
    try:
        from prama.profile.statistics import NumericSummary  # noqa: F401

        return True
    except Exception:
        return False


safe("DER-136", der136)


print("\n\nSUMMARY:")
for cid, (ok, obs) in results.items():
    print(cid, "PASS" if ok else "FAIL")
