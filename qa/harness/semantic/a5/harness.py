import dataclasses
import sys
import traceback

from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.derive import persisted
from prama.derive.generator import (
    ControlGenerator,
    Generation,
    Unsatisfiable,
    Deferred,
    severity_for,
    evidence_for,
    fail_action_for,
    _and,
    _arrival,
    _volume,
    _range_words,
    _one_below,
    _parse_condition,
    _number,
    _coalesce,
    _fold,
)
from prama.semantic.values import (
    Optionality,
    Sensitivity,
    ValueDomain,
    ValueDomainKind,
    Criticality,
    Grain,
    Rhythm,
    Frequency,
    Temporality,
    Authoritativeness,
    LifecycleState,
)
from prama.pql.types import Catalogue, DatasetSchema, Column, TypeChecker
from prama.pql import ast
from prama.pql.parser import parse_control
from prama.pql.errors import PqlError
from prama.classify.validators import REGISTRY as VALIDATORS
from prama.classify.codelists import REGISTRY as CODELISTS

RESULTS = {}


def record(case_id, ok, observed):
    RESULTS[case_id] = (ok, observed)
    print(f"{case_id}: {'PASS' if ok else 'FAIL'} :: {observed}")


def run(case_id, fn):
    try:
        fn()
    except AssertionError as e:
        record(case_id, False, f"AssertionError: {e}")
    except Exception as e:
        record(case_id, False, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


def cid(fn_name):
    # der001 -> DER-001
    num = fn_name[3:]
    return f"DER-{num}"


# ---------------------------------------------------------------------------
# DER-001..014 declaration.py / persisted.py
# ---------------------------------------------------------------------------

def der001():
    a = AttributeDeclaration(name="amount")
    assert a.optionality is Optionality.OPTIONAL
    assert a.sensitivity is Sensitivity.INTERNAL
    assert a.is_cde is False
    assert a.value_domain == ValueDomain()
    assert a.value_domain.kind is ValueDomainKind.FREE_TEXT
    assert a.generates_a_domain_control is False
    record("DER-001", True, f"optionality={a.optionality}, sensitivity={a.sensitivity}, is_cde={a.is_cde}, value_domain.kind={a.value_domain.kind}, generates_a_domain_control={a.generates_a_domain_control}")


def der002():
    results = {}
    for unit in ("currency", "Money", "AMOUNT", "EUR"):
        a = AttributeDeclaration(name="x", unit=unit)
        results[unit] = a.is_monetary
    a5 = AttributeDeclaration(name="x", currency_attribute="ccy")
    results["currency_attribute=ccy,no unit"] = a5.is_monetary
    expected = {"currency": True, "Money": True, "AMOUNT": True, "EUR": False, "currency_attribute=ccy,no unit": True}
    ok = results == expected
    record("DER-002", ok, str(results))


def der003():
    a1 = AttributeDeclaration(name="x", semantic_type="isin")
    a2 = AttributeDeclaration(name="x", value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0))
    a3 = AttributeDeclaration(name="x", semantic_type="isin", value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0))
    a4 = AttributeDeclaration(name="x")
    results = (a1.generates_a_domain_control, a2.generates_a_domain_control, a3.generates_a_domain_control, a4.generates_a_domain_control)
    ok = results == (True, True, True, False)
    record("DER-003", ok, str(results))


def der004():
    attrs = (
        AttributeDeclaration(name="a", is_cde=True, obligations=("FINREP",)),
        AttributeDeclaration(name="b", is_cde=True, obligations=("FINREP", "FR Y-14Q")),
        AttributeDeclaration(name="c", is_cde=False),
    )
    d = DatasetDeclaration(name="ds", attributes=attrs)
    cdes = d.cdes
    obligations = d.obligations
    ok = len(cdes) == 2 and obligations == ("FINREP", "FR Y-14Q")
    record("DER-004", ok, f"cdes={[c.name for c in cdes]}, obligations={obligations}")


def der005():
    attrs = (AttributeDeclaration(name="a", optionality=Optionality.MANDATORY),)
    d = DatasetDeclaration(
        name="ds",
        owner_id="owner1",
        steward_id="steward1",
        custodian_id="custodian1",
        attributes=attrs,
    )
    gen = ControlGenerator().generate(d)
    owners = {c.control.owner for c in gen.controls}
    ok = owners == {"owner1"} and "steward1" not in owners and "custodian1" not in owners
    # Confirm steward/custodian never appear anywhere in dict form of controls
    dicts = [c.to_dict() for c in gen.controls]
    import json
    blob = json.dumps(dicts)
    leaked = "steward1" in blob or "custodian1" in blob
    record("DER-005", ok and not leaked, f"owners={owners}, leaked_steward_or_custodian={leaked}, n_controls={len(gen.controls)}")


def der006():
    d = DatasetDeclaration(name="ds", lifecycle_state="deprecated")
    a = d.is_live
    b = LifecycleState.DEPRECATED.is_live
    ok = a is False and b is True
    record("DER-006", ok, f"DatasetDeclaration.is_live={a}, LifecycleState.DEPRECATED.is_live={b}")


def der007():
    results = {}
    for shape in ("unbound", "table", "feed", ""):
        d = DatasetDeclaration(name="ds", shape=shape)
        results[shape] = d.is_bound
    expected = {"unbound": False, "table": True, "feed": True, "": True}
    ok = results == expected
    record("DER-007", ok, str(results))


def der008():
    d = DatasetDeclaration(name="ds", attributes=(AttributeDeclaration(name="amount"),))
    r1 = d.attribute("amount") is not None
    r2 = d.attribute("Amount") is not None
    r3 = d.attribute(" amount") is not None
    ok = (r1, r2, r3) == (True, False, False)
    record("DER-008", ok, f"amount={r1}, Amount={r2}, ' amount'={r3}")


def der009():
    row = {
        "name": "positions_table",
        "slug": "positions",
        "recorded_by": "bob",
        "dataset_id": "ds-1",
        "recorded_at": "2026-01-01T00:00:00Z",
    }

    class FakeVersion:
        slug = "positions"
        description = None
        purpose = None
        shape = "table"
        domain_id = None
        owner_id = None
        steward_id = None
        custodian_id = None
        criticality = 4
        grain_json = None
        business_key_json = None
        temporality = "snapshot"
        rhythm_json = None
        authoritativeness = "unknown"
        source_of_truth_id = None
        retention_days = None
        jurisdiction = None
        sensitivity = "internal"
        lifecycle_state = "proposed"
        tags_json = None
        dataset_id = "ds-1"
        authored_by = "alice"
        recorded_at = "2026-02-02T00:00:00Z"

    from_row_decl = DatasetDeclaration.from_row(row)
    persisted_decl = persisted.dataset_declaration_of(FakeVersion())
    diff_name = from_row_decl.name != persisted_decl.name
    diff_declared_by = from_row_decl.declared_by != persisted_decl.declared_by
    ok = diff_name and diff_declared_by and from_row_decl.name == "positions_table" and persisted_decl.name == "positions"
    ok = ok and from_row_decl.declared_by == "bob" and persisted_decl.declared_by == "alice"
    record("DER-009", ok, f"from_row.name={from_row_decl.name!r} persisted.name={persisted_decl.name!r}; from_row.declared_by={from_row_decl.declared_by!r} persisted.declared_by={persisted_decl.declared_by!r}")


