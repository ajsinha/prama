"""A secret that resists being written down.

The failures here are all the same shape: one line of ordinary, well-meaning
code that copies a credential somewhere it will outlive its usefulness.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import logging
import pickle

import pytest

from prama.secrets import REDACTED, SecretValue

PASSWORD = "hunter2-correct-horse"


class TestItDoesNotPrintItself:
    def test_str_is_redacted(self) -> None:
        assert str(SecretValue(PASSWORD)) == REDACTED

    def test_repr_is_redacted(self) -> None:
        # repr is what an exception renders for its arguments, and what a
        # debugger and most log formatters show.
        assert PASSWORD not in repr(SecretValue(PASSWORD, origin="env://PG"))
        assert "env://PG" in repr(SecretValue(PASSWORD, origin="env://PG"))

    def test_an_f_string_cannot_expose_it(self) -> None:
        secret = SecretValue(PASSWORD)
        assert f"{secret}" == REDACTED

    def test_a_format_spec_cannot_route_around_str(self) -> None:
        # Without __format__, f"{secret:>30}" would call __format__ on the
        # underlying object and print the password padded to thirty columns.
        secret = SecretValue(PASSWORD)
        assert PASSWORD not in f"{secret:>30}"
        assert PASSWORD not in "{:s}".format(secret)  # noqa: UP032

    def test_it_does_not_leak_through_a_log_line(self, caplog: pytest.LogCaptureFixture) -> None:
        secret = SecretValue(PASSWORD)
        with caplog.at_level(logging.INFO):
            logging.getLogger("test").info("connecting with %s", secret)
        assert PASSWORD not in caplog.text

    def test_it_does_not_leak_through_an_exception(self) -> None:
        secret = SecretValue(PASSWORD)
        try:
            raise ValueError(f"bad credential: {secret}")
        except ValueError as exc:
            assert PASSWORD not in str(exc)
            assert PASSWORD not in repr(exc)

    def test_its_length_is_not_a_side_channel(self) -> None:
        assert len(SecretValue("a")) == len(SecretValue("a much longer passphrase"))


class TestItDoesNotTravel:
    def test_it_refuses_to_pickle(self) -> None:
        # Pickling is how a credential reaches a task queue, a cache file or a
        # crash dump. There is no legitimate reason to move one that way.
        with pytest.raises(TypeError, match="cannot be serialised"):
            pickle.dumps(SecretValue(PASSWORD))

    def test_it_is_not_json_serialisable_by_accident(self) -> None:
        with pytest.raises(TypeError):
            json.dumps({"password": SecretValue(PASSWORD)})


class TestGettingItOut:
    def test_reveal_is_the_only_way_and_is_easy_to_grep_for(self) -> None:
        assert SecretValue(PASSWORD).reveal() == PASSWORD

    def test_comparison_does_not_require_revealing(self) -> None:
        assert SecretValue(PASSWORD).matches(PASSWORD)
        assert not SecretValue(PASSWORD).matches("wrong")

    def test_two_secrets_compare_by_value(self) -> None:
        assert SecretValue(PASSWORD) == SecretValue(PASSWORD)
        assert SecretValue(PASSWORD) != SecretValue("other")

    def test_a_secret_never_equals_a_bare_string(self) -> None:
        # Otherwise `if secret == "": ...` and similar comparisons would leak
        # the value one character at a time through timing, and would invite
        # treating the wrapper as interchangeable with plain text.
        assert SecretValue(PASSWORD) != PASSWORD


class TestFingerprint:
    def test_it_identifies_a_value_without_revealing_it(self) -> None:
        # So an audit trail can show that a credential changed, without the
        # trail itself holding a credential.
        assert SecretValue(PASSWORD).fingerprint() == SecretValue(PASSWORD).fingerprint()
        assert SecretValue(PASSWORD).fingerprint() != SecretValue("rotated").fingerprint()
        assert PASSWORD not in SecretValue(PASSWORD).fingerprint()

    def test_hashing_uses_the_fingerprint_not_the_value(self) -> None:
        assert hash(SecretValue(PASSWORD)) == hash(SecretValue(PASSWORD))

    def test_emptiness_is_visible_without_revealing(self) -> None:
        assert SecretValue("").is_empty
        assert not SecretValue(PASSWORD).is_empty
        assert not bool(SecretValue(""))
