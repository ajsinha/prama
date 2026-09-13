import dataclasses
import sys
import traceback

from prama.core.errors import ValidationError
from prama.derive.generator import Unsatisfiable
from prama.derive.relationships import (
    ComparisonKind,
    RelationshipGenerator,
    as_generation,
    generation_for,
)
from prama.pql import ast
from prama.semantic.relationships import (
    Cardinality,
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    TimeOffset,
    Tolerance,
)

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


# ---------------------------------------------------------------------------
# DER-079: REFERENCES lowers to correlated EXISTS
def der079():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.REFERENCES,
        from_dataset_id="trade",
        to_dataset_id="counterparty",
        match_keys=(MatchKey(left="cpty_id"),),
    )
    gen = generation_for(decl)
    ctrl = gen.controls[0].control
    ok = (
        isinstance(ctrl.assertion, ast.ReferenceAssertion)
        and ctrl.assertion.target_dataset == "counterparty"
        and ctrl.assertion.target_column == "cpty_id"
        and not isinstance(ctrl.assertion, ast.PredicateAssertion)
    )
    report(
        "DER-079",
        ok,
        f"controls={len(gen.controls)}, assertion_type={type(ctrl.assertion).__name__}, "
        f"target_dataset={ctrl.assertion.target_dataset}, target_column={ctrl.assertion.target_column}",
    )


safe("DER-079", der079)


# DER-080: one control per match key
def der080():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.REFERENCES,
        from_dataset_id="trade",
        to_dataset_id="counterparty",
        match_keys=(MatchKey(left="cpty_id"), MatchKey(left="book_id")),
    )
    gen = generation_for(decl)
    identities = {c.identity for c in gen.controls}
    ok = len(gen.controls) == 2 and len(identities) == 2
    report(
        "DER-080",
        ok,
        f"controls={len(gen.controls)}, identities={identities}",
    )


safe("DER-080", der080)


# DER-081: ENRICHES reuses reference mechanism
def der081():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.ENRICHES,
        from_dataset_id="trade",
        to_dataset_id="trade_enriched",
        match_keys=(MatchKey(left="trade_id"),),
    )
    gen = generation_for(decl)
    dc = gen.controls[0]
    ctrl = dc.control
    ok = (
        dc.rule == "enriches.coverage"
        and ctrl.dimensions == (ast.Dimension.COMPLETENESS,)
        and "a value that came from nowhere, which is worse than a missing one because it will be used"
        in ctrl.because
    )
    report(
        "DER-081",
        ok,
        f"rule={dc.rule}, dimensions={ctrl.dimensions}, because={ctrl.because!r}",
    )


safe("DER-081", der081)


# DER-082: PARENT_OF orphan check on child side
def der082():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.PARENT_OF,
        from_dataset_id="cost_centre",
        to_dataset_id="cost_centre_child",
        match_keys=(MatchKey(left="parent_id", right="cost_centre_id"),),
    )
    gen = generation_for(decl)
    ctrl = gen.controls[0].control
    ok = (
        ctrl.target == decl.to_dataset_id
        and ctrl.assertion.target_dataset == decl.from_dataset_id
    )
    report(
        "DER-082",
        ok,
        f"control.target={ctrl.target!r} (expect to={decl.to_dataset_id!r}), "
        f"assertion.target_dataset={ctrl.assertion.target_dataset!r} (expect from={decl.from_dataset_id!r})",
    )


safe("DER-082", der082)


# DER-083: PARENT_OF no cycle check, no Deferred
def der083():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.PARENT_OF,
        from_dataset_id="node_parent",
        to_dataset_id="node_child",
        match_keys=(MatchKey(left="parent_id", right="node_id"),),
    )
    gen = generation_for(decl)
    # No Deferred type is even produced anywhere by RelationshipGeneration (it has no
    # deferred field at all) -- confirm the dataclass fields.
    fields = set(dataclasses.fields(gen.__class__))
    field_names = {f.name for f in fields}
    has_deferred_field = "deferred" in field_names
    only_one_control = len(gen.controls) == 1 and gen.controls[0].rule == "parent_of.orphan_node"
    no_cycle_mentioned = not any(
        "cycle" in c.rule.lower() or "cycle" in c.control.because.lower() for c in gen.controls
    )
    ok = only_one_control and no_cycle_mentioned and not has_deferred_field
    report(
        "DER-083",
        ok,
        f"controls={[c.rule for c in gen.controls]}, "
        f"RelationshipGeneration fields={sorted(field_names)} (no 'deferred' field), "
        f"docstring mentions cycle: {'cycle' in RelationshipGenerator._parent_of.__doc__.lower()}",
    )