def der010():
    class FakeVersion:
        slug = "end_of_day_positions"
        description = None
        purpose = None
        shape = "table"
        domain_id = None
        owner_id = "owner1"
        steward_id = None
        custodian_id = None
        criticality = 4
        grain_json = {"attributes": ["account_id"], "statement": ""}
        business_key_json = None
        temporality = "snapshot"
        rhythm_json = None
        authoritativeness = "unknown"
        source_of_truth_id = None
        retention_days = None
        jurisdiction = None
        sensitivity = "internal"
        lifecycle_state = "proposed"
        tags_json = None
        dataset_id = "ds-1"
        authored_by = "alice"
        recorded_at = "2026-02-02"

    decl = persisted.dataset_declaration_of(FakeVersion())
    gen = ControlGenerator().generate(decl)
    assert gen.controls, "expected controls"
    rendered = gen.controls[0].content
    ok = "CHECK end_of_day_positions" in rendered and "End-of-day Positions" not in rendered
    record("DER-010", ok, f"first control render starts: {rendered.splitlines()[0]!r}; decl.name={decl.name!r}")


def der011():
    class FakeVersion:
        slug = "ds1"
        description = None
        purpose = None
        shape = "table"
        domain_id = None
        owner_id = None
        steward_id = None
        custodian_id = None
        criticality = 4
        grain_json = None
        business_key_json = None
        temporality = "bitemporal"
        rhythm_json = None
        authoritativeness = "unknown"
        source_of_truth_id = None
        retention_days = None
        jurisdiction = None
        sensitivity = "secret"
        lifecycle_state = "proposed"
        tags_json = None
        dataset_id = "ds-1"
        authored_by = None
        recorded_at = None
        criticality = 9

    decl = persisted.dataset_declaration_of(FakeVersion())
    ok = (
        decl.temporality is Temporality.SNAPSHOT
        and decl.sensitivity is Sensitivity.INTERNAL
        and decl.criticality is Criticality.TIER_4
    )
    record("DER-011", ok, f"temporality={decl.temporality}, sensitivity={decl.sensitivity}, criticality={decl.criticality}")


def der012():
    payload = {"kind": "free_text", "pattern": None}
    vd = persisted._value_domain(payload)
    ok = vd.is_constrained is False
    record("DER-012", ok, f"kind={vd.kind!r}, is_constrained={vd.is_constrained}")


def der013():
    payload = {"kind": "colour", "allowed_values": ["red"]}
    vd = persisted._value_domain(payload)
    ok = vd.kind is ValueDomainKind.FREE_TEXT and vd.is_constrained is False
    record("DER-013", ok, f"kind={vd.kind}, is_constrained={vd.is_constrained}")


def der014():
    payload = {"kind": "range", "minimum": 0, "units": "EUR"}
    try:
        vd = persisted._value_domain(payload)
        record("DER-014", False, f"no exception raised; got {vd!r}")
    except TypeError as e:
        record("DER-014", True, f"TypeError: {e}")
    except Exception as e:
        record("DER-014", False, f"raised {type(e).__name__} instead of TypeError: {e}")


for fn in (der001, der002, der003, der004, der005, der006, der007, der008, der009, der010, der011, der012, der013, der014):
    run(cid(fn.__name__), fn)

print("\n=== Section 2: generator.py ===\n")


def mk_ds(**kwargs):
    kwargs.setdefault("name", "ds")
    return DatasetDeclaration(**kwargs)


def der015():
    grain = Grain(attributes=("account_id", "business_date"))
    attrs = (
        AttributeDeclaration(name="account_id"),
        AttributeDeclaration(name="business_date"),
    )
    d = mk_ds(grain=grain, attributes=attrs)
    gen = ControlGenerator().generate(d)
    uniq = gen.by_rule("grain.uniqueness")
    comp = gen.by_rule("grain.completeness")
    ok = len(uniq) == 1 and len(comp) == 2
    ok = ok and all(grain.render() in c.control.because for c in (*uniq, *comp))
    record("DER-015", ok, f"uniqueness={len(uniq)}, completeness={len(comp)}, becauses contain grain sentence={ok}")


def der016():
    grain = Grain(attributes=("account_id",))
    attrs = (AttributeDeclaration(name="account_id", optionality=Optionality.OPTIONAL),)
    d = mk_ds(grain=grain, attributes=attrs)
    gen = ControlGenerator().generate(d)
    comp = gen.by_rule("grain.completeness")
    assert comp, "expected a completeness control"
    because = comp[0].control.because
    ok = "would slip past the uniqueness control" in because and "SQL does not count nulls as duplicates" in because
    record("DER-016", ok, f"because={because!r}")


def der017():
    grain = Grain(attributes=("settlement_date",))
    attrs = (AttributeDeclaration(name="account_id"), AttributeDeclaration(name="amount"))
    d = mk_ds(grain=grain, attributes=attrs)
    gen = ControlGenerator().generate(d)
    ok = len(gen.controls) == 0 and len(gen.unsatisfiable) == 1
    u = gen.unsatisfiable[0]
    ok = ok and u.rule == "grain.uniqueness" and u.declared == grain.render()
    ok = ok and "settlement_date" in u.reason and u.remedy
    record("DER-017", ok, f"n_controls={len(gen.controls)}, unsatisfiable={u.to_dict() if gen.unsatisfiable else None}")


def der018():
    grain = Grain(attributes=("a", "b", "c"))
    d = mk_ds(grain=grain, attributes=(AttributeDeclaration(name="other"),))
    gen = ControlGenerator().generate(d)
    assert gen.unsatisfiable
    reason = gen.unsatisfiable[0].reason
    ok = "a, b and c" in reason and " are not in " in reason
    record("DER-018", ok, f"reason={reason!r}")


def der019():
    grain = Grain(attributes=("account_id",))
    d = mk_ds(grain=grain, attributes=())
    gen = ControlGenerator().generate(d)
    ok = len(gen.controls) > 0 and not gen.unsatisfiable
    record("DER-019", ok, f"n_controls={len(gen.controls)}, unsatisfiable={len(gen.unsatisfiable)}")


def der020():
    grain = Grain(attributes=("account_id",))
    attrs = (AttributeDeclaration(name="account_id"),)
    d = mk_ds(grain=grain, attributes=attrs)
    cat = Catalogue.of(ds={"other_col": "text"})
    gen = ControlGenerator(catalogue=cat).generate(d)
    ok = len(gen.controls) == 0 and len(gen.unsatisfiable) >= 1
    record("DER-020", ok, f"n_controls={len(gen.controls)}, unsatisfiable={[u.rule for u in gen.unsatisfiable]}")


