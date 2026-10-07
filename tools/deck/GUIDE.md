# Deck generator

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.</sub>

---

Regenerates Prama's deck from source, so it is reproducible rather than a binary nobody can
edit safely. Adopted from Maya's generator, with Prama's palette and a second, rendered audit.

```bash
uv sync --extra dev --extra deck                       # python-pptx
.venv/bin/python tools/deck/build.py                   # the deck, into docs/publications/deck/
.venv/bin/python tools/deck/audit.py docs/publications/deck/Prama-Evidence-First-Data-Quality.pptx
.venv/bin/python tools/deck/render_audit.py docs/publications/deck/Prama-Evidence-First-Data-Quality.pptx
.venv/bin/python -m pytest -q tests/docs/test_deck.py  # both audits, as tests
```

## One deck

| Deck | Slides | Source |
|---|---|---|
| `docs/publications/deck/Prama-Evidence-First-Data-Quality.pptx` | 59 | `prama_deck.py`, then `deck_part1.py` to `deck_part3.py` |

It is written for the people who must stand behind a number: a chief data officer, a data
owner, a head of risk or audit, and the engineer asked to run it. Its storytelling is a
pyramid, the answer first:

- **The opening.** A TL;DR in five questions (what is the problem, what is Prama, why it
  matters, what it does today, where it is going); the question every number must answer;
  ten principles of evidence-first data quality; the four ways a programme fails; what a
  supervisor asks for; Prama in one slide.
- **Ten numbered sections**, each opened by a divider that says what it covers:
  1. How Prama works: the core primitives, the system in context, the life of a control.
  2. Declare it: the semantic layer.
  3. The language.
  4. Prove it: evidence and reconciliation.
  5. Lineage and impact.
  6. Trust it.
  7. AI that never adjudicates.
  8. How it runs: deployment, what is built and tested, storage, agents, security.
  9. Worked examples: three questions somebody actually asks (month-end close, a defect's
     blast radius, fitness for a purpose), each answered step by step from a case study.
  10. Where Prama stands: built, coming next, a comparison by category, what it does not
      do, where to start.
- **The close.**

Most content slides end with one line in a tinted box: the thing to remember.

**Every figure comes from somewhere a reader can check:** the code, a test, a case study's run,
or `prama bench run --seed 42`. Where a slide depends on a test, its note names the test. The
research paper in [`docs/publications/paper/`](../../docs/publications/paper/) is cited once, as where the proofs are.

## How it is put together

| File | Purpose |
|---|---|
| `metrics.py` | The text estimator: a greedy word-wrap simulation and paragraph heights. The builder and the geometry audit share it, so the builder never believes a box fits that the audit then reports |
| `theme.py` | The design system: the console's crimson theme, token for token from its light theme (`src/prama/web/static/css/themes.css`), so the deck and the product look like one thing; the console header's gradient on the dark slides; the prism's six-colour spectrum as the one flourish (`docs/reference/brand.md`). It also holds the primitives and `fitted()`, which shrinks a text block until it fits or raises `DoesNotFit` |
| `layouts.py` | Slide kinds drawn from plain dictionaries: `title`, `divider`, `bullets`, `table`, `cards`, `stats`, `split`, `flow`, `context` (boxes joined by straight arrows), and for the storytelling: `qa` (the TL;DR), `numbered` (principles, steps), `workflow` (a worked example from a quoted question), `compare` (yes, partly, no, coloured) and `thanks` |
| `prama_deck.py`, `deck_part1.py` … `deck_part3.py` | The deck, as data. Split into parts only to keep each file short; they are one deck, meant to be read in order |
| `build.py` | Builds the deck and sets the document properties explicitly: the author, and no tool |
| `audit.py` | The geometry audit, from estimates |
| `render_audit.py` | The rendered audit, from what LibreOffice actually lays out |

A slide that cannot be made to fit **fails the build**, naming the slide. The fix is to shorten
the text or split the slide, never to lower the floor.

## Two audits, because estimates were what failed

`audit.py` re-derives the geometry of every shape and reports the following:

- a shape off the slide;
- a table taller than its frame;
- an opaque shape drawn over earlier content;
- anything printed over a table;
- text escaping its container;
- content crossing the footer rule;
- a textbox whose overflow lands on another shape.

It works from the same estimates the builder uses. That is its weakness: in Maya's decks, the
builder believed a box fitted, the audit agreed, and the rendered slide was wrong.

`render_audit.py` does not estimate. It converts the deck to PDF with LibreOffice and reads
every word's box back with `pdftotext -bbox-layout`. It then reports:

- a word that leaves the slide;
- a word of content at or below the footer rule;
- two words printed over each other.

**It caught a real defect that the geometry audit passed.** On the title slide, the last agenda
line sat on the footer rule, because LibreOffice's metric-compatible fonts set nine lines taller
than the estimate. Both audits must pass before the deck ships. `tests/docs/test_deck.py` runs
them both, asserts the slide count above, and checks that the file names its author and no tool.
The rendered audit is skipped where LibreOffice or poppler is not installed.
