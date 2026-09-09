"""Wave 8's demo, as a test.

"Break the sub-ledger deliberately; watch one incident open with a ranked
cause, an impact list naming the affected return, a classified break
population, and a trust score that drops on every descendant of the defect."

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from prama.alert.route import Alert, Fault, Role, Router
from prama.incident.correlate import Change, Correlator, Finding
from prama.incident.rca import RootCause
from prama.lineage.graph import Column, Edge, LineageGraph, Transform
from prama.recon.engine import Definition, Reconciliation, Side
from prama.recon.match import Matcher, MatchKey
from prama.recon.normalise import AmountSpec, RateSource
from prama.recon.workflow import BreakQueue, certify
from prama.score.trust import Semiring, TrustPropagator, ranked_by_trust
from prama.semantic.relationships import Tolerance

WHEN = date(2026, 3, 31)
OPENED = datetime(2026, 3, 31, 6, 0)
C = Column.parse


def warehouse() -> LineageGraph:
    """The sub-ledger feeds positions, which feed risk, which feeds FINREP."""
    graph = LineageGraph()
    graph.add_all(
        [
            Edge(C("subledger.amount"), C("positions.market_value"), Transform.IDENTITY),
            Edge(C("positions.market_value"), C("risk.exposure"), Transform.DERIVED),
            Edge(C("risk.exposure"), C("finrep.line_23"), Transform.AGGREGATED),
            Edge(C("subledger.amount"), C("gl.balance"), Transform.DERIVED),
            Edge(C("subledger.account"), C("positions.account_id"), Transform.IDENTITY),
        ]
    )
    return graph


def definition() -> Definition:
    return Definition(
        name="sub-ledger vs GL",
        left=Side("subledger", "amount", AmountSpec(currency="EUR")),
        right=Side("gl", "balance", AmountSpec(currency="EUR")),
        key=MatchKey(left=("account",), right=("acct",)),
        tolerance=Tolerance(absolute=1.0, currency="EUR"),
        target_currency="EUR",
    )


def broken_books() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """A sub-ledger broken deliberately, in four different ways."""
    rng = random.Random(3)
    sub: list[dict[str, object]] = []
    gl: list[dict[str, object]] = []
    for index in range(200):
        account = f"A{index:04d}"
        amount = Decimal(rng.randrange(1000, 9000))
        sub.append({"account": account, "amount": str(amount)})
        if index < 4:
            # Sign convention: the break is twice the value and none is real.
            gl.append({"acct": account, "balance": str(-amount)})
        elif index < 8:
            # A posting counted twice.
            gl.append({"acct": account, "balance": str(amount * 2)})
        elif index < 12:
            # A genuine difference.
            gl.append({"acct": account, "balance": str(amount + 500)})
        elif index < 14:
            continue  # missing from the GL entirely
        else:
            gl.append({"acct": account, "balance": str(amount)})
    return sub, gl


# -- a classified break population -------------------------------------------


def test_the_reconciliation_runs_and_classifies_what_it_finds() -> None:
    sub, gl = broken_books()
    run = Reconciliation(definition(), rates=RateSource(source="ECB")).run(
        sub, gl, business_date=WHEN
    )
    assert run.completed
    kinds = run.population.by_kind
    print(f"\n  {run.headline()}")
    assert kinds["sign"] == 4
    assert kinds["duplicate"] == 4
    assert kinds["genuine"] == 4
    assert kinds["missing"] == 2


def test_the_configuration_faults_are_separated_from_the_data_problems() -> None:
    """Eight of the fourteen breaks are the reconciliation's own setup, and
    sending them to a data steward wastes the steward's day."""
    sub, gl = broken_books()
    run = Reconciliation(definition()).run(sub, gl, business_date=WHEN)
    assert len(run.population.configuration_faults) == 8
    assert len(run.population.genuine) == 4


