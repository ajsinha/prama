"""QA harness for PRP-001..067 (propose/ and learn/)."""
from __future__ import annotations

import dataclasses
import math
import sys

sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

RESULTS: list[tuple[str, str, str]] = []


def record(case_id: str, ok: bool, observed: str) -> None:
    RESULTS.append((case_id, "PASS" if ok else "FAIL", observed))


def run(case_id: str, fn):
    try:
        ok, observed = fn()
        record(case_id, ok, observed)
    except Exception as exc:  # noqa: BLE001
        record(case_id, False, f"EXCEPTION: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from prama.core.provenance import Citation, Corroboration, Origin, Provenance, content_hash, identity
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.derive.generator import ControlGenerator, DerivedControl, Generation
from prama.derive.relationships import (
    ComparisonKind,
    ComparisonSpec,
    RelationshipGeneration,
    RelationshipGenerator,
    generation_for,
)
from prama.pql import ast
from prama.propose.adapt import from_comparison, from_control, from_generation, from_relationship
from prama.propose.proposal import (
    Backtest,
    Decision,
    Proposal,
    ProposalStatus,
    RejectionReason,
)
from prama.propose.queue import Admission, ProposalQueue, Suppression, suppression_from
from prama.propose.utility import (
    NOT_THE_RULES_FAULT,
    PRIOR_CEILING,
    WEIGHTS,
    AcceptanceHistory,
    Context,
    UtilityScorer,
    indicted_rules,
    rank,
)
from prama.semantic.relationships import (
    Cardinality,
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)
from prama.semantic.values import (
    Criticality,
    Frequency,
    Grain,
    Optionality,
    Rhythm,
    ValueDomain,
    ValueDomainKind,
)

NOW = "2026-09-08T10:00:00Z"


def positions() -> DatasetDeclaration:
    return DatasetDeclaration(
        name="positions",
        slug="pos",
        criticality=Criticality.TIER_1,
        declared_by="a.sinha",
        declared_at="2026-03-04T09:12:00Z",
        reference="DS01",
        grain=Grain(
            attributes=("account_id", "business_date"),
            statement="one position per account per business day",
        ),
        rhythm=Rhythm(
            frequency=Frequency.DAILY,
            arrival_by="06:30",
            calendar="TARGET2",
            lateness_tolerance_seconds=900,
            expected_volume_min=10_000,
            expected_volume_max=90_000,
        ),
        attributes=(
            AttributeDeclaration(name="account_id", optionality=Optionality.MANDATORY),
            AttributeDeclaration(name="business_date", optionality=Optionality.MANDATORY),
            AttributeDeclaration(
                name="counterparty_lei",
                semantic_type="lei",
                is_cde=True,
                obligations=("FR Y-14Q",),
                optionality=Optionality.MANDATORY,
            ),
            AttributeDeclaration(
                name="market_value",
                currency_attribute="settlement_ccy",
                value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0),
            ),
            AttributeDeclaration(name="settlement_ccy"),
        ),
    )


def holdings() -> RelationshipDeclaration:
    return RelationshipDeclaration(
        kind=RelationshipKind.REFERENCES,
        from_dataset_id="positions",
        to_dataset_id="accounts",
        match_keys=(MatchKey("account_id"),),
        name="REL01",
    )


def mirrors_decl() -> RelationshipDeclaration:
    return RelationshipDeclaration(
        kind=RelationshipKind.MIRRORS,
        from_dataset_id="positions",
        to_dataset_id="positions_replica",
        match_keys=(MatchKey("account_id"),),
        compare=("market_value",),
        name="MIR01",
    )


def q_proposal(
    identity_: str = "P1",
    *,
    origin: Origin = Origin.MINING,
    content: str = "CHECK t.x IS NOT NULL",
    rule: str = "mine.not_null",
    backtest: Backtest | None = None,
    dataset: str = "t",
) -> Proposal:
    return Proposal(
        identity=identity_,
        content=content,
        content_hash=f"h:{content}",
        provenance=Provenance(origin=origin, rule=rule, statement="x is never null"),
        description="every x has a value",
        dataset=dataset,
        subject="x",
        rule=rule,
        backtest=backtest,
    )


def u_proposal(
    identity_: str = "P1",
    *,
    origin: Origin = Origin.MINING,
    rule: str = "mine.not_null",
    dataset: str = "t",
    backtest: Backtest | None = None,
) -> Proposal:
    return Proposal(
        identity=identity_,
        content=f"CHECK {dataset}.x IS NOT NULL",
        content_hash=identity_,
        provenance=Provenance(origin=origin, rule=rule),
        description="every x has a value",
        dataset=dataset,
        subject="x",
        rule=rule,
        backtest=backtest,
    )


GEN_POS = ControlGenerator().generate(positions())
GEN_REL = generation_for(holdings())


# ===========================================================================
# PRP-001..004 : adapt.py
# ===========================================================================


def prp001():
    control = GEN_POS.controls[0]
    p = from_control(control)
    checks = {
        "identity": p.identity == control.identity,
        "content": p.content == control.content,
        "content_hash": p.content_hash == control.content_hash,
        "provenance": p.provenance == control.provenance,
        "description": p.description == control.control.describe(),
        "dataset": p.dataset == control.control.target,
        "rule": p.rule == control.rule,
        "severity": p.severity == control.control.severity.value,
    }
    ok = all(checks.values())
    return ok, f"control.rule={control.rule!r}; checks={checks}; subject={p.subject!r}"


def prp002():
    decl = RelationshipDeclaration(
        kind=RelationshipKind.RECONCILES_WITH,
        from_dataset_id="subledger",
        to_dataset_id="gl",
        match_keys=(MatchKey("account_id"),),
        compare=("amount",),
        tolerance=Tolerance(absolute=1.0),
    )
    gen = generation_for(decl)
    spec = gen.comparison(ComparisonKind.RECONCILIATION)
    assert spec is not None
    p1 = from_comparison(spec)
    ok1 = p1.content == spec.render() and p1.content.startswith("COMPARE ")
    ok2 = p1.subject == ", ".join(spec.compare)
    # no-compare case: subject should fall back to right-hand dataset
    spec2 = dataclasses.replace(spec, compare=())
    p2 = from_comparison(spec2)
    ok3 = p2.subject == spec2.right
    ok = ok1 and ok2 and ok3
    return ok, (
        f"p1.content={p1.content!r}; p1.subject={p1.subject!r}; "
        f"p2.subject(no-compare)={p2.subject!r} right={spec2.right!r}"
    )


