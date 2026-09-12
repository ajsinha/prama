"""One pass over the estate's live controls.

This is the join that turns a stored estate and a stored ledger into a system
that operates, and the tests are written against the four ways such a runner
lies: it stops on the first bad source and the rest goes unchecked, it loses a
run without saying so, it reports a pass from a query that could not establish
one, or it runs controls nobody agreed to.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.db import Database
from prama.execute import ControlRun

pytestmark = pytest.mark.anyio

CLEAN = (
    "CHECK positions_eod.notional IS NOT NULL "
    "SEVERITY critical DIMENSION completeness BECAUSE 'CDE for FRTB'"
)
UNIQUE = (
    "CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id) "
    "SEVERITY critical DIMENSION uniqueness BECAUSE 'declared grain'"
)
#: An LEI check compiles to a screen plus a residual: the SQL is a necessary
#: condition and not the exact test.
SCREENED = (
    "CHECK positions_eod.lei IS VALID 'lei' SEVERITY major DIMENSION validity BECAUSE 'ISO 17442'"
)


def rows_for(**metrics: float) -> Any:
    def execute(_query: str) -> list[dict[str, float]]:
        return [dict(metrics)]

    return execute


def exploding(message: str = "the warehouse refused the query") -> Any:
    def execute(_query: str) -> list[dict[str, float]]:
        raise RuntimeError(message)

    return execute


async def _control(
    database: Database, tenant_id: str, pql: str, *, identity: str = "i1", active: bool = True
) -> str:
    async with database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(
            tenant_id=tenant_id, identity=identity, pql=pql, criticality=1
        )
        if active:
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
        return str(control.id)


class TestTheLoopIsClosed:
    async def test_a_run_writes_evidence_for_every_live_control(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _control(started_database, tenant_id, CLEAN, identity="a")
        await _control(started_database, tenant_id, UNIQUE, identity="b")

        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=1000, violating_rows=0, distinct_keys=1000),
            ).execute_all()
            chain = await uow.evidence.chain(tenant_id)

        assert len(report.outcomes) == 2
        assert len(chain) == 2
        assert report.executed == 2

    async def test_the_chain_verifies_after_a_run(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=10, violating_rows=0)
            ).execute_all()
            verification = await uow.evidence.verify(tenant_id)
        assert verification.is_intact, verification.render()

    async def test_the_records_carry_dimension_and_tier(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Without them the scorecard can say how much passed and not which
        kind of quality it was, nor how much it mattered."""
        await _control(started_database, tenant_id, UNIQUE)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=100, violating_rows=0, distinct_keys=100),
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)
        assert record.dimensions == ("uniqueness",)
        assert record.criticality == 1

    async def test_the_run_groups_its_own_records(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=10, violating_rows=0)
            ).execute_all()
            assert len(await uow.evidence.for_run(report.run_id)) == 1
            [run] = await uow.evidence_runs.recent(tenant_id)
        assert run.status == "complete"
        assert run.record_count == 1

    async def test_a_failing_control_is_recorded_as_failing(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=1000, violating_rows=12)
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)
        assert record.verdict == "fail"
        assert record.metrics["violating_rows"] == 12