safe("DER-083", der083)


# DER-084: PARENT_OF with no match key is unsatisfiable
def der084():
    # SEM-047 permits declaring PARENT_OF with no match keys (requires_match_keys is False)
    decl = RelationshipDeclaration(
        kind=RelationshipKind.PARENT_OF,
        from_dataset_id="node_parent",
        to_dataset_id="node_child",
        match_keys=(),
    )
    gen = generation_for(decl)
    u = gen.unsatisfiable[0] if gen.unsatisfiable else None
    ok = (
        u is not None
        and u.rule == "parent_of.orphan_node"
        and "parent_id = node_id" in u.remedy
    )
    report(
        "DER-084",
        ok,
        f"declaration accepted={True}, unsatisfiable={u.to_dict() if u else None}",
    )


safe("DER-084", der084)


# DER-085: RECONCILES_WITH produces a comparison, not a control
def der085():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.RECONCILES_WITH,
        from_dataset_id="sub_ledger",
        to_dataset_id="gl",
        match_keys=(MatchKey(left="account_id"),),
        compare=("amount",),
        tolerance=Tolerance(absolute=1.0, currency="EUR"),
    )
    gen = generation_for(decl)
    comp = gen.comparisons[0] if gen.comparisons else None
    ok = (
        gen.controls == ()
        and comp is not None
        and comp.kind is ComparisonKind.RECONCILIATION
        and comp.left == "sub_ledger"
        and comp.right == "gl"
        and tuple(k.left for k in comp.match_keys) == ("account_id",)
        and comp.compare == ("amount",)
        and comp.tolerance is not None
        and comp.offset is not None or comp.offset is None  # offset optional
        and comp.cardinality is not None
        and comp.workflow != ""
        and "classified" in comp.workflow
    )
    report(
        "DER-085",
        ok,
        f"controls={gen.controls}, comparisons_count={len(gen.comparisons)}, "
        f"kind={comp.kind if comp else None}, workflow={comp.workflow if comp else None}",
    )


safe("DER-085", der085)


# DER-086: reconciliation declaration produces nothing on control-only path
def der086():
    import subprocess

    grep = subprocess.run(
        ["grep", "-rn", "RelationshipGenerator", "src/prama/"],
        cwd="/home/ashutosh/PycharmProjects/prama",
        capture_output=True,
        text=True,
    )
    hits = [
        line
        for line in grep.stdout.splitlines()
        if "derive/relationships.py" not in line and "derive/__init__.py" not in line
    ]
    # also confirm proposal_routes only imports ControlGenerator
    with open(
        "/home/ashutosh/PycharmProjects/prama/src/prama/web/routes/proposal_routes.py"
    ) as f:
        text = f.read()
    ok = (
        "from prama.derive import ControlGenerator" in text
        and "RelationshipGenerator" not in text
        and hits == []
    )
    report(
        "DER-086",
        ok,
        f"proposal_routes.py imports ControlGenerator only: "
        f"{'from prama.derive import ControlGenerator' in text}; "
        f"RelationshipGenerator referenced in proposal_routes.py: {'RelationshipGenerator' in text}; "
        f"other references to RelationshipGenerator outside its own module: {hits}",
    )


safe("DER-086", der086)


# DER-087: DERIVES_FROM and AGGREGATES both produce aggregate parity, different rule strings
def der087():
    decl1 = RelationshipDeclaration(
        kind=RelationshipKind.DERIVES_FROM,
        from_dataset_id="report_total",
        to_dataset_id="ledger_detail",
        match_keys=(MatchKey(left="account_id"),),
        compare=("amount",),
        tolerance=Tolerance(absolute=1.0),
    )
    decl2 = RelationshipDeclaration(
        kind=RelationshipKind.AGGREGATES,
        from_dataset_id="summary",
        to_dataset_id="detail",
        match_keys=(MatchKey(left="account_id"),),
        compare=("amount",),
        tolerance=Tolerance(absolute=1.0),
    )
    gen1 = generation_for(decl1)
    gen2 = generation_for(decl2)
    c1 = gen1.comparisons[0]
    c2 = gen2.comparisons[0]
    ok = (
        c1.kind is ComparisonKind.AGGREGATE_PARITY
        and c2.kind is ComparisonKind.AGGREGATE_PARITY
        and c1.rule == "derives_from.aggregate_parity"
        and c2.rule == "aggregates.rollup_parity"
        and c1.rule != c2.rule
    )
    report(
        "DER-087",
        ok,
        f"c1.kind={c1.kind}, c1.rule={c1.rule}, c2.kind={c2.kind}, c2.rule={c2.rule}",
    )


