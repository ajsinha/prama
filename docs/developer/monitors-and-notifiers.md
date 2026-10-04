<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Monitors and notifiers

A monitor watches one metric over time (rows per day, a null rate, freshness) and says when an
observation is unusual enough to tell somebody; alert routing decides who that somebody is, and
whether they have already been told; a notifier carries the message. Two of those are extension
points: the **detector**, which scores how strange an observation is, and the **notifier**, which
delivers a message over one channel. The calibration between them and the routing after them are
fixed on purpose. Why monitoring is built this way is in
[Evidence and assurance](../architecture/evidence-and-assurance.md#calibration-and-monitoring).

## When you would write one

- A **detector**, when the shipped ones are blind to the shape your metric has: a series with a
  structure none of robust deviation, quantile distance, local outlier factor, forecast residual
  or shape distance captures.
- A **notifier**, when alerts must reach a channel the shipped `log`, `webhook` and `email` do
  not: a pager, a chat tool's own API, a ticketing system.
- A **routing change**, when a new kind of fault needs a different owner: a member of `Fault`
  and its `route_to` role in `src/prama/alert/route.py`.

## The interfaces

### Detector

```python
# src/prama/monitor/detect.py:96
class Detector(Plugin):
    """Turns an observation and its history into a nonconformity score."""

    name: ClassVar[str] = ""
    good_at: ClassVar[str] = ""     # for the model card and the person choosing
    blind_to: ClassVar[str] = ""    # every detector is blind to something; say what

    @classmethod
    def manifest(cls) -> PluginManifest: ...   # derived from name, good_at, blind_to

    def score(self, observation: float, history: Sequence[float]) -> Score | None:
        """The nonconformity score, or None when the history cannot support one."""
        return self.compute(observation, list(history[-MAXIMUM_CALIBRATION:]))

    @abc.abstractmethod
    def compute(self, observation: float, history: Sequence[float]) -> Score | None:   # line 142
        """Score against an already-windowed history. Subclasses override this."""
```

You implement `compute`. `score` caps the window once, so the observation and the calibration
points are scored against the same reference set, and `scores(history)` produces the
calibration scores leave-one-out. A `Score` (line 69) carries the value, the detector's name, an
explanation a person can read, and the expected and observed values for the chart.

**A detector produces a nonconformity score, never a verdict.** Its only contract is that a
stranger point scores higher, computed the same way for calibration and observation. How unusual
the score is, and whether that is enough to alert, is the conformal calibrator's question. That
split is why a badly chosen detector costs sensitivity and never validity: noise scores are
exchangeable with calibration scores, so the false-alarm rate still holds and the monitor simply
finds less.

### Notifier

```python
# src/prama/alert/notify.py:54
@dataclasses.dataclass(frozen=True, slots=True)
class Message:
    """One composed message, ready for one channel."""

    subject: str
    body: str
    recipients: tuple[str, ...] = ()                  # email addresses, else usernames
    alert: Mapping[str, Any] = ...                    # Dispatch.to_dict(), or a digest's


# src/prama/alert/notify.py:76
class Notifier(Plugin, abc.ABC):
    """Delivers one composed message over one channel."""

    description: ClassVar[str] = ""

    def __init__(self, settings: Mapping[str, Any] | None = None) -> None:
        self.settings: dict[str, Any] = dict(settings or {})   # the alerts.<key> section

    @abc.abstractmethod
    def deliver(self, message: Message) -> None:     # line 102
        """Send *message*, or raise `DeliveryError` saying why it was not sent."""
```

You set `plugin_key` and implement `deliver`; the manifest is derived. **A notifier decides
nothing.** Who hears, whether they have already heard, whether it can wait for the digest, and
whether residency allows the message to leave were all settled by the router before the message
reached it, so a new channel cannot re-announce an open incident or send what the residency gate
withheld. Its one obligation is honesty about failure: raise `DeliveryError` (`ALERT.DELIVERY`)
or any `PramaError` when the message did not arrive, and never return quietly. The pipeline
catches the error, logs it, records it on the alert (`alr_state.last_error`) and carries on: a
delivery failure never fails the run, because the evidence has already committed.

Secrets are references. A notifier that needs a credential takes a `*_ref` setting and resolves
it when it sends, through `prama.secrets.resolver.default_resolver`, as the shipped webhook
(`alerts.webhook.secret_ref`) and email (`alerts.email.password_ref`) notifiers in
`src/prama/alert/channels.py` do; a literal secret in the setting is refused.

![From a metric to a person: detector, calibration, alert, router, notifier](../assets/diagrams/dev-monitor.svg)

## Worked examples

### A detector

**The real ones.** `RobustDeviation` in `src/prama/monitor/detect.py` is the simplest: distance
from the median in units of the median absolute deviation, returning `None` below
`MINIMUM_HISTORY`, and treating a constant history as spread 1 rather than dividing by zero.

**A new one.** `docs/developer/examples/trimmed_deviation_detector.py` measures distance from a
trimmed mean, discarding the most extreme tenth at each end first, so a few bad days in the
window do not widen the band the next bad day is judged against:

```python
class TrimmedDeviation(Detector):
    name: ClassVar[str] = "trimmed_deviation"
    good_at: ClassVar[str] = (
        "a level that has shifted, on a roughly symmetric series with occasional outliers"
    )
    blind_to: ClassVar[str] = (
        "a trend, and a bounded or skewed quantity such as a null rate, where a "
        "symmetric band spends half its width on the impossible side"
    )

    def compute(self, observation: float, history: Sequence[float]) -> Score | None:
        if len(history) < MINIMUM_HISTORY:
            return None
        ordered = sorted(history)
        cut = int(len(ordered) * TRIM)
        kept = ordered[cut : len(ordered) - cut] or ordered
        centre = sum(kept) / len(kept)
        spread = math.sqrt(sum((v - centre) ** 2 for v in kept) / len(kept)) or 1.0
        deviation = abs(observation - centre) / spread
        return Score(value=deviation, detector=self.name, expected=centre, observed=observation,
                     explanation=f"{observation:,.0f} against a trimmed mean of {centre:,.0f}, ...")
```

It is a function of the history as a *set*: sorting first means the order of the points does not
matter, which is what leave-one-out calibration assumes. A detector keyed on "the last value"
would not be, and the validity test below would catch it.

### A notifier

**The real ones.** `LogNotifier` in `src/prama/alert/notify.py` writes to Prama's own log and
needs nothing configured. `WebhookNotifier` in `src/prama/alert/channels.py` POSTs
`Message.to_dict()` as JSON with the standard library's `urllib`, signing the exact body with
HMAC-SHA256 in `X-Prama-Signature: sha256=<hex>` when a secret is set; `EmailNotifier` sends
through an SMTP relay with STARTTLS, to the recipients that have an address.

**A new one.** `docs/developer/examples/outbox_notifier.py` appends each message as one JSON
line in a drop directory, the shape a ticketing system that polls a folder already reads:

```python
class OutboxNotifier(Notifier):
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
            raise DeliveryError(f"could not append to the outbox: {exc}", ...) from exc
```

Its settings are its own section of `alerts`, and an operator routes roles to it by key:

```yaml
alerts:
  enabled: true
  channels: {owner: email, steward: outbox, custodian: outbox}
  outbox:
    directory: /var/spool/prama-alerts
```

## Registration and configuration

**Discovery.** Both seams are entry-point groups, loaded once at start by
`prama.plugins.bootstrap`, which the CLI (`Application.run`) and the server (`create_app`) both
call, after the configuration is known:

```toml
# the third-party distribution's pyproject.toml
[project.entry-points."prama.monitors"]
trimmed_deviation = "acme_prama.detectors:TrimmedDeviation"

[project.entry-points."prama.notifiers"]
outbox = "acme_prama.notifiers:OutboxNotifier"
```

`plugins.disabled` switches one off by entry-point name or plugin key; a disabled plugin is never
imported, and says so in the log. A plugin can never take a shipped plugin's key: the shipped
ones are registered first, and a duplicate is refused and logged. The registries are
`prama.monitor.registry` (`detector("trimmed_deviation")` builds one by name) and
`prama.alert.notify` (`build("outbox", settings)`).

**Detectors.** Registering a detector makes it *available*, not a default:

```python
from prama.monitor.detect import Ensemble, default_ensemble
from prama.monitor.fleet import MetricKind, Monitor

monitor = Monitor("trades", "rows", kind=MetricKind.VOLUME, detector="trimmed_deviation")
ensemble = Ensemble(detectors=(*default_ensemble().detectors, TrimmedDeviation()))
```

`Monitor` (`src/prama/monitor/fleet.py:166`) takes a detector or its registered name, and chooses
a default from the metric's kind when none is given (`_default_detector`: quantile distance for a
bounded quantity, forecast residual for freshness, robust deviation otherwise). To make yours a
default, change that function: a package changing what every monitor in an estate runs merely by
being installed would be a change nobody decided. `Ensemble` scores and calibrates each detector
apart and combines the p-values, never the raw scores. A challenger can run in shadow and be
promoted on measured precision through `src/prama/monitor/tournament.py`.

