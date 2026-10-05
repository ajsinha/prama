<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Operations

For people running Prama rather than designing it.

| Document | When you need it |
|---|---|
| [QUICKSTART](../../QUICKSTART.md) | Installing it, the first run, and running the steps separately on a real deployment |
| [Runbook](runbook.md) | Something is wrong in production and you are on call |
| [Troubleshooting](troubleshooting.md) | You are trying to make it work, or an error means something other than it says |
| [CLI reference](cli-reference.md) | Every command and flag — *generated from the argument parser* |
| [Configuration reference](configuration-reference.md) | Every setting and its default — *generated from the shipped YAML* |
| [Observability](observability.md) | Probes, Prometheus metrics, traces, OpenLineage, the Helm values, alerts |
| [Metrics reference](metrics-reference.md) | Every metric at `/metrics` — *generated from the registry* |
| [The agent operator's guide](../agent/README.md) | Installing and running `prama-agent` beside the data |

The three references are generated. If one disagrees with the code, the gate fails
— so a flag listed here exists, and one that is not listed does not.

## The shape of a Prama incident

Worth knowing before the first page. Prama's thesis is that a control's verdict
must be defensible, so almost every failure mode is a **refusal** rather than a
wrong answer: an empty session secret stops the boot, schema drift stops the
start, an undeclared jurisdiction stops an export, a full dead letter stops the
pipeline.

That is deliberate and it changes what an incident looks like. The common page
is *"Prama will not do something"*, not *"Prama did something wrong"*. Every
refusal carries a remedy — the next thing to do, not a restatement of the
problem — and an error without one is itself a defect worth reporting.

The corollary: when Prama *does* produce a surprising answer, treat it as a data
finding first. `not_established` is not `fail`, and neither is a bug.
