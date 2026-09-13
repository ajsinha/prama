# QA execution logs — round 3

The same 4,660 cases in `qa/catalogue/`, executed against the remediated tree.

Round 2's logs are in [`../logs/`](../logs/) and are a point-in-time record of
the tree as it stood before ten batches of fixes. They cannot say what those
fixes closed — only a re-run can, which is what this is.

## What changed between the two rounds

Ten remediation batches, `B1` through `B10`, committed between `ec16cfe` and
`03dcf7c`. Their commit messages carry the reasoning; `../findings.md` carries
the ranked register including the findings that came *out* of remediation
(`Q-57` through `Q-65`).

## The rule, unchanged

A case is `PASS` only if it was **run** and the observed behaviour matched the
catalogue's **Expected**. Not "the code looks right", not "the regression suite
covers it". If it was not executed, it is `BLOCKED`, with the reason stated.

## Reading the comparison

A case that failed in round 2 and passes here was fixed. A case that passes in
both was never broken. A case that **passed in round 2 and fails here is a
regression introduced by the remediation**, and is the most important thing
this round can find — more important than the fixes it confirms.

Format is identical to round 2 so the two are directly comparable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
