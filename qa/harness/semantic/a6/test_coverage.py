import traceback

from prama.derive.coverage import (
    MAXIMUM_RISK,
    CoverageAnalyser,
    Coverage,
    Gap,
)
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.pql import ast
from prama.semantic.values import Optionality, Criticality

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


def completeness_control(dataset, attr, dims=(ast.Dimension.COMPLETENESS,)):
    return ast.Control(
        target=dataset,
        assertion=ast.PredicateAssertion(subject=ast.ColumnRef(name=attr), operator="is_not_null"),
        name=f"{dataset}_{attr}_present",
        dimensions=dims,
        because="test control",
    )


def reference_control(dataset, attr, target_dataset, target_column):
    return ast.Control(
        target=dataset,
        assertion=ast.ReferenceAssertion(
            column=ast.ColumnRef(name=attr),
            target_dataset=target_dataset,
            target_column=target_column,
        ),
        name=f"{dataset}_{attr}_ref",
        dimensions=(ast.Dimension.INTEGRITY,),
        because="test control",
    )


analyser = CoverageAnalyser()


# DER-108: coverage counted per attribute-dimension pair
def der108():
    attr = AttributeDeclaration(
        name="lei_code", optionality=Optionality.MANDATORY, semantic_type="lei"
    )
    ds = DatasetDeclaration(name="counterparty", attributes=(attr,))
    controls = [completeness_control("counterparty", "lei_code")]
    cov = analyser.analyse(ds, controls)
    ok = (
        cov.covered == 1
        and cov.applicable == 2
        and len(cov.gaps) == 1
        and cov.gaps[0].dimension is ast.Dimension.VALIDITY
    )
    report(
        "DER-108",
        ok,
        f"covered={cov.covered}, applicable={cov.applicable}, gaps={[g.dimension.value for g in cov.gaps]}",
    )


safe("DER-108", der108)


# DER-109: flattering number kept beside honest one
def der109():
    attrs = tuple(
        AttributeDeclaration(
            name=f"attr{i}",
            optionality=Optionality.MANDATORY,
            semantic_type="code",
            currency_attribute="ccy",
            is_cde=True,
        )
        for i in range(10)
    )
    ds = DatasetDeclaration(name="ds", attributes=attrs)
    # each attribute has exactly one control, covering only one of its four
    # applicable dimensions (completeness)
    controls = [completeness_control("ds", f"attr{i}") for i in range(10)]
    cov = analyser.analyse(ds, controls)
    ok = (
        abs(cov.fraction - 0.25) < 1e-9
        and abs(cov.touched_fraction - 1.0) < 1e-9
        and "flatters" in cov.describe()
    )
    report(
        "DER-109",
        ok,
        f"fraction={cov.fraction}, touched_fraction={cov.touched_fraction}, describe={cov.describe()!r}",
    )


safe("DER-109", der109)


# DER-110: only applicable dimensions are counted
def der110():
    attr = AttributeDeclaration(
        name="free_note", optionality=Optionality.OPTIONAL, is_cde=False
    )
    ds = DatasetDeclaration(name="ds", attributes=(attr,))
    cov = analyser.analyse(ds, [])
    ok = cov.applicable == 0 and cov.gaps == () and cov.fraction == 1.0
    report(
        "DER-110",
        ok,
        f"applicable={cov.applicable}, gaps={cov.gaps}, fraction={cov.fraction}",
    )


safe("DER-110", der110)


# DER-111: an optional attribute has no completeness dimension
def der111():
    a_opt = AttributeDeclaration(name="a_opt", optionality=Optionality.OPTIONAL)
    a_cond = AttributeDeclaration(
        name="a_cond", optionality=Optionality.CONDITIONAL, optionality_condition="x > 0"
    )
    a_mand = AttributeDeclaration(name="a_mand", optionality=Optionality.MANDATORY)
    ds = DatasetDeclaration(name="ds", attributes=(a_opt, a_cond, a_mand))
    cov = analyser.analyse(ds, [])
    # applicable should only be 2 (cond + mand), each with a completeness gap
    completeness_gaps = {g.attribute for g in cov.gaps if g.dimension is ast.Dimension.COMPLETENESS}
    ok = completeness_gaps == {"a_cond", "a_mand"} and cov.applicable == 2
    report(
        "DER-111",
        ok,
        f"applicable={cov.applicable}, completeness_gaps={completeness_gaps}",
    )


safe("DER-111", der111)