class TestOnlyAgreedControlsRun:
    async def test_a_proposal_does_not_run(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A coverage figure that counted proposals would claim protection the
        estate has not agreed to."""
        await _control(started_database, tenant_id, CLEAN, active=False)
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=10, violating_rows=0)
            ).execute_all()
        assert report.outcomes == ()

    async def test_a_suppressed_control_does_not_run(
        self, started_database: Database, tenant_id: str
    ) -> None:
        control_id = await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await uow.controls.suppress(
                control_id,
                tenant_id=tenant_id,
                until="2099-01-01T00:00:00Z",
                because="upstream migration",
            )
            report = await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=10, violating_rows=0)
            ).execute_all()
        assert report.outcomes == ()

    async def test_another_tenant_s_controls_are_not_run(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            other = uow.tenants.create(slug="other", display_name="Other")
            await uow.flush()
            other_id = str(other.id)
        await _control(started_database, other_id, CLEAN)

        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=10, violating_rows=0)
            ).execute_all()
        assert report.outcomes == ()


class TestAFailureIsAFindingNotACrash:
    async def test_an_unreadable_source_becomes_an_error_record(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(uow, tenant_id, execute=exploding()).execute_all()
            [record] = await uow.evidence.chain(tenant_id)

        assert record.verdict == "error"
        assert "the warehouse refused the query" in record.detail
        assert report.failed_to_run == 1

    async def test_one_bad_control_does_not_stop_the_rest(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A run that stopped on the first unreadable table would take the rest
        of the estate down with it, and the estate would go unchecked for a
        reason nobody can see from the console."""
        await _control(started_database, tenant_id, CLEAN, identity="a")
        await _control(started_database, tenant_id, UNIQUE, identity="b")

        calls: list[str] = []

        def flaky(query: str) -> list[dict[str, float]]:
            calls.append(query)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return [{"scanned_rows": 100.0, "violating_rows": 0.0, "distinct_keys": 100.0}]

        async with started_database.unit_of_work() as uow:
            report = await ControlRun(uow, tenant_id, execute=flaky).execute_all()

        assert len(report.outcomes) == 2
        assert report.executed == 1
        assert report.failed_to_run == 1

    async def test_the_summary_names_what_did_not_run(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A summary reporting only verdicts reads as complete whatever
        proportion of the estate refused to execute."""
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(uow, tenant_id, execute=exploding()).execute_all()
        assert "could not be executed at all" in report.describe()

    async def test_an_empty_metric_result_is_not_judged_as_a_pass(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """ "The query returned no rows" is not a measurement of anything, and
        zeros would be judged as clean."""
        await _control(started_database, tenant_id, CLEAN)

        def nothing(_query: str) -> list[dict[str, float]]:
            return []

        async with started_database.unit_of_work() as uow:
            await ControlRun(uow, tenant_id, execute=nothing).execute_all()
            [record] = await uow.evidence.chain(tenant_id)
        assert record.metrics == {}
        assert record.verdict != "pass"


class TestAnIncompleteScreenCannotPass:
    async def test_zero_violations_from_a_screen_is_not_a_pass(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The whole reason the two-stage design exists. A lower bound of zero
        is not "clean" — it is "not established" — and reporting it as a pass
        is a false assurance about exactly the columns whose validation SQL
        cannot express."""
        await _control(started_database, tenant_id, SCREENED)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=1000, violating_rows=0)
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)

        assert record.verdict == "indeterminate"
        assert "lower bound" in record.detail
        assert "residual" in record.detail

    async def test_a_complete_query_still_passes(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The counterfactual. A rule that downgraded everything would be
        useless and would be switched off."""
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=1000, violating_rows=0)
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)
        assert record.verdict == "pass"

    async def test_a_screen_that_found_violations_still_fails(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A screen is a *necessary* condition: what it rejects is genuinely
        invalid, so a failure from one is real. Only the pass is in doubt."""
        await _control(started_database, tenant_id, SCREENED)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=1000, violating_rows=7)
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)
        assert record.verdict == "fail"