def prp003():
    # predicate assertion -> subject from `subject`
    predicate_control = next(
        c for c in GEN_POS.controls if isinstance(c.control.assertion, ast.PredicateAssertion)
    )
    p_pred = from_control(predicate_control)
    subj_from_subject = p_pred.subject != ""

    # reference assertion -> subject from `column`
    ref_control = next(
        c for c in GEN_REL.controls if isinstance(c.control.assertion, ast.ReferenceAssertion)
    )
    p_ref = from_control(ref_control)
    subj_from_column = p_ref.subject == ref_control.control.assertion.column.name

    # unique-key assertion -> falls through to ""
    key_control = next(
        c for c in GEN_POS.controls if isinstance(c.control.assertion, ast.UniqueKeyAssertion)
    )
    p_key = from_control(key_control)
    key_empty = p_key.subject == ""

    ok = subj_from_subject and subj_from_column and key_empty
    return ok, (
        f"predicate.subject={p_pred.subject!r}; reference.subject={p_ref.subject!r} "
        f"(expected {ref_control.control.assertion.column.name!r}); "
        f"unique_key.subject={p_key.subject!r}"
    )


def prp004():
    gen = generation_for(mirrors_decl())
    ok_shape = len(gen.controls) == 0 and len(gen.comparisons) == 3
    proposals = from_relationship(gen)
    ok = ok_shape and len(proposals) == 3
    return ok, (
        f"controls={len(gen.controls)}, comparisons={len(gen.comparisons)}, "
        f"kinds={[c.kind.value for c in gen.comparisons]}, proposals={len(proposals)}"
    )


run("PRP-001", prp001)
run("PRP-002", prp002)
run("PRP-003", prp003)
run("PRP-004", prp004)


# ===========================================================================
# PRP-005..015 : proposal.py + provenance.py
# ===========================================================================


def prp005():
    try:
        Decision(status=ProposalStatus.REJECTED, decided_by="a", decided_at=NOW, reason=None)
        return False, "no exception raised"
    except ValueError as exc:
        return True, f"ValueError: {exc}"


def prp006():
    expected_true = {RejectionReason.INCORRECT, RejectionReason.COINCIDENTAL}
    actual_true = {r for r in RejectionReason if r.indicts_the_rule}
    ok = actual_true == expected_true
    return ok, f"indicts_the_rule True for: {sorted(r.value for r in actual_true)}"


def prp007():
    expected_true = {
        RejectionReason.NOT_MATERIAL,
        RejectionReason.TOO_NOISY,
        RejectionReason.PENDING_REMEDIATION,
    }
    actual_true = {r for r in RejectionReason if r.may_be_reconsidered}
    ok = actual_true == expected_true
    return ok, f"may_be_reconsidered True for: {sorted(r.value for r in actual_true)}"


def prp008():
    bt = Backtest(scanned=1000, violations=410, days=30, affected_segments=("EMEA", "APAC"))
    desc = bt.describe()
    ok = (
        "410" in desc
        and "1,000" in desc
        and "41.00%" in desc
        and "14 a day" in desc
        and "EMEA" in desc
        and "APAC" in desc
    )
    return ok, f"describe()={desc!r}; violation_rate={bt.violation_rate}; alerts_per_day={bt.alerts_per_day}"


def prp009():
    a = Backtest(scanned=1000, violations=200)  # 0.20
    b = Backtest(scanned=1000, violations=210)  # 0.21
    ok = (a.is_unactionable is False) and (b.is_unactionable is True)
    return ok, f"a.rate={a.violation_rate}, a.is_unactionable={a.is_unactionable}; b.rate={b.violation_rate}, b.is_unactionable={b.is_unactionable}"


def prp010():
    unavailable_bt = Backtest(scanned=0, violations=0, unavailable="the column does not exist in retained snapshots")
    zero_bt = Backtest(scanned=0, violations=0)
    ok = (
        unavailable_bt.ran is False
        and zero_bt.ran is False
        and unavailable_bt.would_pass_today is False
        and zero_bt.would_pass_today is False
        and unavailable_bt.is_unactionable is False
        and zero_bt.is_unactionable is False
        and unavailable_bt.describe() != zero_bt.describe()
    )
    return ok, (
        f"unavailable.describe()={unavailable_bt.describe()!r}; zero.describe()={zero_bt.describe()!r}; "
        f"unavailable.ran={unavailable_bt.ran}; zero.ran={zero_bt.ran}"
    )


def prp011():
    bt = Backtest(scanned=100, violations=5, days=0)
    ok = bt.alerts_per_day == 5.0
    return ok, f"alerts_per_day={bt.alerts_per_day}"


def prp012():
    results = {}
    for origin in Origin:
        prov = Provenance(
            origin=origin,
            rule="r",
            citation=Citation(document="d", quote="q") if origin is Origin.DOCUMENT else None,
        )
        p = Proposal(
            identity="i",
            content="c",
            content_hash="h",
            provenance=prov,
            description="d",
        )
        results[origin.value] = p.needs_review
    expected = {o.value: (o is not Origin.DECLARATION) for o in Origin}
    ok = results == expected
    return ok, f"needs_review by origin: {results}"


def prp013():
    prov = Provenance(origin=Origin.DECLARATION, rule="r")
    bt = Backtest(scanned=1000, violations=410)  # 41%
    p = Proposal(
        identity="i", content="c", content_hash="h", provenance=prov, description="d", backtest=bt
    )
    ok = p.needs_review is True
    return ok, f"backtest.is_unactionable={bt.is_unactionable}; needs_review={p.needs_review}"


def prp014():
    expected_order = [
        (Origin.DECLARATION, 100),
        (Origin.DOCUMENT, 80),
        (Origin.IMPORT, 60),
        (Origin.MINING, 40),
        (Origin.EXAMPLE, 30),
        (Origin.INDUCTION, 20),
    ]
    actual = [(o, o.authority) for o in expected_order_keys(expected_order)]
    ok_values = all(o.authority == v for o, v in expected_order)
    authorities = [o.authority for o, _ in expected_order]
    no_ties = len(set(authorities)) == len(authorities)
    ok = ok_values and no_ties
    return ok, f"authorities={[(o.value, o.authority) for o, _ in expected_order]}"


def expected_order_keys(pairs):
    return [o for o, _ in pairs]


def prp015():
    try:
        Provenance(origin=Origin.DOCUMENT, rule="r", citation=None)
        return False, "no exception raised"
    except ValueError as exc:
        return True, f"ValueError: {exc}"


