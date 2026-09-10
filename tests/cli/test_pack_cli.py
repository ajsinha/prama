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
    def test_it_leads_with_what_needs_work(self) -> None:
        """A readiness matrix leading with what is covered is one whose gaps are
        read last or not at all."""
        code, text = run(["pack", "soc2"])
        assert code == EXIT_OK
        assert text.index("Gaps in the product") < text.index("Evidenceable today")
        assert text.index("Partial") < text.index("Evidenceable today")

    def test_an_empty_gap_section_still_appears(self) -> None:
        """A section that silently vanishes reads as "nothing needs work", and
        the partial criteria still do."""
        _, text = run(["pack", "soc2"])
        assert "Gaps in the product" in text
        if "none outright" in text:
            assert "not the same as covered" in text

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


class TestParse:
    """``prama pack parse`` — one message, and what is wrong with it.

    The command exists because the first question about a rejected payment is
    "is the message wrong, or is our reader wrong?", and answering it should not
    require a running platform.
    """

    def fix_file(self, tmp_path, body: str = ""):
        from prama.packs.banking import fix

        body = body or "35=D\x0149=S\x0156=T\x0111=ORD1\x0155=IBM\x0154=1\x0138=1\x0140=2\x01"
        raw = f"8=FIX.4.4\x019=0\x01{body}10=000\x01"
        raw = f"8=FIX.4.4\x019={fix.body_length(raw)}\x01{body}10=000\x01"
        raw = raw.replace("10=000", f"10={fix.checksum(raw)}")
        path = tmp_path / "order.fix"
        path.write_text(raw)
        return path

    def iso8583_file(self, tmp_path):
        bits = ["0"] * 64
        for field in (2, 3, 4, 7, 11, 49):
            bits[field - 1] = "1"
        bitmap = "".join(f"{int(''.join(bits[i : i + 4]), 2):X}" for i in range(0, 64, 4))
        path = tmp_path / "auth.8583"
        path.write_text(
            "0200"
            + bitmap
            + "16"
            + "4111111111111111"  # 2  PAN, LLVAR
            + "000000"  # 3  processing code
            + "000000012345"  # 4  amount, minor units
            + "0910120000"  # 7  transmission date/time
            + "000001"  # 11 STAN
            + "826"  # 49 currency
        )
        return path

    def fpml_file(self, tmp_path, *, currency: str = "EUR"):
        path = tmp_path / "swap.fpml"
        path.write_text(
            '<dataDocument xmlns="http://www.fpml.org/FpML-5/confirmation" version="5-10">'
            "<trade><tradeHeader><partyTradeIdentifier><tradeId>SW-1</tradeId>"
            "</partyTradeIdentifier></tradeHeader><swap>"
            '<swapStream><payerPartyReference href="A"/><receiverPartyReference href="B"/>'
            "<calculationPeriodAmount><calculation><notionalSchedule><notionalStepSchedule>"
            "<initialValue>100</initialValue><currency>EUR</currency>"
            "</notionalStepSchedule></notionalSchedule></calculation>"
            "</calculationPeriodAmount></swapStream>"
            '<swapStream><payerPartyReference href="B"/><receiverPartyReference href="A"/>'
            "<calculationPeriodAmount><calculation><notionalSchedule><notionalStepSchedule>"
            f"<initialValue>100</initialValue><currency>{currency}</currency>"
            "</notionalStepSchedule></notionalSchedule></calculation>"
            "</calculationPeriodAmount></swapStream></swap></trade></dataDocument>"
        )
        return path

    def test_it_infers_fix_and_reports_a_clean_message(self, tmp_path) -> None:
        code, text = run(["pack", "parse", str(self.fix_file(tmp_path))])
        assert code == EXIT_OK
        assert "fix (inferred)" in text
        assert "No structural defects" in text

    def test_it_infers_iso8583_and_restores_the_decimal_point(self, tmp_path) -> None:
        code, text = run(["pack", "parse", str(self.iso8583_file(tmp_path))])
        assert code == EXIT_OK
        assert "0200" in text
        assert "123.45" in text

    def test_it_never_prints_a_full_pan(self, tmp_path) -> None:
        """The terminal this runs in is somebody's scrollback, and increasingly
        somebody's CI log."""
        _, text = run(["pack", "parse", str(self.iso8583_file(tmp_path))])
        assert "4111111111111111" not in text

    def test_it_infers_fpml_and_names_both_legs(self, tmp_path) -> None:
        code, text = run(["pack", "parse", str(self.fpml_file(tmp_path))])
        assert code == EXIT_OK
        assert "fpml" in text
        assert "legs" in text

    def test_a_named_format_is_not_marked_inferred(self, tmp_path) -> None:
        _, text = run(["pack", "parse", str(self.fix_file(tmp_path)), "--format", "fix"])
        assert "inferred" not in text

    def test_defects_are_reported_rather_than_raised(self, tmp_path) -> None:
        """A message the parser cannot make sense of is a finding about the
        message. Exiting non-zero would make it a finding about the tool."""
        body = "35=D\x0149=S\x0156=T\x0111=ORD1\x0155=IBM\x0138=1\x0140=2\x01"
        code, text = run(["pack", "parse", str(self.fix_file(tmp_path, body))])
        assert code == EXIT_OK
        assert "defect(s):" in text
        assert "54" in text

    def test_an_unrecognisable_file_declines_rather_than_guesses(self, tmp_path, capsys) -> None:
        """Guessing wrong produces a page of findings about a file that was
        never in that format, which reads as a very broken message."""
        path = tmp_path / "notes.txt"
        path.write_text("just some notes about the payment")
        code, _ = run(["pack", "parse", str(path)])
        assert code == EXIT_ERROR
        assert "--format" in capsys.readouterr().err

    def test_a_missing_file_says_so(self, tmp_path, capsys) -> None:
        code, _ = run(["pack", "parse", str(tmp_path / "absent.fix")])
        assert code == EXIT_ERROR
        assert "no such file" in capsys.readouterr().err

    def test_a_refusal_reaches_stderr_not_stdout(self, tmp_path, capsys) -> None:
        """`prama pack parse x.fix > report.txt` must not write a clean-looking
        empty report and leave the reason on the floor."""
        code, out = run(["pack", "parse", str(tmp_path / "absent.fix")])
        assert code == EXIT_ERROR
        assert out == ""
        assert capsys.readouterr().err.strip()

    def test_every_label_is_separated_from_its_value(self, tmp_path) -> None:
        """A fixed column width runs the longest label into its value, and
        `legs directedFalse` reads as a label nobody defined."""
        _, text = run(["pack", "parse", str(self.fpml_file(tmp_path))])
        for line in text.splitlines():
            if line and not line.startswith(" ") and ":" not in line:
                assert "  " in line or line.count(" ") == 0 or line.endswith(".")

    def test_json_output_carries_the_defects(self, tmp_path) -> None:
        code, text = run(["--json", "pack", "parse", str(self.fpml_file(tmp_path))])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert payload["format"] == "fpml"
        assert payload["legs"] == 2

    def test_the_format_list_matches_the_parsers_that_exist(self) -> None:
        """`pack list` advertising a format `pack parse` cannot read is the
        restatement this codebase keeps being bitten by."""
        from prama.cli.pack import _PARSERS

        _, text = run(["pack", "list"])
        for name in _PARSERS:
            assert name.upper()[:3] in text.upper().replace(" ", "")


