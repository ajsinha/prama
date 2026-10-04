"""Notifiers: the last step, where a routed alert becomes a message somebody gets.

`prama.alert.route.Router` decides *who* hears about *what*, and *whether* they
have already heard; a notifier only carries one composed message over one
channel. The split is the point. Deduplication, the quiet period, the digest
and the residency gate are decided once, upstream, for every channel alike —
so a new channel cannot quietly re-announce an open incident, or send an alert
the residency rule withheld, because it never sees one.

A notifier is a :class:`prama.core.registry.Plugin`. The shipped ones are
``log`` (always available), ``webhook`` and ``email``
(`prama.alert.channels`); a distribution adds another by advertising it on the
``prama.notifiers`` entry-point group, which `prama.plugins.bootstrap` loads
at start, honouring ``plugins.disabled``. Which notifier serves which role is
``alerts.channels`` in configuration, and a notifier's own settings are the
``alerts.<key>`` section.

**A delivery failure raises; it never fails the run.** A notifier raises
:class:`DeliveryError` (or any `PramaError`) when the message did not arrive,
so the failure is real and attributable rather than a log line nobody reads.
The pipeline catches it, logs it and records it against the alert. Evidence is
the product; an alert is a courtesy.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
from collections.abc import Mapping
from typing import Any, ClassVar

from prama.core.errors import PramaError
from prama.core.log import get_logger
from prama.core.registry import Plugin, PluginManifest, Registry

_log = get_logger(__name__)

#: The entry-point group a distribution advertises notifiers under.
ENTRY_POINT_GROUP = "prama.notifiers"

#: The manifest kind every notifier declares.
KIND = "notifier"


class DeliveryError(PramaError):
    """A message did not reach its channel. Recorded against the alert."""

    code = "ALERT.DELIVERY"


@dataclasses.dataclass(frozen=True, slots=True)
class Message:
    """One composed message, ready for one channel.

    ``alert`` is the routed dispatch as a dictionary (`Dispatch.to_dict()`, or
    a digest's), so a channel that forwards structure — a webhook — forwards
    the same document every other channel was composed from.
    """

    subject: str
    body: str
    recipients: tuple[str, ...] = ()
    alert: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "body": self.body,
            "recipients": list(self.recipients),
            "alert": dict(self.alert),
        }


class Notifier(Plugin, abc.ABC):
    """Delivers one composed message over one channel.

    Constructed with its own section of configuration (``alerts.<key>``), once
    per pass, and asked to :meth:`deliver` each message. A subclass declares
    ``plugin_key`` and implements :meth:`deliver`; :meth:`manifest` is derived
    from the class unless it wants to say more.
    """

    #: Shown in the manifest. One line: what the channel is.
    description: ClassVar[str] = ""

    def __init__(self, settings: Mapping[str, Any] | None = None) -> None:
        self.settings: dict[str, Any] = dict(settings or {})

    @classmethod
    def manifest(cls) -> PluginManifest:
        return PluginManifest(
            key=cls.plugin_key,
            kind=KIND,
            display_name=cls.plugin_key,
            version="1",
            description=cls.description,
        )

    @abc.abstractmethod
    def deliver(self, message: Message) -> None:
        """Send *message*, or raise `DeliveryError` saying why it was not sent.

        Returning means it was handed to the channel. Never return quietly on
        failure: an alert that silently did not arrive is the one failure a
        person cannot see, because the thing that would tell them is the alert.
        """


class LogNotifier(Notifier):
    """Writes the message to Prama's own log. Always available.

    The default channel for every role, so turning alerts on does something
    observable before an operator has configured a webhook or a mail relay.
    """

    plugin_key: ClassVar[str] = "log"
    description: ClassVar[str] = "Prama's own log, at WARNING: always available"

    def deliver(self, message: Message) -> None:
        _log.warning(
            "ALERT %s → %s: %s",
            message.subject,
            ", ".join(message.recipients) or "(nobody)",
            message.body,
        )


def builtin() -> tuple[type[Notifier], ...]:
    """The shipped notifiers, in the order a console would list them."""
    from prama.alert.channels import EmailNotifier, WebhookNotifier

    return (LogNotifier, WebhookNotifier, EmailNotifier)


def new_registry() -> Registry[Notifier]:
    """A registry holding the shipped notifiers and nothing else."""
    registry: Registry[Notifier] = Registry(
        KIND,
        Notifier,  # type: ignore[type-abstract]
        entry_point_group=ENTRY_POINT_GROUP,
    )
    for notifier in builtin():
        registry.register(notifier)
    return registry


_default: Registry[Notifier] | None = None


def default_registry() -> Registry[Notifier]:
    """The process-wide notifier registry: the shipped ones, plus discovered."""
    global _default
    if _default is None:
        _default = new_registry()
    return _default


def build(
    key: str, settings: Mapping[str, Any], registry: Registry[Notifier] | None = None
) -> Notifier:
    """A notifier by key, constructed with its settings. Raises if unknown."""
    return (registry or default_registry()).get(key)(settings)


__all__ = [
    "ENTRY_POINT_GROUP",
    "DeliveryError",
    "LogNotifier",
    "Message",
    "Notifier",
    "build",
    "default_registry",
    "new_registry",
]
