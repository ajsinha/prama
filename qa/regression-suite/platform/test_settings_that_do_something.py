"""A setting that is read by nothing is a promise the product does not keep.

QA round 2, `CFG-036`, `CFG-014`, `CFG-205`, `PCK-209`, `SCH-014`. Five values
carried through configuration, documentation or a template and applied nowhere
— which is the "derive, never restate" rule failing in its most expensive
direction: the restatement is the part a reader believes.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

import pytest

from prama.recon.match import MatchKey, ToleranceMatcher


class TestThePluginMechanismIsActuallyCalled:
    """`CFG-036`, and `BE-179` with it.

    `load_entry_points` had no caller anywhere — not in `src/`, not in
    `tests/`. So `plugins.entry_point_groups` and `plugins.disabled` were read
    by nothing, and the implementation-hash freeze that stops a validator's
    code changing under a sealed plan could never fire, because the registry it
    guards was always empty.

    That is the defect `install_shipped`'s own docstring was written about, one
    layer along: `install()` was written, tested, and called only from tests.
    A mechanism nothing calls is indistinguishable from one that does not
    exist, and both pass their unit tests.
    """

    def test_the_plugin_bootstrap_loads_entry_points(self) -> None:
        """Validators are loaded by the bootstrap both entry points call.

        They were loaded from `install_shipped`; every plugin group now has its
        loader in `prama.plugins.LOADERS`, called by `prama.plugins.bootstrap`.
        """
        import inspect

        from prama import plugins

        assert "load_entry_points" in inspect.getsource(plugins.LOADERS["prama.validators"])
        assert "LOADERS" in inspect.getsource(plugins.bootstrap)

    def test_the_disabled_list_is_a_real_setting(self) -> None:
        """It lived in the shipped YAML and in no defaults mapping.

        `defaults.py` states that it is the authority and the file is
        documentation, so a key present only in the file is one nobody can rely
        on — and this one was read by nothing either way.
        """
        from prama.core.config.defaults import DEFAULTS

        assert "disabled" in DEFAULTS["plugins"]

    def test_a_disabled_plugin_is_not_loaded(self) -> None:
        from prama.classify.plugins import load_entry_points
        from prama.classify.validators import ValidatorRegistry

        registry = ValidatorRegistry()
        before = len(registry)
        # Nothing advertises validators in this environment, so the assertion
        # is about the argument being accepted and honoured rather than about a
        # count. A signature that cannot express "off" cannot implement it.
        load_entry_points(registry, disabled=["anything"])
        assert len(registry) == before


class TestTheCookieCommentMatchesTheCookie:
    """`CFG-014`. The comment said "off in development"; the value was True.

    Documentation-only, and the most misleading possible pairing: a reader
    checking whether the shipped default is safe was told it is not.
    """

    def test_the_default_is_on(self) -> None:
        from prama.core.config.defaults import DEFAULTS

        assert DEFAULTS["security"]["cookies_https_only"] is True

    def test_the_comment_does_not_contradict_it(self) -> None:
        import inspect

        from prama.core.config import defaults

        source = inspect.getsource(defaults)
        block = source.split("cookies_https_only")[0][-600:]
        assert "Off in development only" not in block


class TestASuccessfulPassIsNotACrash:
    """`CFG-205`. Restart accounting ran after a *successful* ALWAYS iteration.

    A poller finishing its pass — the whole point of the policy — had its
    restart total incremented, was throttled by exponential backoff toward
    thirty seconds, and could be given up on as a crash loop having never
    failed once.
    """

    async def test_a_healthy_always_task_is_not_counted_as_restarting(self) -> None:
        import asyncio

        from prama.core.concurrency.supervisor import RestartPolicy, TaskSupervisor

        passes = 0

        async def poller() -> None:
            nonlocal passes
            passes += 1
            await asyncio.sleep(0)

        async with TaskSupervisor("qa") as supervisor:
            handle = supervisor.spawn("poller", poller, policy=RestartPolicy.ALWAYS)
            await asyncio.sleep(0.05)

        assert passes > 1, "the task did not loop at all"
        assert handle.restarts == 0, (
            f"a task that never failed was counted as restarting {handle.restarts} times"
        )


class TestAToleranceAppliesToTheColumnItNames:
    """`PCK-209`. The window shifted the *last* key component, whatever it was.

    `cashbook-to-statement` keys on (account, value_date, reference), so a
    window of three days shifted a reference string and paired nothing — while
    the setting read as configured and working. Two rows one day apart appeared
    as one missing and one extra: the phantom break population the tolerance
    exists to remove.
    """

    KEY = MatchKey(
        left=("account", "value_date", "reference"),
        right=("account", "value_date", "reference"),
    )
    LEFT: ClassVar[list[dict[str, str]]] = [
        {"account": "A1", "value_date": "2026-09-01", "reference": "R1"}
    ]
    RIGHT: ClassVar[list[dict[str, str]]] = [
        {"account": "A1", "value_date": "2026-09-03", "reference": "R1"}
    ]

    def test_naming_the_date_column_pairs_the_rows(self) -> None:
        report = ToleranceMatcher(self.KEY, window=3, near="value_date").match(
            self.LEFT, self.RIGHT
        )
        assert len(report.pairs) == 1
        assert not report.unmatched_left and not report.unmatched_right

    def test_the_old_behaviour_is_still_available(self) -> None:
        """The counterfactual.

        Templates whose date genuinely is the last component rely on it, so
        the default must not change under them.
        """
        key = MatchKey(left=("account", "as_of_date"), right=("account", "as_of_date"))
        report = ToleranceMatcher(key, window=2).match(
            [{"account": "A1", "as_of_date": "2026-09-01"}],
            [{"account": "A1", "as_of_date": "2026-09-02"}],
        )
        assert len(report.pairs) == 1

    def test_a_column_outside_the_key_is_refused(self) -> None:
        """Naming a column the key does not contain is a typo, not a no-op."""
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="not part of this match key"):
            ToleranceMatcher(self.KEY, window=3, near="settlement_date")


class TestACalendarScheduleIsStaggeredToo:
    """`SCH-014`. `spec.parse` computed the offset and passed it to intervals only.

    Every control declared `06:30 TARGET2` fired at exactly 06:30, together.
    That is the shape that takes a source down, and the stagger existed — it
    simply reached one of the two trigger kinds.
    """

    def test_two_controls_at_the_same_time_do_not_fire_together(self) -> None:
        from prama.schedule.due import _stagger
        from prama.schedule.spec import parse

        # Timezone-aware: `expected_at` returns an aware datetime, because a
        # business calendar without a timezone is a schedule that is wrong
        # twice a year.
        moment = datetime(2026, 9, 14, 3, 0, tzinfo=UTC)
        fires = {
            parse("06:30", offset_minutes=_stagger(control)).next_after(moment)
            for control in ("control-alpha", "control-beta", "control-gamma")
        }
        assert len(fires) > 1, "every control fired at the identical moment"

    def test_the_same_control_always_gets_the_same_slot(self) -> None:
        """Derived from the id, not random: a re-staggering estate on every
        deploy makes load unpredictable and history incomparable."""
        from prama.schedule.due import _stagger

        assert _stagger("control-alpha") == _stagger("control-alpha")

    def test_the_declared_time_is_what_is_described(self) -> None:
        """An author who wrote 06:30 must not read 06:34 back.

        The offset is load-spreading, not a property of the schedule anybody
        declared, and describing it invites a bug report about the wrong thing.
        """
        from prama.schedule.spec import parse

        assert "06:30" in parse("06:30", offset_minutes=17).describe()