def der021():
    grain = Grain(attributes=("account_id",))
    attrs = (AttributeDeclaration(name="account_id"),)
    d = mk_ds(name="unseen_dataset", grain=grain, attributes=attrs)
    cat = Catalogue.of(other_dataset={"col": "text"})
    gen = ControlGenerator(catalogue=cat).generate(d)
    ok = len(gen.controls) > 0 and not gen.unsatisfiable
    record("DER-021", ok, f"n_controls={len(gen.controls)}, unsatisfiable={len(gen.unsatisfiable)}")


def der022():
    attrs = (
        AttributeDeclaration(
            name="amount",
            value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0, maximum=100),
        ),
    )
    d = mk_ds(attributes=attrs)
    cat = Catalogue.of(ds={"amount": "text"})
    gen = ControlGenerator(catalogue=cat).generate(d)
    ok = len(gen.controls) == 0 and len(gen.unsatisfiable) >= 1
    msg = gen.unsatisfiable[0].reason if gen.unsatisfiable else ""
    remedy = gen.unsatisfiable[0].remedy if gen.unsatisfiable else ""
    record("DER-022", ok, f"n_controls={len(gen.controls)}, reason={msg!r}, remedy={remedy!r}")


def der023():
    attrs = (
        AttributeDeclaration(
            name="amount",
            value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0, maximum=100),
        ),
    )
    d = mk_ds(attributes=attrs)
    gen = ControlGenerator().generate(d)
    ok = len(gen.controls) >= 1 and not any("type-check" in u.reason for u in gen.unsatisfiable)
    record("DER-023", ok, f"n_controls={len(gen.controls)}, unsatisfiable={len(gen.unsatisfiable)}")


def der024():
    grain = Grain(attributes=("account_id", "business_date"))
    attrs = (
        AttributeDeclaration(name="account_id", optionality=Optionality.MANDATORY),
        AttributeDeclaration(name="business_date"),
        AttributeDeclaration(
            name="isin_code", semantic_type="isin",
        ),
        AttributeDeclaration(
            name="side", value_domain=ValueDomain(kind=ValueDomainKind.CODELIST, allowed_values=("BUY", "SELL")),
        ),
        AttributeDeclaration(
            name="qty", value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0, maximum=1000),
        ),
        AttributeDeclaration(
            name="ref_code", value_domain=ValueDomain(kind=ValueDomainKind.PATTERN, pattern=r"^[A-Z]{2}\d{4}$"),
        ),
        AttributeDeclaration(name="ccy_code", semantic_type="iso4217"),
        AttributeDeclaration(
            name="amount", currency_attribute="settlement_ccy",
        ),
        AttributeDeclaration(name="settlement_ccy"),
        AttributeDeclaration(
            name="product_type_flag", optionality=Optionality.CONDITIONAL, optionality_condition="side = 'BUY'"
        ),
    )
    rhythm = Rhythm(frequency=Frequency.DAILY, arrival_by="06:30", calendar="TARGET2", lateness_tolerance_seconds=900)
    d = mk_ds(grain=grain, attributes=attrs, rhythm=rhythm)
    gen = ControlGenerator().generate(d)
    problems = []
    for c in gen.controls:
        text = c.content
        try:
            parsed = parse_control(text)
        except PqlError as e:
            problems.append((c.rule, "parse-error", str(e)))
            continue
        rerendered = parsed.render()
        if rerendered != text:
            problems.append((c.rule, "mismatch", f"{text!r} != {rerendered!r}"))
    ok = not problems and len(gen.controls) > 0
    record("DER-024", ok, f"n_controls={len(gen.controls)}, problems={problems}")


def der025():
    results = {}
    for tier, sev in (
        (Criticality.TIER_1, "critical"),
        (Criticality.TIER_2, "major"),
        (Criticality.TIER_3, "minor"),
        (Criticality.TIER_4, "info"),
    ):
        d = mk_ds(criticality=tier, attributes=(AttributeDeclaration(name="a", optionality=Optionality.MANDATORY),))
        gen = ControlGenerator().generate(d)
        c = gen.by_rule("attribute.completeness")[0]
        results[tier.name] = (c.control.severity.value, sev)
    ok = all(a == b for a, b in results.values())
    record("DER-025", ok, str({k: v[0] for k, v in results.items()}))


def der026():
    d3 = mk_ds(criticality=Criticality.TIER_3, attributes=(AttributeDeclaration(name="a", optionality=Optionality.MANDATORY, is_cde=True),))
    d1 = mk_ds(criticality=Criticality.TIER_1, attributes=(AttributeDeclaration(name="a", optionality=Optionality.MANDATORY, is_cde=True),))
    g3 = ControlGenerator().generate(d3).by_rule("attribute.completeness")[0]
    g1 = ControlGenerator().generate(d1).by_rule("attribute.completeness")[0]
    ok = g3.control.severity == ast.Severity.MAJOR and g1.control.severity == ast.Severity.CRITICAL
    record("DER-026", ok, f"tier3_cde={g3.control.severity.value}, tier1_cde={g1.control.severity.value}")


def der027():
    a = AttributeDeclaration(name="a", is_cde=True, obligations=("FR Y-14Q",))
    d = mk_ds(attributes=(a,))
    ev = evidence_for(a)
    fa = fail_action_for(a)
    ok = ev.level is ast.EvidenceLevel.FULL and fa is ast.FailAction.BLOCK
    record("DER-027", ok, f"evidence={ev.level}, fail_action={fa}")


def der028():
    a = AttributeDeclaration(name="a", is_cde=True, obligations=())
    ev = evidence_for(a)
    fa = fail_action_for(a)
    ok = ev == ast.EvidenceSpec() and fa is ast.FailAction.ALERT
    record("DER-028", ok, f"evidence={ev}, fail_action={fa}")


def der029():
    a = AttributeDeclaration(name="a", sensitivity=Sensitivity.PII, is_cde=True, obligations=("FR Y-14Q",))
    ev = evidence_for(a)
    ok = ev.level is ast.EvidenceLevel.COUNTS
    record("DER-029", ok, f"evidence={ev.level}")


def der030():
    a = AttributeDeclaration(name="a", sensitivity=Sensitivity.CONFIDENTIAL)
    ev = evidence_for(a)
    ok = ev == ast.EvidenceSpec() and ev.level is not ast.EvidenceLevel.COUNTS
    record("DER-030", ok, f"evidence={ev.level}, masked_by_default={a.sensitivity.masked_by_default}")


def der031():
    grain = Grain(attributes=("a", "b"))
    d = mk_ds(grain=grain, business_key=("b", "a"), attributes=(AttributeDeclaration(name="a"), AttributeDeclaration(name="b")))
    gen = ControlGenerator().generate(d)
    ok = len(gen.by_rule("business_key.uniqueness")) == 0
    record("DER-031", ok, f"business_key.uniqueness count={len(gen.by_rule('business_key.uniqueness'))}")


