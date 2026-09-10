"""SWIFT MT and ISO 20022, as named business fields.

Parsing a message is not the point; turning it into rows a control can assert on
is. So these tests are mostly about the four things a naive parser gets wrong,
each of which is a defect class rather than a formatting nicety: the comma
decimal, the debit mark, a malformed message taking the file down with it, and
inferring a value that was never stated.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from prama.packs.banking import iso20022, swift

MT940 = """{1:F01BANKGB2LAXXX0000000000}{2:O940BANKDEFFXXXXN}{4:
:20:STMT-2026-09-09
:25:GB33BUKB20201555555555
:28C:00251/001
:60F:C260908EUR10000,00
:61:2609090909C1500,50NTRFCUST-REF-1//BANKREF1
:86:Incoming payment from Acme
:61:260909D250,25NCHGFEE-REF//BANKREF2
:62F:C260909EUR11250,25
-}"""

MT103 = """{1:F01COBADEFFAXXX0000000000}{2:I103BNPAFRPPXXXXN}{4:
:20:PAY-2026-0001
:23B:CRED
:32A:260910EUR1000,00
:50K:/DE89370400440532013000
ACME GMBH
BERLIN
:52A:COBADEFFXXX
:57A:BNPAFRPPXXX
:59:/FR1420041010050500013M02606
BETA SARL
:70:INVOICE 4471
:71A:SHA
-}"""

PACS008 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <FIToFICstmrCdtTrf>
    <GrpHdr><MsgId>MSG-001</MsgId><CreDtTm>2026-09-09T10:15:00</CreDtTm>
      <NbOfTxs>2</NbOfTxs><CtrlSum>1500.00</CtrlSum>
      <IntrBkSttlmDt>2026-09-10</IntrBkSttlmDt>
      <SttlmInf><SttlmMtd>INDA</SttlmMtd></SttlmInf></GrpHdr>
    <CdtTrfTxInf>
      <PmtId><TxId>TX-1</TxId><EndToEndId>E2E-1</EndToEndId>
        <UETR>7f8a1c2d-3e4b-4a5c-8d9e-0f1a2b3c4d5e</UETR></PmtId>
      <IntrBkSttlmAmt Ccy="EUR">1000.00</IntrBkSttlmAmt>
      <Dbtr><Nm>Acme GmbH</Nm></Dbtr>
      <DbtrAcct><Id><IBAN>DE89370400440532013000</IBAN></Id></DbtrAcct>
      <DbtrAgt><FinInstnId><BICFI>COBADEFFXXX</BICFI></FinInstnId></DbtrAgt>
      <Cdtr><Nm>Beta SARL</Nm></Cdtr>
      <CdtrAcct><Id><IBAN>FR1420041010050500013M02606</IBAN></Id></CdtrAcct>
      <CdtrAgt><FinInstnId><BICFI>BNPAFRPPXXX</BICFI></FinInstnId></CdtrAgt>
      <RmtInf><Ustrd>Invoice 4471</Ustrd></RmtInf></CdtTrfTxInf>
    <CdtTrfTxInf>
      <PmtId><TxId>TX-2</TxId></PmtId>
      <IntrBkSttlmAmt Ccy="EUR">500.00</IntrBkSttlmAmt>
      <DbtrAgt><FinInstnId><BIC>COBADEFFXXX</BIC></FinInstnId></DbtrAgt>
      <CdtrAgt><FinInstnId><BICFI>BUKBGB22XXX</BICFI></FinInstnId></CdtrAgt></CdtTrfTxInf>
  </FIToFICstmrCdtTrf></Document>"""


class TestBlockStructure:
    def test_the_message_type_comes_from_the_application_header(self) -> None:
        assert swift.parse(MT940).kind == "940"
        assert swift.parse(MT103).kind == "103"

    def test_the_sender_bic_comes_from_block_one(self) -> None:
        assert swift.parse(MT103).sender_bic == "COBADEFFAXXX"

    def test_a_multi_line_field_keeps_its_lines(self) -> None:
        """Field 50K carries an address. Joining continuation lines onto the
        previous tag is the only way to keep it together, and a parser that
        starts a new field on every line reports the city as an unknown tag."""
        ordering = swift.parse(MT103).first("50K")
        assert ordering is not None
        assert "ACME GMBH" in ordering
        assert "BERLIN" in ordering

    def test_an_absent_field_is_none_and_not_empty(self) -> None:
        """Different facts. A caller that cannot tell them apart reports one as
        the other."""
        assert swift.parse(MT103).first("77B") is None

    def test_a_message_with_no_text_block_is_a_finding_not_a_crash(self) -> None:
        broken = swift.parse("{1:F01BANKGB2LAXXX0000000000}{2:O940BANKDEFFXXXXN}")
        assert not broken.is_well_formed
        assert "missing or unterminated" in broken.defects[0].problem

    def test_a_file_splits_into_messages(self) -> None:
        both = swift.split(MT940 + MT103)
        assert len(both) == 2
        assert swift.parse(both[0]).kind == "940"
        assert swift.parse(both[1]).kind == "103"

    def test_splitting_does_not_cut_on_a_blank_line(self) -> None:
        """A field 86 narrative may contain one, and splitting there cuts a
        message in half and reports two malformed messages instead of one good
        one."""
        with_blank = MT940.replace(":86:Incoming payment from Acme", ":86:Incoming\n\npayment")
        assert len(swift.split(with_blank)) == 1