safe("DER-087", der087)


# DER-088: MIRRORS produces three comparisons
def der088():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="replica",
        to_dataset_id="source",
        match_keys=(MatchKey(left="id"),),
        compare=("amount",),
    )
    gen = generation_for(decl)
    kinds = {c.kind for c in gen.comparisons}
    ok = kinds == {
        ComparisonKind.ROW_COUNT_PARITY,
        ComparisonKind.VALUE_PARITY,
        ComparisonKind.STALENESS,
    }
    report("DER-088", ok, f"comparisons={len(gen.comparisons)}, kinds={kinds}")


safe("DER-088", der088)


# DER-089: MIRRORS content parity demands no tolerance
def der089():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="replica",
        to_dataset_id="source",
        match_keys=(MatchKey(left="id"),),
        compare=("amount",),
        tolerance=None,
    )
    gen = generation_for(decl)
    value_parity = gen.comparison(ComparisonKind.VALUE_PARITY)
    ok = value_parity is not None and value_parity.tolerance is None
    report(
        "DER-089",
        ok,
        f"value_parity present={value_parity is not None}, tolerance={value_parity.tolerance if value_parity else 'N/A'}, "
        f"unsatisfiable={gen.unsatisfiable}",
    )


safe("DER-089", der089)


# DER-090: MIRRORS with no compared attribute produces two comparisons
def der090():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="replica",
        to_dataset_id="source",
        match_keys=(MatchKey(left="id"),),
        compare=(),
    )
    gen = generation_for(decl)
    kinds = {c.kind for c in gen.comparisons}
    ok = (
        kinds == {ComparisonKind.ROW_COUNT_PARITY, ComparisonKind.STALENESS}
        and gen.unsatisfiable == ()
    )
    report(
        "DER-090",
        ok,
        f"comparisons={len(gen.comparisons)}, kinds={kinds}, unsatisfiable={gen.unsatisfiable}",
    )


safe("DER-090", der090)


# DER-091: SUPERSEDES produces dual-run comparison with workflow
def der091():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.SUPERSEDES,
        from_dataset_id="old_system",
        to_dataset_id="new_system",
        match_keys=(MatchKey(left="id"),),
        compare=("amount",),
        tolerance=Tolerance(absolute=1.0),
    )
    gen = generation_for(decl)
    comp = gen.comparisons[0] if gen.comparisons else None
    ok = (
        comp is not None
        and comp.kind is ComparisonKind.VALUE_PARITY
        and "run both" in comp.workflow
        and "old system is still authoritative" in comp.workflow
    )
    report(
        "DER-091",
        ok,
        f"comparisons={len(gen.comparisons)}, kind={comp.kind if comp else None}, workflow={comp.workflow if comp else None}",
    )


safe("DER-091", der091)


# DER-092: SUPERSEDES with no keys is unsatisfiable
def der092():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.SUPERSEDES,
        from_dataset_id="old_system",
        to_dataset_id="new_system",
        match_keys=(),
        compare=("amount",),
        tolerance=Tolerance(absolute=1.0),
    )
    gen = generation_for(decl)
    u = gen.unsatisfiable[0] if gen.unsatisfiable else None
    ok = u is not None and u.reason == "no match key joins the two datasets"
    report("DER-092", ok, f"unsatisfiable={u.to_dict() if u else None}")


safe("DER-092", der092)


# DER-093: SAME_ENTITY_AS produces identifier consistency
def der093():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.SAME_ENTITY_AS,
        from_dataset_id="party_a",
        to_dataset_id="party_b",
        match_keys=(MatchKey(left="tax_id"),),
        compare=("lei",),
    )
    gen = generation_for(decl)
    comp = gen.comparisons[0] if gen.comparisons else None
    sentence = comp.describe() if comp else ""
    ok = (
        comp is not None
        and comp.kind is ComparisonKind.IDENTIFIER_CONSISTENCY
        and "where party_a and party_b describe the same thing, matched on tax_id, they carry the same lei"
        in sentence
    )
    report("DER-093", ok, f"kind={comp.kind if comp else None}, sentence={sentence!r}")


