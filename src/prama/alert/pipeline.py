"""From a finished run to a message in somebody's inbox.

`prama.alert.route` had everything an alert needs — routing by fault, a quiet
period, a digest, resolution, the residency gate — and nothing called it: the
server never built a `Router`, nothing turned a failing run into an `Alert`,
and no code delivered a `Dispatch` anywhere. This is that join, called after
every run commits, wherever a run completes: the in-server scheduler, ``prama
control run``, ``POST /api/v1/runs`` and an agent's report.

What happens, in order:

1. **Each failing record becomes an `Alert`**: what failed, where, how badly
   (the control's declared severity), and the fault that decides who hears.
2. **Recipients come from the semantic layer** — the dataset's declared owner,
   steward and custodian, as principals, by email address when the principal
   has one.
3. **A `Router` routes it**, seeded from the database with what has already
   been sent, so an incident still open is not announced again — after a
   restart, or from another server.
4. **Immediate dispatches are delivered now**; digest items are queued for the
   daily digest, which the scheduler's tick sends once a day after
   ``alerts.digest_hour``.
5. **A control that passes again resolves its open alert**, and the
   resolution is sent the way the alert was.

Off unless ``alerts.enabled`` is true. **A failure here never fails the run**:
the run's evidence has already committed, a notifier failure is logged and
recorded against the alert, and anything else is logged and dropped. Evidence
is the product; an alert is a courtesy.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from prama.alert.notify import Message, Notifier, default_registry
from prama.alert.route import (
    DEFAULT_QUIET,
    Alert,
    Change,
    Delivery,
    Dispatch,
    Fault,
    Role,
    Router,
)
from prama.core.clock import Clock, SystemClock
from prama.core.log import get_logger
from prama.core.registry import Registry

_log = get_logger(__name__)

#: A control's declared severity, as the 0..1 the router orders and gates by.
#: Major and above wake somebody; minor and below wait for the digest.
SEVERITY: dict[str, float] = {
    "critical": 1.0,
    "major": 0.75,
    "minor": 0.4,
    "warning": 0.25,
    "info": 0.1,
}

#: Where each role's contact is recorded on a dataset declaration.
_ROLE_COLUMNS: tuple[tuple[Role, str], ...] = (
    (Role.OWNER, "owner_id"),
    (Role.STEWARD, "steward_id"),
    (Role.CUSTODIAN, "custodian_id"),
)


@dataclasses.dataclass(frozen=True, slots=True)
class AlertSettings:
    """The ``alerts`` section of configuration, read once per pass."""

    enabled: bool = False
    #: Role → notifier key.
    channels: Mapping[Role, str] = dataclasses.field(default_factory=dict)
    #: Notifier key → where it delivers, for the residency gate.
    channel_regions: Mapping[str, str] = dataclasses.field(default_factory=dict)
    quiet: timedelta = DEFAULT_QUIET
    #: The hour (UTC, 0-23) after which the day's digest goes out.
    digest_hour: int = 9
    #: Notifier key → its own settings (``alerts.<key>``).
    notifier_settings: Mapping[str, Mapping[str, Any]] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Any) -> AlertSettings:
        channels = {
            role: str(config.get_str(f"alerts.channels.{role.value}", "log") or "log")
            for role in Role
        }
        keys = set(channels.values())
        return cls(
            enabled=config.get_bool("alerts.enabled", False),
            channels=channels,
            channel_regions={
                str(k): str(v) for k, v in config.get_dict("alerts.channel_regions", {}).items()
            },
            quiet=timedelta(seconds=float(config.get_duration("alerts.quiet_period", "6h"))),
            digest_hour=max(0, min(23, config.get_int("alerts.digest_hour", 9))),
            notifier_settings={key: config.get_dict(f"alerts.{key}", {}) for key in keys},
        )


@dataclasses.dataclass(slots=True)
class AlertReport:
    """What one pass did with a run's records."""

    dispatches: list[Dispatch] = dataclasses.field(default_factory=list)
    #: Messages handed to a notifier without error.
    delivered: int = 0
    queued: int = 0
    resolved: int = 0
    #: fingerprint → why delivery failed.
    failures: dict[str, str] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatches": [d.to_dict() for d in self.dispatches],
            "delivered": self.delivered,
            "queued": self.queued,
            "resolved": self.resolved,
            "failures": dict(self.failures),
        }