run("PRP-005", prp005)
run("PRP-006", prp006)
run("PRP-007", prp007)
run("PRP-008", prp008)
run("PRP-009", prp009)
run("PRP-010", prp010)
run("PRP-011", prp011)
run("PRP-012", prp012)
run("PRP-013", prp013)
run("PRP-014", prp014)
run("PRP-015", prp015)


# ===========================================================================
# PRP-016..034 : queue.py
# ===========================================================================


def prp016():
    queue = ProposalQueue()
    p = q_proposal()
    queue.register_existing(p.identity, p.content_hash)
    admission = queue.offer(p)
    ok = admission.outcome == "already_live" and admission.proposal is None and not admission.admitted
    return ok, f"outcome={admission.outcome!r}, proposal={admission.proposal}, admitted={admission.admitted}"


def prp017():
    queue = ProposalQueue()
    queue.register_existing("P1", "h:old-content")
    p = q_proposal()
    admission = queue.offer(p)
    ok = (
        admission.outcome == "superseded"
        and admission.proposal is not None
        and admission.proposal.supersedes == "h:old-content"
        and "replaces rather than adds" in admission.detail
    )
    return ok, f"outcome={admission.outcome!r}, supersedes={admission.proposal.supersedes!r}, detail={admission.detail!r}"


def prp018():
    queue = ProposalQueue()
    bt = Backtest(scanned=1000, violations=30)  # 3%
    queue.offer(q_proposal(backtest=bt))
    queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)
    again = queue.offer(q_proposal(backtest=bt))
    ok = (
        not again.admitted
        and again.outcome == "suppressed"
        and RejectionReason.NOT_MATERIAL.value in again.detail
        and "a.sinha" in again.detail
        and NOW[:10] in again.detail
    )
    return ok, f"outcome={again.outcome!r}, detail={again.detail!r}"


def prp019():
    # Literal sequential execution -- no manual re-rejection between steps.
    queue = ProposalQueue()
    queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=30)))  # 3%
    queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)

    a = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=59)))  # 5.9%
    ok_a = a.outcome == "suppressed"
    b = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=60)))  # 6.0%
    ok_b = b.outcome == "reopened"
    c = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=400)))  # 40%
    ok_c = c.outcome == "reopened" and "3.0%" in c.detail and "40.0%" in c.detail
    ok = ok_a and ok_b and ok_c
    return ok, (
        f"a(5.9%)={a.outcome!r} detail={a.detail!r}; "
        f"b(6.0%)={b.outcome!r} detail={b.detail!r}; "
        f"c(40%)={c.outcome!r} detail={c.detail!r}"
    )


def prp020():
    # Literal sequential execution -- no manual re-rejection between steps.
    queue = ProposalQueue()
    queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=400)))  # 40%
    queue.reject("P1", "a.sinha", NOW, RejectionReason.TOO_NOISY)
    a = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=190)))  # 19%
    ok_a = a.outcome == "reopened"
    b = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=210)))  # 21%
    ok_b = b.outcome == "suppressed"
    ok = ok_a and ok_b
    return ok, f"19%={a.outcome!r} detail={a.detail!r}; 21%={b.outcome!r} detail={b.detail!r}"


def prp021():
    queue = ProposalQueue()
    queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=30)))  # 3%
    queue.reject("P1", "a.sinha", NOW, RejectionReason.INCORRECT)
    again = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=900)))  # 90%
    ok = again.outcome == "suppressed"
    return ok, f"outcome={again.outcome!r}"


def prp022():
    # rejected with no backtest, reoffered with one
    queue = ProposalQueue()
    queue.offer(q_proposal())
    queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)
    a = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=900)))
    ok_a = a.outcome == "suppressed"

    # rejected with a backtest, reoffered with none
    queue2 = ProposalQueue()
    queue2.offer(q_proposal(backtest=Backtest(scanned=1000, violations=30)))
    queue2.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)
    b = queue2.offer(q_proposal())
    ok_b = b.outcome == "suppressed"
    ok = ok_a and ok_b
    return ok, f"no-bt-then-bt={a.outcome!r}; bt-then-no-bt={b.outcome!r}"


def prp023():
    queue = ProposalQueue()
    queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=0)))
    queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)
    a = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=0)))
    ok_a = a.outcome == "suppressed"
    b = queue.offer(q_proposal(backtest=Backtest(scanned=1000, violations=5)))  # 0.5%
    ok_b = b.outcome == "reopened" and "nothing failed it" in b.detail
    ok = ok_a and ok_b
    return ok, f"0%={a.outcome!r}; 0.5%={b.outcome!r} detail={b.detail!r}"


def prp024():
    queue = ProposalQueue()
    queue.offer(q_proposal())
    before_open = dict(queue._open)
    again = queue.offer(q_proposal())
    ok = (
        again.outcome == "duplicate"
        and again.proposal is not None
        and again.proposal.identity == "P1"
        and dict(queue._open) == before_open
    )
    return ok, f"outcome={again.outcome!r}, proposal_identity={again.proposal.identity!r}, queue_unchanged={dict(queue._open) == before_open}"


def prp025():
    queue = ProposalQueue()
    queue.offer(q_proposal(origin=Origin.DECLARATION, rule="grain.completeness"))
    second = queue.offer(q_proposal(origin=Origin.MINING, rule="mine.not_null"))
    ok = (
        second.outcome == "corroborated"
        and second.proposal is not None
        and second.proposal.origin is Origin.DECLARATION
        and second.proposal.provenance.is_corroborated
        and any(c.origin is Origin.MINING for c in second.proposal.provenance.corroborations)
    )
    return ok, f"outcome={second.outcome!r}, origin={second.proposal.origin.value!r}, corroborations={[c.origin.value for c in second.proposal.provenance.corroborations]}"


def prp026():
    queue = ProposalQueue()
    queue.offer(q_proposal(origin=Origin.MINING))
    merged = queue.offer(q_proposal(origin=Origin.DECLARATION))
    ok = (
        merged.proposal is not None
        and merged.proposal.origin is Origin.DECLARATION
        and any(c.origin is Origin.MINING for c in merged.proposal.provenance.corroborations)
    )
    return ok, f"survivor_origin={merged.proposal.origin.value!r}"


