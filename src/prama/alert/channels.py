"""The shipped network notifiers: a webhook and email.

Both use the standard library alone — ``urllib.request`` and ``smtplib`` — so
alerting adds no dependency and nothing to vet.

Neither consults the residency gate, and that is deliberate rather than an
omission: the gate is consulted in `prama.alert.route`, the registered
``alert-delivery`` egress point, before a dispatch is released, and a notifier
only ever receives what the router released. A second check here would be a
second policy that could disagree with the first.

Secrets are references, never literals: the webhook's signing key comes from
``alerts.webhook.secret_ref`` and the mail password from
``alerts.email.password_ref``, both resolved through
`prama.secrets.resolver.default_resolver` at the moment of sending, so a
rotated credential is picked up without a restart.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import hmac
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any, ClassVar

from prama.alert.notify import DeliveryError, Message, Notifier
from prama.core import pjson

#: The header a webhook's HMAC-SHA256 signature travels in, as ``sha256=<hex>``
#: over the exact request body — the convention most receivers already check.
SIGNATURE_HEADER = "X-Prama-Signature"


def _secret(reference: str, *, setting: str, purpose: str) -> str:
    """Resolve a secret reference, refusing a literal secret in configuration."""
    if not reference:
        return ""
    if "://" not in reference:
        raise DeliveryError(
            f"{setting} holds a value that is not a secret reference",
            remedy=(
                f"Set {setting} to a reference such as env://PRAMA_ALERT_SECRET and put "
                "the secret there. A literal secret in configuration is one every "
                "reader of the file has."
            ),
            context={"setting": setting},
        )
    from prama.secrets.resolver import default_resolver

    return default_resolver().resolve(reference, purpose=purpose).reveal()


def signature(secret: str, body: bytes) -> str:
    """The value of `SIGNATURE_HEADER` for *body*: what a receiver recomputes."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class WebhookNotifier(Notifier):
    """POSTs the message as JSON to one URL, optionally signed."""

    plugin_key: ClassVar[str] = "webhook"
    description: ClassVar[str] = (
        "an HTTP POST of the message as JSON, signed with HMAC-SHA256 when a secret is set"
    )

    def deliver(self, message: Message) -> None:
        url = str(self.settings.get("url", "") or "")
        if not url.startswith(("http://", "https://")):
            raise DeliveryError(
                "alerts.webhook.url is not set to an http(s) URL",
                remedy="Set alerts.webhook.url to the receiver's address, or route no role to it.",
                context={"url": url},
            )
        body = pjson.dumps(message.to_dict(), sort_keys=True).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "prama-alerts"}
        secret = _secret(
            str(self.settings.get("secret_ref", "") or ""),
            setting="alerts.webhook.secret_ref",
            purpose="alert-webhook-signature",
        )
        if secret:
            headers[SIGNATURE_HEADER] = signature(secret, body)
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        timeout = float(self.settings.get("timeout", 10) or 10)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
        except urllib.error.HTTPError as exc:
            raise DeliveryError(
                f"the webhook answered {exc.code}",
                remedy="Check the receiver's logs; the message was not accepted.",
                context={"url": url, "status": exc.code},
                cause=exc,
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DeliveryError(
                f"the webhook could not be reached: {exc}",
                remedy="Check alerts.webhook.url and that this server can reach it.",
                context={"url": url},
                cause=exc,
            ) from exc
        if not 200 <= status < 300:
            raise DeliveryError(
                f"the webhook answered {status}",
                remedy="Check the receiver's logs; the message was not accepted.",
                context={"url": url, "status": status},
            )


class EmailNotifier(Notifier):
    """Sends the message by SMTP, with STARTTLS unless switched off."""

    plugin_key: ClassVar[str] = "email"
    description: ClassVar[str] = "email through an SMTP relay, over STARTTLS"

    def deliver(self, message: Message) -> None:
        host = str(self.settings.get("host", "") or "")
        sender = str(self.settings.get("sender", "") or "")
        if not host or not sender:
            raise DeliveryError(
                "alerts.email.host and alerts.email.sender must both be set",
                remedy="Name the SMTP relay and the From address, or route no role to email.",
                context={"host": host, "sender": sender},
            )
        recipients = [r for r in message.recipients if "@" in r]
        if not recipients:
            raise DeliveryError(
                "nobody this alert is for has an email address",
                remedy=(
                    "Record an email address on the principal named as the dataset's "
                    "owner, steward or custodian."
                ),
                context={"recipients": list(message.recipients)},
            )
        mail = EmailMessage()
        mail["Subject"] = message.subject
        mail["From"] = sender
        mail["To"] = ", ".join(recipients)
        mail.set_content(message.body)

        port = int(self.settings.get("port", 587) or 587)
        timeout = float(self.settings.get("timeout", 30) or 30)
        username = str(self.settings.get("username", "") or "")
        password = _secret(
            str(self.settings.get("password_ref", "") or ""),
            setting="alerts.email.password_ref",
            purpose="alert-email-login",
        )
        try:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                if self.settings.get("starttls", True):
                    smtp.starttls()
                if username:
                    smtp.login(username, password)
                refused: Any = smtp.send_message(mail)
        except (smtplib.SMTPException, OSError) as exc:
            raise DeliveryError(
                f"the mail relay did not accept the message: {exc}",
                remedy="Check alerts.email.host, port, starttls and the login.",
                context={"host": host, "port": port},
                cause=exc,
            ) from exc
        if refused:
            raise DeliveryError(
                f"the mail relay refused {len(refused)} recipient(s)",
                remedy="Check those addresses on the principals they belong to.",
                context={"refused": sorted(refused)},
            )
