# prama-kernel

The deterministic code a Prama server and a remote Prama agent share: the plan
model, the judge, the evidence record, the reconciliation engine, business
calendars, the agent protocol with residency and spooling, and the delegate
runtime with its sandbox. One copy, so a verdict judged beside the data on an
agent is the verdict the server would have judged.

Standard library only. You do not install this directly: `prama` (the server)
and `prama-agent` depend on it.

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential; see LICENSE.