def der032():
    grain = Grain(attributes=("account_id", "business_date"))
    d = mk_ds(
        grain=grain, business_key=("trade_ref",),
        attributes=(AttributeDeclaration(name="account_id"), AttributeDeclaration(name="business_date"), AttributeDeclaration(name="trade_ref")),
    )
    gen = ControlGenerator().generate(d)
    bk = gen.by_rule("business_key.uniqueness")
    ok = len(bk) == 1 and "business key" in bk[0].control.because and "grain" in bk[0].control.because
    record("DER-032", ok, f"count={len(bk)}, because={bk[0].control.because if bk else None!r}")


def der033():
    d = mk_ds(business_key=("missing_col",), attributes=(AttributeDeclaration(name="other"),))
    gen = ControlGenerator().generate(d)
    assert gen.unsatisfiable
    u = gen.unsatisfiable[0]
    ok = u.rule == "business_key.uniqueness" and "which is not present" in u.reason
    record("DER-033", ok, f"reason={u.reason!r}")


def der034():
    rhythm = Rhythm(frequency=Frequency.DAILY, arrival_by="06:30", calendar="TARGET2", lateness_tolerance_seconds=900)
    d = mk_ds(rhythm=rhythm)
    gen = ControlGenerator().generate(d)
    fresh = gen.by_rule("rhythm.freshness")
    assert fresh
    c = fresh[0].control
    a = c.assertion
    ok = a.due_time == "06:30" and a.calendar == "TARGET2" and a.tolerance_minutes == 15
    ok = ok and "06:30" in c.because and "grace" in c.because
    ok = ok and str(rhythm.expected_volume_min) not in c.because
    record("DER-034", ok, f"due_time={a.due_time}, calendar={a.calendar}, tolerance_minutes={a.tolerance_minutes}, because={c.because!r}")


def der035():
    results = {}
    for secs, expected_min in ((59, 0), (60, 1), (61, 1), (0, 0)):
        rhythm = Rhythm(frequency=Frequency.DAILY, arrival_by="06:30", lateness_tolerance_seconds=secs)
        d = mk_ds(rhythm=rhythm)
        gen = ControlGenerator().generate(d)
        c = gen.by_rule("rhythm.freshness")[0].control
        results[secs] = c.assertion.tolerance_minutes
    ok = results == {59: 0, 60: 1, 61: 1, 0: 0}
    record("DER-035", ok, str(results))


def der036():
    rhythm = Rhythm(frequency=Frequency.DAILY, expected_volume_min=1000, expected_volume_max=5000)
    d1 = mk_ds(criticality=Criticality.TIER_1, rhythm=rhythm)
    gen1 = ControlGenerator().generate(d1)
    vol1 = gen1.by_rule("rhythm.volume")[0]
    d4 = mk_ds(criticality=Criticality.TIER_4, rhythm=rhythm)
    gen4 = ControlGenerator().generate(d4)
    vol4 = gen4.by_rule("rhythm.volume")[0]
    ok = vol1.control.severity == ast.Severity.MAJOR and vol4.control.severity == ast.Severity.INFO
    record("DER-036", ok, f"tier1_volume_sev={vol1.control.severity.value}, tier4_volume_sev={vol4.control.severity.value}")


def der037():
    rmin = Rhythm(frequency=Frequency.DAILY, expected_volume_min=1000)
    rmax = Rhythm(frequency=Frequency.DAILY, expected_volume_max=5000)
    dmin = mk_ds(rhythm=rmin)
    dmax = mk_ds(rhythm=rmax)
    cmin = ControlGenerator().generate(dmin).by_rule("rhythm.volume")[0]
    cmax = ControlGenerator().generate(dmax).by_rule("rhythm.volume")[0]
    ok = "at least 1,000 records" in cmin.control.because and "at most 5,000 records" in cmax.control.because
    record("DER-037", ok, f"min_because={cmin.control.because!r}, max_because={cmax.control.because!r}")


def der038():
    rhythm = Rhythm(frequency=Frequency.DAILY, volume_drivers=("month_end",))
    d = mk_ds(rhythm=rhythm)
    gen = ControlGenerator().generate(d)
    ok = len(gen.controls) == 0
    deferred = [x for x in gen.deferred if x.rule == "rhythm.seasonality"]
    ok = ok and len(deferred) == 1 and "month_end" in deferred[0].declared
    record("DER-038", ok, f"n_controls={len(gen.controls)}, deferred={[d.to_dict() for d in deferred]}")


def der039():
    r1 = Rhythm(frequency=Frequency.CONTINUOUS)
    d1 = mk_ds(rhythm=r1)
    gen1 = ControlGenerator().generate(d1)
    deferred1 = [x for x in gen1.deferred if x.rule == "rhythm.freshness"]
    ok1 = len(deferred1) == 1 and not gen1.by_rule("rhythm.freshness")

    r2 = Rhythm(frequency=Frequency.CONTINUOUS, arrival_by="06:30")
    d2 = mk_ds(rhythm=r2)
    gen2 = ControlGenerator().generate(d2)
    ok2 = gen2.by_rule("rhythm.freshness") and not [x for x in gen2.deferred if x.rule == "rhythm.freshness"]
    ok = ok1 and bool(ok2)
    record("DER-039", ok, f"no_cutoff_deferred={len(deferred1)}, with_cutoff_has_control={bool(gen2.by_rule('rhythm.freshness'))}")


def der040():
    results = {}
    for temp in Temporality:
        d = mk_ds(temporality=temp)
        gen = ControlGenerator().generate(d)
        results[temp.value] = (len(gen.controls), len(gen.deferred))
    expected_snapshot = results["snapshot"] == (0, 0)
    others_ok = all(
        results[t.value] == (0, 1)
        for t in Temporality
        if t is not Temporality.SNAPSHOT
    )
    destinations = set()
    for t in Temporality:
        if t is Temporality.SNAPSHOT:
            continue
        d = mk_ds(temporality=t)
        gen = ControlGenerator().generate(d)
        destinations.add(gen.deferred[0].destination)
    distinct = len(destinations) == 5
    ok = expected_snapshot and others_ok and distinct
    record("DER-040", ok, f"per_temporality(controls,deferred)={results}, distinct_destinations={distinct}")


def der041():
    d = mk_ds(temporality=Temporality.MUTABLE)
    gen = ControlGenerator().generate(d)
    dest = gen.deferred[0].destination
    ok = "no control at all until an as-at column exists" in dest
    record("DER-041", ok, f"destination={dest!r}")


def der042():
    a = AttributeDeclaration(name="amount", optionality=Optionality.MANDATORY, definition="the position's carrying value")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.completeness")[0]
    ok = c.control.where is None and c.control.because == "amount is mandatory. the position's carrying value"
    record("DER-042", ok, f"where={c.control.where}, because={c.control.because!r}")


def der043():
    a = AttributeDeclaration(name="amount", optionality=Optionality.OPTIONAL)
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    ok = not gen.by_rule("attribute.completeness") and not gen.unsatisfiable and not gen.deferred
    record("DER-043", ok, f"completeness_controls={len(gen.by_rule('attribute.completeness'))}, unsatisfiable={len(gen.unsatisfiable)}, deferred={len(gen.deferred)}")


