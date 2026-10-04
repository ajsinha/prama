<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Discussion and your queue

## Comments

Every dataset's **Metadata** page has a **Discussion** section. Comment on the dataset or on one
of its attributes, and mention a colleague with `@username`. Replying to a resolved thread
reopens it. Comments can also be posted on a control, a glossary term or an incident, through
the API (`POST /api/v1/comments`) or the CLI (`prama comment … --as you`). Every comment and
resolution is written to the audit log.

## My queue

**My queue** (user menu) gathers everything waiting on you, read from where it already lives:

- threads that mention you, and open threads on datasets you own or steward;
- failing controls on those datasets;
- metadata inconsistencies that touch those datasets;
- curation suggestions for those datasets;
- if you can approve controls, the rules and delegate uploads that **somebody else** proposed.

Datasets come into your queue when you are their owner or steward on the declaration.

The same queue is available at `GET /api/v1/queue`, and from `prama queue --as you --approver`.

## Go deeper

- [The semantic layer](../../../../docs/architecture/semantic-layer.md): the objects comments are made on.
- [Evidence and assurance](../../../../docs/architecture/evidence-and-assurance.md): incidents and approvals, the other things waiting on a person.
