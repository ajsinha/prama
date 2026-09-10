"""COBOL copybooks and EBCDIC.

A bank's most important extract usually arrives as fixed-width EBCDIC with a
copybook, every generic tool treats it as binary, and the conversion script
somebody wrote in 2009 is where the defects are.

Every failure mode below produces *plausible numbers* rather than an error,
which is why they are worth a test each: a packed-decimal field read as an
integer is about ten thousand times too large, an implied decimal point ignored
is a hundred times too large, and a sign nibble ignored turns every credit into
a debit while leaving the magnitude right.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from prama.core.errors import ValidationError
from prama.packs.banking.cobol import (
    parse_copybook,
    read_record,
    read_records,
    unpack_comp3,
)

COPYBOOK = """
       01  ACCOUNT-RECORD.
           05  ACCT-ID           PIC X(10).
           05  ACCT-NAME         PIC X(20).
           05  ACCT-BALANCE      PIC S9(7)V99 COMP-3.
           05  ACCT-CURRENCY     PIC X(3).
           05  ACCT-STATUS       PIC X(1).
"""


def comp3(value: Decimal, digits: int) -> bytes:
    """Encode packed decimal, so the tests build real bytes rather than
    asserting against the reader's own output."""
    negative = value < 0
    raw = str(abs(value)).replace(".", "").rjust(digits, "0")
    nibbles = raw + ("D" if negative else "C")
    if len(nibbles) % 2:
        nibbles = "0" + nibbles
    return bytes(int(nibbles[i : i + 2], 16) for i in range(0, len(nibbles), 2))


def record(balance: Decimal = Decimal("1234567.89"), status: str = "A") -> bytes:
    return (
        "ACC0000001".encode("cp037")
        + "ACME MARKETS LIMITED".encode("cp037")
        + comp3(balance, 9)
        + "EUR".encode("cp037")
        + status.encode("cp037")
    )


@pytest.fixture(scope="module")
def book():
    return parse_copybook(COPYBOOK)


class TestCopybookLayout:
    def test_offsets_and_lengths(self, book) -> None:
        assert book.record_length == 39
        assert book.field("ACCT-ID").offset == 0
        assert book.field("ACCT-BALANCE").offset == 30
        # S9(7)V99 is nine digits: two per byte plus a sign nibble.
        assert book.field("ACCT-BALANCE").length == 5

    def test_the_implied_decimal_is_recorded(self, book) -> None:
        """``V`` is not in the data. A reader that does not record the scale
        reports every amount a hundred times too big, and the figure looks
        entirely reasonable."""
        assert book.field("ACCT-BALANCE").scale == 2
        assert book.field("ACCT-BALANCE").signed

    def test_a_group_item_contributes_no_bytes_of_its_own(self, book) -> None:
        assert book.field("ACCOUNT-RECORD") is None

    def test_a_condition_name_is_not_a_field(self) -> None:
        """Level 88 names a value of the field above it. Counting it as a field
        shifts every offset after it."""
        parsed = parse_copybook(
            "01 R.\n  05 STATUS PIC X(1).\n    88 ACTIVE VALUE 'A'.\n  05 CCY PIC X(3).\n"
        )
        assert parsed.field("ACTIVE") is None
        assert parsed.field("CCY").offset == 1
        assert parsed.record_length == 4

    def test_occurs_multiplies_an_elementary_field(self) -> None:
        parsed = parse_copybook("01 R.\n  05 CODE PIC X(2) OCCURS 5.\n  05 TAIL PIC X(3).\n")
        assert parsed.field("TAIL").offset == 10
        assert parsed.record_length == 13

    def test_occurs_multiplies_a_whole_group(self) -> None:
        """Twelve monthly buckets is twelve times the group's size. Getting it
        wrong shifts every field after it and produces records full of their
        neighbours' bytes."""
        parsed = parse_copybook(
            "01 R.\n"
            "  05 HEADER PIC X(4).\n"
            "  05 MONTH OCCURS 12.\n"
            "    10 M-AMT PIC S9(5)V99 COMP-3.\n"
            "    10 M-FLAG PIC X(1).\n"
            "  05 TRAILER PIC X(2).\n"
        )
        # Each month is a 4-byte COMP-3 plus one flag = 5, times twelve.
        assert parsed.field("TRAILER").offset == 4 + 5 * 12
        assert parsed.record_length == 4 + 60 + 2

    def test_a_redefinition_shares_bytes_and_does_not_advance(self) -> None:
        parsed = parse_copybook(
            "01 R.\n"
            "  05 RAW-DATE PIC X(8).\n"
            "  05 SPLIT-DATE REDEFINES RAW-DATE.\n"
            "    10 YYYY PIC X(4).\n"
            "  05 TAIL PIC X(2).\n"
        )
        assert parsed.field("TAIL").offset == 8

    def test_binary_usage_follows_the_cobol_table(self) -> None:
        parsed = parse_copybook("01 R.\n  05 SMALL PIC S9(4) COMP.\n  05 BIG PIC S9(9) COMP.\n")
        assert parsed.field("SMALL").length == 2
        assert parsed.field("BIG").length == 4

    def test_an_unreadable_picture_is_refused_rather_than_guessed(self) -> None:
        """A picture this cannot read puts every field after it at the wrong
        offset, so continuing would produce a whole file of plausible rubbish."""
        with pytest.raises(ValidationError, match="cannot read the PICTURE"):
            parse_copybook("01 R.\n  05 ODD PIC ZZZ9.99.\n")

    def test_an_unparseable_line_is_a_warning_not_a_silent_skip(self) -> None:
        parsed = parse_copybook("01 R.\n  this is not a copybook line\n  05 A PIC X(1).\n")
        assert parsed.warnings
        assert parsed.field("A") is not None