def fault_of(record: Any, pql: str = "") -> Fault:
    """Which kind of problem a failing record is, which decides who hears.

    From the control's declared dimensions and its text, never from the
    message: a reconciliation goes to the steward, a late feed and a broken
    shape to the custodian, a wrong value to the steward.
    """
    text = " ".join(str(pql).upper().split())
    dimensions = {str(d).lower() for d in getattr(record, "dimensions", ()) or ()}
    if text.startswith("RECONCILE"):
        return Fault.RECONCILIATION
    if "timeliness" in dimensions or "IS FRESH" in text:
        return Fault.ARRIVAL
    if "conformity" in dimensions:
        return Fault.SCHEMA
    return Fault.VALUE


def describe_failure(record: Any, name: str) -> str:
    """What failed, in the terms the evidence itself uses."""
    metrics = dict(getattr(record, "metrics", {}) or {})
    what = f"{name} failed on {record.dataset}"
    violating = metrics.get("violating_rows")
    scanned = metrics.get("scanned_rows")
    if violating is not None:
        what += f": {float(violating):,.0f} violating row(s)"
        if scanned:
            what += f" of {float(scanned):,.0f} scanned"
    threshold = dict(getattr(record, "parameters", {}) or {}).get("threshold")
    if threshold:
        what += f", against {threshold}"
    detail = str(getattr(record, "detail", "") or "")
    if detail:
        what += f". {detail}"
    return what