**Notifiers.** The `alerts` section of `config/application.yaml` chooses one per role and holds
each one's settings; the full list is in the
[configuration reference](../operations/configuration-reference.md):

| Key | Meaning |
|---|---|
| `alerts.enabled` | off by default: nothing is sent until an operator decides where alerts go |
| `alerts.channels.owner`, `.steward`, `.custodian` | the notifier key for each role (`log` by default) |
| `alerts.channel_regions` | notifier key → where it delivers, for the residency gate |
| `alerts.quiet_period` | an open incident is not announced again within it unless it worsens (`6h`) |
| `alerts.digest_hour` | the UTC hour after which the scheduler's tick sends the daily digest (`9`) |
| `alerts.<key>` | that notifier's own settings: `alerts.webhook.url`, `.secret_ref`; `alerts.email.host`, `.port`, `.starttls`, `.sender`, `.username`, `.password_ref` |

## Alert routing and delivery

`Router` (`src/prama/alert/route.py:331`) takes an `Alert` and returns a `Dispatch`: who should
hear, immediately or in the digest, and whether anything changed since the last message. Routing
follows the **fault**, not the severity:

```python
# src/prama/alert/route.py:80
class Fault(enum.Enum):
    ARRIVAL = "arrival"              # -> Role.CUSTODIAN: runs the pipeline
    SCHEMA = "schema"                # -> Role.CUSTODIAN
    VALUE = "value"                  # -> Role.STEWARD: owns the meaning
    DEFINITION = "definition"        # -> Role.STEWARD
    RECONCILIATION = "reconciliation"  # -> Role.STEWARD
    CALIBRATION = "calibration"      # -> Role.CUSTODIAN: Prama's own problem
```