class TestConcepts:
    def test_it_lists_the_ontology_with_what_identifies_each(self) -> None:
        code, text = run(["pack", "concepts"])
        assert code == EXIT_OK
        assert "Exposure" in text
        assert "identified by: counterparty_id, as_of_date" in text

    def test_it_says_a_tenant_vocabulary_wins(self) -> None:
        """A shipped ontology invites a reader to treat it as the definition."""
        _, text = run(["pack", "concepts"])
        assert "tenant's own wins" in text

    def test_one_concept_shows_where_it_ends(self) -> None:
        code, text = run(["pack", "concepts", "Exposure"])
        assert code == EXIT_OK
        assert "What it is not:" in text
        assert "Gross notional is not exposure" in text

    def test_it_distinguishes_identifying_from_defining(self) -> None:
        """The distinction is the whole basis of recognition; a flat list of
        properties would hide it."""
        _, text = run(["pack", "concepts", "Exposure"])
        assert "! counterparty_id" in text
        assert "* net_notional" in text
        assert "without it, the table is not this concept" in text

    def test_it_names_the_semantic_type_a_property_carries(self) -> None:
        _, text = run(["pack", "concepts", "Instrument"])
        assert "isin [isin]" in text

    def test_an_unknown_concept_is_an_error(self, capsys) -> None:
        code, _ = run(["pack", "concepts", "Sprocket"])
        assert code == EXIT_ERROR

    def test_json_carries_the_boundary(self) -> None:
        code, text = run(["--json", "pack", "concepts"])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert len(payload["concepts"]) == 17
        exposure = next(c for c in payload["concepts"] if c["name"] == "Exposure")
        assert exposure["boundary"]
        assert exposure["identifying"] == ["counterparty_id", "as_of_date"]