def prp027():
    queue = ProposalQueue()
    queue.offer(q_proposal(origin=Origin.DECLARATION, rule="grain.completeness"))
    queue.offer(q_proposal(origin=Origin.MINING, rule="mine.not_null"))
    third = queue.offer(q_proposal(origin=Origin.MINING, rule="mine.not_null_2"))
    corroborations = third.proposal.provenance.corroborations if third.proposal else ()
    mining_count = sum(1 for c in corroborations if c.origin is Origin.MINING)
    ok = mining_count == 1
    return ok, f"outcome={third.outcome!r}, corroborations={[c.origin.value for c in corroborations]}, mining_count={mining_count}"


def prp028():
    queue = ProposalQueue()
    queue.offer(q_proposal(content="CHECK t.x IS NOT NULL"))
    newer = queue.offer(q_proposal(content="CHECK t.x IS NOT NULL AND t.x <> ''"))
    ok = (
        newer.admitted
        and newer.outcome == "superseded"
        and newer.proposal.supersedes == "h:CHECK t.x IS NOT NULL"
        and queue._open["P1"].content_hash == newer.proposal.content_hash
    )
    return ok, f"outcome={newer.outcome!r}, supersedes={newer.proposal.supersedes!r}"


def prp029():
    queue = ProposalQueue()
    queue.offer(q_proposal())
    queue.accept("P1", "a.sinha", NOW)
    err1 = None
    err2 = None
    try:
        queue.accept("P1", "a.sinha", NOW)
    except KeyError as exc:
        err1 = str(exc)
    try:
        queue.accept("nope", "a.sinha", NOW)
    except KeyError as exc:
        err2 = str(exc)
    ok = err1 is not None and "already decided" in err1 and err2 is not None and "never offered" in err2
    return ok, f"decided_error={err1!r}; never_offered_error={err2!r}"


def prp030():
    queue = ProposalQueue()
    queue.offer(q_proposal(identity_="A"))
    queue.offer(q_proposal(identity_="B", content="CHECK t.y IS NOT NULL"))
    accepted = queue.accept("A", "a.sinha", NOW)
    rejected = queue.reject("B", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)
    ok = (
        queue.pending() == []
        and len(queue.decided()) == 2
        and len(queue.suppressions()) == 1
        and queue.suppressions()[0].identity == "B"
        and accepted.identity in [p.identity for p in queue.decided()]
        and rejected.identity in [p.identity for p in queue.decided()]
    )
    return ok, f"pending={queue.pending()}; decided_ids={[p.identity for p in queue.decided()]}; suppressed_ids={[s.identity for s in queue.suppressions()]}"


def prp031():
    queue = ProposalQueue()
    queue.offer(q_proposal())
    queue.defer("P1", "waiting on the grain declaration")
    d = queue.deferred()
    ok = (
        queue.pending() == []
        and len(d) == 1
        and d[0].is_open
        and d[0].deferred_because == "waiting on the grain declaration"
    )
    return ok, f"pending={queue.pending()}; deferred_because={d[0].deferred_because!r}; is_open={d[0].is_open}"


def prp032():
    queue = ProposalQueue()
    queue.offer(q_proposal(identity_="D", origin=Origin.DECLARATION, content="CHECK t.a IS NOT NULL"))
    queue.offer(q_proposal(identity_="M", origin=Origin.MINING, content="CHECK t.b IS UNIQUE", rule="mine.key"))
    queue.offer(q_proposal(identity_="I", origin=Origin.IMPORT, content="CHECK t.c IS NOT NULL"))
    queue.offer(q_proposal(identity_="X", origin=Origin.EXAMPLE, content="CHECK t.d IS NOT NULL"))
    queue.offer(q_proposal(identity_="N", origin=Origin.INDUCTION, content="CHECK t.e IS NOT NULL"))
    doc_p = Proposal(
        identity="DOC",
        content="CHECK t.f IS NOT NULL",
        content_hash="h:CHECK t.f IS NOT NULL",
        provenance=Provenance(
            origin=Origin.DOCUMENT, rule="doc.rule", citation=Citation(document="d", quote="q")
        ),
        description="every f has a value",
        dataset="t",
        subject="f",
        rule="doc.rule",
    )
    queue.offer(doc_p)
    activatable = queue.auto_activatable()
    ok = [p.identity for p in activatable] == ["D"]
    return ok, f"auto_activatable identities={[p.identity for p in activatable]}"


def prp033():
    queue = ProposalQueue()
    queue.offer(q_proposal(backtest=Backtest(scanned=100, violations=5)))
    rejected = queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)

    reloaded = ProposalQueue()
    reloaded.remember_rejection(suppression_from(rejected))
    a = reloaded.offer(q_proposal(backtest=Backtest(scanned=100, violations=5)))
    ok_a = a.outcome == "suppressed"

    queue2 = ProposalQueue()
    queue2.offer(q_proposal())
    accepted = queue2.accept("P1", "a.sinha", NOW)
    err = None
    try:
        suppression_from(accepted)
    except ValueError as exc:
        err = str(exc)
    ok_b = err is not None
    ok = ok_a and ok_b
    return ok, f"reloaded_offer_outcome={a.outcome!r}; accepted_suppression_error={err!r}"


def prp034():
    history = AcceptanceHistory()
    for i in range(5):
        history.record(
            u_proposal(identity_=f"R{i}", rule="bad.rule").rejected_by("a.sinha", NOW, RejectionReason.INCORRECT)
        )
    queue = ProposalQueue(history=history)
    queue.offer(q_proposal(identity_="A", origin=Origin.MINING))
    queue.offer(
        q_proposal(
            identity_="B",
            content="CHECK t.y IS NOT NULL",
            backtest=Backtest(scanned=100, violations=60),
        )
    )
    queue.offer(q_proposal(identity_="C", content="CHECK t.z IS NOT NULL", origin=Origin.DECLARATION))
    queue.defer("C", "waiting")
    queue.offer(q_proposal(identity_="D", content="CHECK t.w IS NOT NULL"))
    queue.accept("D", "a.sinha", NOW)
    summary = queue.summary()
    ok = (
        summary["pending"] == 2
        and summary["deferred"] == 1
        and summary["decided"] == 1
        and summary["would_be_too_noisy"] == 1
        and summary["by_origin"].get("mining", 0) == 2
        and "bad.rule" in summary["suspect_rules"]
        and len(summary["top"]) <= 10
    )
    return ok, f"summary={summary}"