def der044():
    a = AttributeDeclaration(name="settlement_type", optionality=Optionality.CONDITIONAL, optionality_condition="product_type = 'BOND'")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.completeness")[0]
    rendered = c.content
    ok = "WHERE product_type = 'BOND'" in rendered and c.control.because == "settlement_type is mandatory when product_type = 'BOND'"
    record("DER-044", ok, f"rendered={rendered!r}, because={c.control.because!r}")


def der045():
    a = AttributeDeclaration(name="x", optionality=Optionality.CONDITIONAL, optionality_condition="")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    ok = len(gen.unsatisfiable) == 1 and gen.unsatisfiable[0].rule == "attribute.completeness"
    ok = ok and "stricter than" in gen.unsatisfiable[0].remedy
    record("DER-045", ok, f"unsatisfiable={gen.unsatisfiable[0].to_dict() if gen.unsatisfiable else None}")


def der046():
    results = {}
    for cond in ("when it is a bond", "product_type =", "1; DROP TABLE t"):
        a = AttributeDeclaration(name="x", optionality=Optionality.CONDITIONAL, optionality_condition=cond)
        d = mk_ds(attributes=(a,))
        gen = ControlGenerator().generate(d)
        results[cond] = (len(gen.unsatisfiable), gen.unsatisfiable[0].reason if gen.unsatisfiable else None)
    ok = all(v[0] == 1 and cond in (v[1] or "") for cond, v in results.items())
    record("DER-046", ok, str(results))


def der047():
    # SATISFIES x DETERMINES y parses successfully to a
    # FunctionalDependencyAssertion, not an ExpressionAssertion -- the
    # non-exception path through _parse_condition's final `return None`.
    cond = "account_id DETERMINES legal_entity_id"
    parsed_directly = parse_control(f"CHECK x SATISFIES {cond}")
    assertion_type = type(parsed_directly.assertion).__name__
    result = _parse_condition(cond)
    ok = assertion_type != "ExpressionAssertion" and result is None

    a = AttributeDeclaration(name="x", optionality=Optionality.CONDITIONAL, optionality_condition=cond)
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    ok = ok and len(gen.unsatisfiable) == 1 and not gen.controls
    record("DER-047", ok, f"direct_parse_assertion_type={assertion_type}, _parse_condition result={result}, generate() -> unsatisfiable={len(gen.unsatisfiable)}, controls={len(gen.controls)}")


def der048():
    a = AttributeDeclaration(name="isin_code", semantic_type="isin")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.semantic_type")[0]
    rendered = c.content
    ok = "IS VALID 'isin'" in rendered and ast.Dimension.VALIDITY in c.control.dimensions
    validator = VALIDATORS.find("isin")
    ok = ok and validator.describe() in c.control.because
    record("DER-048", ok, f"rendered snippet={[l for l in rendered.splitlines() if 'IS VALID' in l]}, dimensions={c.control.dimensions}, because={c.control.because!r}")


def der049():
    a = AttributeDeclaration(name="lei_code", semantic_type="lei")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.semantic_type")[0]
    validator = VALIDATORS.find("lei")
    ok = validator.screen_is_complete is False
    expected_suffix = validator.beyond_shape.capitalize()
    ok = ok and expected_suffix in c.control.because
    record("DER-049", ok, f"screen_is_complete={validator.screen_is_complete}, because={c.control.because!r}")


def der050():
    from prama.classify.validators import ValidatorRegistry
    empty_validators = ValidatorRegistry()
    a = AttributeDeclaration(name="ccy", semantic_type="iso4217")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator(validators=empty_validators).generate(d)
    c = gen.by_rule("attribute.semantic_type")[0]
    rendered = c.content
    label = CODELISTS.find("iso4217").label
    ok = "IN CODELIST 'iso4217'" in rendered and label in c.control.because
    record("DER-050", ok, f"rendered_snippet={[l for l in rendered.splitlines() if 'IN CODELIST' in l]}, because={c.control.because!r}")


def der051():
    a = AttributeDeclaration(name="isin_code", semantic_type="isin_code")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    assert gen.unsatisfiable
    u = gen.unsatisfiable[0]
    all_names = (*VALIDATORS.names(), *CODELISTS.names())
    ok = all(name in u.remedy for name in all_names)
    ok = ok and "compile to a check that passes everything" in u.remedy
    record("DER-051", ok, f"n_names_expected={len(all_names)}, all_present={ok}, remedy_len={len(u.remedy)}")


def der052():
    a = AttributeDeclaration(name="ccy", value_domain=ValueDomain(kind=ValueDomainKind.CODELIST, codelist_ref="iso4217"))
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.value_domain")[0]
    ok = "IN CODELIST 'iso4217'" in c.content
    record("DER-052", ok, f"rendered={[l for l in c.content.splitlines() if 'CODELIST' in l]}")


def der053():
    a = AttributeDeclaration(name="code", value_domain=ValueDomain(kind=ValueDomainKind.CODELIST, codelist_ref="internal_product_codes"))
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    assert gen.unsatisfiable
    u = gen.unsatisfiable[0]
    ok = u.rule == "attribute.value_domain" and "replay" in u.remedy
    record("DER-053", ok, f"unsatisfiable={u.to_dict()}")


def der054():
    a = AttributeDeclaration(name="side", value_domain=ValueDomain(kind=ValueDomainKind.CODELIST, allowed_values=("BUY", "SELL")))
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.value_domain")[0]
    rendered = c.content
    parsed = parse_control(rendered)
    ok = "IN ('BUY', 'SELL')" in rendered and "may only be BUY and SELL" in c.control.because
    ok = ok and parsed.render() == rendered
    record("DER-054", ok, f"rendered_snippet={[l for l in rendered.splitlines() if ' IN ' in l]}, because={c.control.because!r}, reparse_ok={parsed.render() == rendered}")


def der055():
    results = {}
    for kind, mn, mx in (("both", 0, 100), ("min", 0, None), ("max", None, 100)):
        a = AttributeDeclaration(name="qty", value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=mn, maximum=mx))
        d = mk_ds(attributes=(a,))
        gen = ControlGenerator().generate(d)
        c = gen.by_rule("attribute.value_domain")[0]
        results[kind] = [l.strip() for l in c.content.splitlines() if "qty" in l]
    ok = (
        any("BETWEEN" in l for l in results["both"])
        and any(">= 0" in l for l in results["min"])
        and any("<= 100" in l for l in results["max"])
    )
    record("DER-055", ok, str(results))


def der056():
    a = AttributeDeclaration(name="market_value", value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0))
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.value_domain")[0]
    line = next(l.strip() for l in c.content.splitlines() if "market_value" in l and ">=" in l)
    ok = "market_value >= 0" in line and "'0'" not in line
    record("DER-056", ok, f"line={line!r}")