# DER-112: a CDE earns an accuracy dimension and nothing else does
def der112():
    cde = AttributeDeclaration(name="cde_attr", is_cde=True)
    non_cde = AttributeDeclaration(name="non_cde_attr", is_cde=False)
    ds = DatasetDeclaration(name="ds", attributes=(cde, non_cde))
    cov = analyser.analyse(ds, [])
    accuracy_gaps = {g.attribute for g in cov.gaps if g.dimension is ast.Dimension.ACCURACY}
    ok = accuracy_gaps == {"cde_attr"}
    report("DER-112", ok, f"accuracy_gap_attributes={accuracy_gaps}")


safe("DER-112", der112)


# DER-113: an integrity control satisfies the accuracy expectation
def der113():
    cde = AttributeDeclaration(name="cpty_id", is_cde=True, optionality=Optionality.OPTIONAL)
    ds = DatasetDeclaration(name="trade", attributes=(cde,))
    controls = [reference_control("trade", "cpty_id", "counterparty_master", "cpty_id")]
    cov = analyser.analyse(ds, controls)
    accuracy_covered = ast.Dimension.ACCURACY not in {g.dimension for g in cov.gaps}
    ok = accuracy_covered
    report(
        "DER-113",
        ok,
        f"gaps={[(g.attribute, g.dimension.value) for g in cov.gaps]}, accuracy_covered={accuracy_covered}",
    )


safe("DER-113", der113)


# DER-114: a currency control on the code column covers the amount's consistency
def der114():
    amount = AttributeDeclaration(
        name="exposure_amount",
        currency_attribute="exposure_ccy",
        optionality=Optionality.OPTIONAL,
    )
    ccy = AttributeDeclaration(name="exposure_ccy", optionality=Optionality.OPTIONAL)
    ds = DatasetDeclaration(name="exposure", attributes=(amount, ccy))
    # the "currency control" is generated on exposure_ccy, dimension CONSISTENCY
    controls = [completeness_control("exposure", "exposure_ccy", dims=(ast.Dimension.CONSISTENCY,))]
    cov = analyser.analyse(ds, controls)
    consistency_covered_for_amount = not any(
        g.attribute == "exposure_amount" and g.dimension is ast.Dimension.CONSISTENCY
        for g in cov.gaps
    )
    ok = consistency_covered_for_amount
    report(
        "DER-114",
        ok,
        f"gaps={[(g.attribute, g.dimension.value) for g in cov.gaps]}, amount_consistency_covered={consistency_covered_for_amount}",
    )


safe("DER-114", der114)


# DER-115: a control with no declared dimension covers nothing
def der115():
    attr = AttributeDeclaration(name="a", optionality=Optionality.MANDATORY)
    ds = DatasetDeclaration(name="ds", attributes=(attr,))
    controls = [completeness_control("ds", "a", dims=())]
    cov = analyser.analyse(ds, controls)
    ok = cov.attributes_touched == 1 and cov.covered == 0 and len(cov.gaps) == 1
    report(
        "DER-115",
        ok,
        f"attributes_touched={cov.attributes_touched}, covered={cov.covered}, gaps={[(g.attribute, g.dimension.value) for g in cov.gaps]}",
    )


safe("DER-115", der115)


# DER-116: every assertion shape is attributed to its columns
def der116():
    from prama.derive.coverage import _subjects

    predicate = ast.Control(
        target="ds",
        assertion=ast.PredicateAssertion(subject=ast.ColumnRef(name="col_pred"), operator="is_not_null"),
        name="c1",
    )
    reference = ast.Control(
        target="ds",
        assertion=ast.ReferenceAssertion(
            column=ast.ColumnRef(name="col_ref"), target_dataset="other", target_column="id"
        ),
        name="c2",
    )
    unique_key = ast.Control(
        target="ds",
        assertion=ast.UniqueKeyAssertion(columns=(ast.ColumnRef(name="col_uk1"), ast.ColumnRef(name="col_uk2"))),
        name="c3",
    )
    fd = ast.Control(
        target="ds",
        assertion=ast.FunctionalDependencyAssertion(
            determinant=(ast.ColumnRef(name="col_det"),), dependent=(ast.ColumnRef(name="col_dep"),)
        ),
        name="c4",
    )
    row_count = ast.Control(
        target="ds", assertion=ast.RowCountAssertion(minimum=1), name="c5"
    )
    freshness = ast.Control(
        target="ds", assertion=ast.FreshnessAssertion(tolerance_minutes=60), name="c6"
    )
    results_map = {
        "predicate": _subjects(predicate),
        "reference": _subjects(reference),
        "unique_key": _subjects(unique_key),
        "functional_dependency": _subjects(fd),
        "row_count": _subjects(row_count),
        "freshness": _subjects(freshness),
    }
    ok = (
        results_map["predicate"] == ("col_pred",)
        and results_map["reference"] == ("col_ref",)
        and set(results_map["unique_key"]) == {"col_uk1", "col_uk2"}
        and set(results_map["functional_dependency"]) == {"col_det", "col_dep"}
        and results_map["row_count"] == ()
        and results_map["freshness"] == ()
    )
    report("DER-116", ok, f"subjects={results_map}")