run("PRP-016", prp016)
run("PRP-017", prp017)
run("PRP-018", prp018)
run("PRP-019", prp019)
run("PRP-020", prp020)
run("PRP-021", prp021)
run("PRP-022", prp022)
run("PRP-023", prp023)
run("PRP-024", prp024)
run("PRP-025", prp025)
run("PRP-026", prp026)
run("PRP-027", prp027)
run("PRP-028", prp028)
run("PRP-029", prp029)
run("PRP-030", prp030)
run("PRP-031", prp031)
run("PRP-032", prp032)
run("PRP-033", prp033)
run("PRP-034", prp034)


# ===========================================================================
# PRP-035..053 : utility.py
# ===========================================================================


def prp035():
    # Expected field: the four weight values, and ceiling == prior weight.
    # (The module's "Why" doc-comment additionally claims the weights "sum to
    # more than 1 before the noise penalty" -- checked here too, and reported,
    # but it is not part of the literal Expected field.)
    ok = (
        WEIGHTS["criticality"] == 0.35
        and WEIGHTS["coverage_gap"] == 0.25
        and WEIGHTS["confidence"] == 0.20
        and WEIGHTS["acceptance_prior"] == 0.20
        and PRIOR_CEILING == WEIGHTS["acceptance_prior"]
    )
    total = sum(WEIGHTS.values())
    return ok, (
        f"WEIGHTS={WEIGHTS}; PRIOR_CEILING={PRIOR_CEILING}; sum={total} "
        f"(module docstring claims 'more than 1'; actual sum is exactly 1.0, not > 1)"
    )


def prp036():
    scorer = UtilityScorer()
    vals = {}
    for tier in (1, 2, 3, 4):
        vals[tier] = scorer._criticality(Context(criticality=tier))
    tier2_cde = scorer._criticality(Context(criticality=2, is_cde=True))
    tier1_cde = scorer._criticality(Context(criticality=1, is_cde=True))
    ok = (
        vals[1] == 1.0 and vals[2] == 0.75 and vals[3] == 0.5 and vals[4] == 0.25
        and tier2_cde == 1.0 and tier1_cde == 1.0
    )
    return ok, f"tiers={vals}; tier2_cde={tier2_cde}; tier1_cde_clamped={tier1_cde}"


def prp037():
    scorer = UtilityScorer()
    val = scorer._coverage_gap(Context(subject_already_covered=True, covered_fraction=0.0))
    ok = val == 0.0
    return ok, f"coverage_gap={val}"


def prp038():
    scorer = UtilityScorer()
    expected = {
        Origin.DECLARATION: 0.9,
        Origin.DOCUMENT: 0.85,
        Origin.IMPORT: 0.7,
        Origin.MINING: 0.55,
        Origin.EXAMPLE: 0.45,
        Origin.INDUCTION: 0.35,
    }
    actual = {}
    for origin in expected:
        prov_kwargs = {}
        if origin is Origin.DOCUMENT:
            prov_kwargs["citation"] = Citation(document="d", quote="q")
        p = Proposal(
            identity="i",
            content="c",
            content_hash="h",
            provenance=Provenance(origin=origin, rule="r", **prov_kwargs),
            description="d",
        )
        actual[origin] = scorer._confidence(p)
    ok1 = actual == expected
    declaration_not_one = actual[Origin.DECLARATION] < 1.0
    # corroboration adds .15 clamped at 1.0
    declared = Proposal(
        identity="i", content="c", content_hash="h",
        provenance=Provenance(origin=Origin.DECLARATION, rule="r"), description="d"
    )
    corroborated = declared.corroborated_by(
        Proposal(identity="j", content="c2", content_hash="h2",
                 provenance=Provenance(origin=Origin.MINING, rule="r2"), description="d2")
    )
    boosted = scorer._confidence(corroborated)
    ok2 = abs(boosted - min(1.0, 0.9 + 0.15)) < 1e-9
    ok = ok1 and declaration_not_one and ok2
    return ok, f"confidence_by_origin={{o.value: v for o, v in actual.items()}}; boosted={boosted}"


def prp039():
    # simulate a new Origin not in the confidence table by monkeypatching
    scorer = UtilityScorer()
    class FakeOrigin:
        value = "fake"
    p = Proposal(
        identity="i", content="c", content_hash="h",
        provenance=Provenance(origin=Origin.DECLARATION, rule="r"), description="d"
    )
    p_fake = dataclasses.replace(p, provenance=dataclasses.replace(p.provenance))
    object.__setattr__(p_fake, "provenance", dataclasses.replace(p.provenance))
    # Directly craft a proposal whose .origin resolves to something not in the dict
    # by patching the origin property is hard since it's derived from provenance.origin
    # which is validated to be an Origin enum member. Instead call _confidence directly
    # with a stand-in object exposing `.origin` as a value not in the internal dict.
    class FakeProposal:
        origin = FakeOrigin()
        provenance = type("P", (), {"is_corroborated": False})()
    try:
        scorer._confidence(FakeProposal())
        return False, "no KeyError raised"
    except KeyError as exc:
        return True, f"KeyError: {exc}"


def prp040():
    scorer = UtilityScorer()
    rates = [0.0, 0.05, 0.051, 0.30, 0.60]
    penalties = []
    for rate in rates:
        violations = round(rate * 1000)
        bt = Backtest(scanned=1000, violations=violations)
        penalties.append(round(scorer._noise_penalty(dataclasses.replace(u_proposal(), backtest=bt)), 6))
    expected = [0.0, 0.0, -0.051, -0.3, -0.5]
    ok = all(abs(a - b) < 1e-6 for a, b in zip(penalties, expected))
    return ok, f"penalties={penalties} expected={expected}"


def prp041():
    scorer = UtilityScorer()
    p1 = u_proposal(backtest=None)
    p2 = u_proposal(backtest=Backtest(scanned=0, violations=0, unavailable="no data"))
    v1 = scorer._noise_penalty(p1)
    v2 = scorer._noise_penalty(p2)
    ok = v1 == 0.0 and v2 == 0.0
    return ok, f"no_backtest_penalty={v1}; unavailable_backtest_penalty={v2}"


def prp042():
    scorer = UtilityScorer()
    p = u_proposal(backtest=Backtest(scanned=1000, violations=900))
    utility = scorer.score(p, Context(criticality=4, covered_fraction=1.0, subject_already_covered=True))
    ok = utility.score == 0.0 and utility.score >= 0.0
    return ok, f"score={utility.score}; components={utility.to_dict()}"