class TestTheCommaIsADecimalPoint:
    def test_an_amount_is_read_at_its_real_magnitude(self) -> None:
        """``float("1234,56")`` raises, and the common shortcut — strip
        non-digits — turns it into 123456. This is money."""
        found = swift.statement(swift.parse(MT940))
        assert found.lines[0].amount == Decimal("1500.50")
        assert found.opening_balance == Decimal("10000.00")

    def test_amounts_are_decimal_not_float(self) -> None:
        """Binary floating point manufactures exactly the small discrepancies a
        reconciliation exists to find."""
        found = swift.statement(swift.parse(MT940))
        assert isinstance(found.opening_balance, Decimal)
        assert isinstance(found.lines[0].amount, Decimal)


class TestTheDebitMarkCarriesTheSign:
    def test_a_debit_line_is_negative(self) -> None:
        """Field 61 states a mark and a positive amount. A parser that ignores
        the mark produces a statement whose entries only ever add up, and
        continuity then passes on a statement that does not balance."""
        found = swift.statement(swift.parse(MT940))
        assert found.lines[1].amount == Decimal("-250.25")
        assert not found.lines[1].is_credit

    def test_a_debit_balance_is_negative(self) -> None:
        overdrawn = MT940.replace(":60F:C260908EUR10000,00", ":60F:D260908EUR10000,00")
        found = swift.statement(swift.parse(overdrawn))
        assert found.opening_balance == Decimal("-10000.00")

    def test_a_reversal_flips_the_sign(self) -> None:
        """RC is the reversal of a credit, which is a debit."""
        reversed_ = MT940.replace(":61:2609090909C1500,50NTRF", ":61:2609090909RC1500,50NTRF")
        found = swift.statement(swift.parse(reversed_))
        assert found.lines[0].amount == Decimal("-1500.50")


class TestStatementContinuity:
    """Opening plus movement equals closing — the check docs/12 §4 names.

    An aggregate within one message. No column check can find it, because every
    individual figure is well-formed.
    """

    def test_a_balanced_statement_balances(self) -> None:
        found = swift.statement(swift.parse(MT940))
        assert found.movement == Decimal("1250.25")
        assert found.balances is True
        assert found.discrepancy == Decimal("0.00")

    def test_a_dropped_entry_is_caught(self) -> None:
        """The defect this exists for: a truncated file whose every remaining
        line is perfectly valid."""
        truncated = MT940.replace(":61:260909D250,25NCHGFEE-REF//BANKREF2\n", "")
        found = swift.statement(swift.parse(truncated))
        assert found.balances is False
        assert found.discrepancy == Decimal("-250.25")

    def test_a_missing_closing_balance_is_unknown_not_unbalanced(self) -> None:
        """A statement with no closing balance has not failed continuity, it has
        failed to state it — and the two go to different people."""
        without = MT940.replace(":62F:C260909EUR11250,25\n", "")
        found = swift.statement(swift.parse(without))
        assert found.balances is None
        assert found.discrepancy is None
        assert any(defect.field == "62F" for defect in found.defects)

    def test_a_currency_change_mid_statement_is_a_defect(self) -> None:
        """A statement that opens in euros and closes in dollars is not a
        statement, and the arithmetic would be meaningless."""
        mixed = MT940.replace(":62F:C260909EUR11250,25", ":62F:C260909USD11250,25")
        found = swift.statement(swift.parse(mixed))
        assert any("opens in EUR and closes in USD" in d.problem for d in found.defects)

    def test_an_unreadable_line_is_named_and_the_rest_survive(self) -> None:
        """One bad line must not lose the statement. It becomes a defect, and
        the balance check then reports a discrepancy rather than silently
        omitting an entry."""
        broken = MT940.replace(":61:260909D250,25NCHGFEE-REF//BANKREF2", ":61:GARBAGE")
        found = swift.statement(swift.parse(broken))
        assert len(found.lines) == 1
        assert any(d.field == "61" for d in found.defects)


