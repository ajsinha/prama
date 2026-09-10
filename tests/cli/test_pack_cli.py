"""``prama pack`` — inspecting a domain pack before trusting it.

A pack that cannot be inspected from a terminal is a pack nobody audits, and
the question these commands exist for is the one asked *before* an examination
rather than during: what does this pack not claim?

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io

from prama.cli.base import EXIT_ERROR, EXIT_OK, Application
from prama.cli.commands import all_commands
from prama.core import pjson


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    return Application(all_commands()).run(argv, out=out), out.getvalue()


class TestList:
    def test_it_names_what_the_pack_ships(self) -> None:
        code, text = run(["pack", "list"])
        assert code == EXIT_OK
        assert "TARGET2" in text
        assert "IBAN_BIC_CONSISTENT" in text
        assert "SWIFT MT" in text

    def test_it_points_at_the_boundary(self) -> None:
        """A list of capabilities invites a reader to assume the rest."""
        _, text = run(["pack", "list"])
        assert "does NOT discharge" in text

    def test_json_output_is_machine_readable(self) -> None:
        code, text = run(["--json", "pack", "list"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert len(payload["calendars"]) == 4
        assert payload["obligations"] == 9
        assert len(payload["reconciliations"]) == 9


class TestClaims:
    def test_it_separates_discharged_from_merely_supported(self) -> None:
        """Naming the boundary is what makes the covered part believable."""
        code, text = run(["pack", "claims"])
        assert code == EXIT_OK
        assert "Discharged by controls" in text
        assert "NOT discharged by a control" in text

    def test_every_discharged_obligation_is_cited(self) -> None:
        _, text = run(["pack", "claims"])
        assert "BCBS239-P3-CDE-COMPLETE" in text
        assert "Principle 3" in text

    def test_it_says_why_the_boundary_is_where_it_is(self) -> None:
        _, text = run(["pack", "claims"])
        assert "cannot defend at an examination" in text

    def test_json_output_carries_both_halves(self) -> None:
        code, text = run(["--json", "pack", "claims"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert payload["discharged"] == ["P3", "P4", "P5"]
        assert "P1" in payload["supported_not_discharged"]


class TestCalendar:
    def test_it_computes_a_year_that_no_table_was_written_for(self) -> None:
        """The reason the calendars are rules. 2040 is inside the horizon and
        nobody typed it."""
        code, text = run(["pack", "calendar", "TARGET2", "--year", "2040"])
        assert code == EXIT_OK
        assert "2040-12-25" in text

    def test_target2_closes_six_times(self) -> None:
        _, text = run(["pack", "calendar", "TARGET2", "--year", "2027"])
        assert "6 closure(s)" in text

    def test_it_states_what_it_does_not_know(self) -> None:
        """A calendar that listed its closures and stopped invites the reader to
        believe it knows about all of them."""
        _, text = run(["pack", "calendar", "London", "--year", "2027"])
        assert "no ad-hoc closures supplied" in text

    def test_an_unknown_calendar_is_refused_with_the_list(self) -> None:
        code, _ = run(["pack", "calendar", "TOKYO"])
        assert code == EXIT_ERROR

    def test_json_output_carries_the_dates(self) -> None:
        code, text = run(["--json", "pack", "calendar", "NYSE", "--year", "2027"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert payload["calendar"] == "NYSE"
        assert all("date" in row for row in payload["closures"])


class TestReconciliation:
    def test_it_lists_them_all_when_none_is_named(self) -> None:
        code, text = run(["pack", "reconciliation"])
        assert code == EXIT_OK
        assert "cashbook-to-statement" in text
        assert "mt-to-mx" in text

    def test_it_gives_the_reasoning_not_just_the_choice(self) -> None:
        """A key supplied without its reasoning is one somebody changes on a
        hunch."""
        code, text = run(["pack", "reconciliation", "cashbook-to-statement"])
        assert code == EXIT_OK
        assert "why these keys:" in text
        assert "tolerance:" in text
        assert "expect breaks:" in text

    def test_an_unknown_template_is_refused_with_the_list(self) -> None:
        code, _ = run(["pack", "reconciliation", "no-such-thing"])
        assert code == EXIT_ERROR

    def test_json_output_is_machine_readable(self) -> None:
        code, text = run(["--json", "pack", "reconciliation", "mt-to-mx"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert payload["key_roles"] == ["payment_reference"]


class TestSoc2:
    def test_it_leads_with_the_gaps(self) -> None:
        """A readiness matrix leading with what is covered is one whose gaps are
        read last or not at all."""
        code, text = run(["pack", "soc2"])
        assert code == EXIT_OK
        assert text.index("Gaps in the product") < text.index("Evidenceable today")

    def test_it_says_readiness_is_not_compliance(self) -> None:
        """This is exactly the artefact somebody would use to mislead an
        auditor."""
        _, text = run(["pack", "soc2"])
        assert "Readiness is not compliance" in text

    def test_every_criterion_says_what_an_auditor_asks_for(self) -> None:
        _, text = run(["pack", "soc2"])
        assert text.count("auditor asks for:") >= 10

    def test_json_output_carries_the_gaps(self) -> None:
        code, text = run(["--json", "pack", "soc2"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert "CC6.8" in payload["gaps"]
        assert payload["caveat"]