def prp043():
    history = AcceptanceHistory()
    before = history.rate("rule:x")
    history.record(u_proposal(rule="x").rejected_by("a.sinha", NOW, RejectionReason.NOT_MATERIAL))
    after = history.rate("rule:x")
    ok = before == 0.5 and abs(after - (1 / 3)) < 1e-9 and after != 0.0
    return ok, f"before={before}; after={after}"


def prp044():
    history = AcceptanceHistory()
    for i in range(20):
        history.record(u_proposal(identity_=f"acc{i}", rule="great.rule").accepted_by("a.sinha", NOW))
    poor_history = AcceptanceHistory()
    for i in range(20):
        poor_history.record(
            u_proposal(identity_=f"bad{i}", rule="poor.rule").rejected_by("a.sinha", NOW, RejectionReason.INCORRECT)
        )
    scorer_good = UtilityScorer(history)
    tier4_great_rule = scorer_good.score(u_proposal(rule="great.rule"), Context(criticality=4, covered_fraction=1.0))
    scorer_poor = UtilityScorer(poor_history)
    tier1_cde_poor_rule = scorer_poor.score(
        u_proposal(rule="poor.rule"), Context(criticality=1, is_cde=True)
    )
    prior_capped = tier4_great_rule.acceptance_prior <= PRIOR_CEILING + 1e-9
    ok = prior_capped and tier1_cde_poor_rule.score > tier4_great_rule.score
    return ok, (
        f"tier4_great_rule.prior={tier4_great_rule.acceptance_prior}, score={tier4_great_rule.score}; "
        f"tier1_cde_poor_rule.score={tier1_cde_poor_rule.score}; PRIOR_CEILING={PRIOR_CEILING}"
    )


def prp045():
    history = AcceptanceHistory()
    history.record(u_proposal(rule="found.it").rejected_by("a.sinha", NOW, RejectionReason.PENDING_REMEDIATION))
    history.record(u_proposal(rule="found.it").rejected_by("a.sinha", NOW, RejectionReason.DUPLICATE))
    rate = history.rate("rule:found.it")
    obs = history.observations("rule:found.it")
    ok = rate == 0.5 and obs == 0
    return ok, f"rate={rate}; observations={obs}"


def prp046():
    history = AcceptanceHistory()
    # Give "rule:r1" a strong, distinct record (many accepts) while diluting
    # "origin:mining" with other rules' rejections, so the two keys' rates
    # genuinely diverge and averaging can be observed.
    for i in range(5):
        history.record(u_proposal(identity_=f"r1-{i}", rule="r1").accepted_by("a.sinha", NOW))
    for i in range(5):
        history.record(
            u_proposal(identity_=f"other-{i}", rule="other.rule").rejected_by(
                "a.sinha", NOW, RejectionReason.NOT_MATERIAL
            )
        )
    p_with_rule = u_proposal(identity_="new", rule="r1")
    p_without_rule = dataclasses.replace(p_with_rule, rule="")
    prior_with = history.prior(p_with_rule)
    prior_without = history.prior(p_without_rule)
    origin_rate = history.rate("origin:mining")
    rule_rate = history.rate("rule:r1")
    expected_prior_with = (origin_rate + rule_rate) / 2
    ok = (
        prior_without == origin_rate
        and abs(prior_with - expected_prior_with) < 1e-9
        and prior_with != prior_without
    )
    return ok, (
        f"prior_with_rule={prior_with}; prior_without_rule={prior_without}; "
        f"origin_rate={origin_rate}; rule_rate={rule_rate}; mean={expected_prior_with}"
    )


def prp047():
    history = AcceptanceHistory()
    proposed = u_proposal(rule="r1")  # status PROPOSED, decision None
    deferred = u_proposal(rule="r1").deferred("waiting")
    before = history.rate("rule:r1")
    history.record(proposed)
    history.record(deferred)
    after = history.rate("rule:r1")
    ok = before == after == 0.5 and history.observations("rule:r1") == 0
    return ok, f"before={before}; after={after}; observations={history.observations('rule:r1')}"


def prp048():
    history = AcceptanceHistory()
    for i in range(4):
        history.record(u_proposal(identity_=f"a{i}", rule="rule.a").rejected_by("a.sinha", NOW, RejectionReason.INCORRECT))
    for i in range(5):
        history.record(u_proposal(identity_=f"b{i}", rule="rule.b").rejected_by("a.sinha", NOW, RejectionReason.INCORRECT))
    suspects = history.suspect_rules()
    indicted = indicted_rules(history)
    ok = suspects == ("rule.b",) and indicted == (("rule.b", 5),)
    return ok, f"suspect_rules={suspects}; indicted_rules={indicted}"


def prp049():
    history = AcceptanceHistory()
    for i in range(3):
        history.record(u_proposal(identity_=f"h{i}", rule="check.digit").accepted_by("a.sinha", NOW))
    scorer = UtilityScorer(history)
    p = u_proposal(rule="check.digit", backtest=Backtest(scanned=100, violations=30))
    utility = scorer.score(p, Context(criticality=1, is_cde=True, covered_fraction=0.2))
    explanation = utility.explanation
    has_tier = "Tier 1" in explanation
    has_cde = "CDE" in explanation
    has_unprotected = "unprotected" in explanation
    has_rule_rate = "accepted" in explanation and "3 decided" in explanation
    has_noise = "flag" in explanation and "rows" in explanation
    ok = has_tier and has_cde and has_unprotected and has_rule_rate and has_noise
    return ok, f"explanation={explanation!r}"


def prp050():
    scorer = UtilityScorer()
    p = u_proposal()
    u1 = scorer.score(p, Context(criticality=4))
    u2 = scorer.score(p, Context(criticality=1, is_cde=True, covered_fraction=0.0))
    ok = u1.explanation != u2.explanation and "Tier 1" in u2.explanation and "Tier 1" not in u1.explanation
    return ok, f"explanation1={u1.explanation!r}; explanation2={u2.explanation!r}"


def prp051():
    history = AcceptanceHistory()
    for i in range(2):
        history.record(u_proposal(identity_=f"h{i}", rule="r").accepted_by("a.sinha", NOW))
    scorer = UtilityScorer(history)
    at_two = scorer.score(u_proposal(rule="r"), Context(criticality=1))
    history.record(u_proposal(identity_="h2", rule="r").accepted_by("a.sinha", NOW))
    at_three = scorer.score(u_proposal(rule="r"), Context(criticality=1))
    ok = "decided" not in at_two.explanation and "decided" in at_three.explanation
    return ok, f"at_two={at_two.explanation!r}; at_three={at_three.explanation!r}"