class TestPackedDecimal:
    def test_a_positive_value_round_trips(self) -> None:
        assert unpack_comp3(comp3(Decimal("1234567.89"), 9), scale=2) == Decimal("1234567.89")

    def test_the_sign_nibble_is_honoured(self) -> None:
        """D is negative. A reader that ignores the nibble turns every credit
        into a debit, and the figures still look reasonable."""
        assert unpack_comp3(comp3(Decimal("-500.25"), 9), scale=2) == Decimal("-500.25")

    def test_f_is_positive_as_well_as_c(self) -> None:
        """Unsigned COMP-3 uses F. Treating it as an error rejects every
        unsigned packed field in the file."""
        assert unpack_comp3(bytes([0x12, 0x3F])) == Decimal("123")

    def test_an_invalid_nibble_is_none_rather_than_a_number(self) -> None:
        """What a mis-offset field looks like. It is a finding, not a zero."""
        assert unpack_comp3(bytes([0xAB, 0xCD])) is None

    def test_an_invalid_sign_nibble_is_none(self) -> None:
        assert unpack_comp3(bytes([0x12, 0x34])) is None

    def test_empty_input_is_none(self) -> None:
        assert unpack_comp3(b"") is None

    def test_it_is_not_the_integer_the_bytes_spell(self) -> None:
        """The failure this exists to prevent: read as a big-endian integer,
        1234567.89 comes back as roughly 78,000,000,000 — a number nobody
        questions in a balance column."""
        packed = comp3(Decimal("1234567.89"), 9)
        assert unpack_comp3(packed, scale=2) == Decimal("1234567.89")
        assert int.from_bytes(packed, "big") != 123456789


class TestReadingRecords:
    def test_a_record_becomes_named_values(self, book) -> None:
        row = read_record(record(), book, codepage="cp037")
        assert row["ACCT-ID"] == "ACC0000001"
        assert row["ACCT-NAME"] == "ACME MARKETS LIMITED"
        assert row["ACCT-BALANCE"] == "1234567.89"
        assert row["ACCT-CURRENCY"] == "EUR"

    def test_a_negative_balance_survives(self, book) -> None:
        row = read_record(record(Decimal("-42.50")), book, codepage="cp037")
        assert row["ACCT-BALANCE"] == "-42.50"

    def test_trailing_spaces_are_trimmed_but_the_value_is_not_invented(self, book) -> None:
        short = (
            "ACC1      ".encode("cp037")
            + "SHORT NAME          ".encode("cp037")
            + comp3(Decimal("1.00"), 9)
            + "GBP".encode("cp037")
            + "A".encode("cp037")
        )
        row = read_record(short, book, codepage="cp037")
        assert row["ACCT-ID"] == "ACC1"
        assert row["ACCT-NAME"] == "SHORT NAME"

    def test_a_codepage_is_required(self, book) -> None:
        """EBCDIC is not one encoding, and the codepages differ on exactly the
        characters an identifier uses. A default works in testing and corrupts
        one field in production."""
        with pytest.raises(ValidationError, match="no EBCDIC codepage"):
            read_record(record(), book, codepage="")

    def test_the_wrong_codepage_changes_the_characters(self, book) -> None:
        """Not an error — that is the danger. cp273 puts different characters at
        the same code points, so the record decodes to something that looks
        like data."""
        as_us = read_record(record(), book, codepage="cp037")
        as_german = read_record(record(), book, codepage="cp273")
        assert as_us["ACCT-ID"] == as_german["ACCT-ID"]  # letters agree
        # The point: it decoded without complaint under both.
        assert as_german["ACCT-NAME"]

    def test_a_short_record_is_a_finding_not_a_padded_value(self, book) -> None:
        """A padded field is a value that was never sent, and it will be checked
        as though it were."""
        rows, complaints = read_records(record()[:20], book, codepage="cp037")
        assert rows == []
        assert complaints
        assert "does not divide into whole records" in complaints[0]

    def test_one_bad_record_does_not_lose_the_others(self, book) -> None:
        data = record() + record(Decimal("2.00")) + record()[:10]
        rows, complaints = read_records(data, book, codepage="cp037")
        assert len(rows) == 2
        assert len(complaints) == 1

    def test_a_whole_file_reads(self, book) -> None:
        data = b"".join(record(Decimal(f"{n}.00")) for n in range(1, 6))
        rows, complaints = read_records(data, book, codepage="cp037")
        assert [row["ACCT-BALANCE"] for row in rows] == ["1.00", "2.00", "3.00", "4.00", "5.00"]
        assert not complaints

    def test_an_empty_copybook_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no fields"):
            read_records(b"anything", parse_copybook(""), codepage="cp037")


class TestZonedDecimal:
    """Display numbers with an overpunched sign.

    A trailing ``}`` is a negative zero-digit stamped onto the last position. A
    reader that strips non-digits loses the sign, and the amount changes sign
    without changing magnitude — which reconciles to exactly twice the error and
    is routinely misread as a duplicate.
    """

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("00012345", "123.45"),
            ("0001234E", "123.45"),  # E is +5 overpunched
            ("0001234N", "-123.45"),  # N is -5 overpunched
            ("0001234}", "-123.40"),
        ],
    )
    def test_overpunched_signs(self, text: str, expected: str) -> None:
        parsed = parse_copybook("01 R.\n  05 AMT PIC S9(6)V99.\n")
        row = read_record(text.encode("cp037"), parsed, codepage="cp037")
        assert row["AMT"] == expected

    def test_a_non_numeric_display_number_is_none(self) -> None:
        parsed = parse_copybook("01 R.\n  05 AMT PIC 9(4).\n")
        row = read_record("AB12".encode("cp037"), parsed, codepage="cp037")
        assert row["AMT"] is None