class TestMt103:
    def test_it_becomes_named_business_fields(self) -> None:
        row = swift.payment(swift.parse(MT103))
        assert row["reference"] == "PAY-2026-0001"
        assert row["currency"] == "EUR"
        assert row["amount"] == "1000.00"
        assert row["value_date"] == "2026-09-10"
        assert row["ordering_institution"] == "COBADEFFXXX"
        assert row["account_with_institution"] == "BNPAFRPPXXX"
        assert row["details_of_charges"] == "SHA"

    def test_a_missing_amount_field_is_none_rather_than_zero(self) -> None:
        """Zero is a number that balances."""
        without = MT103.replace(":32A:260910EUR1000,00\n", "")
        row = swift.payment(swift.parse(without))
        assert row["amount"] is None
        assert row["currency"] == ""


class TestPacs008:
    def test_it_reports_the_version_rather_than_refusing_on_it(self) -> None:
        """A parser keyed on the full namespace refuses next year's file. The
        version is worth reporting and is a decision for a control."""
        assert iso20022.parse_pacs008(PACS008).version == "pacs.008.001.08"

    def test_a_later_version_still_parses(self) -> None:
        newer = PACS008.replace("pacs.008.001.08", "pacs.008.001.13")
        parsed = iso20022.parse_pacs008(newer)
        assert parsed.version == "pacs.008.001.13"
        assert parsed.actual_count == 2

    def test_what_is_claimed_is_kept_apart_from_what_is_there(self) -> None:
        """Deriving one from the other makes the most useful check in the file
        impossible to write."""
        parsed = iso20022.parse_pacs008(PACS008)
        assert parsed.stated_count == 2
        assert parsed.actual_count == 2
        assert parsed.control_sum == Decimal("1500.00")
        assert parsed.transaction_total == Decimal("1500.00")
        assert parsed.count_agrees is True
        assert parsed.sum_agrees is True

    def test_a_dropped_transaction_disagrees_with_the_header(self) -> None:
        truncated = PACS008[: PACS008.index("<CdtTrfTxInf>\n      <PmtId><TxId>TX-2")] + (
            "</FIToFICstmrCdtTrf></Document>"
        )
        parsed = iso20022.parse_pacs008(truncated)
        assert parsed.actual_count == 1
        assert parsed.count_agrees is False
        assert parsed.sum_agrees is False

    def test_an_absent_control_total_is_unknown_not_disagreeing(self) -> None:
        """An absent control total is a sender problem; a wrong one is a
        truncation. Different people."""
        without = PACS008.replace("<CtrlSum>1500.00</CtrlSum>", "")
        parsed = iso20022.parse_pacs008(without)
        assert parsed.sum_agrees is None

    def test_unreadable_amounts_are_counted_separately(self) -> None:
        """A file whose sum agrees while three amounts were unreadable has not
        been checked; it has been under-counted twice in the same direction."""
        bad = PACS008.replace(
            '<IntrBkSttlmAmt Ccy="EUR">500.00</IntrBkSttlmAmt>',
            '<IntrBkSttlmAmt Ccy="EUR">not-a-number</IntrBkSttlmAmt>',
        )
        parsed = iso20022.parse_pacs008(bad)
        assert parsed.unreadable_amounts == 1
        assert parsed.transaction_total == Decimal("1000.00")

    def test_both_spellings_of_the_bic_element_are_read(self) -> None:
        """BICFI since version .03 and BIC before it. Reading only one silently
        returns nothing, and a control reports that as a missing field rather
        than as a parser that did not look."""
        parsed = iso20022.parse_pacs008(PACS008)
        assert parsed.transactions[0].debtor_agent_bic == "COBADEFFXXX"
        assert parsed.transactions[1].debtor_agent_bic == "COBADEFFXXX"

    def test_an_absent_branch_is_empty_rather_than_a_crash(self) -> None:
        """The second transaction has no debtor account at all."""
        parsed = iso20022.parse_pacs008(PACS008)
        assert parsed.transactions[1].debtor_iban == ""

    def test_malformed_xml_is_a_defect_not_an_exception(self) -> None:
        """One bad file must not stop the others being checked."""
        parsed = iso20022.parse_pacs008("<Document><unclosed>")
        assert parsed.defects
        assert "not well-formed XML" in parsed.defects[0]
        assert parsed.actual_count == 0