A new fault is a member here and a line in `route_to`; a test in `tests/alert/` that an alert of
that fault reaches the role you intend.

**After every run** — the scheduler's tick, `prama control run`, `POST /api/v1/runs` and an
agent's report — `prama.alert.pipeline.alert_after_run` runs in a unit of work of its own, after
the run's evidence has committed:

1. each `fail` record becomes an `Alert`: what failed and by how much, the control's declared
   severity (`critical` 1.0, `major` 0.75, `minor` 0.4 …), and the fault (`timeliness` is
   arrival, `conformity` is schema, a reconciliation is reconciliation, the rest are values);
2. the recipients are the dataset's declared owner, steward and custodian
   (`sem_dataset_version`), as principals, by email address when the principal has one;
3. a `Router` built with `history=` from `alr_state` routes it, so an incident already announced
   (by this server before a restart, or by another server) is `UNCHANGED` and quiet;
4. `IMMEDIATE` dispatches go to their channels' notifiers now; `DIGEST` ones are queued in
   `alr_digest`, and `digest_if_due`, called from the scheduler's tick, sends each recipient one
   digest a day after `alerts.digest_hour`;
5. a control with an open alert that now passes is resolved, and the resolution is sent the
   way the alert was; `router.history` is saved back to `alr_state`.

## Testing

- **A detector's contract**, as `tests/monitor/test_detect.py` applies it to every shipped
  detector: a stranger point scores higher; nothing is said on a history shorter than
  `MINIMUM_HISTORY`; `good_at` and `blind_to` are filled in; calibration scores are leave-one-out
  (an outlier planted in the history has the highest score of its own).
- **Validity.** Over a few hundred pure-noise series, the share of p-values at or below 0.10
  must stay near 0.10. This is the test that catches a detector that is not a symmetric function
  of its history.
- **Sensitivity.** `src/prama/monitor/benchmark.py` measures detection on stationary, seasonal,
  level-shift, regime-switch and bursty series; run it before claiming a detector is better.
- **A notifier against the real thing.** `tests/alert/test_notifiers.py` posts to a real HTTP
  server on loopback and recomputes the signature the way a receiver would; email is checked at
  the `smtplib` boundary. Test the failure path as carefully as the success: a refusal, an
  unreachable endpoint and a missing setting must each raise.
- **The pipeline.** `tests/alert/test_delivery.py` runs a failing control and asserts exactly
  one message, then silence on an identical second run, then a resolution when it passes, and
  that a router rebuilt from the database does not repeat it.
- **Discovery.** `tests/core/test_plugin_bootstrap.py` installs a real distribution (a
  `dist-info` with `entry_points.txt` on `sys.path`) and asserts each plugin is usable and that
  `plugins.disabled` keeps it out.
- **The counterfactuals.** The examples' tests in `tests/docs/test_developer_examples.py` run
  the detector contract on `TrimmedDeviation` (replace its trimmed centre with the most recent
  value and the leave-one-out test fails) and send a failing run's alert through
  `OutboxNotifier` (point it at a missing directory and it must raise, not return).

## Checklist

- [ ] A detector's `compute` returns `None` below `MINIMUM_HISTORY`, and never a verdict.
- [ ] The score is a symmetric function of the history, computed the same way for every point.
- [ ] `good_at` and `blind_to` say something a person choosing a detector can use.
- [ ] A notifier's `deliver` raises a `PramaError` on every failure, and decides nothing about
      who hears or when.
- [ ] Credentials are `*_ref` settings resolved when sending, never literals.
- [ ] The contract, validity and delivery tests pass; the benchmark run is attached for a detector.
- [ ] Advertised on `"prama.monitors"` or `"prama.notifiers"`, and chosen where it is used:
      `Monitor(detector=...)`, an `Ensemble`, or `alerts.channels`.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