def _instant(stamp: str | None, fallback: datetime) -> datetime:
    if not stamp:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class AlertPipeline:
    """One estate's alerts for one pass, on one unit of work."""

    def __init__(
        self,
        uow: Any,
        tenant_id: str,
        settings: AlertSettings,
        *,
        registry: Registry[Notifier] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._uow = uow
        self._tenant = tenant_id
        self._settings = settings
        self._registry = registry or default_registry()
        self._clock = clock or SystemClock()
        self._notifiers: dict[str, Notifier] = {}

    # -- after a run ---------------------------------------------------------

    async def process(self, records: Sequence[Any]) -> AlertReport:
        """Alert on failures, resolve what passes again, deliver, and save."""
        report = AlertReport()
        relevant = [r for r in records if str(getattr(r, "verdict", "")) in ("fail", "pass")]
        if not relevant:
            return report
        before = await self._uow.alerts.history(self._tenant)
        router, jurisdictions = await self._router(relevant, before)
        alerts: dict[str, Alert] = {}

        for record in relevant:
            if record.verdict == "fail":
                alert = await self._alert_for(record, jurisdictions.get(record.dataset, ""))
                alerts[alert.fingerprint] = alert
                await self._handle(router.dispatch(alert), report)
                continue
            for row in await self._uow.alerts.open_for(self._tenant, str(record.control_id)):
                opened = Alert.from_stored(row.alert_json)
                if not router.has_sent(opened):
                    continue  # resolved earlier in this same pass
                resolution = router.resolve(dataclasses.replace(opened, at=self._clock.now()))
                report.resolved += 1
                await self._handle(resolution, report)

        await self._save(before, router.history, alerts)
        for fingerprint, error in report.failures.items():
            await self._uow.alerts.record_error(self._tenant, fingerprint, error)
        return report

    async def _router(
        self, records: Sequence[Any], history: Mapping[str, tuple[datetime, float]]
    ) -> tuple[Router, dict[str, str]]:
        contacts: dict[tuple[str, Role], str] = {}
        jurisdictions: dict[str, str] = {}
        for dataset in sorted({str(r.dataset) for r in records}):
            declared = await self._uow.datasets.by_slug(self._tenant, dataset)
            if declared is None:
                continue
            jurisdictions[dataset] = str(getattr(declared, "jurisdiction", "") or "")
            for role, column in _ROLE_COLUMNS:
                identity = await self._contact(getattr(declared, column, None))
                if identity:
                    contacts[(dataset, role)] = identity
        gate = None
        tenant = await self._uow.tenants.get(self._tenant)
        residency = getattr(tenant, "residency", None) if tenant is not None else None
        if residency:
            from prama.security.egress import Gate

            gate = Gate.for_tenant(residency, self._tenant)
        router = Router(
            contacts,
            quiet=self._settings.quiet,
            channels=self._settings.channels,
            channel_regions=self._settings.channel_regions,
            gate=gate,
            history=history,
        )
        return router, jurisdictions

    async def _contact(self, principal_id: str | None) -> str:
        """A principal as somebody a channel can reach: email, else username."""
        if not principal_id:
            return ""
        principal = await self._uow.principals.get(principal_id)
        if principal is None or principal.tenant_id != self._tenant:
            return ""
        if str(getattr(principal, "status", "active")) != "active":
            return ""
        return str(principal.email or principal.username)

    async def _alert_for(self, record: Any, jurisdiction: str) -> Alert:
        control_id = str(record.control_id)
        version = await self._uow.controls.current(control_id, tenant_id=self._tenant)
        name = str(getattr(version, "name", "") or "") or f"control {control_id}"
        severity = SEVERITY.get(str(getattr(version, "severity", "major") or "major"), 0.75)
        return Alert(
            identity=control_id,
            dataset=str(record.dataset),
            fault=fault_of(record, str(getattr(version, "pql", "") or "")),
            what=describe_failure(record, name),
            severity=severity,
            at=_instant(getattr(record, "finished_at", ""), self._clock.now()),
            jurisdiction=jurisdiction,
        )

    async def _handle(self, dispatch: Dispatch, report: AlertReport) -> None:
        report.dispatches.append(dispatch)
        if not dispatch.sent:
            _log.info(
                "alert %s on %s not sent: %s",
                dispatch.alert.identity,
                dispatch.alert.dataset,
                dispatch.reason,
            )
            return
        if dispatch.delivery is Delivery.DIGEST:
            await self._uow.alerts.queue(
                self._tenant,
                fingerprint=dispatch.alert.fingerprint,
                dataset=dispatch.alert.dataset,
                change=dispatch.change.value,
                dispatch=dispatch.to_dict(),
                queued_at=self._clock.now().isoformat(),
            )
            report.queued += 1
            return
        errors = self._deliver_dispatch(dispatch)
        if errors:
            report.failures[dispatch.alert.fingerprint] = "; ".join(errors)
        else:
            report.delivered += 1

    def _deliver_dispatch(self, dispatch: Dispatch) -> list[str]:
        """Send one dispatch on each of its recipients' channels; the failures."""
        alert = dispatch.alert
        subject = f"[Prama] {dispatch.change.value}: {alert.dataset} ({alert.fault.value})"
        if dispatch.change is Change.RESOLVED:
            body = f"Resolved: {alert.what.rstrip('.')} — the control passes again."
        else:
            body = alert.compose()
        roles = sorted({r.role.value for r in dispatch.recipients})
        body += f"\n\nSent to the {', '.join(roles)}: {dispatch.reason}."
        by_channel: dict[str, list[str]] = {}
        for person in dispatch.recipients:
            by_channel.setdefault(person.channel, []).append(person.identity)
        errors = []
        for channel, people in sorted(by_channel.items()):
            message = Message(
                subject=subject, body=body, recipients=tuple(people), alert=dispatch.to_dict()
            )
            error = self._send(channel, message)
            if error:
                errors.append(f"{channel}: {error}")
        return errors

    def _send(self, channel: str, message: Message) -> str:
        """Deliver through one notifier. The failure as text, or empty."""
        try:
            notifier = self._notifiers.get(channel)
            if notifier is None:
                settings = self._settings.notifier_settings.get(channel, {})
                notifier = self._registry.get(channel)(settings)
                self._notifiers[channel] = notifier
            notifier.deliver(message)
        except Exception as exc:
            # Logged and returned for recording, never raised: the run this
            # alert is about has committed, and must stay committed.
            text = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
            _log.warning("alert delivery through %r failed: %s", channel, text)
            return str(text)
        return ""

    async def _save(
        self,
        before: Mapping[str, tuple[datetime, float]],
        after: Mapping[str, tuple[datetime, float]],
        alerts: Mapping[str, Alert],
    ) -> None:
        """Write the router's state back: what is newly sent, what is over."""
        for fingerprint, (sent_at, severity) in after.items():
            if before.get(fingerprint) == (sent_at, severity):
                continue
            alert = alerts.get(fingerprint)
            if alert is None:  # pragma: no cover - only alerts routed here change
                continue
            await self._uow.alerts.remember(
                self._tenant,
                fingerprint=fingerprint,
                identity=alert.identity,
                dataset=alert.dataset,
                fault=alert.fault.value,
                severity=severity,
                last_sent_at=sent_at.isoformat(),
                alert=alert.as_stored(),
            )
        for fingerprint in set(before) - set(after):
            await self._uow.alerts.forget(self._tenant, fingerprint)

    # -- the daily digest ----------------------------------------------------

    async def send_digest_if_due(self) -> int:
        """Send the day's digest if it is past the hour and none went today.

        Returns how many queued items it carried. One digest per recipient
        and channel, so each person reads only what was routed to them.
        """
        now = self._clock.now().astimezone(UTC)
        if now.hour < self._settings.digest_hour:
            return 0
        due_from = now.replace(hour=self._settings.digest_hour, minute=0, second=0, microsecond=0)
        last = await self._uow.alerts.last_digest_at(self._tenant)
        if last and _instant(last, now) >= due_from:
            return 0
        pending = await self._uow.alerts.pending(self._tenant)
        if not pending:
            return 0

        groups: dict[tuple[str, str], list[Any]] = {}
        for item in pending:
            for person in item.dispatch_json.get("recipients", []):
                key = (str(person.get("channel", "log")), str(person.get("identity", "")))
                groups.setdefault(key, []).append(item)
        errors: dict[str, list[str]] = {}
        for (channel, identity), items in sorted(groups.items()):
            error = self._send(channel, digest_message(items, recipient=identity, at=now))
            if error:
                for item in items:
                    errors.setdefault(str(item.id), []).append(f"{channel}: {error}")

        stamp = now.isoformat()
        clean = [str(item.id) for item in pending if str(item.id) not in errors]
        await self._uow.alerts.mark_sent(self._tenant, clean, sent_at=stamp)
        for item_id, failures in errors.items():
            await self._uow.alerts.mark_sent(
                self._tenant, [item_id], sent_at=stamp, error="; ".join(failures)
            )
        return len(pending)


def digest_message(items: Sequence[Any], *, recipient: str, at: datetime) -> Message:
    """One person's digest, most severe first."""
    entries = [dict(item.dispatch_json) for item in items]
    entries.sort(key=lambda d: -float(dict(d.get("alert", {})).get("severity", 0.0)))
    datasets = {dict(d.get("alert", {})).get("dataset", "") for d in entries}
    lines = [
        f"{len(entries)} finding(s) across {len(datasets)} dataset(s) since the last digest.",
        "",
    ]
    for entry in entries:
        alert = dict(entry.get("alert", {}))
        lines.append(f"- {entry.get('change', '')}: {alert.get('message', '')}")
    return Message(
        subject=f"[Prama] daily digest: {len(entries)} finding(s)",
        body="\n".join(lines),
        recipients=(recipient,),
        alert={"digest": {"at": at.isoformat(), "count": len(entries), "items": entries}},
    )


# ---------------------------------------------------------------------------
# Entry points: called where runs complete, after their evidence has committed.
# ---------------------------------------------------------------------------


async def alert_after_run(
    database: Any,
    tenant_id: str,
    config: Any,
    *,
    run_id: str | None = None,
    records: Iterable[Any] | None = None,
    registry: Registry[Notifier] | None = None,
    clock: Clock | None = None,
) -> AlertReport | None:
    """Alert on a finished run, in a unit of work of its own, if alerts are on.

    Give it the run's id (its records are read back from the ledger) or the
    records themselves (an agent's report, which has no run). Never raises:
    whatever goes wrong is logged, and the run it is about stays committed.
    """
    try:
        settings = AlertSettings.from_config(config)
        if not settings.enabled:
            return None
        async with database.unit_of_work() as uow:
            batch = list(records or ())
            if run_id:
                batch.extend(await uow.evidence.for_run(run_id, tenant_id=tenant_id))
            if not batch:
                return AlertReport()
            return await AlertPipeline(
                uow, tenant_id, settings, registry=registry, clock=clock
            ).process(batch)
    except Exception as exc:
        _log.warning("alerting after run %s failed and was skipped: %s", run_id or "", exc)
        return None


async def digest_if_due(
    database: Any,
    tenant_id: str,
    config: Any,
    *,
    registry: Registry[Notifier] | None = None,
    clock: Clock | None = None,
) -> int:
    """Send the daily digest if it is due. Called from the scheduler's tick."""
    try:
        settings = AlertSettings.from_config(config)
        if not settings.enabled:
            return 0
        async with database.unit_of_work() as uow:
            return await AlertPipeline(
                uow, tenant_id, settings, registry=registry, clock=clock
            ).send_digest_if_due()
    except Exception as exc:
        _log.warning("the alert digest for %s failed and was skipped: %s", tenant_id, exc)
        return 0


__all__ = [
    "SEVERITY",
    "AlertPipeline",
    "AlertReport",
    "AlertSettings",
    "alert_after_run",
    "describe_failure",
    "digest_if_due",
    "digest_message",
    "fault_of",
]
