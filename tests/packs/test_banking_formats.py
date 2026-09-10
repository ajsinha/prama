"""FIX, ISO 8583 and FpML.

Three formats, and in each one the same lesson: the thing that looks like a flat
map of values is not one, and flattening it produces plausible numbers rather
than an error.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from prama.packs.banking import fix, fpml, iso8583

# -- FIX -------------------------------------------------------------------


def fix_message(body: str, *, delimiter: str = fix.SOH, fix_totals: bool = True) -> str:
    raw = f"8=FIX.4.4{delimiter}9=0{delimiter}{body}10=000{delimiter}"
    if not fix_totals:
        return raw
    length = fix.body_length(raw, delimiter)
    raw = f"8=FIX.4.4{delimiter}9={length}{delimiter}{body}10=000{delimiter}"
    return raw.replace("10=000", f"10={fix.checksum(raw, delimiter)}")


ORDER_BODY = "35=D\x0149=SENDER\x0156=TARGET\x0111=ORD1\x0155=IBM\x0154=1\x0138=100\x0140=2\x01"


class TestFixIsNotAFlatMap:
    def test_a_well_formed_order_validates_its_own_totals(self) -> None:
        message = fix.parse(fix_message(ORDER_BODY))
        assert message.msg_type == "D"
        assert message.is_well_formed, [d.render() for d in message.defects]

    def test_a_wrong_checksum_is_caught(self) -> None:
        """The protocol's only integrity check, and the one a parser that reads
        tag 10 as an ordinary field throws away."""
        raw = fix_message(ORDER_BODY).replace("10=", "10=")
        raw = raw[: raw.rindex("10=")] + "10=999\x01"
        [defect] = [d for d in fix.parse(raw).defects if d.tag == 10]
        assert "the bytes give" in defect.problem

    def test_a_wrong_body_length_is_caught(self) -> None:
        raw = fix_message(ORDER_BODY).replace("9=", "9=", 1)
        raw = raw.replace(f"9={fix.body_length(raw)}\x01", "9=999\x01", 1)
        assert any(d.tag == 9 for d in fix.parse(raw).defects)

    def test_a_missing_required_field_is_named(self) -> None:
        body = ORDER_BODY.replace("54=1\x01", "")
        [defect] = [d for d in fix.parse(fix_message(body)).defects if d.tag == 54]
        assert "required for message type D" in defect.problem

    def test_a_repeating_group_keeps_every_entry(self) -> None:
        """NoLegs=2 introduces two legs. Flattened, the last one wins — and a
        two-leg swap read that way is a one-leg swap that balances."""
        body = (
            "35=AE\x01571=T1\x0155=SWAP\x0132=100\x0131=1.5\x01"
            "555=2\x01600=LEG1\x01610=EUR\x01600=LEG2\x01610=USD\x01"
        )
        message = fix.parse(fix_message(body))
        assert len(message.groups[555]) == 2
        assert message.groups[555][0].get(600) == "LEG1"
        assert message.groups[555][1].get(600) == "LEG2"

    def test_a_truncated_group_is_a_finding(self) -> None:
        """The count is a statement by the sender; the entries are what
        arrived. Trusting the count reports a truncated group as complete."""
        body = "35=AE\x01571=T1\x0155=S\x0132=1\x0131=1\x01555=3\x01600=LEG1\x01"
        [defect] = [d for d in fix.parse(fix_message(body)).defects if d.tag == 555]
        assert "declares 3 entr(ies) and carries 1" in defect.problem

    def test_the_delimiter_is_soh_and_a_pipe_is_reported(self) -> None:
        """Pipes are what a log viewer shows. A message that arrived
        pipe-delimited on a session is itself a finding."""
        piped = fix.parse(fix_message(ORDER_BODY.replace("\x01", "|"), delimiter="|"))
        assert piped.arrived_display_delimited
        assert not fix.parse(fix_message(ORDER_BODY)).arrived_display_delimited

    def test_fields_come_back_with_business_names(self) -> None:
        """A control written against tag 55 is a control nobody can review."""
        named = fix.parse(fix_message(ORDER_BODY)).named()
        assert named["symbol"] == "IBM"
        assert named["cl_ord_id"] == "ORD1"
        assert named["msg_type"] == "D"

    def test_a_session_log_splits_into_messages(self) -> None:
        log = fix_message(ORDER_BODY) + fix_message(ORDER_BODY)
        assert len(fix.split(log)) == 2

    def test_a_malformed_field_does_not_lose_the_message(self) -> None:
        raw = fix_message("35=D\x01garbage\x0155=IBM\x0111=X\x0154=1\x0138=1\x0140=2\x01")
        message = fix.parse(raw)
        assert message.get(55) == "IBM"
        assert any("not a tag=value" in d.problem for d in message.defects)


# -- ISO 8583 --------------------------------------------------------------


def bitmap_for(fields: list[int]) -> str:
    bits = ["0"] * 64
    for field in fields:
        bits[field - 1] = "1"
    return "".join(f"{int(''.join(bits[i : i + 4]), 2):X}" for i in range(0, 64, 4))


CARD = (
    "0200"
    + bitmap_for([2, 3, 4, 7, 11, 49])
    + "16"
    + "4111111111111111"
    + "000000"
    + "000000012345"
    + "0910120000"
    + "000001"
    + "826"
)


class TestIso8583:
    def test_the_bitmap_decides_what_is_present(self) -> None:
        message = iso8583.parse(CARD)
        assert message.mti == "0200"
        assert message.present == (2, 3, 4, 7, 11, 49)
        assert message.is_well_formed

    def test_the_pan_is_masked_by_default(self) -> None:
        """A parser that hands a full card number to whatever called it has put
        it in that caller's logs."""
        message = iso8583.parse(CARD)
        assert message.values[2] == "************1111"
        assert "4111111111111111" not in repr(message.named())

    def test_the_full_pan_needs_an_explicit_call(self) -> None:
        """Named so it appears in a code review."""
        assert iso8583.parse(CARD).unmasked(2) == "4111111111111111"

    def test_masking_preserves_the_length(self) -> None:
        """A thirteen-digit Visa and a sixteen-digit one are different
        findings, and the length is what a control asserts on."""
        assert len(iso8583.mask_pan("4111111111111")) == 13
        assert len(iso8583.mask_pan("4111111111111111")) == 16

    def test_the_amount_has_its_decimal_point_restored(self) -> None:
        """Minor units with no separator: read as an integer this is ten
        thousand times too large, which is noticed at settlement rather than at
        parse time."""
        assert iso8583.parse(CARD).amount() == Decimal("123.45")

    def test_a_variable_length_field_excludes_its_own_prefix(self) -> None:
        """Including it turns a 16-digit PAN into 1655…, a perfectly plausible
        18-digit card number."""
        assert iso8583.parse(CARD).unmasked(2) == "4111111111111111"

    def test_a_secondary_bitmap_is_not_read_as_a_field(self) -> None:
        """Bit 1 says a second bitmap follows. Treating it as data loses sixteen
        bytes off the front of field 2 and reports somebody else's PAN."""
        primary = bitmap_for([1, 2, 3])
        secondary = bitmap_for([])
        message = iso8583.parse("0200" + primary + secondary + "16" + "4111111111111111" + "000000")
        assert 1 not in message.present
        assert message.unmasked(2) == "4111111111111111"

    def test_a_truncated_message_is_a_finding_not_a_crash(self) -> None:
        message = iso8583.parse(CARD[:40])
        assert not message.is_well_formed

    def test_a_message_too_short_for_a_bitmap_says_so(self) -> None:
        message = iso8583.parse("0200")
        assert "too short" in message.defects[0].problem


