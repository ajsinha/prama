"""`SdkFleetLink`: the SDK's fleet namespace, with every failure turned into one the loop handles.

The SDK's ``client.fleet`` is built on the server side of the contract; these
tests stand in for it with an object that has its three methods, exactly as
the contract names them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import prama_sdk
import pytest
from prama_agent.link import LinkUnavailable, SdkFleetLink
from prama_kernel.errors import ConfigError


class Fleet:
    def __init__(self, fail: Exception | None = None, answer: Any = None) -> None:
        self.fail, self.answer = fail, answer
        self.calls: list[tuple[str, Any, Any]] = []

    def enrol(self, token: str, *, name: str, version: str, capabilities: dict) -> dict:
        self.calls.append(("enrol", token, name))
        return {"agent_id": "a1", "key": "00", "zone": "z", "poll_after_seconds": 30}

    def hello(self, hello: dict, *, key: bytes) -> Any:
        self.calls.append(("hello", hello, key))
        if self.fail:
            raise self.fail
        return self.answer if self.answer is not None else {"accepted_through": -1}

    def report(self, report: dict, *, key: bytes) -> Any:
        self.calls.append(("report", report, key))
        if self.fail:
            raise self.fail
        return {"accepted_through": 0}


class Client:
    def __init__(self, fleet: Fleet | None) -> None:
        if fleet is not None:
            self.fleet = fleet
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_the_three_calls_reach_the_sdk_with_the_key() -> None:
    fleet = Fleet()
    link = SdkFleetLink("https://prama.example.com", client=Client(fleet))
    assert link.enrol("t", name="eu-01", version="1", capabilities={})["agent_id"] == "a1"
    assert link.hello({"agent_id": "a1"}, key=b"k") == {"accepted_through": -1}
    assert link.report({"agent_id": "a1"}, key=b"k") == {"accepted_through": 0}
    assert [c[0] for c in fleet.calls] == ["enrol", "hello", "report"]
    assert fleet.calls[1][2] == b"k"


@pytest.mark.parametrize(
    "failure",
    [
        prama_sdk.ServerUnavailable("no server", remedy="start it"),
        prama_sdk.ServerError("boom", remedy="later"),
        prama_sdk.NotFoundError("no such route", remedy="upgrade the server"),
        prama_sdk.RateLimitedError("slow down", remedy="wait"),
    ],
)
def test_every_sdk_failure_is_unavailability_for_the_loop(failure: Exception) -> None:
    link = SdkFleetLink("https://prama.example.com", client=Client(Fleet(fail=failure)))
    with pytest.raises(LinkUnavailable):
        link.hello({}, key=b"k")
    with pytest.raises(LinkUnavailable):
        link.report({}, key=b"k")


def test_an_answer_that_is_not_a_message_is_unavailability() -> None:
    link = SdkFleetLink("https://prama.example.com", client=Client(Fleet(answer="<html>")))
    with pytest.raises(LinkUnavailable, match="not a protocol message"):
        link.hello({}, key=b"k")


def test_an_sdk_without_the_fleet_namespace_is_refused_at_start() -> None:
    client = Client(None)
    with pytest.raises(ConfigError, match="no fleet namespace"):
        SdkFleetLink("https://prama.example.com", client=client)
    assert client.closed