def der057():
    payload = {"kind": "pattern"}
    vd = persisted._value_domain(payload)
    a = AttributeDeclaration(name="ref_code", value_domain=vd)
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    ok = len(gen.controls) == 0 and len(gen.unsatisfiable) == 1
    u = gen.unsatisfiable[0] if gen.unsatisfiable else None
    ok = ok and u is not None and "MATCHES /None/" not in (u.reason + u.remedy)
    ok = ok and u is not None and u.dataset == ""
    record("DER-057", ok, f"n_controls={len(gen.controls)}, unsatisfiable={u.to_dict() if u else None}")


def der058():
    pattern = r"^[A-Z]{2}\d{10}$"
    a = AttributeDeclaration(name="ref_code", value_domain=ValueDomain(kind=ValueDomainKind.PATTERN, pattern=pattern))
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.value_domain")[0]
    rendered = c.content
    line = next(l.strip() for l in rendered.splitlines() if "MATCHES" in l)
    parsed = parse_control(rendered)
    ok = f"MATCHES /{pattern}/" in line and parsed.render() == rendered

    # boundary: pattern containing a slash (no backslash, to isolate the slash case)
    pattern2 = r"^[A-Z]{2}/[0-9]{3}$"
    try:
        a2 = AttributeDeclaration(name="ref_code2", value_domain=ValueDomain(kind=ValueDomainKind.PATTERN, pattern=pattern2))
        d2 = mk_ds(attributes=(a2,))
        gen2 = ControlGenerator().generate(d2)
        c2 = gen2.by_rule("attribute.value_domain")[0]
        rendered2 = c2.content
        parsed2 = parse_control(rendered2)
        slash_ok = parsed2.render() == rendered2
        slash_note = f"rendered2_line={[l for l in rendered2.splitlines() if 'MATCHES' in l]}"
    except Exception as e:
        slash_ok = False
        slash_note = f"exception on pattern-with-slash: {type(e).__name__}: {e}"
    ok = ok and slash_ok
    record("DER-058", ok, f"line={line!r}, reparse_ok={parsed.render() == rendered}, slash_case_ok={slash_ok}, {slash_note}")


def der059():
    a = AttributeDeclaration(name="ref_code", value_domain=ValueDomain(kind=ValueDomainKind.PATTERN, pattern=r"^\d+$"))
    d = mk_ds(attributes=(a,))
    c_pattern = ControlGenerator().generate(d).by_rule("attribute.value_domain")[0]

    b = AttributeDeclaration(name="side", value_domain=ValueDomain(kind=ValueDomainKind.CODELIST, allowed_values=("BUY", "SELL")))
    d2 = mk_ds(attributes=(b,))
    c_codelist = ControlGenerator().generate(d2).by_rule("attribute.value_domain")[0]

    e = AttributeDeclaration(name="qty", value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0))
    d3 = mk_ds(attributes=(e,))
    c_range = ControlGenerator().generate(d3).by_rule("attribute.value_domain")[0]

    ok = (
        c_pattern.control.dimensions == (ast.Dimension.CONFORMITY,)
        and c_codelist.control.dimensions == (ast.Dimension.VALIDITY,)
        and c_range.control.dimensions == (ast.Dimension.VALIDITY,)
    )
    record("DER-059", ok, f"pattern={c_pattern.control.dimensions}, codelist={c_codelist.control.dimensions}, range={c_range.control.dimensions}")


def der060():
    a = AttributeDeclaration(name="amount", currency_attribute="settlement_ccy")
    ccy = AttributeDeclaration(name="settlement_ccy")
    d = mk_ds(attributes=(a, ccy))
    gen = ControlGenerator().generate(d)
    c = gen.by_rule("attribute.currency")
    assert c
    c = c[0]
    rendered = c.content
    ok = "settlement_ccy IN CODELIST 'iso4217'" in rendered
    ok = ok and set(c.control.dimensions) == {ast.Dimension.VALIDITY, ast.Dimension.CONSISTENCY}
    ok = ok and "meaningless" in c.control.because
    record("DER-060", ok, f"rendered_line={[l for l in rendered.splitlines() if 'CODELIST' in l]}, dimensions={c.control.dimensions}, because={c.control.because!r}")


def der061():
    a = AttributeDeclaration(name="amount", currency_attribute="ccy")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    u = [x for x in gen.unsatisfiable if x.rule == "attribute.currency"]
    ok = len(u) == 1 and "euros to yen" in u[0].remedy
    record("DER-061", ok, f"unsatisfiable={u[0].to_dict() if u else None}")


def der062():
    a = AttributeDeclaration(name="amount", unit="currency", currency_attribute="")
    d = mk_ds(attributes=(a,))
    gen = ControlGenerator().generate(d)
    ok = not gen.by_rule("attribute.currency") and not [x for x in gen.unsatisfiable if x.rule == "attribute.currency"]
    # check CoverageAnalyser behaviour if reachable
    coverage_note = ""
    try:
        from prama.semantic.coverage import CoverageAnalyser
        coverage_note = "CoverageAnalyser importable; not exercised in this harness (needs separate DB/coverage test suite)"
    except Exception as e:
        coverage_note = f"CoverageAnalyser import failed: {e}"
    record("DER-062", ok, f"currency_controls=0? {ok}; {coverage_note}")


def der063():
    d = mk_ds(authoritativeness=Authoritativeness.REPLICA, source_of_truth="")
    gen = ControlGenerator().generate(d)
    u = [x for x in gen.unsatisfiable if x.rule == "authoritativeness.parity"]
    ok = len(u) == 1 and "perfect copy of wrong data is a perfect copy" in u[0].remedy
    record("DER-063", ok, f"unsatisfiable={u[0].to_dict() if u else None}")


def der064():
    d = mk_ds(authoritativeness=Authoritativeness.EXTRACT, source_of_truth="positions")
    gen = ControlGenerator().generate(d)
    deferred = [x for x in gen.deferred if x.rule == "authoritativeness.parity"]
    ok = len(deferred) == 1 and "MIRRORS" in deferred[0].destination and not gen.controls
    record("DER-064", ok, f"deferred={[x.to_dict() for x in deferred]}, n_controls={len(gen.controls)}")


def der065():
    results = {}
    for a in (Authoritativeness.GOLDEN_SOURCE, Authoritativeness.DERIVED, Authoritativeness.VENDOR_SUPPLIED, Authoritativeness.UNKNOWN):
        d = mk_ds(authoritativeness=a)
        gen = ControlGenerator().generate(d)
        results[a.value] = (len(gen.controls), len([x for x in gen.deferred if x.rule == "authoritativeness.parity"]), len([x for x in gen.unsatisfiable if x.rule == "authoritativeness.parity"]))
    ok = all(v == (0, 0, 0) for v in results.values())
    record("DER-065", ok, str(results))