safe("DER-093", der093)


# DER-094: TEMPORAL_SUCCESSOR needs tolerance Gamma demands, declaration does not
def der094():
    # SEM-046 permits TEMPORAL_SUCCESSOR without tolerance at declaration
    decl = RelationshipDeclaration(
        kind=RelationshipKind.TEMPORAL_SUCCESSOR,
        from_dataset_id="period_open",
        to_dataset_id="period_close",
        match_keys=(MatchKey(left="account_id"),),
        compare=("balance",),
        tolerance=None,
    )
    gen = generation_for(decl)
    u = gen.unsatisfiable[0] if gen.unsatisfiable else None
    ok = u is not None and u.reason == "no materiality tolerance was given"
    report(
        "DER-094",
        ok,
        f"declaration accepted with tolerance=None: True; unsatisfiable={u.to_dict() if u else None}",
    )


safe("DER-094", der094)


# DER-095: roll-forward sentence names opening, movements, closing
def der095():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.TEMPORAL_SUCCESSOR,
        from_dataset_id="period_open",
        to_dataset_id="period_close",
        match_keys=(MatchKey(left="account_id"),),
        compare=("balance",),
        tolerance=Tolerance(absolute=1.0),
    )
    gen = generation_for(decl)
    comp = gen.comparisons[0]
    sentence = comp.describe()
    ok = (
        "the opening balance in period_open plus the movements equals the closing balance in period_close"
        in sentence
    )
    report("DER-095", ok, f"sentence={sentence!r}")


safe("DER-095", der095)


# DER-096: MUTUALLY_EXCLUSIVE produces overlap detection with no tolerance
def der096():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.MUTUALLY_EXCLUSIVE,
        from_dataset_id="active_accounts",
        to_dataset_id="closed_accounts",
        match_keys=(MatchKey(left="account_id"),),
    )
    gen = generation_for(decl)
    comp = gen.comparisons[0] if gen.comparisons else None
    ok = (
        comp is not None
        and comp.kind is ComparisonKind.OVERLAP
        and comp.tolerance is None
        and comp.compare == ()
        and gen.unsatisfiable == ()
    )
    report(
        "DER-096",
        ok,
        f"kind={comp.kind if comp else None}, tolerance={comp.tolerance if comp else None}, "
        f"compare={comp.compare if comp else None}, unsatisfiable={gen.unsatisfiable}",
    )


safe("DER-096", der096)


# DER-097: TOGETHER_COMPLETE produces population coverage
def der097():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.TOGETHER_COMPLETE,
        from_dataset_id="onshore_accounts",
        to_dataset_id="offshore_accounts",
        match_keys=(MatchKey(left="account_id"),),
    )
    gen = generation_for(decl)
    comp = gen.comparisons[0] if gen.comparisons else None
    sentence = comp.describe() if comp else ""
    ok = comp is not None and comp.kind is ComparisonKind.COVERAGE and "the population" in sentence
    report("DER-097", ok, f"kind={comp.kind if comp else None}, sentence={sentence!r}")


safe("DER-097", der097)


# DER-098: FEEDS produces edge and deliberately no check
def der098():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.FEEDS,
        from_dataset_id="upstream_feed",
        to_dataset_id="downstream_table",
    )
    gen = generation_for(decl)
    ok = (
        gen.controls == ()
        and gen.comparisons == ()
        and len(gen.edges) == 1
        and gen.edges[0].carries_trust is True
    )
    report(
        "DER-098",
        ok,
        f"controls={gen.controls}, comparisons={gen.comparisons}, edges={gen.edges}",
    )


safe("DER-098", der098)


