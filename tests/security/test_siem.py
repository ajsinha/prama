"""SIEM export.

A bank's security team does not read your audit screen; they read whatever
aggregates every system in the estate. A product whose audit trail exists only
inside itself gets a finding at the next examination, because nobody can
correlate it with anything else.

Three of these tests are about the things that decide whether an export is
usable at three in the morning: triage-able severity, a secret that cannot ride
out in a free-form field, and escaping that does not silently rewrite an event.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from prama.core.errors import ValidationError
from prama.security.siem import render, severity_of, to_cef, to_ecs


@dataclasses.dataclass
class Event:
    """The shape AuditEvent presents, without needing a database."""

    id: str = "01EVENT"
    tenant_id: str = "01TENANT"
    occurred_at: Any = datetime(2026, 9, 9, 10, 0, tzinfo=UTC)
    actor_id: str | None = "01ALICE"
    actor_kind: str = "human"
    action: str = "control.approve"
    object_kind: str = "control"
    object_id: str | None = "01CONTROL"
    outcome: str = "success"
    correlation_id: str | None = "01TRACE"
    source_ip: str | None = "10.0.0.1"
    detail_json: dict[str, Any] = dataclasses.field(default_factory=dict)


class TestSeverityIsTriageable:
    def test_a_denial_outranks_a_failure_which_outranks_a_success(self) -> None:
        """A feed where everything is severity 5 gets a suppression rule within
        a week."""
        assert severity_of("x", "denied") > severity_of("x", "failure")
        assert severity_of("x", "failure") > severity_of("x", "success")

    def test_a_successful_privilege_change_still_ranks_high(self) -> None:
        """A successful grant of an admin role is a security event whatever its
        outcome field says. Ranking it below a failed page load buries the line
        a reviewer is looking for."""
        assert severity_of("role.grant", "success") > severity_of("page.view", "failure")

    def test_erasing_evidence_is_the_loudest_thing_in_the_product(self) -> None:
        assert severity_of("evidence.erase", "success") >= 8

    def test_the_higher_of_the_two_signals_wins(self) -> None:
        assert severity_of("role.grant", "denied") == 8


class TestSecretsDoNotRideOut:
    def test_an_unlisted_detail_key_is_dropped(self) -> None:
        """`detail_json` is free-form and written by call sites all over the
        product. Shipping it whole to a system with different access controls is
        how a password reaches a log aggregator."""
        event = Event(detail_json={"dataset": "positions", "password": "hunter2"})
        exported = to_ecs([event])
        assert "hunter2" not in exported.text()
        assert "positions" in exported.text()

    def test_the_drop_is_counted_rather_than_silent(self) -> None:
        """Nobody should read an empty detail as "there was none"."""
        exported = to_ecs([Event(detail_json={"secret": "x", "token": "y"})])
        assert exported.dropped_detail_keys == 2
        assert "not the same as there having been none" in exported.describe()

    def test_nothing_is_dropped_when_everything_is_allowed(self) -> None:
        exported = to_ecs([Event(detail_json={"dataset": "d", "verdict": "pass"})])
        assert exported.dropped_detail_keys == 0

    def test_a_non_dictionary_detail_does_not_crash(self) -> None:
        assert to_ecs([Event(detail_json="not a dict")]).events == 1


class TestEcs:
    def test_it_is_one_json_object_per_line(self) -> None:
        exported = to_ecs([Event(), Event(id="02")])
        assert exported.events == 2
        for line in exported.lines:
            json.loads(line)

    def test_the_field_names_are_ecs_rather_than_pramas(self) -> None:
        """A field a SIEM has to be taught about is a field nobody filters
        on."""
        document = json.loads(to_ecs([Event()]).lines[0])
        assert document["event"]["action"] == "control.approve"
        assert document["event"]["outcome"] == "success"
        assert document["user"]["id"] == "01ALICE"
        assert document["source"]["ip"] == "10.0.0.1"
        assert document["@timestamp"].startswith("2026-09-09T10:00")

    def test_the_tenant_travels_as_the_organisation(self) -> None:
        document = json.loads(to_ecs([Event()]).lines[0])
        assert document["organization"]["id"] == "01TENANT"

    def test_the_product_identifies_itself(self) -> None:
        document = json.loads(to_ecs([Event()]).lines[0])
        assert document["observer"]["product"]
        assert document["observer"]["version"]


class TestCefEscaping:
    def test_a_pipe_in_a_header_is_escaped(self) -> None:
        """An unescaped pipe ends the field, and the event silently becomes a
        different event that still parses."""
        line = to_cef([Event(action="weird|action")]).lines[0]
        assert "weird\\|action" in line

    def test_an_equals_in_an_extension_is_escaped(self) -> None:
        line = to_cef([Event(object_id="a=b")]).lines[0]
        assert "a\\=b" in line

    def test_a_newline_is_escaped_rather_than_ending_the_record(self) -> None:
        """A newline ends the event entirely: unescaped, it truncates the record
        or merges it with the next."""
        line = to_cef([Event(object_id="line1\nline2")]).lines[0]
        assert "\n" not in line
        assert "\\n" in line

    def test_the_header_has_the_seven_cef_fields(self) -> None:
        line = to_cef([Event()]).lines[0]
        header = line.split("|")[:7]
        assert header[0] == "CEF:0"
        assert header[6].isdigit()

    def test_the_severity_appears_in_the_header(self) -> None:
        denied = to_cef([Event(outcome="denied")]).lines[0]
        assert denied.split("|")[6] == "8"

    def test_detail_fills_the_custom_string_slots(self) -> None:
        line = to_cef([Event(detail_json={"dataset": "positions"})]).lines[0]
        assert "cs5Label=dataset" in line
        assert "cs5=positions" in line

    def test_it_never_emits_more_than_six_custom_strings(self) -> None:
        """CEF defines cs1 to cs6. A cs7 is a field the receiver drops, and a
        value silently dropped is worse than one never sent."""
        detail = {
            "dataset": "d",
            "control": "c",
            "verdict": "v",
            "reason": "r",
            "scope": "s",
            "regime": "g",
        }
        line = to_cef([Event(detail_json=detail)]).lines[0]
        assert "cs7" not in line


class TestRender:
    def test_both_formats_are_reachable_by_name(self) -> None:
        assert render([Event()], "ecs").events == 1
        assert render([Event()], "cef").events == 1

    def test_an_unknown_format_is_refused_with_the_list(self) -> None:
        with pytest.raises(ValidationError, match="no SIEM format"):
            render([Event()], "syslog")

    def test_an_empty_feed_renders_to_nothing_rather_than_a_blank_line(self) -> None:
        exported = render([], "ecs")
        assert exported.text() == ""
        assert exported.events == 0