class TestRecognise:
    def test_it_recognises_a_complete_table(self) -> None:
        code, text = run(
            ["pack", "recognise", "account_id", "balance_date", "bal_type", "balance", "ccy"]
        )
        assert code == EXIT_OK
        assert "Balance — recognised" in text

    def test_it_maps_each_column_to_the_property_it_spells(self) -> None:
        _, text = run(["pack", "recognise", "deal_id", "execution_time", "venue_mic"])
        assert "deal_id -> trade_id" in text

    def test_it_declines_on_a_shared_shape(self) -> None:
        """Position, Balance and Exposure all carry an amount, a currency and
        an as-of date. Naming one would be a guess wearing the tool's
        authority."""
        code, text = run(["pack", "recognise", "as_of_date", "amount", "currency"])
        assert code == EXIT_OK
        assert "No concept recognised" in text
        assert "Position" not in text

    def test_a_refusal_says_what_such_a_table_usually_is(self) -> None:
        """ "No" is not an answer somebody can act on."""
        _, text = run(["pack", "recognise", "as_of_date", "amount", "currency"])
        assert "references business objects rather than being" in text

    def test_it_says_a_recognition_is_a_proposal(self) -> None:
        """CON-007. The tool proposes; a steward confirms."""
        _, text = run(["pack", "recognise", "account_id", "ccy", "status"])
        assert "steward confirms" in text

    def test_testing_against_one_concept_reports_the_refutation(self) -> None:
        code, text = run(["pack", "recognise", "currency", "status", "--as", "Account"])
        assert code == EXIT_OK
        assert "not_recognised" in text
        assert "account_id" in text

    def test_it_names_the_columns_it_could_not_place(self) -> None:
        _, text = run(["pack", "recognise", "account_id", "ccy", "status", "widget_flag"])
        assert "unplaced: widget_flag" in text

    def test_it_says_which_column_should_validate_as_what(self) -> None:
        _, text = run(["pack", "recognise", "isin", "asset_class", "ccy"])
        assert "expect: isin is isin" in text

    def test_json_carries_every_candidate(self) -> None:
        code, text = run(
            [
                "--json",
                "pack",
                "recognise",
                "account_id",
                "balance_date",
                "bal_type",
                "balance",
                "ccy",
            ]
        )
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert payload["candidates"][0]["concept"] == "Balance"
        assert payload["candidates"][0]["standing"] == "recognised"