# -- FpML ------------------------------------------------------------------


def swap(*, second_currency: str = "EUR", drop_direction: bool = False) -> str:
    receiver = "" if drop_direction else '<receiverPartyReference href="PartyA"/>'
    return f"""<dataDocument xmlns="http://www.fpml.org/FpML-5/confirmation" version="5-10">
 <trade><tradeHeader><partyTradeIdentifier><tradeId>SW-001</tradeId></partyTradeIdentifier>
 <tradeDate>2026-09-10</tradeDate></tradeHeader>
 <swap>
  <swapStream><payerPartyReference href="PartyA"/><receiverPartyReference href="PartyB"/>
   <calculationPeriodAmount><calculation>
    <notionalSchedule><notionalStepSchedule><initialValue>10000000</initialValue>
    <currency>EUR</currency></notionalStepSchedule></notionalSchedule>
    <fixedRateSchedule><initialValue>0.0325</initialValue></fixedRateSchedule>
   </calculation></calculationPeriodAmount></swapStream>
  <swapStream><payerPartyReference href="PartyB"/>{receiver}
   <calculationPeriodAmount><calculation>
    <notionalSchedule><notionalStepSchedule><initialValue>10000000</initialValue>
    <currency>{second_currency}</currency></notionalStepSchedule></notionalSchedule>
    <floatingRateCalculation><floatingRateIndex>EUR-EURIBOR</floatingRateIndex></floatingRateCalculation>
   </calculation></calculationPeriodAmount></swapStream>
 </swap></trade>
 <party id="PartyA"/><party id="PartyB"/></dataDocument>"""