class TestSamples:
    async def test_failing_rows_are_kept_when_a_sampler_is_given(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=100, violating_rows=3),
                sample=lambda _q: [{"account_id": "A1"}, {"account_id": "A2"}],
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)
            stored = await uow.samples.get(record.samples_digest)

        assert record.sample_count == 2
        assert stored is not None
        assert stored.row_count == 2

    async def test_a_passing_control_is_not_sampled(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Sampling a passing control reads rows nobody needs and puts personal
        data on a retention clock for no reason."""
        sampled: list[str] = []
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=100, violating_rows=0),
                sample=lambda q: sampled.append(q) or [],  # type: ignore[func-returns-value]
            ).execute_all()
        assert sampled == []

    async def test_a_sampling_failure_does_not_lose_the_verdict(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The verdict was established by the metric query. What is lost is the
        ability to show which rows, and that is a smaller loss than discarding
        the finding."""

        def broken(_query: str) -> list[dict[str, Any]]:
            raise RuntimeError("no permission to read rows")

        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=100, violating_rows=3),
                sample=broken,
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)

        assert record.verdict == "fail"
        assert record.sample_count == 0

    async def test_no_sampler_still_produces_verdicts(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A deployment that must not move rows supplies no sampler and still
        gets a working control estate."""
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=100, violating_rows=3)
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)
        assert record.verdict == "fail"
        assert record.samples_digest == ""


class TestRunLifecycle:
    async def test_the_run_is_opened_before_anything_executes(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """If the process dies mid-run the row stays 'running', and
        unfinished() surfaces it — a run that vanished silently means every
        screen quietly under-reports."""
        seen: list[int] = []
        await _control(started_database, tenant_id, CLEAN)

        async with started_database.unit_of_work() as uow:

            def watch(_query: str) -> list[dict[str, float]]:
                # Inside execution: the run row must already exist.
                seen.append(1)
                return [{"scanned_rows": 1.0, "violating_rows": 0.0}]

            run_ids_before: list[str] = []

            class Watching(ControlRun):
                async def _run_one(self, version: Any, run_id: str) -> Any:
                    run_ids_before.append(run_id)
                    return await super()._run_one(version, run_id)

            await Watching(uow, tenant_id, execute=watch).execute_all()

        assert seen == [1]
        assert run_ids_before

    async def test_a_run_where_everything_errored_is_still_complete(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """'Complete' means the run finished, not that everything passed.
        Conflating the two would hide a total outage behind a green run — so
        the status says it finished and the verdicts say what happened."""
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(uow, tenant_id, execute=exploding()).execute_all()
            [run] = await uow.evidence_runs.recent(tenant_id)
            failing = await uow.evidence.failing(tenant_id)

        assert run.status == "complete"
        assert [record.verdict for record in failing] == ["error"]

    async def test_an_estate_with_no_live_controls_says_so(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=1)
            ).execute_all()
        assert "no controls were live" in report.describe()


class TestOnlyWhatIsDue:
    async def test_by_default_everything_live_runs(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Somebody typing 'prama control run' means now."""
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=10, violating_rows=0)
            ).execute_all()
        assert len(report.outcomes) == 1
        assert report.skipped == ()

    async def test_a_control_that_just_ran_is_not_due_again(
        self, started_database: Database, tenant_id: str
    ) -> None:
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            first = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=10, violating_rows=0),
                respect_schedule=True,
            ).execute_all()
            second = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=10, violating_rows=0),
                respect_schedule=True,
            ).execute_all()

        # First pass: never run, so due immediately. Second: daily, so not.
        assert len(first.outcomes) == 1
        assert second.outcomes == ()
        assert [item.reason for item in second.skipped] == ["not_due"]

    async def test_a_failing_control_still_counts_as_having_run(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """A control failing to execute every hour has *run* every hour.
        Treating it as never-run would make the scheduler retry continuously
        while the source is down — one broken control becoming a load
        problem."""
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=exploding(), respect_schedule=True
            ).execute_all()
            again = await ControlRun(
                uow, tenant_id, execute=exploding(), respect_schedule=True
            ).execute_all()
        assert again.outcomes == ()

    async def test_an_unreadable_schedule_is_reported_not_defaulted(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """It will never run again and has no verdict to say so."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id, identity="i1", pql=CLEAN, schedule="30 6 * * 1-5"
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")

        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=10, violating_rows=0),
                respect_schedule=True,
            ).execute_all()

        assert report.outcomes == ()
        assert len(report.unschedulable) == 1
        assert "never run until it is fixed" in report.describe()

    async def test_a_manual_control_is_not_run_by_a_timer(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id, identity="i1", pql=CLEAN, schedule="manual"
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
            report = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=10, violating_rows=0),
                respect_schedule=True,
            ).execute_all()

        assert report.outcomes == ()
        assert [item.reason for item in report.skipped] == ["manual"]
        assert report.unschedulable == ()

    async def test_a_manual_control_still_runs_when_asked(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """That is what 'manual' means, and a runner that refused it would
        leave the control unrunnable by any route."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id, identity="i1", pql=CLEAN, schedule="manual"
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
            report = await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=10, violating_rows=0)
            ).execute_all()
        assert len(report.outcomes) == 1


