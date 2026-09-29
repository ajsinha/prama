"""The control estate as a set of operations, shared by every surface.

The console, the CLI and the HTTP API each let a person check a control, derive
controls from a declaration, accept or reject a proposal, and run the estate.
Each of those used to live inside the surface that offered it, which meant a
second surface either reimplemented it — and drifted — or could not offer it at
all. The operations live here instead, and each surface is a thin adapter:

* `prama.controls.language` — check, explain, compile, format, function coverage.
* `prama.controls.proposals` — the proposal queue, derivation (Γ), accept, reject.
* `prama.controls.runs` — a registered connection turned into a run, with evidence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