class TestFpml:
    def test_both_legs_keep_their_direction(self) -> None:
        """Not "counterparty": a two-leg swap has four party references and the
        same firm appears on both sides of different legs."""
        trade = fpml.parse(swap())
        assert trade.is_two_sided
        assert trade.legs[0].payer == "PartyA"
        assert trade.legs[0].receiver == "PartyB"
        assert trade.legs[1].payer == "PartyB"
        assert trade.legs[1].receiver == "PartyA"

    def test_two_legs_is_not_the_same_claim_as_two_sided(self) -> None:
        """Counting legs answers yes for a document where a leg has no payer.
        Downstream, "two-sided" is read as "the offsetting obligation is
        known", which is exactly what that document does not give."""
        trade = fpml.parse(swap(drop_direction=True))
        assert trade.has_two_legs
        assert not trade.is_two_sided

    def test_a_leg_signs_itself_for_a_party(self) -> None:
        trade = fpml.parse(swap())
        assert trade.legs[0].signed_for("PartyB") == Decimal("10000000")
        assert trade.legs[0].signed_for("PartyA") == Decimal("-10000000")

    def test_a_party_not_on_the_leg_gets_none_rather_than_zero(self) -> None:
        """Zero is a position; this is the absence of one."""
        assert fpml.parse(swap()).legs[0].signed_for("PartyC") is None

    def test_a_leg_without_direction_is_named(self) -> None:
        """Its sign cannot be determined, and any position built from it is
        wrong in a direction nobody can predict."""
        trade = fpml.parse(swap(drop_direction=True))
        assert any("who pays and who receives" in defect for defect in trade.defects)
        assert not trade.legs[1].has_direction

    def test_a_matched_swap_nets_to_zero(self) -> None:
        assert fpml.parse(swap()).net_for("PartyA") == Decimal(0)

    def test_a_cross_currency_trade_refuses_to_net(self) -> None:
        """A total across currencies is a number in no currency at all, and it
        looks exactly like a number in one."""
        trade = fpml.parse(swap(second_currency="USD"))
        assert trade.is_cross_currency
        assert trade.net_for("PartyA") is None

    def test_the_rate_and_the_index_are_both_kept(self) -> None:
        trade = fpml.parse(swap())
        assert trade.legs[0].kind == "fixed"
        assert trade.legs[0].rate == Decimal("0.0325")
        assert trade.legs[1].kind == "floating"
        assert trade.legs[1].index == "EUR-EURIBOR"

    def test_the_version_is_reported_rather_than_enforced(self) -> None:
        assert fpml.parse(swap()).version == "5-10"

    def test_malformed_xml_is_a_defect_not_an_exception(self) -> None:
        trade = fpml.parse("<dataDocument><unclosed>")
        assert trade.defects
        assert trade.legs == ()

    def test_a_document_with_no_legs_says_it_states_no_obligation(self) -> None:
        empty = (
            '<dataDocument xmlns="http://www.fpml.org/FpML-5/confirmation"><trade/></dataDocument>'
        )
        assert any("no legs" in defect for defect in fpml.parse(empty).defects)


class TestAllThreeShareTheDiscipline:
    @pytest.mark.parametrize(
        "parse,broken",
        [
            (fix.parse, "not a fix message at all"),
            (iso8583.parse, "xx"),
            (fpml.parse, "<broken"),
        ],
    )
    def test_nothing_raises_on_rubbish(self, parse, broken: str) -> None:
        """One bad message in four thousand must not stop the rest being
        checked: that turns a data defect into an outage, and the outage is what
        gets the control disabled."""
        parse(broken)


class TestNoParserTruthTestsAnElement:
    """A guard, because I got this wrong twice.

    ``element or fallback`` truth-tests an ElementTree Element. It is deprecated
    *and* ambiguous: an element with no children is falsy while being perfectly
    present, so the fallback fires on a real element and the parser silently
    reads the wrong subtree. The symptom is a field that comes back empty, which
    reads as missing data rather than as a parser bug.
    """

    def test_the_xml_parsers_use_is_none_rather_than_truthiness(self) -> None:
        import ast
        import pathlib

        from prama.packs.banking import fpml, iso20022

        for module in (fpml, iso20022):
            tree = ast.parse(pathlib.Path(module.__file__).read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or):
                    continue
                for value in node.values:
                    # A bare call to _find inside an `or` is the shape of the
                    # bug: its result is an Element or None, and `or` asks the
                    # Element whether it is truthy.
                    if (
                        isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Name)
                        and value.func.id == "_find"
                    ):
                        raise AssertionError(
                            f"{module.__name__} line {value.lineno}: `_find(...) or ...` "
                            "truth-tests an Element. Use an explicit `is None` check."
                        )
