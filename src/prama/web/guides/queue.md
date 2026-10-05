<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Discussion and your queue

Comment threads on the estate, and one place that gathers everything waiting on you. Your queue is
**My queue** in the user menu, or the inbox icon in the top bar (`/queue`).

## To start or answer a discussion

1. Open the dataset's page under **Estate → Metadata**, and go to its **Discussion** section.
2. Choose the dataset or one of its attributes, write the comment, and mention a colleague with
   `@username`. The mention reaches their queue.
3. **Reply** to continue a thread, and **Resolve** it when it is settled. Replying to a resolved thread
   reopens it.

Controls, glossary terms and incidents take comments through the API (`POST /api/v1/comments`) or the
CLI (`prama comment <target> "…" --as you`). Every comment and resolution is written to the audit log.

## To work your queue

**My queue** is read from where each item already lives, so nothing is copied into it:

- threads that mention you, and open threads on datasets you own or steward;
- failing controls on those datasets;
- metadata inconsistencies that touch them;
- curation suggestions for them;
- if you may approve controls, the rules and delegate uploads that **somebody else** proposed.

A dataset is yours when you are its owner or steward on the declaration. An item leaves when it is
resolved, not when it is seen. The same queue is at `GET /api/v1/queue` and
`prama queue --as you --approver`.

## Go deeper

- [The semantic layer](../../../../docs/architecture/semantic-layer.md): the objects comments are made on.
- [Evidence and assurance](../../../../docs/architecture/evidence-and-assurance.md): incidents and approvals, the other things waiting on a person.