# DER-099: every kind produces exactly one edge
def der099():
    minimal = {
        RelationshipKind.REFERENCES: dict(match_keys=(MatchKey(left="id"),)),
        RelationshipKind.RECONCILES_WITH: dict(
            match_keys=(MatchKey(left="id"),),
            compare=("amount",),
            tolerance=Tolerance(absolute=1.0),
        ),
        RelationshipKind.DERIVES_FROM: dict(
            match_keys=(MatchKey(left="id"),),
            compare=("amount",),
            tolerance=Tolerance(absolute=1.0),
        ),
        RelationshipKind.FEEDS: dict(),
        RelationshipKind.MIRRORS: dict(match_keys=(MatchKey(left="id"),)),
        RelationshipKind.AGGREGATES: dict(
            match_keys=(MatchKey(left="id"),),
            compare=("amount",),
            tolerance=Tolerance(absolute=1.0),
        ),
        RelationshipKind.ENRICHES: dict(match_keys=(MatchKey(left="id"),)),
        RelationshipKind.SUPERSEDES: dict(),
        RelationshipKind.SAME_ENTITY_AS: dict(
            match_keys=(MatchKey(left="id"),), compare=("lei",)
        ),
        RelationshipKind.TEMPORAL_SUCCESSOR: dict(match_keys=(MatchKey(left="id"),)),
        RelationshipKind.PARENT_OF: dict(match_keys=(MatchKey(left="parent_id"),)),
        RelationshipKind.MUTUALLY_EXCLUSIVE: dict(match_keys=(MatchKey(left="id"),)),
        RelationshipKind.TOGETHER_COMPLETE: dict(match_keys=(MatchKey(left="id"),)),
    }
    all_ok = True
    details = []
    for kind, kwargs in minimal.items():
        decl = RelationshipDeclaration(
            kind=kind, from_dataset_id="left_ds", to_dataset_id="right_ds", **kwargs
        )
        gen = generation_for(decl)
        n_edges = len(gen.edges)
        edge = gen.edges[0] if gen.edges else None
        # The reason is two sentences: "{from} -> {to} (kind): {prompt}." then the
        # capitalised "why" sentence. Check the *ending* sentence starts with a capital.
        last_sentence = edge.reason.rsplit(". ", 1)[-1] if edge else ""
        ends_with_capital_sentence = bool(last_sentence) and last_sentence[:1].isupper()
        ok_kind = (
            n_edges == 1
            and edge.source == "left_ds"
            and edge.target == "right_ds"
            and ends_with_capital_sentence
        )
        details.append(
            f"{kind.value}: edges={n_edges}, "
            f"src/tgt ok={edge.source == 'left_ds' and edge.target == 'right_ds' if edge else False}, "
            f"ends_with_capital_sentence={ends_with_capital_sentence} (last_sentence={last_sentence!r})"
        )
        all_ok = all_ok and ok_kind
    report("DER-099", all_ok, f"13 kinds tested: " + "; ".join(details))


safe("DER-099", der099)


# DER-100: edge produced even when generation is unsatisfiable
def der100():
    # Literal precondition from the catalogue: "a RECONCILES_WITH with no tolerance".
    declaration_error = None
    try:
        RelationshipDeclaration(
            kind=RelationshipKind.RECONCILES_WITH,
            from_dataset_id="sub_ledger",
            to_dataset_id="gl",
            match_keys=(MatchKey(left="account_id"),),
            compare=("amount",),
            tolerance=None,
        )
    except ValidationError as exc:
        declaration_error = str(exc)

    # RECONCILES_WITH.requires_tolerance is True, so the declaration layer itself
    # refuses construction before Gamma is ever reached -- confirm by bypassing
    # __post_init__ (object.__new__) to see what Gamma alone would do with such
    # an object, e.g. one persisted before this validation existed.
    bypassed = object.__new__(RelationshipDeclaration)
    for field, value in dict(
        kind=RelationshipKind.RECONCILES_WITH,
        from_dataset_id="sub_ledger",
        to_dataset_id="gl",
        match_keys=(MatchKey(left="account_id"),),
        compare=("amount",),
        cardinality=Cardinality.MANY_TO_MANY,
        tolerance=None,
        offset=None,
        filter_expression=None,
        name="",
        description="",
    ).items():
        object.__setattr__(bypassed, field, value)
    gen = generation_for(bypassed)
    gamma_ok = len(gen.unsatisfiable) == 1 and len(gen.edges) == 1

    ok = declaration_error is None and len(gen.unsatisfiable) == 1 and len(gen.edges) == 1
    report(
        "DER-100",
        ok,
        f"constructing RelationshipDeclaration(RECONCILES_WITH, tolerance=None) via the public "
        f"constructor raises: {declaration_error!r} (so 'generate' step in the catalogue's Steps "
        f"can never be reached this way); bypassing __post_init__ to hand such an object straight "
        f"to Gamma: unsatisfiable_count={len(gen.unsatisfiable)}, edges_count={len(gen.edges)} "
        f"(Gamma's own merge-unconditionally behaviour is correct: gamma_ok={gamma_ok})",
    )