class TestAnEstateWithMoreThanOneSource:
    async def test_a_pass_runs_only_what_its_source_holds(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """One executor speaks to one source. Running every control against
        every source would produce a table-not-found error for each control
        that lives elsewhere, and bury the real findings under them."""
        await _control(started_database, tenant_id, CLEAN, identity="here")
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="there",
                pql=(
                    "CHECK ledger_feed.amount IS NOT NULL SEVERITY major "
                    "DIMENSION completeness BECAUSE 'why'"
                ),
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")

        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=10, violating_rows=0),
                datasets={"positions_eod"},
            ).execute_all()

        assert [o.record.dataset for o in report.outcomes] == ["positions_eod"]

    async def test_what_the_pass_could_not_reach_is_counted(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """ "This pass covered 1 of the estate's 2 controls" is a fact the
        reader needs. A run that reported one and said nothing about the other
        reads as an estate of one."""
        await _control(started_database, tenant_id, CLEAN, identity="here")
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="there",
                pql=(
                    "CHECK ledger_feed.amount IS NOT NULL SEVERITY major "
                    "DIMENSION completeness BECAUSE 'why'"
                ),
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")

        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=10, violating_rows=0),
                datasets={"positions_eod"},
            ).execute_all()

        elsewhere = [s for s in report.skipped if s.reason == "another_source"]
        assert [s.dataset for s in elsewhere] == ["ledger_feed"]
        assert "1 not due" in report.describe()

    async def test_being_on_another_source_is_not_a_defect(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """An estate with four sources runs four passes, and each legitimately
        leaves the other three alone. Only an unreadable schedule is a defect."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id, identity="there", pql=CLEAN
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
            report = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=1),
                datasets={"somewhere_else"},
            ).execute_all()

        assert report.unschedulable == ()
        assert report.outcomes == ()

    async def test_no_filter_means_everything(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """Right for a single-source estate and for somebody running by hand."""
        await _control(started_database, tenant_id, CLEAN)
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow, tenant_id, execute=rows_for(scanned_rows=10, violating_rows=0)
            ).execute_all()
        assert len(report.outcomes) == 1


class TestARunThatDiedIsVisible:
    """Finding X5. The module docstring promised a recovery property the code
    could not have.

    "A run is opened before it does anything. If the process dies mid-run the
    row stays `running`, and `unfinished()` surfaces it — because a run that
    vanished silently means every screen quietly under-reports."

    `evidence_runs.start()` only flushed, and the class docstring said the
    opposite in as many words — "a run is one transaction, so the run row, its
    records and its samples commit together". Both cannot be true. As
    implemented the transaction won: a process that died mid-run had its
    transaction rolled back by the database, so there was no row at all.
    `unfinished()` returned `[]`, and the operations screen rendered that to an
    operator as "0 unfinished runs", which reads as healthy.

    The existing coverage asserted the run id exists *in memory* during
    execution. Durability was never checked, so the counterfactual was never
    written.
    """

    async def test_the_row_survives_a_transaction_that_never_commits(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The crash, as the database sees one: work in flight, rolled back."""
        await _control(started_database, tenant_id, CLEAN, identity="crash")

        run_id = ""
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=1000, violating_rows=0),
                engine="sqlite",
            ).execute_all()
            run_id = report.run_id
            # Everything this transaction did after the marker is discarded,
            # which is what a process dying mid-run amounts to.
            await uow.rollback()

        async with started_database.unit_of_work() as uow:
            rows = await uow.evidence_runs.recent(tenant_id)
            assert any(str(row.id) == run_id for row in rows), (
                "the run vanished with the transaction; nothing knows it ever started"
            )

    async def test_an_ordinary_run_still_completes(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The counterfactual. A marker committed early must not leave every
        run looking unfinished."""
        await _control(started_database, tenant_id, CLEAN, identity="ok")
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow,
                tenant_id,
                execute=rows_for(scanned_rows=1000, violating_rows=0),
                engine="sqlite",
            ).execute_all()
            run_id = report.run_id

        async with started_database.unit_of_work() as uow:
            assert not [
                r for r in await uow.evidence_runs.unfinished(tenant_id) if str(r.id) == run_id
            ], "a completed run is reported as unfinished"
