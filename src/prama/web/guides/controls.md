<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Working with controls

A control is one statement about the data, in PQL, that a deterministic engine checks. Most
controls are not written by anyone: they are derived from declarations and wait as proposals.

## Proposals

**Controls → Proposals** lists what Prama derived or mined, each with the declaration or metadata
that implied it.

- **Accept** starts it running.
- **Reject it** asks *Why not?*, and the answer matters: *incorrect* says the rule that proposed it
  is wrong; *not material*, *too noisy* and *duplicate* say it is right but not worth running;
  *coincidental* says it was true of this extract only; *pending remediation* says the data will be
  fixed first. A rejection is remembered, so the same proposal does not come back.

## Running, silenced, retired

**Controls** groups every control by whether it actually runs.

- **Start running it** activates a proposal. At **Tier 1**, a control a person wrote must be started
  by a different person; a derived one is checked by whoever accepts it.
- **Silence it** needs an expiry and a reason (*until the new feed settles*). A control silenced
  with neither is one nobody turns back on.
- A retired control is kept, so its evidence stays attributable.

## Writing one

- **Control studio**: write PQL with the estate's datasets listed beside the editor, and, where
  the data allows, see what the control would have done each day last month before it runs.
- **Rule builder**: a form for anyone who will never write PQL. Choose the dataset, the column and
  the rule; the PQL appears as you build it, the same text a person would type.

From the command line:

```bash
prama control check suite.pql      # parse and lint
prama control explain suite.pql    # each control as a sentence a data owner reads
prama control compile suite.pql    # the SQL that will run
```

## Go deeper

- [Controls and PQL](../../../../docs/architecture/controls-and-pql.md): from declaration to running SQL.
- [SDK: controls and runs](../../../../docs/sdk/controls.md): the same, from Python.
- [The rule language (PQL)](../../../../docs/corpus/07-rule-language-spec.md): the language itself.
- [Adding a PQL function](../../../../docs/developer/pql-functions.md): when the language needs a word it lacks.