safe("DER-100", der100)


# DER-101: comparison with nothing to compare is refused, for each kind whose
# needs_compared_attributes is true and can be declared with compare=()
def der101():
    cases = []
    # DERIVES_FROM
    decl = RelationshipDeclaration(
        kind=RelationshipKind.DERIVES_FROM,
        from_dataset_id="a",
        to_dataset_id="b",
        match_keys=(MatchKey(left="id"),),
        compare=(),
        tolerance=Tolerance(absolute=1.0),
    )
    gen = generation_for(decl)
    cases.append(("DERIVES_FROM", gen.unsatisfiable))

    # AGGREGATES
    decl = RelationshipDeclaration(
        kind=RelationshipKind.AGGREGATES,
        from_dataset_id="a",
        to_dataset_id="b",
        match_keys=(MatchKey(left="id"),),
        compare=(),
        tolerance=Tolerance(absolute=1.0),
    )
    gen = generation_for(decl)
    cases.append(("AGGREGATES", gen.unsatisfiable))

    # SAME_ENTITY_AS
    decl = RelationshipDeclaration(
        kind=RelationshipKind.SAME_ENTITY_AS,
        from_dataset_id="a",
        to_dataset_id="b",
        match_keys=(MatchKey(left="id"),),
        compare=(),
    )
    gen = generation_for(decl)
    cases.append(("SAME_ENTITY_AS", gen.unsatisfiable))

    # RECONCILES_WITH: declaration validation itself refuses compare=() before Gamma
    recon_declaration_error = None
    try:
        RelationshipDeclaration(
            kind=RelationshipKind.RECONCILES_WITH,
            from_dataset_id="a",
            to_dataset_id="b",
            match_keys=(MatchKey(left="id"),),
            compare=(),
            tolerance=Tolerance(absolute=1.0),
        )
    except ValidationError as exc:
        recon_declaration_error = str(exc)

    ok = all(
        len(u) == 1
        and u[0].reason == "no attribute was named to compare"
        and "reports a clean result over any two datasets at all" in u[0].remedy
        for _, u in cases
    )
    report(
        "DER-101",
        ok,
        f"results={[(name, u[0].reason if u else None) for name, u in cases]}; "
        f"RECONCILES_WITH blocked at declaration (ValidationError): {recon_declaration_error!r}",
    )


safe("DER-101", der101)


# DER-102: three refusals checked in fixed order
def der102():
    # SUPERSEDES is the kind that permits all three (keys, compare, tolerance)
    # to be simultaneously absent at declaration time (requires_match_keys and
    # requires_tolerance are both False for it, and the explicit "needs compare"
    # check in RelationshipDeclaration.__post_init__ only applies to
    # RECONCILES_WITH) -- so this is the case that actually reaches Gamma with
    # all three gaps at once.
    decl = RelationshipDeclaration(
        kind=RelationshipKind.SUPERSEDES,
        from_dataset_id="a",
        to_dataset_id="b",
        match_keys=(),
        compare=(),
        tolerance=None,
    )
    gen = generation_for(decl)
    ok = (
        len(gen.unsatisfiable) == 1
        and gen.unsatisfiable[0].reason == "no attribute was named to compare"
    )
    report(
        "DER-102",
        ok,
        f"unsatisfiable_count={len(gen.unsatisfiable)}, reason={gen.unsatisfiable[0].reason if gen.unsatisfiable else None}",
    )


safe("DER-102", der102)


# DER-103: comparison renders a canonical diffable line
def der103():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.RECONCILES_WITH,
        from_dataset_id="sub_ledger",
        to_dataset_id="gl",
        match_keys=(MatchKey(left="account_id"),),
        compare=("amount",),
        tolerance=Tolerance(absolute=1.0, relative=0.001, currency="EUR"),
    )
    gen = generation_for(decl)
    comp = gen.comparisons[0]
    line1 = comp.render()
    line2 = comp.render()
    hash1 = comp.content_hash

    comp2 = dataclasses.replace(comp, tolerance=Tolerance(absolute=2.0, currency="EUR"))
    line3 = comp2.render()
    hash2 = comp2.content_hash

    ok = (
        line1 == line2
        and line1.startswith("COMPARE sub_ledger WITH gl ON (account_id)")
        and "MATCHING amount" in line1
        and "WITHIN" in line1
        and "AS RECONCILIATION" in line1
        and line1 != line3
        and hash1 != hash2
    )
    report(
        "DER-103",
        ok,
        f"line1={line1!r}, line1==line2: {line1 == line2}, line3(after tolerance change)={line3!r}, "
        f"hash1={hash1}, hash2={hash2}, hashes_differ={hash1 != hash2}",
    )