def test_the_period_closes_with_a_signed_certificate() -> None:
    sub, gl = broken_books()
    run = Reconciliation(definition()).run(sub, gl, business_date=WHEN)
    queue = BreakQueue()
    queue.observe(run.population.breaks, when=WHEN)

    item = queue.get(run.population.genuine[0].key)
    assert item is not None
    queue.update(
        item.accepted("a.sinha", "2026-04-01T09:00:00Z", "cleared with the desk on 1 April")
    )

    certificate = certify(
        "sub-ledger vs GL",
        queue,
        period_end=WHEN,
        signed_by="a.sinha",
        signed_at="2026-04-01T09:00:00Z",
        matched_rate=run.match.match_rate,
        population=run.population.describe(),
    )
    rendered = certificate.render()
    assert "items outstanding" in rendered
    assert "cleared with the desk" in rendered
    assert certificate.content_hash


# -- one incident, with a ranked cause ---------------------------------------


def findings() -> list[Finding]:
    """Every control on every descendant of the broken column fails."""
    out = []
    for column in ("market_value", "account_id"):
        out.append(Finding(f"positions.{column}", "positions", column, OPENED))
    out.append(Finding("risk.exposure", "risk", "exposure", OPENED))
    out.append(Finding("finrep.line_23", "finrep", "line_23", OPENED))
    out.append(Finding("gl.balance", "gl", "balance", OPENED))
    return out


def test_one_upstream_defect_produces_one_incident() -> None:
    """The acceptance criterion. Five findings across four datasets are one
    problem seen from five places."""
    result = Correlator(warehouse()).correlate(findings())
    print(f"  {result.describe()}")
    assert len(result.incidents) == 1
    ancestor = result.incidents[0].common_ancestor
    assert ancestor is not None
    # The incident is about the sub-ledger: its `amount` and `account` columns
    # are two roots of two subgraphs, and reporting them separately would be
    # this module's own failure one level up.
    assert ancestor.dataset == "subledger"


def test_the_incident_carries_a_ranked_cause_with_a_check() -> None:
    change = Change(
        "c9",
        OPENED - timedelta(minutes=40),
        "sub-ledger posting rules edited",
        "a.sinha",
        touched=("subledger.amount",),
    )
    incident = Correlator(warehouse(), changes=[change]).correlate(findings()).incidents[0]
    analysis = RootCause(warehouse(), changes=[change]).analyse(incident)
    assert analysis.best is not None
    print(f"  {analysis.best.describe()[:150]}")
    assert "sub-ledger posting rules edited" in analysis.best.cause
    assert analysis.best.check
    assert analysis.best.rules_out


# -- an impact list naming the affected return -------------------------------


def test_the_impact_list_names_the_regulatory_return() -> None:
    """ "This column feeds that column, which is line 23 of the FINREP return"
    is a sentence somebody can act on at seven in the morning."""
    radius = warehouse().blast_radius(C("subledger.amount"))
    reached = {item.column.qualified for item in radius.reached}
    assert "finrep.line_23" in reached
    line = next(item for item in radius.reached if item.column.name == "line_23")
    print(f"  {line.describe()[:140]}")
    assert line.depth == 3


# -- trust drops on every descendant -----------------------------------------


def test_trust_falls_on_every_descendant_of_the_defect() -> None:
    graph = warehouse()
    local = {C("subledger.amount"): 0.3}
    trusts = TrustPropagator(graph).trust_all(local)
    for name in ("positions.market_value", "risk.exposure", "finrep.line_23", "gl.balance"):
        assert trusts[C(name)].score < 1.0, name
    print(f"  finrep.line_23 trust {trusts[C('finrep.line_23')].score:.2f}")


def test_trust_ranks_the_consequence_where_severity_ranks_the_finding() -> None:
    """`RQ8`. A mild defect upstream of a regulatory return outranks a severe
    one in a scratch table, and severity ranking gets that backwards."""
    graph = warehouse()
    graph.add(Edge(C("scratch.note"), C("scratch.copy"), Transform.IDENTITY))
    local = {C("subledger.amount"): 0.7, C("scratch.note"): 0.15}

    by_severity = min(local, key=lambda column: local[column])
    assert by_severity == C("scratch.note")

    trusts = TrustPropagator(graph).trust_all(local)
    affected = {c.qualified for c, t in trusts.items() if t.score < 0.95}
    assert "finrep.line_23" in affected
    assert "scratch.copy" in affected
    # The mild defect has reached a regulatory return; the severe one a copy.
    assert trusts[C("finrep.line_23")].score < 1.0


