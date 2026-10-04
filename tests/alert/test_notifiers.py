"""The shipped notifiers deliver for real, and fail loudly when they cannot.

The webhook is exercised against a real HTTP server on loopback, so what is
asserted is the request that arrived — its body and its signature recomputed
the way a receiver would — not the request the code meant to build. Email is
exercised with `smtplib.SMTP` replaced at the module boundary, recording the
conversation a relay would see.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import pytest

from prama.alert import channels
from prama.alert.channels import SIGNATURE_HEADER, EmailNotifier, WebhookNotifier
from prama.alert.notify import DeliveryError, LogNotifier, Message, Notifier, build, new_registry
from prama.core.errors import PramaError, RegistryError

MESSAGE = Message(
    subject="[Prama] opened: positions_eod (value)",
    body="Notional is null on 12 rows.",
    recipients=("sam@example.com", "ops"),
    alert={"alert": {"dataset": "positions_eod", "severity": 1.0}, "change": "opened"},
)


class Receiver:
    """A loopback HTTP server that keeps what it was sent."""

    def __init__(self, status: int = 204) -> None:
        received: list[dict[str, Any]] = []
        self.received = received

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                received.append({"headers": dict(self.headers), "body": self.rfile.read(length)})
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/hook"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> Receiver:
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def receiver() -> Iterator[Receiver]:
    with Receiver() as running:
        yield running


class TestWebhook:
    def test_the_body_and_the_signature_are_what_a_receiver_checks(
        self, receiver: Receiver, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRAMA_TEST_HOOK_SECRET", "hook-key")
        WebhookNotifier(
            {"url": receiver.url, "secret_ref": "env://PRAMA_TEST_HOOK_SECRET"}
        ).deliver(MESSAGE)

        [request] = receiver.received
        assert json.loads(request["body"]) == MESSAGE.to_dict()
        assert request["headers"]["Content-Type"] == "application/json"
        expected = hmac.new(b"hook-key", request["body"], hashlib.sha256).hexdigest()
        assert request["headers"][SIGNATURE_HEADER] == f"sha256={expected}"

    def test_a_signature_from_another_key_does_not_verify(
        self, receiver: Receiver, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The counterfactual: the receiver's check can fail."""
        monkeypatch.setenv("PRAMA_TEST_HOOK_SECRET", "another-key")
        WebhookNotifier(
            {"url": receiver.url, "secret_ref": "env://PRAMA_TEST_HOOK_SECRET"}
        ).deliver(MESSAGE)
        [request] = receiver.received
        expected = hmac.new(b"hook-key", request["body"], hashlib.sha256).hexdigest()
        assert request["headers"][SIGNATURE_HEADER] != f"sha256={expected}"

    def test_without_a_secret_it_is_unsigned(self, receiver: Receiver) -> None:
        WebhookNotifier({"url": receiver.url}).deliver(MESSAGE)
        [request] = receiver.received
        assert SIGNATURE_HEADER not in request["headers"]

    def test_a_literal_secret_in_configuration_is_refused(self, receiver: Receiver) -> None:
        with pytest.raises(DeliveryError, match="not a secret reference"):
            WebhookNotifier({"url": receiver.url, "secret_ref": "hook-key"}).deliver(MESSAGE)
        assert receiver.received == []

    def test_a_refusal_by_the_receiver_raises(self) -> None:
        with Receiver(status=500) as failing, pytest.raises(DeliveryError, match="500"):
            WebhookNotifier({"url": failing.url}).deliver(MESSAGE)

    def test_an_unreachable_receiver_raises(self) -> None:
        with Receiver() as gone:
            url = gone.url
        with pytest.raises(DeliveryError, match="could not be reached"):
            WebhookNotifier({"url": url, "timeout": 2}).deliver(MESSAGE)

    def test_no_url_is_a_refusal_not_a_quiet_return(self) -> None:
        with pytest.raises(DeliveryError, match=r"alerts\.webhook\.url"):
            WebhookNotifier({}).deliver(MESSAGE)


