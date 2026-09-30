"""What the agent keeps in its state directory, and how.

Three files, all written whole and moved into place so a daemon killed mid-write
never leaves one that will not load:

* ``identity.json`` — who this agent is: its id, its zone, the server it enrolled
  with, and its **key**, shown by the server once and held nowhere else. Mode
  0600 in a 0700 directory, because whoever can read it can sign findings as
  this agent.
* ``spool.json`` — findings not yet acknowledged (the kernel's `Spool`).
* ``contact.json`` — when the server last answered, how many calls since have
  failed, and whether it refused this agent for good. What ``prama-agent
  status`` reads; nothing in it is secret.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

from prama_kernel.errors import ConfigError, ValidationError

IDENTITY = "identity.json"
SPOOL = "spool.json"
CONTACT = "contact.json"


@dataclasses.dataclass(frozen=True, slots=True)
class Identity:
    """This agent, as the server enrolled it."""

    agent_id: str
    key_hex: str
    zone: str
    server: str
    name: str = ""
    enrolled_at: str = ""
    poll_after_seconds: int = 30

    @property
    def key(self) -> bytes:
        return bytes.fromhex(self.key_hex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "key": self.key_hex,
            "zone": self.zone,
            "server": self.server,
            "name": self.name,
            "enrolled_at": self.enrolled_at,
            "poll_after_seconds": self.poll_after_seconds,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Identity:
        key = str(payload["key"])
        bytes.fromhex(key)  # a key that is not hex is a corrupt file, said now
        return cls(
            agent_id=str(payload["agent_id"]),
            key_hex=key,
            zone=str(payload.get("zone", "")),
            server=str(payload.get("server", "")),
            name=str(payload.get("name", "")),
            enrolled_at=str(payload.get("enrolled_at", "")),
            poll_after_seconds=int(payload.get("poll_after_seconds", 30)),
        )

    def public(self) -> dict[str, Any]:
        """Everything but the key: for ``status`` and logs."""
        shown = self.to_dict()
        del shown["key"]
        return shown


def prepare(state_dir: Path) -> Path:
    """The state directory, created 0700 if it is not there."""
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return state_dir


def save_identity(state_dir: Path, identity: Identity, *, replace: bool = False) -> Path:
    path = prepare(state_dir) / IDENTITY
    if path.exists() and not replace:
        raise ValidationError(
            f"{path} already holds an agent identity",
            remedy=(
                "This machine is already enrolled. Pass --force to replace it with a new "
                "enrolment; the old agent should then be revoked on the server."
            ),
            context={"path": str(path)},
        )
    _write_private(path, identity.to_dict())
    return path


def load_identity(state_dir: Path) -> Identity:
    path = state_dir / IDENTITY
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Identity.from_dict(payload)
    except FileNotFoundError as exc:
        raise ConfigError(
            f"this agent is not enrolled: there is no {path}",
            remedy=(
                "Enrol it first: prama-agent enrol --server URL --token TOKEN --name NAME "
                f"--state {state_dir}"
            ),
            context={"path": str(path)},
        ) from exc
    except (OSError, ValueError, KeyError) as exc:
        raise ConfigError(
            f"the identity at {path} could not be read: {exc}",
            remedy="Restore it from backup, or enrol again with a new token and --force.",
            context={"path": str(path)},
        ) from exc


@dataclasses.dataclass(slots=True)
class Contact:
    """The daemon's last conversation with the server."""

    last_attempt_at: str = ""
    last_contact_at: str = ""
    consecutive_failures: int = 0
    last_error: str = ""
    #: A permanent refusal: the daemon will not start again until re-enrolled.
    refused: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Contact:
        return cls(
            last_attempt_at=str(payload.get("last_attempt_at", "")),
            last_contact_at=str(payload.get("last_contact_at", "")),
            consecutive_failures=int(payload.get("consecutive_failures", 0)),
            last_error=str(payload.get("last_error", "")),
            refused=dict(payload.get("refused") or {}),
        )


def load_contact(state_dir: Path) -> Contact:
    path = state_dir / CONTACT
    try:
        return Contact.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return Contact()
    except (OSError, ValueError) as exc:
        # Only a record of the last call. Unreadable, it is started afresh
        # rather than stopping an agent over its own diary.
        return Contact(last_error=f"contact.json was unreadable: {exc}")


def save_contact(state_dir: Path, contact: Contact) -> None:
    _write_private(prepare(state_dir) / CONTACT, contact.to_dict())


def _write_private(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON readable by the owner only, whole, then move it into place."""
    temporary = path.with_suffix(path.suffix + ".writing")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    # O_CREAT's mode does not apply to a file that already existed.
    temporary.chmod(0o600)
    temporary.replace(path)