safe("DER-103", der103)


# DER-104: only kinds that need them carry compared attributes
def der104():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.MUTUALLY_EXCLUSIVE,
        from_dataset_id="a",
        to_dataset_id="b",
        match_keys=(MatchKey(left="id"),),
        compare=("amount",),
    )
    gen = generation_for(decl)
    comp = gen.comparisons[0]
    ok = comp.compare == ()
    report("DER-104", ok, f"declared compare=('amount',), spec.compare={comp.compare!r}")


safe("DER-104", der104)


# DER-105: comparison severity is passed in, not guessed
def der105():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.RECONCILES_WITH,
        from_dataset_id="a",
        to_dataset_id="b",
        match_keys=(MatchKey(left="id"),),
        compare=("amount",),
        tolerance=Tolerance(absolute=1.0),
    )
    gen_default = generation_for(decl)
    gen_critical = generation_for(decl, severity=ast.Severity.CRITICAL)
    ok = (
        gen_default.comparisons[0].severity is ast.Severity.MAJOR
        and gen_critical.comparisons[0].severity is ast.Severity.CRITICAL
    )
    report(
        "DER-105",
        ok,
        f"default_severity={gen_default.comparisons[0].severity}, "
        f"caller_supplied_severity={gen_critical.comparisons[0].severity}",
    )


safe("DER-105", der105)


# DER-106: comparison identity stable and distinct per rule
def der106():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="replica",
        to_dataset_id="source",
        match_keys=(MatchKey(left="id"),),
        compare=("amount",),
    )
    gen1 = generation_for(decl)
    gen2 = generation_for(decl)
    ids1 = {c.rule: c.identity for c in gen1.comparisons}
    ids2 = {c.rule: c.identity for c in gen2.comparisons}
    ok = len(set(ids1.values())) == 3 and ids1 == ids2
    report(
        "DER-106",
        ok,
        f"run1 identities={ids1}, run2 identities={ids2}, distinct_count={len(set(ids1.values()))}, stable={ids1 == ids2}",
    )


safe("DER-106", der106)


# DER-107: unnamed relationship falls back to kind for identity
def der107():
    decl_pair1 = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="replica_a",
        to_dataset_id="source_a",
        match_keys=(MatchKey(left="id"),),
    )
    decl_pair2 = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="replica_b",
        to_dataset_id="source_b",
        match_keys=(MatchKey(left="id"),),
    )
    gen1 = generation_for(decl_pair1)
    gen2 = generation_for(decl_pair2)
    rcp1 = gen1.comparison(ComparisonKind.ROW_COUNT_PARITY)
    rcp2 = gen2.comparison(ComparisonKind.ROW_COUNT_PARITY)
    distinct_pairs = rcp1.identity != rcp2.identity

    # two unnamed relationships of the SAME kind between the SAME pair
    decl_a = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="replica_c",
        to_dataset_id="source_c",
        match_keys=(MatchKey(left="id"),),
        compare=("amount",),
    )
    decl_b = RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="replica_c",
        to_dataset_id="source_c",
        match_keys=(MatchKey(left="id"),),
        compare=("quantity",),
    )
    gen_a = generation_for(decl_a)
    gen_b = generation_for(decl_b)
    rcp_a = gen_a.comparison(ComparisonKind.ROW_COUNT_PARITY)
    rcp_b = gen_b.comparison(ComparisonKind.ROW_COUNT_PARITY)
    same_pair_collide = rcp_a.identity == rcp_b.identity

    ok = distinct_pairs and same_pair_collide
    report(
        "DER-107",
        ok,
        f"different_pairs_distinct: {distinct_pairs} (id1={rcp1.identity}, id2={rcp2.identity}); "
        f"same_pair_same_kind_collide: {same_pair_collide} (idA={rcp_a.identity}, idB={rcp_b.identity})",
    )


safe("DER-107", der107)

print("\n\nSUMMARY:")
for cid, (ok, obs) in results.items():
    print(cid, "PASS" if ok else "FAIL")
