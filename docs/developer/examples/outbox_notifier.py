"""An alert notifier, ``outbox``.

The worked example of docs/developer/monitors-and-notifiers.md.

Appends each message as one JSON line to a file in a configured directory —
the shape a ticketing system that polls a drop folder, or a log shipper that
tails one, already reads. Configured under ``alerts.outbox`` and chosen per
role in ``alerts.channels``::

    alerts:
      enabled: true
      channels: {owner: email, steward: outbox, custodian: outbox}
      outbox:
        directory: /var/spool/prama-alerts

A notifier carries one composed message over one channel and decides nothing:
who hears, whether they have already heard, and whether residency allows it
were settled by the router before the message reached it. Its one obligation
is honesty about failure — raise `DeliveryError` when the message did not
arrive, never return quietly.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from prama.alert.notify import DeliveryError, Message, Notifier


class OutboxNotifier(Notifier):
    """One JSON line per message, appended to ``<directory>/alerts.jsonl``."""

    plugin_key: ClassVar[str] = "outbox"
    description: ClassVar[str] = "a JSON line per message, in a drop directory"

    def deliver(self, message: Message) -> None:
        directory = Path(str(self.settings.get("directory", "") or ""))
        if not str(directory) or not directory.is_dir():
            raise DeliveryError(
                f"alerts.outbox.directory {str(directory)!r} is not a directory",
                remedy="Create it, or point alerts.outbox.directory at one that exists.",
                context={"directory": str(directory)},
            )
        line = json.dumps(message.to_dict(), sort_keys=True)
        try:
            with (directory / "alerts.jsonl").open("a", encoding="utf-8") as outbox:
                outbox.write(line + "\n")
        except OSError as exc:
            raise DeliveryError(
                f"could not append to the outbox: {exc}",
                remedy="Check that the server can write to alerts.outbox.directory.",
                context={"directory": str(directory)},
                cause=exc,
            ) from exc
