"""SIEM export: audit events in a shape a security team's tooling already reads.

A bank's security team does not read your audit screen. They read Splunk, or
Sentinel, or whatever aggregates every system in the estate — and a product
whose audit trail only exists inside itself is one that gets a finding at the
next examination, because nobody can correlate it with anything else.

So this renders Prama's audit events into two formats that need no adapter on
the receiving side:

* **ECS** (Elastic Common Schema) as JSON Lines. The lingua franca of modern log
  pipelines, and structured, so a field survives.
* **CEF** (ArcSight Common Event Format). Older, line-oriented, and still what a
  great many bank SIEMs ingest natively.

Three things that decide whether an export is usable at three in the morning:

* **Severity is derived from the event, not stamped uniform.** A SIEM's whole
  value is triage, and a feed where everything is severity 5 is a feed that gets
  a suppression rule within a week. A denied action outranks a failed one, which
  outranks a success.
* **A field that could carry a secret is not exported.** ``detail_json`` is
  free-form and written by call sites all over the product; shipping it whole to
  a system with different access controls is how a password reaches a log
  aggregator. Named keys are carried and the rest is dropped, with the count of
  dropped keys reported so nobody thinks the detail was empty.
* **CEF escaping is not optional.** A pipe or an equals sign in a value ends the
  field, and an unescaped one silently truncates the event or merges it with the
  next — producing a log line that parses and means something else.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable
from typing import Any

from prama.version import PRODUCT_NAME, VERSION

#: Detail keys safe to export. Everything else is dropped: `detail_json` is
#: free-form and written by call sites all over the product, and shipping it
#: whole to a system with different access controls is how a secret travels.
EXPORTABLE_DETAIL = frozenset(
    {
        "dataset",
        "control",
        "control_id",
        "plan_id",
        "verdict",
        "reason",
        "count",
        "scope",
        "from",
        "to",
        "role",
        "permission",
        "template",
        "regime",
    }
)

#: Outcome to CEF severity, 0 to 10. Derived rather than uniform: a feed where
#: everything is a 5 gets a suppression rule within a week.
_SEVERITY = {"denied": 8, "failure": 6, "success": 2}

#: Actions that outrank their outcome. A successful permission grant is more
#: interesting than a failed read, and a SIEM ranking them the other way buries
#: the one a reviewer is looking for.
_ELEVATED = {
    "principal.create": 7,
    "principal.disable": 7,
    "role.grant": 7,
    "role.revoke": 7,
    "attestation.sign": 6,
    "control.suppress": 6,
    "evidence.erase": 8,
    "tenant.create": 7,
}


def severity_of(action: str, outcome: str) -> int:
    """How loudly this should arrive.

    The higher of what the outcome implies and what the action implies. A
    *successful* grant of an admin role is a security event whatever its
    outcome field says, and ranking it below a failed page load is how the
    interesting line gets buried.
    """
    return max(_SEVERITY.get(outcome, 2), _ELEVATED.get(action, 0))


@dataclasses.dataclass(frozen=True, slots=True)
class Exported:
    """Rendered lines, and what was left out of them."""

    lines: tuple[str, ...] = ()
    events: int = 0
    #: Detail keys dropped because they are not on the allow-list. Counted so
    #: nobody reads an empty detail as "there was none".
    dropped_detail_keys: int = 0

    def describe(self) -> str:
        note = ""
        if self.dropped_detail_keys:
            note = (
                f"; {self.dropped_detail_keys} detail field(s) were not exported "
                "because they are not on the allow-list, which is not the same as "
                "there having been none"
            )
        return f"{self.events} event(s) rendered{note}"

    def text(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.lines else "")


def _detail(payload: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict):
        return {}, 0
    kept = {key: value for key, value in payload.items() if key in EXPORTABLE_DETAIL}
    return kept, len(payload) - len(kept)


def to_ecs(events: Iterable[Any]) -> Exported:
    """Elastic Common Schema, one JSON object per line.

    Structured, so a field survives the pipeline. The mapping follows ECS names
    rather than Prama's — ``event.action``, ``user.id``, ``source.ip`` — because
    a field a SIEM has to be taught about is a field nobody filters on.
    """
    lines: list[str] = []
    dropped = 0
    for event in events:
        detail, lost = _detail(getattr(event, "detail_json", None))
        dropped += lost
        occurred = getattr(event, "occurred_at", "")
        document = {
            "@timestamp": occurred.isoformat() if hasattr(occurred, "isoformat") else str(occurred),
            "event": {
                "kind": "event",
                "category": ["configuration"],
                "action": event.action,
                "outcome": event.outcome,
                "severity": severity_of(event.action, event.outcome),
                "id": str(event.id),
            },
            "observer": {"product": PRODUCT_NAME, "version": VERSION, "vendor": PRODUCT_NAME},
            "organization": {"id": event.tenant_id},
            "user": {"id": event.actor_id or "", "roles": [event.actor_kind]},
            "source": {"ip": event.source_ip or ""},
            "trace": {"id": event.correlation_id or ""},
            "prama": {
                "object_kind": event.object_kind,
                "object_id": event.object_id or "",
                **detail,
            },
        }
        lines.append(json.dumps(document, sort_keys=True, default=str))
    return Exported(lines=tuple(lines), events=len(lines), dropped_detail_keys=dropped)


def _escape_header(value: str) -> str:
    """A CEF header field. Only the pipe and the backslash are special here."""
    return value.replace("\\", "\\\\").replace("|", "\\|")


def _escape_extension(value: str) -> str:
    """A CEF extension value.

    The equals sign matters as well as the pipe, and a newline ends the event
    entirely — an unescaped one silently truncates the record or merges it with
    the next, producing a log line that parses and means something else.
    """
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def to_cef(events: Iterable[Any]) -> Exported:
    """ArcSight Common Event Format, one line per event.

    Older than ECS and still what a great many bank SIEMs ingest natively,
    which is the whole reason it is here.
    """
    lines: list[str] = []
    dropped = 0
    for event in events:
        detail, lost = _detail(getattr(event, "detail_json", None))
        dropped += lost
        occurred = getattr(event, "occurred_at", "")
        extensions = {
            "rt": occurred.isoformat() if hasattr(occurred, "isoformat") else str(occurred),
            "suid": event.actor_id or "",
            "suser": event.actor_kind,
            "src": event.source_ip or "",
            "outcome": event.outcome,
            "cs1Label": "tenant",
            "cs1": event.tenant_id,
            "cs2Label": "objectKind",
            "cs2": event.object_kind,
            "cs3Label": "objectId",
            "cs3": event.object_id or "",
            "cs4Label": "correlationId",
            "cs4": event.correlation_id or "",
        }
        for index, (key, value) in enumerate(sorted(detail.items()), start=5):
            if index > 6:  # CEF defines cs1..cs6
                break
            extensions[f"cs{index}Label"] = key
            extensions[f"cs{index}"] = value

        header = "|".join(
            _escape_header(part)
            for part in (
                "CEF:0",
                PRODUCT_NAME,
                PRODUCT_NAME,
                VERSION,
                event.action,
                event.action,
                str(severity_of(event.action, event.outcome)),
            )
        )
        body = " ".join(f"{key}={_escape_extension(value)}" for key, value in extensions.items())
        lines.append(f"{header}|{body}")
    return Exported(lines=tuple(lines), events=len(lines), dropped_detail_keys=dropped)


FORMATS = {"ecs": to_ecs, "cef": to_cef}


def render(events: Iterable[Any], fmt: str = "ecs") -> Exported:
    try:
        return FORMATS[fmt](events)
    except KeyError:
        from prama.core.errors import ValidationError

        raise ValidationError(
            f"no SIEM format called {fmt!r}",
            remedy=f"One of: {', '.join(sorted(FORMATS))}.",
            context={"format": fmt},
        ) from None


__all__ = [
    "EXPORTABLE_DETAIL",
    "FORMATS",
    "Exported",
    "render",
    "severity_of",
    "to_cef",
    "to_ecs",
]