def der066():
    # Two independent controls in one declaration: a grain control (whose
    # BECAUSE embeds the grain's *statement*) and a range control on an
    # unrelated attribute (whose bound is a genuine "threshold"). Editing the
    # grain's statement must not perturb the range control's identity or
    # content; editing the range's minimum (the threshold) must change only
    # that control's content, never its identity.
    grain = Grain(attributes=("account_id",), statement="one row per account")
    attrs = (
        AttributeDeclaration(name="account_id"),
        AttributeDeclaration(name="qty", value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0)),
    )
    d = mk_ds(grain=grain, attributes=attrs)
    gen1 = ControlGenerator().generate(d)
    range1 = gen1.by_rule("attribute.value_domain")[0]

    grain2 = Grain(attributes=("account_id",), statement="a different statement entirely")
    d2 = dataclasses.replace(d, grain=grain2)
    gen2 = ControlGenerator().generate(d2)
    range2 = gen2.by_rule("attribute.value_domain")[0]

    attrs3 = (
        attrs[0],
        AttributeDeclaration(name="qty", value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=10)),
    )
    d3 = dataclasses.replace(d2, attributes=attrs3)
    gen3 = ControlGenerator().generate(d3)
    range3 = gen3.by_rule("attribute.value_domain")[0]

    identity_stable = range1.identity == range2.identity == range3.identity
    unaffected_by_statement_edit = range1.content_hash == range2.content_hash
    changed_by_threshold_edit = range2.content_hash != range3.content_hash
    ok = identity_stable and unaffected_by_statement_edit and changed_by_threshold_edit
    record(
        "DER-066",
        ok,
        f"identity_stable={identity_stable} ({range1.identity},{range2.identity},{range3.identity}), "
        f"content_hash unaffected by grain-statement edit={unaffected_by_statement_edit} "
        f"({range1.content_hash} vs {range2.content_hash}), "
        f"content_hash changed by threshold(minimum) edit={changed_by_threshold_edit} "
        f"({range2.content_hash} vs {range3.content_hash})",
    )


def der067():
    d = mk_ds(attributes=(
        AttributeDeclaration(name="a", optionality=Optionality.MANDATORY),
        AttributeDeclaration(name="b", optionality=Optionality.MANDATORY),
    ))
    gen = ControlGenerator().generate(d)
    ids = [c.identity for c in gen.controls]
    ok1 = len(set(ids)) == len(ids)

    d_other = mk_ds(name="other_ds", attributes=(
        AttributeDeclaration(name="a", optionality=Optionality.MANDATORY),
        AttributeDeclaration(name="b", optionality=Optionality.MANDATORY),
    ))
    gen_other = ControlGenerator().generate(d_other)
    ids_other = [c.identity for c in gen_other.controls]
    ok2 = not (set(ids) & set(ids_other))
    ok = ok1 and ok2
    record("DER-067", ok, f"same_dataset_unique={ok1}, no_cross_dataset_collision={ok2}, ids={ids}, ids_other={ids_other}")


def der068():
    a = AttributeDeclaration(name="x", optionality=Optionality.MANDATORY)
    d_no_ref = mk_ds(attributes=(a,), reference="")
    d_ref = mk_ds(attributes=(a,), reference="ds-ref-123")
    id_no_ref = ControlGenerator().generate(d_no_ref).controls[0].identity
    id_ref = ControlGenerator().generate(d_ref).controls[0].identity
    ok = id_no_ref != id_ref
    record("DER-068", ok, f"id_no_ref={id_no_ref}, id_ref={id_ref}, differ={ok}")


def der069():
    a = AttributeDeclaration(name="counterparty_lei", semantic_type="lei")
    d = mk_ds(name="exposures", reference="ds-exposures", attributes=(a,))
    gen = ControlGenerator().generate(d)
    attr_control = gen.by_rule("attribute.semantic_type")[0]
    grain = Grain(attributes=("account_id",))
    d2 = mk_ds(name="exposures2", reference="ds-exposures2", grain=grain, attributes=(AttributeDeclaration(name="account_id"),))
    gen2 = ControlGenerator().generate(d2)
    ds_control = gen2.by_rule("grain.uniqueness")[0]
    ok = attr_control.provenance.source_ref == "ds-exposures#counterparty_lei"
    ok = ok and ds_control.provenance.source_ref == "ds-exposures2"
    record("DER-069", ok, f"attr_source_ref={attr_control.provenance.source_ref!r}, ds_source_ref={ds_control.provenance.source_ref!r}")


def der070():
    a = AttributeDeclaration(name="x", optionality=Optionality.MANDATORY)
    d = mk_ds(attributes=(a,), declared_by="alice", declared_at="2026-03-04")
    gen = ControlGenerator().generate(d)
    sentences = [c.provenance.sentence() for c in gen.controls]
    ok = all(s == "alice declared it on 2026-03-04. “”".replace("“”", s.split(". ",1)[1]) or True for s in sentences)
    # exact check
    expected_prefix = "alice declared it on 2026-03-04. “"
    ok = all(s.startswith(expected_prefix) and s.endswith("”") for s in sentences)
    record("DER-070", ok, f"sentences={sentences}")


def der071():
    grain = Grain(attributes=("account_id", "business_date"))
    d = mk_ds(grain=grain, attributes=(
        AttributeDeclaration(name="account_id", optionality=Optionality.MANDATORY),
        AttributeDeclaration(name="business_date"),
    ))
    gen = ControlGenerator().generate(d)
    matching = [c for c in gen.controls if c.rule == "attribute.completeness+grain.completeness"]
    ok = len(matching) == 1
    if matching:
        because = matching[0].control.because
        sentences = because.split(". ")
        ok = ok and because.count(".") >= 2
        ok = ok and "account_id is mandatory" in because
        ok = ok and "grain" in because
    record("DER-071", ok, f"n_matching={len(matching)}, rule={matching[0].rule if matching else None}, because={matching[0].control.because if matching else None!r}")


def der072():
    grain = Grain(attributes=("account_id", "business_date"))
    d = mk_ds(grain=grain, attributes=(
        AttributeDeclaration(name="account_id", optionality=Optionality.MANDATORY, is_cde=True, obligations=("FR Y-14Q",)),
        AttributeDeclaration(name="business_date"),
    ))
    gen = ControlGenerator().generate(d)
    matching = [c for c in gen.controls if c.rule == "attribute.completeness+grain.completeness"]
    assert matching
    c = matching[0].control
    ok = c.on_fail is ast.FailAction.BLOCK and c.evidence.level is ast.EvidenceLevel.FULL
    ok = ok and c.severity == severity_for(d, d.attribute("account_id"))
    record("DER-072", ok, f"on_fail={c.on_fail}, evidence={c.evidence.level}, severity={c.severity}")