class TestTheTwoParsersShareAVocabulary:
    """The beachhead docs/12 §4 names.

    MT and MX now run in parallel with translation layers between them, and the
    translation is where the defects are. Two parsers with two vocabularies
    would have made a fidelity control a mapping exercise — and a mapping
    maintained by hand is a third thing that can be wrong.
    """

    def test_the_same_payment_produces_comparable_rows(self) -> None:
        mt = swift.payment(swift.parse(MT103))
        mx = iso20022.parse_pacs008(PACS008).transactions[0].to_dict()

        assert mt["currency"] == mx["currency"] == "EUR"
        assert mt["amount"] == mx["amount"] == "1000.00"
        assert mt["value_date"] == mx["value_date"] == "2026-09-10"
        assert mt["ordering_institution"] == mx["debtor_agent_bic"]
        assert mt["account_with_institution"] == mx["creditor_agent_bic"]

    def test_a_translation_that_lost_the_amount_is_visible(self) -> None:
        """What a RECONCILES_WITH between the two representations would catch."""
        drifted = PACS008.replace(
            '<IntrBkSttlmAmt Ccy="EUR">1000.00</IntrBkSttlmAmt>',
            '<IntrBkSttlmAmt Ccy="EUR">100.00</IntrBkSttlmAmt>',
        )
        mt = swift.payment(swift.parse(MT103))
        mx = iso20022.parse_pacs008(drifted).transactions[0].to_dict()
        assert mt["amount"] != mx["amount"]

    @pytest.mark.parametrize(
        "field", ["reference", "amount", "currency", "value_date", "remittance_information"]
    )
    def test_both_sides_carry_the_field(self, field: str) -> None:
        mt = swift.payment(swift.parse(MT103))
        mx = iso20022.parse_pacs008(PACS008).transactions[0].to_dict()
        assert field in mt, f"the MT row has no {field}"
        assert field in mx, f"the MX row has no {field}"


class TestTranslationFidelityEndToEnd:
    """The beachhead, through the real reconciliation engine.

    Not a demonstration that the parsers agree — a demonstration that when the
    translation layer between MT and MX gets something wrong, the existing
    engine names it. Nothing in the recon package knows what a SWIFT message is;
    it receives two amounts under one key because the two parsers agreed on a
    vocabulary.
    """

    MT = """{1:F01COBADEFFAXXX0000000000}{2:I103BNPAFRPPXXXXN}{4:
:20:E2E-1
:32A:260910EUR1000,00
:52A:COBADEFFXXX
:57A:BNPAFRPPXXX
-}"""

    MX = """<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
<FIToFICstmrCdtTrf><GrpHdr><MsgId>M1</MsgId><NbOfTxs>1</NbOfTxs>
<IntrBkSttlmDt>2026-09-10</IntrBkSttlmDt></GrpHdr>
<CdtTrfTxInf><PmtId><TxId>T1</TxId><EndToEndId>E2E-1</EndToEndId></PmtId>
<IntrBkSttlmAmt Ccy="EUR">{amount}</IntrBkSttlmAmt>
<DbtrAgt><FinInstnId><BICFI>COBADEFFXXX</BICFI></FinInstnId></DbtrAgt>
<CdtrAgt><FinInstnId><BICFI>BNPAFRPPXXX</BICFI></FinInstnId></CdtrAgt>
</CdtTrfTxInf></FIToFICstmrCdtTrf></Document>"""

    def _classify(self, amount: str):
        from prama.recon import Classifier
        from prama.recon.classify import Tolerance

        mt = swift.payment(swift.parse(self.MT))
        mx = iso20022.parse_pacs008(self.MX.format(amount=amount)).transactions[0]
        return Classifier(Tolerance(absolute=0.0)).classify(
            mt["reference"], Decimal(mt["amount"]), mx.amount
        )

    def test_a_faithful_translation_produces_no_break(self) -> None:
        assert self._classify("1000.00") is None

    def test_a_lost_decimal_place_is_a_genuine_break(self) -> None:
        """The defect that matters: both messages are individually valid, both
        pass every format control, and one of them is for a tenth of the money."""
        found = self._classify("100.00")
        assert found is not None
        assert found.kind.value == "genuine"
        assert not found.kind.clears_itself
        assert "1,000.00 against 100.00" in found.describe()

    def test_the_pair_matches_on_the_end_to_end_reference(self) -> None:
        """The only identifier both representations carry unchanged. Matching on
        the transaction id would fail on every payment, because MT and MX assign
        their own."""
        from prama.recon import Matcher, MatchKey

        mt = swift.payment(swift.parse(self.MT))
        mx = iso20022.parse_pacs008(self.MX.format(amount="1000.00")).transactions[0]
        report = Matcher(MatchKey(left=("key",), right=("key",))).match(
            [{"key": mt["reference"]}], [{"key": mx.end_to_end_id}]
        )
        assert len(report.pairs) == 1
        assert not report.unmatched_left
        assert not report.unmatched_right