def prp052():
    proposals = [u_proposal(identity_=f"P{i}") for i in range(10)]
    first = [p.identity for p in rank(list(proposals))]
    second = [p.identity for p in rank(list(reversed(proposals)))]
    ok = first == second
    return ok, f"first={first}; second={second}; equal={first == second}"


def prp053():
    p = u_proposal(identity_="X", dataset="unmapped_dataset")
    scored = rank([p], context={"other_dataset": Context(criticality=1, is_cde=True)})
    default_ctx_score = UtilityScorer().score(p, Context())
    ok = abs(scored[0].score - default_ctx_score.score) < 1e-9
    return ok, f"ranked_score={scored[0].score}; default_context_score={default_ctx_score.score}"


run("PRP-035", prp035)
run("PRP-036", prp036)
run("PRP-037", prp037)
run("PRP-038", prp038)
run("PRP-039", prp039)
run("PRP-040", prp040)
run("PRP-041", prp041)
run("PRP-042", prp042)
run("PRP-043", prp043)
run("PRP-044", prp044)
run("PRP-045", prp045)
run("PRP-046", prp046)
run("PRP-047", prp047)
run("PRP-048", prp048)
run("PRP-049", prp049)
run("PRP-050", prp050)
run("PRP-051", prp051)
run("PRP-052", prp052)
run("PRP-053", prp053)


# ===========================================================================
# learn/loop.py : PRP-054..067
# ===========================================================================
from prama.learn.loop import (
    Arm,
    ArmResult,
    Decision as LoopDecision,
    Outcome,
    Promotion,
    Uplift,
    _difference_interval,
    _summarise,
    assign,
    consider,
    measure,
)


def prp054():
    arms = [assign("identity-a") for _ in range(10)]
    ok1 = len(set(arms)) == 1
    # re-assign after a re-proposal (same identity, called again)
    arm_again = assign("identity-a")
    ok2 = arm_again == arms[0]
    return ok1 and ok2, f"arms={[a.value for a in arms]}; reassigned={arm_again.value}"


def prp055():
    n = 10_000
    def frac(holdout):
        count = sum(1 for i in range(n) if assign(f"item-{i}", holdout=holdout) is Arm.CONTROL)
        return count / n
    tenth = frac(0.1)
    zero = frac(0.0)
    one = frac(1.0)
    ok = abs(tenth - 0.1) < 0.02 and zero == 0.0 and one == 1.0
    return ok, f"holdout=0.1 -> {tenth}; holdout=0.0 -> {zero}; holdout=1.0 -> {one}"


def prp056():
    ids = [f"id-{i}" for i in range(200)]
    a1 = [assign(i, salt="salt-a") for i in ids]
    a2 = [assign(i, salt="salt-b") for i in ids]
    different = a1 != a2
    a1_again = [assign(i, salt="salt-a") for i in ids]
    stable = a1 == a1_again
    ok = different and stable
    return ok, f"different_assignments={different}; salt_a_stable={stable}; num_differences={sum(1 for x,y in zip(a1,a2) if x != y)}"


def prp057():
    decisions = (
        [LoopDecision(identity=f"acc{i}", arm=Arm.TREATMENT, outcome=Outcome.ACCEPTED) for i in range(5)]
        + [LoopDecision(identity=f"rej{i}", arm=Arm.TREATMENT, outcome=Outcome.REJECTED) for i in range(3)]
        + [LoopDecision(identity=f"pend{i}", arm=Arm.TREATMENT, outcome=Outcome.PENDING) for i in range(10)]
    )
    result = _summarise(Arm.TREATMENT, decisions)
    ok = (
        result.surfaced == 18
        and result.reviewed == 8
        and result.accepted == 5
        and result.pending == 10
        and result.precision == 0.625
    )
    return ok, f"surfaced={result.surfaced}; reviewed={result.reviewed}; accepted={result.accepted}; pending={result.pending}; precision={result.precision}"


def prp058():
    result = ArmResult(arm=Arm.TREATMENT, surfaced=5, reviewed=0, accepted=0)
    ok = result.precision is None and "none reviewed yet" in result.describe()
    return ok, f"precision={result.precision}; describe()={result.describe()!r}"


def prp059():
    decisions = (
        [LoopDecision(identity="a1", arm=Arm.TREATMENT, outcome=Outcome.ACCEPTED, rank=1)]
        + [LoopDecision(identity="a2", arm=Arm.TREATMENT, outcome=Outcome.ACCEPTED, rank=2)]
        + [LoopDecision(identity=f"r{i}", arm=Arm.TREATMENT, outcome=Outcome.REJECTED) for i in range(2)]
        + [LoopDecision(identity="b1", arm=Arm.CONTROL, outcome=Outcome.ACCEPTED, rank=5)]
        + [LoopDecision(identity="b2", arm=Arm.CONTROL, outcome=Outcome.ACCEPTED, rank=6)]
        + [LoopDecision(identity=f"cr{i}", arm=Arm.CONTROL, outcome=Outcome.REJECTED) for i in range(2)]
    )
    treatment = _summarise(Arm.TREATMENT, decisions)
    control = _summarise(Arm.CONTROL, decisions)
    equal_precision = treatment.precision == control.precision
    different_rank = treatment.mean_accepted_rank != control.mean_accepted_rank
    uplift = measure(decisions)
    rank_gain = control.mean_accepted_rank - treatment.mean_accepted_rank
    named_in_sentence = abs(rank_gain) > 0.5 and (
        f"{abs(rank_gain):.1f} places" in uplift.describe() if uplift.is_measurable else True
    )
    ok = equal_precision and different_rank
    return ok, (
        f"treatment.precision={treatment.precision}, mean_rank={treatment.mean_accepted_rank}; "
        f"control.precision={control.precision}, mean_rank={control.mean_accepted_rank}; "
        f"rank_gain={rank_gain}"
    )


def prp060():
    def make(n):
        return [LoopDecision(identity=f"t{i}", arm=Arm.TREATMENT, outcome=Outcome.ACCEPTED) for i in range(n)] + \
               [LoopDecision(identity=f"c{i}", arm=Arm.CONTROL, outcome=Outcome.ACCEPTED) for i in range(n)]
    uplift29 = measure(make(29))
    uplift30 = measure(make(30))
    ok = (
        uplift29.is_measurable is False
        and uplift30.is_measurable is True
        and "not measurable yet" in uplift29.describe()
        and "wider than any effect worth claiming" in uplift29.describe()
    )
    return ok, f"29_measurable={uplift29.is_measurable}, describe={uplift29.describe()!r}; 30_measurable={uplift30.is_measurable}"


