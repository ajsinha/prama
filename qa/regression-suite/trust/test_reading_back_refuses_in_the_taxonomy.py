"""Reading a record or a config file back refuses in the taxonomy.

QA round 4 triage, cluster C1 — `EVD-020` and `CFG-062`. Two sites where a
stdlib exception escaped to the caller instead of the typed error, and both are
on a **reading-back** path, which is where it matters most: the caller is
already holding something they suspect.

`EvidenceRecord.from_dict` built its metrics with `float(v)` directly, so a
stored metric of `"eight"` raised `could not convert string to float: 'eight'` —
with nothing naming the record, the metric, or the ledger. That runs while
replaying evidence, so the one moment the message is read is the moment
somebody is asking whether a chain can be trusted.

`FileSource.load` caught `OSError` around `read_text` and its remedy already
said *"UTF-8 is expected"*. But `UnicodeDecodeError` is a `ValueError`, not an
`OSError`, so the clause never fired and a latin-1 config file produced a
traceback. **The message existed; the branch that could show it did not** —
which is a different defect from not having thought about encoding at all, and
a more annoying one, because the author clearly had.

**What a careless version of this test would assert.** That something raises.
Both sites raised before the fix — loudly, with a stack trace. The assertions
below require the refusal to be in the taxonomy *and* to name the specific thing
that was wrong: which metric, which record, which byte at which offset. A typed
error saying "the file could not be read" would pass a `pytest.raises` check and
leave the reader exactly where the traceback did.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prama.contract.odcs import load as load_odcs
from prama.core.config.sources import YamlFileSource
from prama.core.errors import ConfigError, DatabaseError, PramaError, ValidationError
from prama.db.types import UtcDateTime
from prama.evidence.record import EvidenceRecord

GOOD_RECORD = {
    "sequence": 7,
    "plan_id": "ir:sha256:abc",
    "control_id": "c-1",
    "dataset": "positions_eod",
    "verdict": "pass",
}


def test_a_record_with_a_non_numeric_metric_names_it() -> None:
    with pytest.raises(ValidationError) as caught:
        EvidenceRecord.from_dict({**GOOD_RECORD, "metrics": {"scanned_rows": "eight"}})

    message = str(caught.value)
    assert "scanned_rows" in message, f"the refusal does not name the metric: {message}"
    assert "7" in message, f"the refusal does not name the record: {message}"
    assert "eight" in message, f"the refusal does not show the offending value: {message}"


def test_a_record_with_good_metrics_still_reads() -> None:
    """The counterfactual to the refusal.

    Without this, the file is satisfied by a `from_dict` that rejects every
    record — which would make the ledger unreadable rather than checked.
    """
    record = EvidenceRecord.from_dict({**GOOD_RECORD, "metrics": {"scanned_rows": "1200"}})
    assert record.metrics["scanned_rows"] == 1200.0


def test_a_config_file_that_is_not_utf8_says_which_byte(tmp_path: Path) -> None:
    config = tmp_path / "application.yaml"
    # A value with an accent, saved the way an editor defaulting to cp1252 saves
    # it. This is the realistic origin, not a contrived byte.
    config.write_bytes("note: caf\xe9\n".encode("latin-1"))

    with pytest.raises(ConfigError) as caught:
        YamlFileSource(config).load()

    message = str(caught.value)
    assert "UTF-8" in message or "utf-8" in message.lower()
    assert "0xe9" in message, f"the refusal does not name the byte: {message}"
    assert caught.value.remedy, "a refusal without a remedy is half an answer"


def test_a_utf8_config_file_still_loads(tmp_path: Path) -> None:
    """The same file, saved correctly, must still work.

    `UnicodeDecodeError` is caught by name rather than by widening the existing
    `except OSError` to `except Exception`, which would have swallowed every
    other failure in `read_text` along with it.
    """
    config = tmp_path / "application.yaml"
    config.write_text("note: café\n", encoding="utf-8")
    assert YamlFileSource(config).load() == {"note": "café"}


def test_a_missing_file_still_refuses_for_its_own_reason(tmp_path: Path) -> None:
    """The refusal that already worked, so the new clause did not displace it.

    Adding an `except` before an existing one is exactly the change that makes
    the earlier branch unreachable, and a file that refuses for the wrong reason
    is harder to diagnose than one that refuses for the right one.
    """
    with pytest.raises(PramaError) as caught:
        YamlFileSource(tmp_path / "absent.yaml").load()
    assert "not found" in str(caught.value).lower()


# -- somebody else's JSON, and somebody else's row -------------------------
#
# Two more reading-back paths from the same triage cluster. Both take input this
# codebase did not write — an ODCS contract exported by another tool, and a row
# whose timestamp was stored by something that is not Prama — which is exactly
# where assuming a shape produces a traceback about a file the reader is trying
# to import.


@pytest.mark.parametrize(
    "contract,expected",
    [
        ({"schema": ["just a name"]}, "str"),
        ({"schema": [None]}, "NoneType"),
        ({"schema": {"name": "x"}}, "dict"),
    ],
    ids=["list-of-strings", "list-of-nulls", "mapping-not-list"],
)
def test_an_odcs_contract_of_the_wrong_shape_says_what_it_found(
    contract: dict, expected: str
) -> None:
    """`CTR-015`. `schemas[0]` and `.get` on it, with no type check.

    A mapping made `schemas[0]` a `KeyError: 0`; a list of strings or nulls made
    `.get` an `AttributeError` naming only the type. Three different bare
    exceptions for three shapes of the same mistake.
    """
    with pytest.raises(ValidationError) as caught:
        load_odcs(contract)
    assert expected in str(caught.value), (
        f"the refusal does not say what it found instead: {caught.value}"
    )


def test_a_well_formed_odcs_contract_still_imports() -> None:
    """The control. Refusing every contract would satisfy the three above."""
    result = load_odcs({"schema": [{"name": "positions_eod", "properties": [{"name": "isin"}]}]})
    assert result.declaration is not None


def test_a_stored_timestamp_that_will_not_parse_names_the_value() -> None:
    """`DB-098`. Stdlib's message names neither the table nor the column.

    This runs while reading rows back, so the person who sees it is holding a
    row they cannot explain. Prama stores timestamps as ISO-8601 text in
    `VARCHAR(32)` so they sort chronologically; a value that will not parse was
    written by something other than this code, which is what the remedy says.
    """
    with pytest.raises(DatabaseError) as caught:
        UtcDateTime().process_result_value("not-a-date", None)
    assert "not-a-date" in str(caught.value)
    assert caught.value.remedy


def test_a_stored_timestamp_that_does_parse_still_reads() -> None:
    """The control, and the reason `except ValueError` was scoped to one call."""
    parsed = UtcDateTime().process_result_value("2026-09-14T00:00:00Z", None)
    assert parsed is not None and parsed.tzinfo is not None