safe("DER-116", der116)


# DER-117: gap risk stays separable all the way to the end
def der117():
    g1 = Gap(dataset="ds", attribute="a1", dimension=ast.Dimension.COMPLETENESS, criticality=1, is_cde=True, obligations=("FR Y-14Q",))
    g2 = Gap(dataset="ds", attribute="a2", dimension=ast.Dimension.VALIDITY, criticality=1, is_cde=True, obligations=())
    g3 = Gap(dataset="ds", attribute="a3", dimension=ast.Dimension.COMPLETENESS, criticality=1, is_cde=False, obligations=())
    g4 = Gap(dataset="ds", attribute="a4", dimension=ast.Dimension.VALIDITY, criticality=1, is_cde=False, obligations=())
    risks = [g1.risk, g2.risk, g3.risk, g4.risk]
    ok = len(set(risks)) == 4 and sorted(risks, reverse=True) == risks
    report(
        "DER-117",
        ok,
        f"risks (obligation+cde+completeness, cde-only, completeness-only, neither)={risks}, "
        f"distinct={len(set(risks))}, strictly_ordered_desc={sorted(risks, reverse=True) == risks}",
    )


safe("DER-117", der117)


# DER-118: risk normalised into [0,1]
def der118():
    maximal = Gap(
        dataset="ds", attribute="a", dimension=ast.Dimension.COMPLETENESS, criticality=1, is_cde=True, obligations=("X",)
    )
    minimal = Gap(
        dataset="ds", attribute="b", dimension=ast.Dimension.VALIDITY, criticality=4, is_cde=False, obligations=()
    )
    ok = abs(maximal.risk - 1.0) < 1e-9 and abs(minimal.risk - (0.25 / 2.3)) < 1e-9
    report(
        "DER-118",
        ok,
        f"MAXIMUM_RISK={MAXIMUM_RISK}, maximal.risk={maximal.risk}, minimal.risk={minimal.risk}, "
        f"expected_minimal={0.25 / 2.3}",
    )


safe("DER-118", der118)


# DER-119: criticality is clamped rather than trusted
def der119():
    g_low = Gap(dataset="ds", attribute="a", dimension=ast.Dimension.VALIDITY, criticality=0, is_cde=False)
    g_high = Gap(dataset="ds", attribute="b", dimension=ast.Dimension.VALIDITY, criticality=9, is_cde=False)
    g_tier1 = Gap(dataset="ds", attribute="c", dimension=ast.Dimension.VALIDITY, criticality=1, is_cde=False)
    g_tier4 = Gap(dataset="ds", attribute="d", dimension=ast.Dimension.VALIDITY, criticality=4, is_cde=False)
    ok = g_low.risk == g_tier1.risk and g_high.risk == g_tier4.risk
    report(
        "DER-119",
        ok,
        f"risk(criticality=0)={g_low.risk}, risk(criticality=1)={g_tier1.risk}, "
        f"risk(criticality=9)={g_high.risk}, risk(criticality=4)={g_tier4.risk}",
    )


safe("DER-119", der119)


# DER-120: the wave's target is measured honestly
def der120():
    cov = Coverage(
        dataset="ds",
        covered=85,
        applicable=100,
        cde_covered=90,
        cde_applicable=100,
    )
    ok = cov.meets_target is False and cov.fraction == 0.85 and cov.cde_fraction == 0.90
    report(
        "DER-120",
        ok,
        f"fraction={cov.fraction}, cde_fraction={cov.cde_fraction}, meets_target={cov.meets_target}",
    )


safe("DER-120", der120)