def prp061():
    def fake_uplift(low, high):
        t = ArmResult(arm=Arm.TREATMENT, surfaced=100, reviewed=100, accepted=50)
        c = ArmResult(arm=Arm.CONTROL, surfaced=100, reviewed=100, accepted=50)
        return Uplift(treatment=t, control=c, difference=0, low=low, high=high)
    u1 = fake_uplift(-0.01, 0.09)
    u2 = fake_uplift(0.01, 0.09)
    u3 = fake_uplift(-0.09, -0.01)
    ok = u1.is_significant is False and u2.is_significant is True and u3.is_significant is True
    return ok, f"(-0.01,0.09)->{u1.is_significant}; (0.01,0.09)->{u2.is_significant}; (-0.09,-0.01)->{u3.is_significant}"


def prp062():
    low, high = _difference_interval(80, 100, 70, 100)
    p_a, p_b = 0.8, 0.7
    diff = p_a - p_b
    variance = p_a * (1 - p_a) / 100 + p_b * (1 - p_b) / 100
    spread = 1.959963984540054 * math.sqrt(variance)
    expected_low, expected_high = diff - spread, diff + spread
    center = (low + high) / 2
    ok = abs(center - 0.10) < 1e-6 and abs(low - expected_low) < 1e-9 and abs(high - expected_high) < 1e-9
    zero_case = _difference_interval(0, 0, 5, 10)
    zero_case2 = _difference_interval(5, 10, 0, 0)
    ok_zero = zero_case == (0.0, 0.0) and zero_case2 == (0.0, 0.0)
    ok = ok and ok_zero
    return ok, f"interval=({low}, {high}); center={center}; expected=({expected_low},{expected_high}); zero_reviews_case={zero_case}, {zero_case2}"


def prp063():
    t = ArmResult(arm=Arm.TREATMENT, surfaced=100, reviewed=100, accepted=60)
    c = ArmResult(arm=Arm.CONTROL, surfaced=40, reviewed=40, accepted=20)
    uplift = Uplift(treatment=t, control=c, difference=0.1, low=0.01, high=0.19, holdout_cost=c.reviewed)
    desc = uplift.describe()
    ok = str(c.reviewed) in desc and "price of knowing any of this" in desc
    return ok, f"holdout_cost={uplift.holdout_cost}; describe()={desc!r}"


def prp064():
    t = ArmResult(arm=Arm.TREATMENT, surfaced=100, reviewed=100, accepted=58)
    c = ArmResult(arm=Arm.CONTROL, surfaced=100, reviewed=100, accepted=50)
    uplift = Uplift(treatment=t, control=c, difference=0.08, low=-0.01, high=0.17, holdout_cost=100)
    promotion = consider(uplift)
    ok = (
        promotion.should_promote is False
        and "point estimate" in promotion.reason
        and uplift.is_measurable
        and not uplift.is_significant
    )
    return ok, f"should_promote={promotion.should_promote}; reason={promotion.reason!r}"


def prp065():
    t = ArmResult(arm=Arm.TREATMENT, surfaced=100, reviewed=100, accepted=28)
    c = ArmResult(arm=Arm.CONTROL, surfaced=100, reviewed=100, accepted=50)
    uplift = Uplift(treatment=t, control=c, difference=-0.22, low=-0.35, high=-0.09, holdout_cost=100)
    promotion = consider(uplift)
    ok = (
        promotion.should_promote is False
        and "significantly" in promotion.reason
        and "worse" in promotion.reason
        and uplift.is_significant
    )
    return ok, f"should_promote={promotion.should_promote}; reason={promotion.reason!r}; is_significant={uplift.is_significant}"


def prp066():
    # Construct Uplift objects directly with a significant interval (low > 0)
    # so is_significant is true by construction, and only minimum_gain decides
    # the promotion outcome -- exactly what the case is testing.
    def make_uplift(diff):
        t = ArmResult(arm=Arm.TREATMENT, surfaced=2000, reviewed=2000, accepted=int(1000 + diff * 2000))
        c = ArmResult(arm=Arm.CONTROL, surfaced=2000, reviewed=2000, accepted=1000)
        return Uplift(treatment=t, control=c, difference=diff, low=0.001, high=diff * 2, holdout_cost=2000)

    u1 = make_uplift(0.029)
    p1 = consider(u1, minimum_gain=0.03)
    ok1 = p1.should_promote is False and "below" in p1.reason

    u2 = make_uplift(0.031)
    p2 = consider(u2, minimum_gain=0.03)
    ok2 = p2.should_promote is True

    ok = ok1 and ok2 and u1.is_significant and u2.is_significant
    return ok, (
        f"diff1={u1.difference:.4f} significant={u1.is_significant} should_promote={p1.should_promote} reason={p1.reason!r}; "
        f"diff2={u2.difference:.4f} significant={u2.is_significant} should_promote={p2.should_promote}"
    )


def prp067():
    t = ArmResult(arm=Arm.TREATMENT, surfaced=200, reviewed=200, accepted=140)
    c = ArmResult(arm=Arm.CONTROL, surfaced=200, reviewed=200, accepted=100)
    low, high = _difference_interval(140, 200, 100, 200)
    diff = 140 / 200 - 100 / 200
    uplift = Uplift(treatment=t, control=c, difference=diff, low=low, high=high, holdout_cost=200)
    promotion = consider(uplift)
    reason = promotion.reason
    ok = (
        promotion.should_promote is True
        and f"{diff:+.1%}" in reason
        and str(t.reviewed) in reason
        and str(c.reviewed) in reason
        and f"{low:+.1%}" in reason
        and f"{high:+.1%}" in reason
    )
    return ok, f"should_promote={promotion.should_promote}; reason={reason!r}"


run("PRP-054", prp054)
run("PRP-055", prp055)
run("PRP-056", prp056)
run("PRP-057", prp057)
run("PRP-058", prp058)
run("PRP-059", prp059)
run("PRP-060", prp060)
run("PRP-061", prp061)
run("PRP-062", prp062)
run("PRP-063", prp063)
run("PRP-064", prp064)
run("PRP-065", prp065)
run("PRP-066", prp066)
run("PRP-067", prp067)


# ===========================================================================
# Print results
# ===========================================================================
print("\n\n===== RESULTS =====")
for case_id, status, observed in RESULTS:
    print(f"{case_id}\t{status}\t{observed}")