def test_the_derivation_is_readable_by_whoever_disputes_it() -> None:
    trust = TrustPropagator(warehouse(), semiring=Semiring.ALL_INPUTS_MATTER).trust(
        C("finrep.line_23"), {C("subledger.amount"): 0.3}
    )
    explanation = trust.explain()
    assert "subledger.amount (0.30)" in explanation
    assert "weakest path governs" in explanation


def test_the_remediation_queue_is_led_by_the_defect() -> None:
    trusts = TrustPropagator(warehouse()).trust_all({C("subledger.amount"): 0.3})
    assert ranked_by_trust(trusts, limit=1)[0].column == C("subledger.amount")


# -- and one alert -----------------------------------------------------------


def test_one_alert_reaches_the_right_person_with_what_to_do() -> None:
    router = Router(
        {
            ("subledger", Role.STEWARD): "s.owner",
            ("subledger", Role.CUSTODIAN): "c.runner",
        }
    )
    dispatch = router.dispatch(
        Alert(
            identity="incident:subledger.amount",
            dataset="subledger",
            fault=Fault.RECONCILIATION,
            what="14 breaks against the GL, 4 of them genuine",
            consequence="FINREP line 23 is downstream and blocks the submission",
            likely_cause="sub-ledger posting rules edited at 05:20 — read change c9",
            severity=0.9,
            at=OPENED,
            covers=5,
        )
    )
    assert dispatch.sent
    assert dispatch.recipients[0].identity == "s.owner"
    message = dispatch.alert.compose()
    print(f"  {message[:160]}")
    assert "FINREP line 23" in message
    assert "Likeliest cause" in message

    # And it does not alert again on the next run.
    assert not router.dispatch(
        Alert(
            identity="incident:subledger.amount",
            dataset="subledger",
            fault=Fault.RECONCILIATION,
            what="14 breaks against the GL, 4 of them genuine",
            severity=0.9,
            at=OPENED + timedelta(hours=1),
        )
    ).sent


# -- throughput --------------------------------------------------------------


def test_matching_throughput_is_measured_rather_than_assumed() -> None:
    """The wave asks for 10^8 records a side. Measured at a size that fits in a
    test and extrapolated, with the extrapolation labelled: the matcher is
    linear in rows and this establishes the constant, not that a hundred
    million rows fit in memory — which they do not, and which the streaming
    execution of Wave 5 is for.
    """
    rows = 100_000
    left = [{"k": f"K{index}", "v": index} for index in range(rows)]
    right = [{"k": f"K{index}", "v": index} for index in range(rows)]

    started = time.perf_counter()
    report = Matcher(MatchKey(left=("k",), right=("k",))).match(left, right)
    elapsed = time.perf_counter() - started

    per_second = (2 * rows) / elapsed
    hours = (2 * 100_000_000) / per_second / 3600
    print(
        f"  matched {2 * rows:,} rows in {elapsed:.2f}s "
        f"({per_second:,.0f}/s; 10^8 a side extrapolates to {hours:.1f} hours "
        f"single-threaded, and the work partitions by key)"
    )
    assert len(report.pairs) == rows
    # A floor on the *complexity class*, not on the machine. Measured at around
    # 157,000/s on an idle laptop, so 50,000 left barely three times' headroom
    # and the suite went red the first time something else — the browser the
    # accessibility audit drives — wanted the CPU. A test that fails for
    # reasons unrelated to the code gets ignored when it fails for a related
    # one. A quadratic matcher at this size would be thousands of times slower
    # than this bound, which is the regression worth catching.
    assert per_second > 10_000