def der073():
    control_a = ast.Control(
        target="ds",
        assertion=ast.PredicateAssertion(subject=ast.ColumnRef(name="x"), operator="is_not_null"),
        name="name_a",
        because="reason a",
    )
    control_b = ast.Control(
        target="ds",
        assertion=ast.PredicateAssertion(subject=ast.ColumnRef(name="x"), operator="is_not_null"),
        name="name_b",
        because="reason b",
    )
    prov = Provenance = None
    from prama.core.provenance import Provenance as _Provenance, Origin as _Origin
    p = _Provenance(origin=_Origin.DECLARATION, rule="r", source_ref="s", statement="st")
    dc_a = dataclasses.replace(ControlGenerator()._control(mk_ds(), rule="r1", subject="x", control=control_a, provenance=p), )
    dc_b = ControlGenerator()._control(mk_ds(), rule="r2", subject="x", control=control_b, provenance=p)
    coalesced = _coalesce((dc_a, dc_b))
    ok1 = len(coalesced) == 1

    control_c = ast.Control(
        target="ds",
        assertion=ast.PredicateAssertion(subject=ast.ColumnRef(name="x"), operator="is_not_null"),
        where=ast.PredicateAssertion(subject=ast.ColumnRef(name="y"), operator="is_not_null"),
        name="name_c",
        because="reason c",
    )
    control_d = ast.Control(
        target="ds",
        assertion=ast.PredicateAssertion(subject=ast.ColumnRef(name="x"), operator="is_not_null"),
        where=ast.PredicateAssertion(subject=ast.ColumnRef(name="z"), operator="is_not_null"),
        name="name_d",
        because="reason d",
    )
    dc_c = ControlGenerator()._control(mk_ds(), rule="r3", subject="x", control=control_c, provenance=p)
    dc_d = ControlGenerator()._control(mk_ds(), rule="r4", subject="x", control=control_d, provenance=p)
    coalesced2 = _coalesce((dc_c, dc_d))
    ok2 = len(coalesced2) == 2
    ok = ok1 and ok2
    record("DER-073", ok, f"same_shape_merges_to={len(coalesced)}, different_where_stays={len(coalesced2)}")


def der074():
    grain = Grain(attributes=("account_id",))
    d = mk_ds(attributes=(AttributeDeclaration(name="account_id"),), grain=grain)
    gen = ControlGenerator().generate(d)
    assert gen.controls
    from prama.propose import adapt
    ok_all = True
    notes = []
    for c in gen.controls:
        proposal = adapt.from_control(c) if hasattr(adapt, "from_control") else None
        if proposal is None:
            ok_all = False
            notes.append("adapt.from_control not found or returned None")
            break
        status = getattr(proposal, "status", None)
        status_val = getattr(status, "value", status)
        if status_val != "proposed":
            ok_all = False
        notes.append(f"status={status_val}")
    record("DER-074", ok_all, "; ".join(notes))


def der075():
    grain = Grain(attributes=("account_id", "business_date"))
    d = mk_ds(grain=grain, attributes=(
        AttributeDeclaration(name="account_id", optionality=Optionality.MANDATORY),
        AttributeDeclaration(name="business_date"),
    ), rhythm=Rhythm(frequency=Frequency.DAILY, arrival_by="06:30"))
    gen1 = ControlGenerator().generate(d)
    gen2 = ControlGenerator().generate(d)
    ids1 = [c.identity for c in gen1.controls]
    ids2 = [c.identity for c in gen2.controls]
    hashes1 = [c.content_hash for c in gen1.controls]
    hashes2 = [c.content_hash for c in gen2.controls]
    u1 = [u.to_dict() for u in gen1.unsatisfiable]
    u2 = [u.to_dict() for u in gen2.unsatisfiable]
    def1 = [x.to_dict() for x in gen1.deferred]
    def2 = [x.to_dict() for x in gen2.deferred]
    ok = ids1 == ids2 and hashes1 == hashes2 and u1 == u2 and def1 == def2
    record("DER-075", ok, f"ids_equal={ids1==ids2}, hashes_equal={hashes1==hashes2}, unsatisfiable_equal={u1==u2}, deferred_equal={def1==def2}")


def der076():
    d = mk_ds(name="named_ds", owner_id="owner1")
    gen = ControlGenerator().generate(d)
    ok = len(gen) == 0 and gen.is_complete is True and not gen.deferred
    record("DER-076", ok, f"len={len(gen)}, is_complete={gen.is_complete}, deferred={len(gen.deferred)}")


def der077():
    a = AttributeDeclaration(name="x", optionality=Optionality.MANDATORY)
    d1 = mk_ds(name="ds1", attributes=(a,))
    d1_bad = mk_ds(name="ds1", business_key=("missing",))
    d2 = mk_ds(name="ds2", temporality=Temporality.MUTABLE)
    gen1 = ControlGenerator().generate(d1)
    gen1b = ControlGenerator().generate(d1_bad)
    gen2 = ControlGenerator().generate(d2)
    merged = gen1.merge(gen1b).merge(gen2)
    ok = merged.controls == (*gen1.controls, *gen1b.controls, *gen2.controls)
    ok = ok and merged.unsatisfiable == (*gen1.unsatisfiable, *gen1b.unsatisfiable, *gen2.unsatisfiable)
    ok = ok and merged.deferred == (*gen1.deferred, *gen1b.deferred, *gen2.deferred)
    ok = ok and set(merged.by_rule("attribute.completeness")) == set(gen1.by_rule("attribute.completeness"))
    ok = ok and set(merged.rules()) >= set(gen1.rules())
    record("DER-077", ok, f"controls_concat_ok={merged.controls == (*gen1.controls, *gen1b.controls, *gen2.controls)}, unsatisfiable_concat_ok={merged.unsatisfiable == (*gen1.unsatisfiable, *gen1b.unsatisfiable, *gen2.unsatisfiable)}, deferred_concat_ok={merged.deferred == (*gen1.deferred, *gen1b.deferred, *gen2.deferred)}")


def der078():
    a = AttributeDeclaration(name="x", optionality=Optionality.MANDATORY)
    d = mk_ds(business_key=("missing",), attributes=(a,))
    gen = ControlGenerator().generate(d)
    ok = bool(gen.controls) and bool(gen.unsatisfiable) and gen.is_complete is False
    d2 = mk_ds(temporality=Temporality.MUTABLE, attributes=(a,))
    gen2 = ControlGenerator().generate(d2)
    ok2 = bool(gen2.deferred) and not gen2.unsatisfiable and gen2.is_complete is True
    ok = ok and ok2
    record("DER-078", ok, f"has_controls={bool(gen.controls)}, has_unsatisfiable={bool(gen.unsatisfiable)}, is_complete_with_unsatisfiable={gen.is_complete}; deferred_only_is_complete={gen2.is_complete}")


for fn in (
    der015, der016, der017, der018, der019, der020, der021, der022, der023, der024,
    der025, der026, der027, der028, der029, der030, der031, der032, der033, der034,
    der035, der036, der037, der038, der039, der040, der041, der042, der043, der044,
    der045, der046, der047, der048, der049, der050, der051, der052, der053, der054,
    der055, der056, der057, der058, der059, der060, der061, der062, der063, der064,
    der065, der066, der067, der068, der069, der070, der071, der072, der073, der074,
    der075, der076, der077, der078,
):
    run(cid(fn.__name__), fn)

print("\n\nSUMMARY")
n_pass = sum(1 for v in RESULTS.values() if v[0])
n_fail = sum(1 for v in RESULTS.values() if not v[0])
print(f"pass={n_pass} fail={n_fail} total={len(RESULTS)}")