# DER-121: a dataset with no attributes reports full coverage
def der121():
    ds = DatasetDeclaration(name="empty_ds", attributes=())
    cov = analyser.analyse(ds, [])
    ok = cov.fraction == 1.0 and cov.cde_fraction == 1.0 and cov.meets_target is True
    report(
        "DER-121",
        ok,
        f"fraction={cov.fraction}, cde_fraction={cov.cde_fraction}, meets_target={cov.meets_target}",
    )


safe("DER-121", der121)


# DER-122: the estate view is ordered worst-covered first
def der122():
    ds_a = DatasetDeclaration(
        name="a_dataset",
        attributes=(AttributeDeclaration(name="x", is_cde=True, optionality=Optionality.MANDATORY),),
    )
    ds_b = DatasetDeclaration(
        name="b_dataset",
        attributes=(AttributeDeclaration(name="x", is_cde=True, optionality=Optionality.MANDATORY),),
    )
    ds_c = DatasetDeclaration(
        name="c_dataset",
        attributes=(AttributeDeclaration(name="x", is_cde=False, optionality=Optionality.MANDATORY),),
    )
    controls = {
        "a_dataset": [completeness_control("a_dataset", "x")],  # fully covered
        "b_dataset": [],  # CDE uncovered -- worst
        "c_dataset": [],  # non-cde uncovered
    }
    results_tuple = analyser.analyse_estate([ds_a, ds_b, ds_c], controls)
    order = [c.dataset for c in results_tuple]
    ok = order[0] == "b_dataset"  # worst cde_fraction first
    report("DER-122", ok, f"order={order}, cde_fractions={[c.cde_fraction for c in results_tuple]}, fractions={[c.fraction for c in results_tuple]}")


safe("DER-122", der122)


# DER-123: a gap names the remedy, and the remedy fits the dimension
def der123():
    attr_with_type = AttributeDeclaration(
        name="a", semantic_type="lei", optionality=Optionality.MANDATORY
    )
    attr_no_type = AttributeDeclaration(
        name="b", value_domain=__import__("prama.semantic.values", fromlist=["ValueDomain"]).ValueDomain(kind=None) if False else None,
    )
    from prama.semantic.values import ValueDomain, ValueDomainKind

    attr_no_type = AttributeDeclaration(
        name="b",
        value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0, maximum=100),
        optionality=Optionality.MANDATORY,
    )
    attr_cons = AttributeDeclaration(
        name="c", currency_attribute="ccy", optionality=Optionality.MANDATORY
    )
    attr_acc = AttributeDeclaration(name="d", is_cde=True, optionality=Optionality.MANDATORY)
    remedy_completeness = analyser._remedy(attr_with_type, ast.Dimension.COMPLETENESS)
    remedy_validity_typed = analyser._remedy(attr_with_type, ast.Dimension.VALIDITY)
    remedy_validity_untyped = analyser._remedy(attr_no_type, ast.Dimension.VALIDITY)
    remedy_consistency = analyser._remedy(attr_cons, ast.Dimension.CONSISTENCY)
    remedy_accuracy = analyser._remedy(attr_acc, ast.Dimension.ACCURACY)
    remedies = {
        "completeness": remedy_completeness,
        "validity_typed": remedy_validity_typed,
        "validity_untyped": remedy_validity_untyped,
        "consistency": remedy_consistency,
        "accuracy": remedy_accuracy,
    }
    distinct_sentences = len({remedy_completeness, remedy_validity_untyped, remedy_consistency, remedy_accuracy})
    ok = (
        distinct_sentences == 4
        and "lei" in remedy_validity_typed
        and "lei" not in remedy_validity_untyped
    )
    report("DER-123", ok, f"remedies={remedies}")


safe("DER-123", der123)


# DER-124: worst() is deterministic under ties
def der124():
    gaps = tuple(
        Gap(dataset="ds", attribute=name, dimension=ast.Dimension.VALIDITY, criticality=2, is_cde=False)
        for name in ("zeta", "alpha", "mu", "beta")
    )
    cov = Coverage(dataset="ds", covered=0, applicable=4, cde_covered=0, cde_applicable=0, gaps=gaps)
    order1 = [g.attribute for g in cov.worst()]
    order2 = [g.attribute for g in cov.worst()]
    ok = order1 == order2 == sorted(order1)
    report("DER-124", ok, f"order1={order1}, order2={order2}, sorted={sorted(order1)}")


safe("DER-124", der124)


print("\n\nSUMMARY:")
for cid, (ok, obs) in results.items():
    print(cid, "PASS" if ok else "FAIL")