class FakeSmtp:
    """`smtplib.SMTP` as a relay would see it."""

    sessions: ClassVar[list[FakeSmtp]] = []
    refuse: ClassVar[dict[str, Any]] = {}

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.events: list[Any] = []
        FakeSmtp.sessions.append(self)

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.events.append("quit")

    def starttls(self) -> None:
        self.events.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.events.append(("login", user, password))

    def send_message(self, mail: Any) -> dict[str, Any]:
        self.events.append(("send", mail))
        return dict(FakeSmtp.refuse)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.sessions = []
    FakeSmtp.refuse = {}
    monkeypatch.setattr(channels.smtplib, "SMTP", FakeSmtp)
    return FakeSmtp


EMAIL = {
    "host": "relay.example.com",
    "port": 2525,
    "sender": "prama@example.com",
    "username": "prama",
    "password_ref": "env://PRAMA_TEST_SMTP_PASSWORD",
}


class TestEmail:
    def test_it_starts_tls_logs_in_and_sends_to_the_addresses(
        self, smtp: type[FakeSmtp], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRAMA_TEST_SMTP_PASSWORD", "relay-pass")
        EmailNotifier(EMAIL).deliver(MESSAGE)

        [session] = smtp.sessions
        assert (session.host, session.port) == ("relay.example.com", 2525)
        assert session.events[0] == "starttls"
        assert session.events[1] == ("login", "prama", "relay-pass")
        _, mail = session.events[2]
        assert mail["Subject"] == MESSAGE.subject
        assert mail["From"] == "prama@example.com"
        # Only addresses: "ops" is a username with no email and cannot be mailed.
        assert mail["To"] == "sam@example.com"
        assert "Notional is null" in mail.get_content()

    def test_starttls_can_be_switched_off_for_a_local_relay(self, smtp: type[FakeSmtp]) -> None:
        EmailNotifier({**EMAIL, "username": "", "password_ref": "", "starttls": False}).deliver(
            MESSAGE
        )
        [session] = smtp.sessions
        assert "starttls" not in session.events

    def test_nobody_with_an_address_is_a_refusal(self, smtp: type[FakeSmtp]) -> None:
        nobody = Message(subject="s", body="b", recipients=("ops",))
        with pytest.raises(DeliveryError, match="email address"):
            EmailNotifier(EMAIL).deliver(nobody)
        assert smtp.sessions == []

    def test_a_refused_recipient_raises(
        self, smtp: type[FakeSmtp], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRAMA_TEST_SMTP_PASSWORD", "relay-pass")
        smtp.refuse = {"sam@example.com": (550, b"no such user")}
        with pytest.raises(DeliveryError, match="refused 1"):
            EmailNotifier(EMAIL).deliver(MESSAGE)

    def test_a_relay_failure_is_a_prama_error(
        self, smtp: type[FakeSmtp], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import smtplib

        monkeypatch.setenv("PRAMA_TEST_SMTP_PASSWORD", "relay-pass")

        def broken(self: FakeSmtp) -> None:
            raise smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")

        monkeypatch.setattr(FakeSmtp, "starttls", broken)
        with pytest.raises(PramaError, match="did not accept"):
            EmailNotifier(EMAIL).deliver(MESSAGE)


class TestTheRegistry:
    def test_the_shipped_notifiers_are_registered_by_key(self) -> None:
        registry = new_registry()
        assert sorted(registry.keys()) == ["email", "log", "webhook"]
        assert all(m.kind == "notifier" for m in registry.manifests())

    def test_log_is_always_available(self, caplog: pytest.LogCaptureFixture) -> None:
        build("log", {}, new_registry()).deliver(MESSAGE)
        assert any(MESSAGE.subject in r.getMessage() for r in caplog.records)

    def test_an_unknown_channel_is_refused_by_name(self) -> None:
        with pytest.raises(RegistryError, match="pager"):
            build("pager", {}, new_registry())

    def test_a_notifier_must_implement_deliver(self) -> None:
        class Mute(Notifier):
            plugin_key = "mute"

        with pytest.raises(TypeError):
            Mute({})  # type: ignore[abstract]
        assert issubclass(LogNotifier, Notifier)
