# Domain knowledge, and the analyses built on it

The seven packages that know something about *the world* rather than about
Prama: the banking pack, the semantic-type validators and their code lists,
reconciliation, data contracts, importers, catalogue write-back, and lineage.

Round 1 asked whether the product works when you use it. This asks whether the
knowledge inside it is *right* — which is a different failure mode, because a
wrong check digit, a calendar that closes a day the market is open, or a code
list that retires a code a year early all produce a **confident, green, wrong**
answer. Every one of those is invisible from the outside.

Three findings already landed in this territory and they set the standard for
what is asked here: **C9** (the Fed calendar closed three Fridays Fedwire was
open, while the comment directly above the rules said it must not), **H1**
(eight cross-field SQL templates each disagreeing with their own Python
reference, every disagreement running the unsafe way), and **H3** (three ways
past the plugin purity gate). All three were *claims the code did not keep*,
and all three were found by reading a docstring and asking whether it was true.

Case ids: `PCK-` banking pack · `CLS-` classification · `RCN-` reconciliation ·
`CTR-` contracts · `IMP-` importers · `INT-` integration · `LIN-` lineage.

Format and rules: see [README.md](README.md). Nothing here has been executed.

## Summary

| Prefix | Area | Cases | P1 | P2 | P3 |
|---|---|---:|---:|---:|---:|
| `PCK-` | The banking pack | 212 | 128 | 78 | 6 |
| `CLS-` | Classification | 135 | 78 | 51 | 6 |
| `RCN-` | Reconciliation | 110 | 66 | 39 | 5 |
| `CTR-` | Data contracts | 62 | 46 | 16 | 0 |
| `IMP-` | Importers | 55 | 33 | 22 | 0 |
| `INT-` | Integration | 43 | 34 | 9 | 0 |
| `LIN-` | Lineage | 63 | 39 | 24 | 0 |
| | **Total** | **680** | **424** | **239** | **17** |

What each area covers:

- **`PCK-` The banking pack** — `packs/banking/` — calendars, cross-field checks, five message parsers, concepts, regimes, reconciliation templates
- **`CLS-` Classification** — `classify/` — twenty semantic-type validators, four dated code lists, the inference cascade, the plugin purity gate
- **`RCN-` Reconciliation** — `recon/` — matching, normalisation, break classification, the workflow and certificate, n-way and roll-forward
- **`CTR-` Data contracts** — `contract/` — ODCS import and export, quality blocks, the diff, and the CI gate's exit codes
- **`IMP-` Importers** — `importers/` — dbt, SodaCL, Great Expectations, and what did not come across
- **`INT-` Integration** — `integrate/` — catalogue badges, three vendor adapters, the operator's decision and its control loop
- **`LIN-` Lineage** — `lineage/` — the column graph, SQL extraction, procedural and ETL scanners


## Calendars and holiday rules — `packs/banking/holidays.py`, `packs/banking/calendars.py`

### PCK-001 · Easter is computed, not tabulated
- **Area:** `packs/banking/holidays.py::easter_sunday`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `easter_sunday(2024)`, `(2025)`, `(2026)`, `(2027)`
- **Expected:** `2024-03-31`, `2025-04-20`, `2026-04-05`, `2027-03-28`
- **Why:** four of the six TARGET2 closures hang off this date, and the module
  says a tabulated Easter is "the single most likely thing in a calendar pack
  to run out". A wrong Easter is four wrong closures a year in the euro RTGS
  calendar.

### PCK-002 · Easter across the Gregorian century corrections
- **Area:** `packs/banking/holidays.py::easter_sunday`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `easter_sunday(1900)`, `(2000)`, `(2100)`, `(2038)`
- **Expected:** `1900-04-15`, `2000-04-23`, `2100-03-28`, `2038-04-25` — 2038
  being the latest possible Easter
- **Why:** the anonymous Gregorian algorithm's `f`/`g` terms only matter at a
  century boundary, so a transcription error there passes every test written
  inside one lifetime.

### PCK-003 · Good Friday is Easter minus two
- **Area:** `packs/banking/holidays.py::Rule._base`, kind `easter`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate `_easter("Good Friday", -2)` for 2026
- **Expected:** `2026-04-03`, a Friday
- **Why:** the sign of the offset is the whole rule, and an inverted one puts
  Good Friday on the Tuesday after Easter, which no test that only counts
  closures would notice.

### PCK-004 · Easter Monday is Easter plus one
- **Area:** `packs/banking/holidays.py::Rule._base`, kind `easter`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** evaluate `_easter("Easter Monday", 1)` for 2026
- **Expected:** `2026-04-06`, a Monday
- **Why:** the counterpart to PCK-003; both signs must be right and they are
  written as one field.

### PCK-005 · A fixed-date rule lands on its date
- **Area:** `packs/banking/holidays.py::Rule._base`, kind `fixed`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `_fixed("Christmas Day", 12, 25).dates_in(2025)`
- **Expected:** `(2025-12-25,)` — a Thursday, so no observance applies
- **Why:** the simplest rule kind, and the base case every observance test
  measures a deviation from.

### PCK-006 · An nth-weekday rule counts from the first of the month
- **Area:** `packs/banking/holidays.py::Rule._base`, kind `nth_weekday`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** third Monday in January 2026; third Monday in February 2026;
  fourth Thursday in November 2026
- **Expected:** `2026-01-19`, `2026-02-16`, `2026-11-26`
- **Why:** `ahead = (weekday - first.weekday()) % 7` is off by a week whenever
  the first of the month *is* the target weekday, which happens about one month
  in seven and produces a holiday everyone else observes a week earlier.

### PCK-007 · An nth-weekday rule where the first of the month is the weekday
- **Area:** `packs/banking/holidays.py::Rule._base`, kind `nth_weekday`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** first Monday in September 2029 (2029-09-01 is a Saturday); first
  Monday in September 2030 (2030-09-02 is a Monday — pick a year where the 1st
  is the target weekday, e.g. first Monday in June 2026, 2026-06-01 being a
  Monday)
- **Expected:** the 1st itself, not the 8th
- **Why:** the modulo-7 boundary. Labor Day on the 8th when it is the 1st is
  the exact shape of PCK-006's failure and the only case that distinguishes it.

### PCK-008 · A last-weekday rule steps back from the next month
- **Area:** `packs/banking/holidays.py::Rule._base`, kind `last_weekday`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** last Monday in May 2026; last Monday in August 2026
- **Expected:** `2026-05-25`, `2026-08-31`
- **Why:** Memorial Day and the UK Summer Bank Holiday both depend on it, and
  stepping back from the first of the next month is the trick that avoids
  knowing month lengths — so it is the arithmetic to check.

### PCK-009 · A last-weekday rule in December crosses the year
- **Area:** `packs/banking/holidays.py::Rule._base`, kind `last_weekday`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `_last("x", 12).dates_in(2026)` — the branch that uses
  `date(year + 1, 1, 1)`
- **Expected:** the last Monday of December 2026, `2026-12-28`; no exception
- **Why:** the only rule kind that constructs a date in a *different* year, and
  the only one that can throw at a year boundary.

### PCK-010 · A last-weekday rule in a leap February
- **Area:** `packs/banking/holidays.py::Rule._base`, kind `last_weekday`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** last Monday in February 2024 and in February 2025
- **Expected:** `2024-02-26` and `2025-02-24`
- **Why:** the leap day changes which weekday the month ends on; a rule that
  hard-coded 28 days would be right three years in four.

### PCK-011 · An unknown rule kind is refused, not guessed
- **Area:** `packs/banking/holidays.py::Rule._base`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Rule(name="x", kind="lunar").dates_in(2026)`
- **Expected:** `ValidationError` naming the kind, with the remedy listing
  `fixed, easter, nth_weekday, last_weekday`
- **Why:** a silently-empty tuple would delete a holiday from a calendar, and
  a calendar that is missing a closure reports a market-closed day as a missed
  delivery.

### PCK-012 · `Observance.NONE` loses a weekend holiday entirely
- **Area:** `packs/banking/holidays.py::Rule._observed`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** TARGET2's `Labour Day` (1 May) in 2021, when 1 May was a Saturday
- **Expected:** `(2021-05-01,)` and no substitute weekday; the set of business
  days that week is unchanged
- **Why:** most European fixed dates work this way, and a substitute invented
  here closes TARGET2 on a day the euro RTGS system was open.

### PCK-013 · `SUNDAY_TO_MONDAY` rolls a Sunday and drops a Saturday
- **Area:** `packs/banking/holidays.py::Observance.SUNDAY_TO_MONDAY`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** Independence Day 2027 (4 July is a Sunday) and 2026 (4 July is a
  Saturday), on the Federal Reserve rules
- **Expected:** 2027 gives `2027-07-05` (Monday); 2026 gives `2026-07-04` only
  — **`2026-07-03` is a business day**
- **Why:** finding C9 exactly. The Fed's published schedule says offices are
  *open* the preceding Friday for a Saturday holiday, and for four releases the
  comment said so while every rule carried `NEAREST_WEEKDAY`.

### PCK-014 · `NEAREST_WEEKDAY` moves a Saturday back and a Sunday forward
- **Area:** `packs/banking/holidays.py::Observance.NEAREST_WEEKDAY`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** NYSE Independence Day 2026 (Saturday) and 2027 (Sunday)
- **Expected:** `2026-07-03` and `2027-07-05` — the exchange *is* closed the
  Friday
- **Why:** the counterpart of PCK-013. The asymmetry between the two
  observances is the entire content of C9, and a fix applied in one direction
  must not silently become a fix in both.

### PCK-015 · A `NEAREST_WEEKDAY` holiday moves, it does not multiply
- **Area:** `packs/banking/holidays.py::Rule._observed`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** NYSE Christmas Day 2027 (25 December is a Saturday); count the
  dates the rule returns
- **Expected:** exactly one date, `2027-12-24`; the 25th itself is **not** in
  the set
- **Why:** the docstring says "the holiday moves; it does not multiply", and
  finding T13 records a parametrised test that accepted the parameter and never
  asserted this.

### PCK-016 · `ROLL_FORWARD` gives Monday for both weekend days
- **Area:** `packs/banking/holidays.py::Rule._observed`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** London New Year's Day 2022 (1 January was a Saturday)
- **Expected:** `2022-01-03`, the Monday, *in addition to* nothing — the
  Saturday is not a business day anyway
- **Why:** UK bank-holiday practice, and the reason the London calendar has
  two substitutes some Christmases.

### PCK-017 · Consecutive UK holidays produce two substitute days, not one
- **Area:** `packs/banking/holidays.py::observed`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** materialise the London calendar for 2021 (25 December Saturday,
  26 December Sunday)
- **Expected:** both `2021-12-27` and `2021-12-28` are closed
- **Why:** the collision loop in `observed` exists only for this; getting it
  wrong "loses a business day every few years in a way nobody notices until a
  month-end report is a day late".

### PCK-018 · Substitute resolution is order-dependent across rules
- **Area:** `packs/banking/holidays.py::observed`
- **Type:** regression
- **Priority:** P2
- **Precondition:** none
- **Steps:** reverse the order of `LONDON_RULES` so Boxing Day precedes
  Christmas Day, and materialise 2021
- **Expected:** the same two closures, `2021-12-27` and `2021-12-28`
- **Why:** the `while candidate in closed` loop walks forward over a set built
  in *iteration order*, so which holiday gets the Monday and which the Tuesday
  depends on how the tuple was typed. A calendar whose answer depends on
  declaration order is one a reordering commit can change silently.

### PCK-019 · A ROLL_FORWARD substitute skips a weekend it lands on
- **Area:** `packs/banking/holidays.py::observed`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct three consecutive ROLL_FORWARD fixed holidays landing
  Friday/Saturday/Sunday and materialise
- **Expected:** three distinct weekday closures, none of them a Saturday or
  Sunday
- **Why:** the loop advances past `candidate.weekday() >= SATURDAY` as well as
  past collisions; a substitute placed on a Saturday is a closure nobody
  observes and a business day silently lost.

### PCK-020 · `since` keeps a holiday out of the years before it existed
- **Area:** `packs/banking/holidays.py::Rule.applies_in`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** Federal Reserve Juneteenth in 2020, 2021 and 2022
- **Expected:** absent in 2020; present from 2021
- **Why:** Juneteenth became a US federal holiday in 2021, and a back-dated
  rule reports a 2019 business day as closed — which makes every timeliness
  control replayed over 2019 wrong.

### PCK-021 · The Fed and the NYSE adopted Juneteenth in different years
- **Area:** `packs/banking/calendars.py::FEDERAL_RESERVE_RULES`, `NYSE_RULES`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** 19 June 2021 against each calendar
- **Expected:** closed on FederalReserve (`since=2021`), **open** on NYSE
  (`since=2022`)
- **Why:** the two `since` values differ by one year on purpose, and a single
  shared constant would be wrong for one of them.

### PCK-022 · `until` is exercised, or declared unused
- **Area:** `packs/banking/holidays.py::Rule.applies_in`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** a rule with `until=2025`, evaluated for 2025 and 2026
- **Expected:** present in 2025, absent in 2026 — inclusive of the `until` year
- **Why:** no shipped rule sets `until`, so the branch is unexercised by the
  pack; a retired holiday is exactly what it is for and the inclusivity is a
  coin-flip nobody has called.

### PCK-023 · TARGET2 has exactly six rules and no national holiday
- **Area:** `packs/banking/calendars.py::TARGET2_RULES`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** materialise TARGET2 for 2026; check 14 July (Bastille Day) and
  3 October (German Unity Day)
- **Expected:** both are business days; the rule count is 6
- **Why:** the module names this as "precisely the trap a European calendar
  assembled from national ones falls into". A payment control on TARGET2 that
  thinks 14 July is closed reports every French payment that day as late.

### PCK-024 · The Fed is open on Good Friday and the NYSE is not
- **Area:** `packs/banking/calendars.py::FEDERAL_RESERVE_RULES`, `NYSE_RULES`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** 2026-04-03 against both calendars
- **Expected:** FederalReserve open, NYSE closed
- **Why:** the stated reason the two calendars exist separately. "A settlement
  control that used one where it meant the other is wrong four days a year."

### PCK-025 · Columbus Day and Veterans Day run the other way
- **Area:** `packs/banking/calendars.py`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** the second Monday of October 2026 and 11 November 2026 against
  both calendars
- **Expected:** FederalReserve closed on both; NYSE open on both
- **Why:** the other half of PCK-024 and the other two of the "four days a
  year"; a calendar pack that got Good Friday right and these wrong would look
  correct in the only test anybody writes.

### PCK-026 · London ships the England-and-Wales set only
- **Area:** `packs/banking/calendars.py::LONDON_RULES`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** 2 January 2026 (a Scottish bank holiday) and 17 March 2026 (a
  Northern Ireland one) against the London calendar
- **Expected:** both are business days, and the calendar's description says
  "England and Wales"
- **Why:** a UK bank with a Scottish entity reading this as "the UK calendar"
  gets two wrong business days a year; the name does not say what the
  description does.

### PCK-027 · Every shipped calendar carries a timezone
- **Area:** `packs/banking/calendars.py::SPECS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each of the four specs, resolve `spec.timezone` through
  `zoneinfo.ZoneInfo`
- **Expected:** all four resolve; TARGET2 is `Europe/Brussels`, London is
  `Europe/London`, the two US ones are `America/New_York`
- **Why:** a business date is derived with the calendar's timezone, and a
  typo'd zone name raises at schedule time rather than at import.

### PCK-028 · `materialise` covers the declared horizon and no more
- **Area:** `packs/banking/calendars.py::CalendarSpec.materialise`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** materialise TARGET2 with the defaults; check 2015-01-01,
  2040-12-25, 2014-12-25 and 2041-12-25
- **Expected:** the first two are closures; the last two are *not in the set*
- **Why:** `FIRST_YEAR`/`LAST_YEAR` exist so "a calendar can say when it stops
  knowing". Silence outside the range is the failure the range was created to
  prevent, so what happens past 2040 must be established.

### PCK-029 · A control scheduled past the horizon fails loudly
- **Area:** `packs/banking/calendars.py` docstring claim · `core/calendars.py`
- **Type:** negative
- **Priority:** P1
- **Precondition:** the shipped calendars installed
- **Steps:** ask the materialised TARGET2 calendar whether 2041-12-25 is a
  business day
- **Expected:** a refusal naming the horizon — **not** `True`
- **Why:** the docstring: "a control scheduled beyond the horizon must fail
  loudly rather than quietly treat an unknown year as all-weekdays". A frozen
  holiday set answers `True` for any year it does not know, which is the exact
  silent failure the sentence forbids.

### PCK-030 · `prama pack calendar --year` ignores the horizon
- **Area:** `cli/pack.py::PackCalendarCommand`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama pack calendar TARGET2 --year 1850` and `--year 2200`
- **Expected:** a refusal naming `FIRST_YEAR`–`LAST_YEAR`, or output that
  states the year is outside what the pack claims to know
- **Why:** the command calls `observed(rules, [year])` directly rather than
  `materialise`, so it will compute and print closures for any year at all —
  under a `describe()` line that says "2015 to 2040". Two sentences in one
  output disagreeing is the H1 shape.

### PCK-031 · `prama pack calendar` never shows ad-hoc closures
- **Area:** `cli/pack.py::PackCalendarCommand`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a spec carrying `with_closures`
- **Steps:** add a closure and run the command for that year
- **Expected:** the closure appears in the listing, or the listing says it is
  showing rule-derived closures only
- **Why:** the command bypasses `materialise`, which is where `self.closures`
  is unioned in, while printing `describe()` which counts them. The count and
  the list would disagree.

### PCK-032 · `describe()` distinguishes "none supplied" from "there were none"
- **Area:** `packs/banking/calendars.py::CalendarSpec.describe`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** `describe()` on a spec with no closures and on one with two
- **Expected:** the first says "none have been provided, which is not the same
  as there having been none"; the second says "2 ad-hoc closure(s) supplied"
- **Why:** the stated reason the field exists. An exchange shut for a state
  funeral is not a rule, and a calendar silent about that invites a reader to
  assume it has them.

### PCK-033 · `with_closures` does not mutate the shipped spec
- **Area:** `packs/banking/calendars.py::CalendarSpec.with_closures`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `spec("TARGET2").with_closures([date(2026,9,9)])`, then
  `spec("TARGET2").closures`
- **Expected:** the original spec is still empty; the returned copy holds one
- **Why:** `SPECS` is module-level and shared; a mutation would leak one
  tenant's exchange closure into every other tenant's calendar in the process.

### PCK-034 · `install` is idempotent and replaces on demand
- **Area:** `packs/banking/calendars.py::install`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `install(registry)` twice without `replace`; then with
  `replace=True`
- **Expected:** the second bare call refuses or is a no-op rather than
  producing a duplicate; `replace=True` succeeds
- **Why:** `install_shipped` calls it with `replace=True` into the default
  registry, and `create_app` plus the CLI entry point can both run in one
  process.

### PCK-035 · `install()` with no registry materialises into nothing
- **Area:** `packs/banking/calendars.py::install`
- **Type:** regression
- **Priority:** P1
- **Precondition:** none
- **Steps:** call `install()` bare, then `parse("06:30 TARGET2")` through
  `prama.schedule.spec`
- **Expected:** the schedule still refuses, because the default registry was
  never touched — and this must be *documented*, since it is indistinguishable
  from not calling it at all
- **Why:** finding H7 in full. `install()` defaults to a fresh registry and
  returns it; the caller that drops the return value has done nothing, and the
  remedy told the reader to write exactly the string that then failed.

### PCK-036 · `spec()` is case-insensitive and refuses an unknown name
- **Area:** `packs/banking/calendars.py::spec`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `spec("target2")`, `spec("FEDERALRESERVE")`, `spec("Sifma")`
- **Expected:** the first two resolve; the third raises `KeyError`, which
  `PackCalendarCommand` converts to a `ValidationError` naming the four
- **Why:** a raw `KeyError` reaching a terminal is finding Q-28's shape, and
  the CLI conversion is the only thing preventing it here.

### PCK-037 · `prama pack list` advertises four calendars and docs/12 claims seven
- **Area:** `cli/pack.py::PackListCommand` vs `docs/12 §7`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare `prama pack list` output against docs/12 §7, which names
  "TARGET2, US SIFMA, UK, JPX, HKEX, per-market and per-currency"
- **Expected:** either the doc is corrected to the four that ship, or the
  missing three are listed as not shipped
- **Why:** the same document's own summary (§0) says "four business calendars",
  so the document disagrees with itself; §7 is the paragraph a procurement
  reader quotes.

## Cross-field checks — `packs/banking/crossfield.py`

### PCK-038 · All eight functions are registered by `install_shipped`
- **Area:** `packs/__init__.py::install_shipped` · `crossfield.install`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a fresh process, CLI entry point only
- **Steps:** `prama control check` on a suite naming each of
  `IBAN_BIC_CONSISTENT`, `MINOR_UNITS_OK`, `SETTLES_AFTER_TRADE`,
  `SIGN_MATCHES_SIDE`, `SAME_COUNTRY`, `IBAN_COUNTRY`, `BIC_COUNTRY`,
  `ISIN_COUNTRY`
- **Expected:** all eight resolve, in the same process where `prama pack list`
  advertises them
- **Why:** finding H1. `install()` was called only from `tests/` for four
  waves, so one CLI command advertised eight checks another refused.

### PCK-039 · The same eight resolve inside the web application
- **Area:** `packs/__init__.py::install_shipped` called from `create_app`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the console running
- **Steps:** author a control using `IBAN_BIC_CONSISTENT` through the console
  and compile it
- **Expected:** it compiles
- **Why:** the fix required *two* production call sites, and a test asserting
  only the CLI one would let the console regress on its own.

### PCK-040 · `IBAN_BIC_CONSISTENT` agrees on a matching pair
- **Area:** `crossfield.py::_iban_bic_consistent` and its SQL template
- **Type:** functional
- **Priority:** P1
- **Precondition:** DuckDB available for SQL execution
- **Steps:** `('DE89370400440532013000', 'COBADEFF')` through both the Python
  reference and the emitted SQL
- **Expected:** `True` from both — `DE` from the IBAN, `DE` from BIC positions
  5-6
- **Why:** the happy path, and the positional arithmetic (1-based `SUBSTR` in
  SQL against 0-based slicing in Python) is where an off-by-one hides.

### PCK-041 · `IBAN_BIC_CONSISTENT` catches a country disagreement
- **Area:** `crossfield.py::_iban_bic_consistent`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `('DE89370400440532013000', 'BNPAFRPP')`
- **Expected:** `False` from both sides
- **Why:** both identifiers are individually valid here — this is the defect
  class that single-column validation structurally cannot reach, and the one
  docs/12 §3 names as the reason the module exists.

### PCK-042 · Two empty identifiers are UNKNOWN, not consistent
- **Area:** `crossfield.py::_iban_bic_consistent` SQL template
- **Type:** regression
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `('', '')` through the emitted SQL
- **Expected:** `NULL` — matching the reference's `UNSET`
- **Why:** finding H1's second half. The template answered `'' = ''` → `TRUE`,
  so a row with two empty identifiers passed a consistency check on the
  strength of having nothing to compare, and the default unknown policy would
  otherwise have routed it to a human.

### PCK-043 · Leading whitespace diverges between SQL and the reference
- **Area:** `crossfield.py::_text` vs the SQL `LENGTH(...)` guard
- **Type:** negative
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `(' ', '      ')` — two values that are whitespace only — and
  `(' DE89…', 'COBADEFF')`
- **Expected:** both sides agree
- **Why:** `_text` **strips** before measuring length and the SQL templates do
  not. `LENGTH('  ') = 2` passes the SQL guard and compares two spaces as a
  country code, while the reference declines. This is the same class as H1 and
  is present in all five guarded templates.

### PCK-044 · `MINOR_UNITS_OK` accepts an integral JPY amount
- **Area:** `crossfield.py::_minor_units_ok`
- **Type:** functional
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `(1050, 'JPY')` and `(1050.00, 'JPY')`
- **Expected:** `True` from both sides in both forms
- **Why:** `1050.00` is integral in value and not in scale; `Decimal.to_integral_value()`
  and `CAST(x AS INTEGER)` must agree on that, or a correct yen ledger fails.

### PCK-045 · `MINOR_UNITS_OK` rejects a fractional JPY amount
- **Area:** `crossfield.py::_minor_units_ok`
- **Type:** functional
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `(1050.75, 'JPY')`
- **Expected:** `False` from both sides
- **Why:** the module's own example: "a number no yen amount can take, and
  every downstream sum inherits it".

### PCK-046 · `MINOR_UNITS_OK` passes any two-decimal currency
- **Area:** `crossfield.py::_minor_units_ok`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `(1050.75, 'EUR')`, `(1050.75, 'USD')`
- **Expected:** `True` — the check only bites on zero-decimal currencies
- **Why:** the docstring is explicit that enumerating the exceptions (KWD has
  three) is not this function's job, and a check that fired on EUR would be
  switched off within a day.

### PCK-047 · A two-letter code is UNKNOWN, not a passing currency
- **Area:** `crossfield.py::_minor_units_ok` SQL template
- **Type:** regression
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `(1050.75, 'JP')` through the emitted SQL
- **Expected:** `NULL`
- **Why:** finding H1's table names this exactly: the template fell through to
  its `ELSE` and answered `TRUE`, so a mistyped currency made the check pass.

### PCK-048 · A negative fractional amount in a zero-decimal currency
- **Area:** `crossfield.py::_minor_units_ok`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** DuckDB
- **Steps:** `(-1050.75, 'JPY')`
- **Expected:** `False` from both sides
- **Why:** `CAST(-1050.75 AS INTEGER)` truncates toward zero on some engines
  and rounds on others; `to_integral_value()` rounds half-even. The reference
  and the SQL must agree on the sign as well as the magnitude, and finding C4
  is the precedent for engines disagreeing about exactly this.

### PCK-049 · The zero-decimal list is imported, never restated
- **Area:** `crossfield.py::_zero_decimal`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare `_zero_decimal()` against
  `classify.codelists.ISO_4217_MINOR_UNITS.latest.codes`
- **Expected:** identical sets, and the SQL template's inlined `IN (...)` list
  matches both
- **Why:** the comment insists it is imported "so the two cannot drift" — but
  the SQL template inlines the list at *registration* time, so a code list
  updated after import is a third copy. "Derive, never restate."

### PCK-050 · `MINOR_UNITS_OK` resolves the currency list as of a date
- **Area:** `crossfield.py::_zero_decimal` · `codelists.CodeList.as_of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** run a `MINOR_UNITS_OK` control with a business date in 2021
- **Expected:** either the 2021 state of the list is used, or the control
  records that it used the latest state
- **Why:** `_zero_decimal` calls `.latest` unconditionally. Every other code
  list resolution in the product takes an as-of date, and a control whose
  membership set cannot be reproduced is an assertion rather than evidence.

### PCK-051 · `SETTLES_AFTER_TRADE` accepts same-day and later settlement
- **Area:** `crossfield.py::_settles_after_trade`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `('2026-03-02','2026-03-02')` and `('2026-03-02','2026-03-04')`
- **Expected:** `True` from both sides — "on or after"
- **Why:** T+0 is legitimate, and a strict `>` would report every same-day
  settlement in the book.

### PCK-052 · `SETTLES_AFTER_TRADE` catches a reversed pair
- **Area:** `crossfield.py::_settles_after_trade`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `('2026-03-04','2026-03-02')`
- **Expected:** `False` from both sides
- **Why:** "almost always a date parsed in the wrong order, and a system that
  accepted it has been silently mis-ageing positions".

### PCK-053 · `SETTLES_AFTER_TRADE` on a non-ISO date format
- **Area:** `crossfield.py::_settles_after_trade`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `('02/03/2026','04/03/2026')` and `('2026-3-2','2026-03-04')`
- **Expected:** a stated behaviour — either a refusal, or a documented caveat
  that the comparison is lexical
- **Why:** the implementation is a **string** comparison. `'2026-3-2' <
  '2026-03-04'` is False lexically and True as dates, so the check reports a
  violation on correct data; and `'02/03/2026' <= '04/03/2026'` compares day
  first. Nothing in the function's docstring says it needs ISO-8601.

### PCK-054 · `SETTLES_AFTER_TRADE` on a date type rather than text
- **Area:** `crossfield.py::_settles_after_trade`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a warehouse column typed `DATE`
- **Steps:** run the control against real `DATE` columns on DuckDB and SQLite
- **Expected:** the same verdict as the Python reference over the same rows
- **Why:** the SQL compares natively-typed dates; the reference compares
  `str(value).strip()`. The argument family is declared `TEMPORAL`, so this is
  the intended input and the two paths use different orderings.

### PCK-055 · `SIGN_MATCHES_SIDE` on the four accepted sides
- **Area:** `crossfield.py::_sign_matches_side`
- **Type:** functional
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `('BUY', 10)`, `('B', 10)`, `('SELL', -10)`, `('S', -10)`
- **Expected:** `True` on all four from both sides
- **Why:** the reference accepts exactly `BUY/SELL/B/S` and the template was
  corrected to accept exactly the same four; a mismatch reappears the moment
  either list is edited alone.

### PCK-056 · `SIGN_MATCHES_SIDE` catches a wrong sign
- **Area:** `crossfield.py::_sign_matches_side`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `('BUY', -10)` and `('SELL', 10)`
- **Expected:** `False` from both sides
- **Why:** "a book mixing the two conventions nets to a position nobody holds".

### PCK-057 · `'BORROW'` is UNKNOWN, not a buy
- **Area:** `crossfield.py::_sign_matches_side` SQL template
- **Type:** regression
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `('BORROW', 10)` through the emitted SQL
- **Expected:** `NULL`
- **Why:** finding H1. The template matched on the first letter, so a
  securities-lending row was judged against an equity convention and passed.

### PCK-058 · A zero quantity is UNKNOWN on both sides
- **Area:** `crossfield.py::_sign_matches_side`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `('BUY', 0)`
- **Expected:** `NULL`/`UNSET` from both
- **Why:** "zero has no sign, and a zero-quantity row is a different finding" —
  and `0 > 0` is `False`, so an unguarded template would report it as a
  violation of the sign convention, which sends somebody to the wrong system.

### PCK-059 · A boolean quantity is UNKNOWN
- **Area:** `crossfield.py::_decimal`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** `('BUY', True)`
- **Expected:** `UNSET` — `_decimal` rejects `bool` explicitly
- **Why:** `Decimal(str(True))` raises and `bool` is an `int` in Python, so
  without the guard `True` would be quantity 1 and a passing buy.

### PCK-060 · `SAME_COUNTRY` compares alpha-2 and refuses alpha-3
- **Area:** `crossfield.py::_same_country` SQL template
- **Type:** regression
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** `('GB','GB')` → `True`; `('GB','FR')` → `False`;
  `('GBR','GBR')` → `NULL`
- **Expected:** as stated, from both sides
- **Why:** finding H1. "`'GBR' = 'GBR'` is not two countries agreeing, it is
  two alpha-3 codes in a field that expects alpha-2", and the template answered
  `TRUE`.

### PCK-061 · `SAME_COUNTRY` is case-insensitive
- **Area:** `crossfield.py::_same_country`
- **Type:** functional
- **Priority:** P2
- **Precondition:** DuckDB
- **Steps:** `('gb','GB')`
- **Expected:** `True` from both sides
- **Why:** the reference upper-cases and the template wraps both operands in
  `UPPER`; a template that upper-cased only one operand is a divergence that
  fires on half the estate.

### PCK-062 · The three extractor functions return a country or nothing
- **Area:** `crossfield.py::_iban_country`, `_bic_country`, `_isin_country`
- **Type:** functional
- **Priority:** P2
- **Precondition:** DuckDB
- **Steps:** `IBAN_COUNTRY('GB82WEST12345698765432')`,
  `BIC_COUNTRY('DEUTDEFF')`, `ISIN_COUNTRY('US0378331005')`, and each with a
  value too short
- **Expected:** `'GB'`, `'DE'`, `'US'`; `NULL` on every short input
- **Why:** finding H1 records `ISIN_COUNTRY('X')` returning `'X'` where the
  reference declined — a one-character "country" flowing into a comparison
  against a jurisdiction.

### PCK-063 · `ISIN_COUNTRY` returns `XS` for a Eurobond and says what it means
- **Area:** `crossfield.py::_isin_country`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ISIN_COUNTRY('XS0629974352')`
- **Expected:** `'XS'`, and the function summary warns that XS is not a country
- **Why:** the docstring's own caveat: "a control comparing an ISIN prefix to
  an issuer's jurisdiction has to allow for it or it fires on every Eurobond in
  the book".

### PCK-064 · Each function's declared arity and argument families are enforced
- **Area:** `crossfield.py::BANKING_FUNCTIONS` · `pql/functions.py`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `IBAN_BIC_CONSISTENT(iban)` with one argument;
  `MINOR_UNITS_OK(currency, amount)` with the arguments swapped
- **Expected:** a type error at check time naming the arity or the family, not
  a runtime surprise
- **Why:** `MINOR_UNITS_OK` declares `(NUMBER, TEXT)`, and the swapped form is
  the mistake a reader makes most often — see PCK-085, where a shipped template
  makes exactly it.

### PCK-065 · Every function's SQL and reference agree on a null argument
- **Area:** all eight in `crossfield.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** DuckDB
- **Steps:** for each function, pass `NULL` in each argument position
- **Expected:** `NULL` from the SQL and `UNSET` from the reference, in every
  position of every function
- **Why:** this is the table in the adversarial review generalised. Every
  disagreement there ran the unsafe way — SQL `TRUE` where the reference said
  UNKNOWN — and under the default policy an unknown is a violation, so the side
  that actually runs in production passed the rows the reference would have
  escalated.

### PCK-066 · Every function's SQL runs on every supported engine
- **Area:** `crossfield.py` SQL templates
- **Type:** contract
- **Priority:** P1
- **Precondition:** SQLite, DuckDB and PostgreSQL
- **Steps:** execute all eight templates on each engine over the same corpus
- **Expected:** identical verdicts on all three
- **Why:** the module claims "the arithmetic here is substring comparison and
  sign agreement, which every engine can do" — but `CAST(x AS INTEGER)` and
  `SUBSTR` do not mean the same thing everywhere, and finding C4 is the
  precedent for two engines disagreeing with each other and with the reference.

## Message parsers — FIX, ISO 8583, FpML

### PCK-067 · A real FIX 4.4 NewOrderSingle parses with no defects
- **Area:** `packs/banking/fix.py::parse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a captured `35=D` message with correct `9=` and `10=`
- **Steps:** `fix.parse(message)`
- **Expected:** `is_well_formed`, `msg_type == 'D'`, required tags 11, 55, 54,
  38, 40 all present, `delimiter == SOH`
- **Why:** the baseline. Every defect case below is a deviation from a message
  that must otherwise be clean, or the defect count means nothing.

### PCK-068 · A pipe-delimited message parses and is reported as such
- **Area:** `fix.py::_split`, `Message.arrived_display_delimited`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** the same message with `|` instead of SOH; then with `^`
- **Expected:** parses; `arrived_display_delimited` is `True`; `named()`
  carries `display_delimited: True`
- **Why:** "a message that arrived pipe-delimited on a session is itself a
  finding", and a parser accepting only one of the two is useless on either
  documentation or the wire.

### PCK-069 · A message containing both SOH and a pipe prefers SOH
- **Area:** `fix.py::_split`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** a SOH-delimited message whose `58=` free-text field contains a `|`
- **Expected:** split on SOH; the pipe stays inside the field value
- **Why:** `_split` checks SOH first for exactly this reason; the reverse order
  would cut a text field in half and report a malformed message.

### PCK-070 · BodyLength is computed and checked against what was stated
- **Area:** `fix.py::body_length`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** a correct message; then the same with `9=` decremented by one
- **Expected:** no defect on the first; a defect on tag 9 naming both the
  stated and the computed value on the second
- **Why:** "a parser that reads them as ordinary tags has thrown away the only
  integrity check the protocol has" — and a truncated message is exactly what a
  BodyLength mismatch detects.

### PCK-071 · CheckSum is computed modulo 256 and zero-padded
- **Area:** `fix.py::checksum`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** a message whose true checksum is below 100; then a message with a
  deliberately wrong `10=`
- **Expected:** three digits with leading zeros on the first (e.g. `067`, not
  `67`); a tag-10 defect on the second
- **Why:** a checksum compared as `'67' != '067'` reports every low-checksum
  message as corrupt, and a zero-pad bug shows on roughly a third of traffic.

### PCK-072 · CheckSum over non-Latin-1 bytes
- **Area:** `fix.py::checksum`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** a message with a UTF-8 name in tag 49 containing `é`
- **Expected:** a defect or a stated caveat, not an unhandled
  `UnicodeEncodeError`
- **Why:** `text[:end+1].encode('latin-1')` raises on any character above
  U+00FF, and `parse` promises "never raises: a malformed message is a
  finding". A CJK counterparty name would take the whole session down.

### PCK-073 · A two-leg repeating group keeps both legs
- **Area:** `fix.py::parse`, `GROUPS`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** a message with `555=2` and two `600=` entries
- **Expected:** `groups[555]` has length 2, each `Group` carrying its own tags;
  `named()` reports `no_legs_entries: 2`
- **Why:** the module's own statement: "a two-leg swap parsed flat is a one-leg
  swap that balances".

### PCK-074 · A group declaring more entries than it carries is a defect
- **Area:** `fix.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `555=3` with only two `600=` entries
- **Expected:** a defect on tag 555 saying "declares 3 entr(ies) and carries 2"
- **Why:** "a parser that trusted the count would report a truncated group as
  complete" — and truncation is the defect a count exists to catch.

### PCK-075 · A group count that is not a number
- **Area:** `fix.py::parse`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `453=many` followed by two `448=` entries
- **Expected:** a defect naming tag 453; the two entries are not silently
  discarded without mention
- **Why:** `int(value) if value.isdigit() else 0` makes the count zero, the
  inner loop never runs, and the entries are then parsed as ordinary top-level
  tags — a two-party message read as a zero-party one, with one defect line
  that does not say so.

### PCK-076 · Nested and adjacent groups
- **Area:** `fix.py::parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** a message carrying `453=2` immediately followed by `555=2`
- **Expected:** both groups parsed with their correct entries; no tag of the
  second group absorbed into the first
- **Why:** the group loop breaks only when it sees a tag that is neither the
  starter nor already in `current`, so the first tag of an adjacent group can be
  swallowed into the last entry of the previous one.

### PCK-077 · A field with no `=` is a defect, not a crash
- **Area:** `fix.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** a message containing `garbage` as one SOH-delimited field, and one
  containing `abc=1`
- **Expected:** a `Defect(None, ...)` quoting the first 32 characters; the rest
  of the message still parsed
- **Why:** "one bad message in a session must not stop the rest being checked —
  that turns a data defect into an outage, and the outage is what gets the
  control disabled".

### PCK-078 · An empty input and a whitespace-only input
- **Area:** `fix.py::parse`, `split`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `parse('')`, `parse('   ')`, `split('')`
- **Expected:** a `Message` with no tags and no exception; `split('')` returns
  `[]`
- **Why:** an empty file is the commonest malformed input in production and the
  one most likely to be reported as "no defects found".

### PCK-079 · Binary junk fed to the FIX parser
- **Area:** `fix.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** 4 KB of random bytes decoded with `errors='replace'`
- **Expected:** defects, no exception, and bounded time
- **Why:** never-raises is a documented property of all three parsers, and
  random bytes are the input that finds the one path that does. `prama pack
  parse` reads any file with `errors='replace'`, so this is reachable from the
  CLI with a JPEG.

### PCK-080 · An unknown tag is carried, not dropped
- **Area:** `fix.py::NAMES`, `Message.named`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** a message with tag `9999=x`
- **Expected:** `named()` carries `tag_9999: 'x'`
- **Why:** a control cannot assert on a field the parser threw away, and a
  user-defined tag above 5000 is ordinary in a bilateral session.

### PCK-081 · Required tags are checked per message type
- **Area:** `fix.py::REQUIRED`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** an ExecutionReport (`35=8`) missing tag 39; an `35=AE` missing 571
- **Expected:** one defect per missing tag, naming the message type
- **Why:** the list is "only the ones whose absence is a defect rather than a
  convention", so a false positive here is worse than an omission.

### PCK-082 · A message type with no required-tag entry produces no defects
- **Area:** `fix.py::REQUIRED`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** a heartbeat (`35=0`)
- **Expected:** no required-tag defects, and the output does not read as "this
  message was checked"
- **Why:** `REQUIRED.get(..., ())` silently means "nothing required", which is
  indistinguishable from "all requirements met" in the CLI's "No structural
  defects found" line.

### PCK-083 · `split` breaks a session log on the `8=FIX` boundary
- **Area:** `fix.py::split`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** three concatenated messages; then a log whose free-text field
  contains the literal `8=FIX`
- **Expected:** three messages in the first case; a stated behaviour in the
  second
- **Why:** the lookahead split has no anchor, so a quoted `8=FIX` inside a
  field cuts a message in half and produces two malformed ones from one good.

### PCK-084 · A FIX message given to the ISO 8583 parser
- **Area:** `cli/pack.py::PackParseCommand`, `_infer`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `prama pack parse order.fix --format iso8583`
- **Expected:** a refusal, or defects that say this is not an ISO 8583 message;
  a non-zero exit
- **Why:** finding Q-39, still open: the command reports "No structural defects
  found" for a FIX message read as ISO 8583, and `pack parse` always exits 0.
  "Guessing wrong is worse than declining" is the module's own rule.

### PCK-085 · `_infer` declines rather than guessing
- **Area:** `cli/pack.py::_infer`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** a SWIFT MT103 (`{1:F01...`), a camt.053 XML, an empty file, a CSV
- **Expected:** each declines with the remedy naming the three supported
  formats — not a misidentification
- **Why:** `stripped[:4].isdigit() and len > 20` claims any numeric-leading
  file as ISO 8583, and a camt.053 starts with `<` but has no "fpml" in its
  first 400 characters, so it falls through to the ISO 8583 test.

### PCK-086 · `prama pack list` advertises six formats and `pack parse` reads three
- **Area:** `cli/pack.py::PackListCommand` vs `_PARSERS`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the "Message formats" block against `--format`'s choices
- **Expected:** the same set, or the list says which are library-only
- **Why:** the H1 shape again: one CLI command advertising what another
  refuses. SWIFT MT, ISO 20022 and COBOL are listed and cannot be parsed from
  the command line.

### PCK-087 · A real ISO 8583 0100 authorisation parses
- **Area:** `packs/banking/iso8583.py::parse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a hex/ASCII 0100 with fields 2, 3, 4, 7, 11, 41, 49
- **Steps:** `iso8583.parse(message)`
- **Expected:** `mti == '0100'`, the declared fields present in order, no
  defects
- **Why:** the baseline for the bitmap arithmetic, which is the whole of this
  format.

### PCK-088 · Bit 1 selects a secondary bitmap and is not a field
- **Area:** `iso8583.py::parse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a message with the top bit of the primary bitmap set
- **Steps:** parse it; check field offsets
- **Expected:** a second 16-character bitmap consumed; fields numbered above 64
  present; field 2's PAN is the real PAN
- **Why:** "a reader that treats it as data loses sixteen bytes off the front of
  field 2 and reports a PAN that is somebody else's" — and that failure does not
  raise, it produces plausible digits.

### PCK-089 · `has_secondary_bitmap` is derived from the wrong thing
- **Area:** `iso8583.py::Message.has_secondary_bitmap`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a message with bit 1 set and no bits set in the secondary
  bitmap
- **Steps:** parse and read `has_secondary_bitmap`
- **Expected:** `True` — a secondary bitmap was present and consumed
- **Why:** the property is `any(field > 64 for field in self.present)`, which
  infers the bitmap's presence from its *contents*. An all-zero secondary
  bitmap is legal and the property then denies the sixteen bytes it just read.

### PCK-090 · LLVAR and LLLVAR length prefixes are not part of the value
- **Area:** `iso8583.py::parse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** field 2 as `164111111111111111`
- **Steps:** parse; read `unmasked(2)`
- **Expected:** a 16-digit PAN, not an 18-digit one beginning `16`
- **Why:** "a reader that includes them turns a 16-digit PAN into `1655...`,
  which is a perfectly plausible 18-digit card number".

### PCK-091 · A non-numeric length prefix stops the parse and says so
- **Area:** `iso8583.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** field 2 prefixed `XX`
- **Steps:** parse
- **Expected:** a defect on field 2 quoting the prefix; parsing stops rather
  than continuing at a guessed offset
- **Why:** "an unknown length means every field after this one is at the wrong
  offset, and guessing would produce a message of plausible rubbish".

### PCK-092 · A truncated message reports which field ran out
- **Area:** `iso8583.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a valid message cut mid-field-43
- **Steps:** parse
- **Expected:** a defect saying field 43 "declares 40 characters and 12 remain"
- **Why:** truncation is the defect this format hides best, because every field
  before the cut reads correctly.

### PCK-093 · A message shorter than an MTI plus a bitmap
- **Area:** `iso8583.py::parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `parse('0100')`, `parse('')`, `parse('0100' + '0'*15)`
- **Expected:** one defect, "too short to carry an MTI and a bitmap", in all
  three
- **Why:** the guard is `len(text) < 20`; 19 characters is the boundary and an
  empty file is the commonest input.

### PCK-094 · A declared field this dialect does not define stops the parse
- **Area:** `iso8583.py::parse`, `FIELDS`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a bitmap declaring field 48 (absent from `FIELDS`)
- **Steps:** parse
- **Expected:** a defect on field 48 saying it is "declared present and not
  defined in this dialect"; nothing after it is reported as a value
- **Why:** the dialect table is deliberately partial, and a private-use field
  is ordinary — so this path runs on real traffic, not only on corrupt input.

### PCK-095 · The PAN is never returned whole by an ordinary read
- **Area:** `iso8583.py::mask_pan`, `SENSITIVE`
- **Type:** security
- **Priority:** P1
- **Precondition:** a message with fields 2, 35 and 52
- **Steps:** read `values`, `named()`, `to_dict`-equivalents, and `repr` of the
  `Message`
- **Expected:** all three sensitive fields masked in every one; `_raw` excluded
  from `repr`
- **Why:** "a parser that hands a full card number to whatever called it has
  put it in that caller's logs" — and the CLI prints `named()`.

### PCK-096 · `mask_pan` preserves length and the last four
- **Area:** `iso8583.py::mask_pan`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `mask_pan('4111111111111111')`, `mask_pan('1234')`,
  `mask_pan('')`, `mask_pan('4111-1111-1111-1111')`
- **Expected:** 12 stars + `1111`; `****`; `''`; and a stated answer for the
  separated form
- **Why:** length is what a control asserts on — "a thirteen-digit Visa and a
  sixteen-digit one are different findings" — and stripping non-digits changes
  the length of a formatted PAN, so the mask no longer preserves what it claims.

### PCK-097 · `mask_pan` on track-2 data
- **Area:** `iso8583.py::mask_pan` applied to field 35
- **Type:** security
- **Priority:** P2
- **Precondition:** a field 35 of the form `4111111111111111=25121010000000000000`
- **Steps:** parse and read `values[35]`
- **Expected:** no digit run recoverable as a PAN, and the expiry and service
  code not left in the clear
- **Why:** `mask_pan` concatenates *all* digits and keeps the last four — which
  for track 2 are the last four of the discretionary data, and the first twelve
  masked digits are the PAN plus the expiry run together. The mask is applied to
  a field it was not designed for.

### PCK-098 · Field 4 is minor units with the point restored
- **Area:** `iso8583.py::Message.amount`
- **Type:** functional
- **Priority:** P1
- **Precondition:** field 4 as `000000012345`
- **Steps:** `message.amount()`
- **Expected:** `Decimal('123.45')`
- **Why:** "read as an integer it is ten thousand times too large, which is
  exactly the failure that gets noticed at settlement rather than at parse
  time".

### PCK-099 · Field 4 scaling is wrong for a zero-decimal currency
- **Area:** `iso8583.py::Message.amount`
- **Type:** negative
- **Priority:** P1
- **Precondition:** field 49 = `392` (JPY), field 4 = `000000012345`
- **Steps:** `amount()`
- **Expected:** `Decimal('12345')` for JPY, or a stated caveat that the method
  assumes two minor units
- **Why:** `scaleb(-2)` is unconditional. The pack ships `MINOR_UNITS_OK`
  precisely because currencies differ here, and this method contradicts it —
  a yen authorisation is reported at one hundredth of its value.

### PCK-100 · A non-numeric field 4 returns None, not zero
- **Area:** `iso8583.py::Message.amount`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** field 4 containing spaces
- **Steps:** `amount()`
- **Expected:** `None`
- **Why:** zero is a number that balances; None is the absence of one, and the
  distinction runs through every parser in this pack.

### PCK-101 · A real FpML 5 interest-rate swap parses with both legs
- **Area:** `packs/banking/fpml.py::parse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a two-stream `swap` document with payer and receiver
  references on each stream
- **Steps:** `fpml.parse(xml)`
- **Expected:** `len(legs) == 2`, `is_two_sided` True, a fixed leg with a rate
  and a floating leg with an index, no defects
- **Why:** "a swap whose direction is lost is a position of twice the size or
  none at all, depending on which way the loss went".

### PCK-102 · A leg with no payer is named as a defect
- **Area:** `fpml.py::parse`, `Leg.has_direction`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a document whose second stream has no
  `payerPartyReference`
- **Steps:** parse
- **Expected:** a defect "leg 2 does not say who pays and who receives";
  `has_two_legs` True and `is_two_sided` **False**
- **Why:** the class distinguishes the two properties on purpose — counting
  legs alone answers yes for a document whose sign cannot be determined.

### PCK-103 · A party reference written as text rather than `href`
- **Area:** `fpml.py::_reference`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a producer that writes `<payerPartyReference>PartyA</...>`
- **Steps:** parse
- **Expected:** `payer == 'PartyA'`
- **Why:** "no payer is a finding a control reports as a missing direction
  rather than as a parser that did not look" — reading only the attribute
  silently manufactures the defect it reports.

### PCK-104 · `signed_for` returns None for a party not on the leg
- **Area:** `fpml.py::Leg.signed_for`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a directed leg between PartyA and PartyB
- **Steps:** `signed_for('PartyA')`, `signed_for('PartyB')`,
  `signed_for('PartyC')`, and on a leg with no notional
- **Expected:** `+n`, `-n`, `None`, `None`
- **Why:** "None rather than zero: zero is a position, and this is the absence
  of one".

### PCK-105 · `net_for` over a trade with no legs returns zero, not None
- **Area:** `fpml.py::Trade.net_for`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a document with no `swapStream`
- **Steps:** `trade.net_for('PartyA')`
- **Expected:** `None` — the trade states no obligation for anybody
- **Why:** `any(... for ... in [])` is False and the loop adds nothing, so the
  method returns `Decimal(0)`. That is a *position* of zero reported for a
  party that has no leg at all, which is the exact confusion `signed_for`'s
  docstring forbids one line above.

### PCK-106 · `net_for` refuses on a cross-currency trade
- **Area:** `fpml.py::Trade.net_for`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a EUR leg and a USD leg
- **Steps:** `net_for('PartyA')`
- **Expected:** `None`
- **Why:** "a total across currencies is a number in no currency at all, and it
  looks exactly like a number in one".

### PCK-107 · Namespaces are matched on local name
- **Area:** `fpml.py::_local`, `_find`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same document under an FpML 5-10 and a 5-12 namespace
- **Steps:** parse both
- **Expected:** identical trades; `version` differs
- **Why:** "a parser keyed on the full namespace refuses next year's file", and
  version enforcement is a control's decision rather than a parser's.

### PCK-108 · Malformed XML is a defect, not an exception
- **Area:** `fpml.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `parse('<trade>')`, `parse('')`, `parse('not xml at all')`,
  `parse(binary_junk)`
- **Expected:** a `Trade` carrying one defect naming the parse error; no
  exception in any of the four
- **Why:** the documented never-raises property, and the CLI depends on it.

### PCK-109 · A billion-laughs entity expansion is refused
- **Area:** `fpml.py::parse`, `iso20022.py::parse_pacs008`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** feed each XML parser a document with a nested entity bomb and one
  with an external entity reference to `/etc/passwd`
- **Expected:** a defect; no memory blow-up and no file read
- **Why:** both parsers use `xml.etree.ElementTree.fromstring` on documents
  that arrive from a counterparty. Entity expansion is off by default in
  modern CPython but the external-DTD path and the memory bound are worth
  pinning rather than inheriting.

### PCK-110 · An FpML document with no `trade` element falls back to the root
- **Area:** `fpml.py::parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a bare `<swap>` document
- **Steps:** parse
- **Expected:** legs found, and the absence of a trade header reported rather
  than silently producing an empty `trade_id`
- **Why:** the fallback exists so an extract still parses, but an empty
  `trade_id` reaching a reconciliation key matches every other empty one.

### PCK-111 · `onBehalfOf` decides the sign of a report
- **Area:** `fpml.py::parse`, `Trade.on_behalf_of`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a document with `<onBehalfOf href="PartyB"/>`
- **Steps:** parse; `net_for(trade.on_behalf_of)`
- **Expected:** `on_behalf_of == 'PartyB'` and the net is negated relative to
  PartyA's
- **Why:** "a report built without it has the sign of every position depending
  on who sent the file".

## SWIFT MT and ISO 20022 — `packs/banking/swift.py`, `iso20022.py`

### PCK-112 · An MT940 statement parses into signed lines
- **Area:** `swift.py::parse`, `statement`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a five-line MT940 with `:60F:`, several `:61:` and `:62F:`
- **Steps:** `statement(parse(text))`
- **Expected:** credits positive, debits negative, `balances` True,
  `discrepancy` zero
- **Why:** "a parser that ignores the mark produces a statement whose entries
  only ever add up, and the continuity check then passes on a statement that
  does not balance".

### PCK-113 · A SWIFT amount uses a comma for the decimal point
- **Area:** `swift.py::_amount`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `_amount('1234,56')`, `_amount('1234')`, `_amount('0,01')`
- **Expected:** `Decimal('1234.56')`, `Decimal('1234')`, `Decimal('0.01')`
- **Why:** "the common shortcut — strip non-digits — turns `1234,56` into
  `123456`", a hundredfold error that reconciles to a plausible number.

### PCK-114 · An unreadable amount is None, not zero
- **Area:** `swift.py::_amount`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `_amount('12,34,56')`, `_amount('abc')`, `_amount('')`
- **Expected:** `None` from all three
- **Why:** the docstring says "None rather than zero when it cannot be read …
  zero is a number that balances" — but the implementation is
  `Decimal(text.replace(",", ".").strip() or "0")`, so an **empty** amount
  returns `Decimal(0)` and balances a statement that stated nothing.

### PCK-115 · A debit balance is stored negative
- **Area:** `swift.py::_balance`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `:60F:D250301EUR1000,00`
- **Steps:** parse
- **Expected:** `opening_balance == Decimal('-1000.00')`
- **Why:** "storing the mark separately and the amount positive is how a
  statement comes to look overdrawn by the same figure it is in credit by".

### PCK-116 · A reversal flips the sign of its mark
- **Area:** `swift.py::_line`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `:61:` line with mark `RC` and one with `RD`
- **Steps:** parse
- **Expected:** `RC` is a debit (negative) and `RD` a credit (positive)
- **Why:** "a reversal of a credit is a debit"; getting it backwards makes the
  statement out by twice the reversal, which reads as a duplicate.

### PCK-117 · An entry date at a year boundary
- **Area:** `swift.py::_line`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a `:61:` line with value date `251231` and entry date
  `0102`
- **Steps:** parse; read `entry_date`
- **Expected:** `2026-01-02`
- **Why:** the code builds the entry date as `value_day[:2] + entry_day`, which
  takes the **year from the value date** — so a January entry against a
  December value date is dated a year early, and every ageing bucket built on
  it is 365 days out.

### PCK-118 · A two-digit year is read as 20xx, and that is stated
- **Area:** `swift.py::_date`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** `_date('990101')`
- **Expected:** `2099-01-01`, and the limitation appears in the output of
  anything that consumes it
- **Why:** the docstring says so plainly — "wrong for archives from the 1990s"
  — and a claim stated in a docstring is a claim the product makes.

### PCK-119 · `balances` is None when a balance is absent
- **Area:** `swift.py::Statement.balances`, `discrepancy`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a statement with no `:62F:`
- **Steps:** read both properties
- **Expected:** both `None`, plus a defect saying the balance field is absent
- **Why:** "a statement with no closing balance has not failed continuity, it
  has failed to state it, and the two go to different people".

### PCK-120 · A statement that opens and closes in different currencies
- **Area:** `swift.py::statement`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `:60F:` in EUR and `:62F:` in USD
- **Steps:** parse
- **Expected:** a defect naming both currencies; the arithmetic is not quoted
  as a discrepancy
- **Why:** "the arithmetic below would be meaningless and the check has to name
  that rather than produce a number". A discrepancy figure is still computed —
  confirm what a consumer sees.

### PCK-121 · `:60M:` and `:62M:` interim balances are used as fallbacks
- **Area:** `swift.py::statement`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a continuation statement carrying only `:60M:`/`:62M:`
- **Steps:** parse
- **Expected:** the interim balances used, and the fact that they are interim
  visible somewhere
- **Why:** an interim balance is a different number from a final one, and the
  fallback is silent — `currency` and `balances` read identically either way.

### PCK-122 · A multi-line field 86 narrative stays with its tag
- **Area:** `swift.py::parse`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an `:86:` spanning four lines, one of them blank
- **Steps:** parse; read `first('86')`
- **Expected:** all four lines joined; no defect about content before a tag
- **Why:** "field 86 and field 50K are multi-line by design, and joining them
  onto the previous tag is the only way to keep an address together".

### PCK-123 · `split` does not cut on a blank line
- **Area:** `swift.py::split`
- **Type:** regression
- **Priority:** P2
- **Precondition:** one message whose `:86:` contains a blank line
- **Steps:** `split(text)`
- **Expected:** one message
- **Why:** stated in the docstring — "splitting there cuts a message in half
  and reports two malformed messages instead of one good one".

### PCK-124 · `first()` returns None for an absent tag and `''` for an empty one
- **Area:** `swift.py::Message.first`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a message with `:70:` present and empty
- **Steps:** `first('70')` and `first('71A')` where 71A is absent
- **Expected:** `''` and `None`
- **Why:** "an absent optional field and a present empty one are different
  facts, and a caller that cannot tell them apart will report one as the
  other" — yet `payment()` immediately collapses both with `or ''`.

### PCK-125 · An MT103 with a short field 32A is silent
- **Area:** `swift.py::payment`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `:32A:250301EUR` — a date and currency with no amount
- **Steps:** `payment(message)`
- **Expected:** a defect, or `currency` set and `amount` None with the reason
  visible
- **Why:** the guard is `len(stripped) > 9`, so a 9-character 32A produces an
  empty value date, an empty currency and a null amount **with no defect at
  all** — a payment row that a completeness control then reports as three
  separate missing fields rather than one malformed field.

### PCK-126 · `sender_bic` comes from block 1
- **Area:** `swift.py::Message.sender_bic`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `{1:F01DEUTDEFFAXXX0000000000}`
- **Steps:** read `sender_bic`
- **Expected:** the 12-character logical terminal address, and a short block 1
  returns `''` rather than raising
- **Why:** the BIC is what a `SAME_COUNTRY` or `IBAN_BIC_CONSISTENT` control
  asserts against, and a slice off by one produces a shape-valid BIC for a
  different bank.

### PCK-127 · A message with no block 4 is a defect
- **Area:** `swift.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a message whose block 4 is unterminated (`-}` missing)
- **Steps:** parse
- **Expected:** one defect, "the text block is missing or unterminated"; the
  blocks that were found are still carried
- **Why:** an unterminated block 4 is what a truncated transmission looks like,
  and it must not be reported as a message with no fields.

### PCK-128 · A pacs.008 file's stated count and control sum are not derived
- **Area:** `iso20022.py::Pacs008.count_agrees`, `sum_agrees`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a pacs.008 with `NbOfTxs` 3 and two transactions
- **Steps:** parse
- **Expected:** `stated_count == 3`, `actual_count == 2`, `count_agrees` False
- **Why:** "deriving one from the other would make the most useful check in the
  file impossible to write", and a truncated batch whose every remaining
  transaction is valid is invisible to any per-transaction check.

### PCK-129 · An absent control total is None, not a disagreement
- **Area:** `iso20022.py::Pacs008.count_agrees`, `sum_agrees`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a pacs.008 with no `CtrlSum`
- **Steps:** read `sum_agrees`
- **Expected:** `None`
- **Why:** "an absent control total is a sender problem, a wrong one is a
  truncation" — and they go to different people.

### PCK-130 · A fractional `NbOfTxs` is silently truncated
- **Area:** `iso20022.py::parse_pacs008`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `<NbOfTxs>2.5</NbOfTxs>`
- **Steps:** parse
- **Expected:** a defect naming the malformed count
- **Why:** the code does `int(Decimal('2.5'))` → 2, so a malformed header
  becomes a plausible count that then *agrees* with two transactions and the
  file passes.

### PCK-131 · Unreadable amounts make the total a lower bound, and say so
- **Area:** `iso20022.py::Pacs008.unreadable_amounts`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a file with three unparseable `IntrBkSttlmAmt` values whose
  `CtrlSum` happens to match the remaining sum
- **Steps:** read `sum_agrees` and `unreadable_amounts`
- **Expected:** `sum_agrees` True **and** `unreadable_amounts == 3`, with the
  caveat reaching whatever renders the result
- **Why:** the docstring: "a file whose sum agrees while three amounts were
  unreadable has not been checked, it has been under-counted twice in the same
  direction". A consumer that reads only `sum_agrees` gets a false clean.

### PCK-132 · The settlement date is inherited from the group header
- **Area:** `iso20022.py::_transaction`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `IntrBkSttlmDt` on the header only
- **Steps:** parse
- **Expected:** every transaction carries the header's value date
- **Why:** "a parser that read only the transaction returns nothing for the
  majority of real files, and a control then reports every payment as missing a
  value date".

### PCK-133 · A BIC under either `BICFI` or `BIC` is found
- **Area:** `iso20022.py::_agent`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one document using `BICFI`, one using `BIC`
- **Steps:** parse both
- **Expected:** the same `creditor_agent_bic`
- **Why:** "reading only one silently returns nothing for the other, and 'no
  BIC' is a finding a control will report as a missing field rather than as a
  parser that did not look".

### PCK-134 · camt.053 balances are matched on code, not position
- **Area:** `iso20022.py::_balance_of`, `_OPENING_CODES`, `_CLOSING_CODES`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a statement carrying `ITBD`, `CLAV`, `OPBD` and `CLBD` in
  that order
- **Steps:** parse
- **Expected:** opening from `OPBD` and closing from `CLBD` — not `ITBD` and
  not `CLAV`
- **Why:** "taking the first is how a reader ends up reporting the available
  balance as the closing one — a different number that usually happens to be
  close".

### PCK-135 · `PRCD` is accepted as an opening balance
- **Area:** `iso20022.py::_OPENING_CODES`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a statement using `PRCD` rather than `OPBD`
- **Steps:** parse
- **Expected:** the opening balance found and no "no opening balance" defect
- **Why:** both codes are in use across banks, and a missing one produces a
  defect on a perfectly good statement.

### PCK-136 · A missing credit/debit indicator becomes a debit
- **Area:** `iso20022.py::_entry`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an `Ntry` with no `CdtDbtInd`
- **Steps:** parse; read `is_credit` and `signed`
- **Expected:** a defect, or an unresolved sign — not a silent debit
- **Why:** `is_credit = _text(node, "CdtDbtInd") == "CRDT"` makes an absent
  indicator False, so a missing field becomes a negative amount and the
  statement fails continuity by twice the entry. The whole point of the class
  is that "no consumer can forget to apply it".

### PCK-137 · A camt.053 carrying two statements loses the second
- **Area:** `iso20022.py::parse_camt053`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a file with two `Stmt` elements for different accounts
- **Steps:** parse
- **Expected:** both statements, or a defect saying only the first was read
- **Why:** `_find(body, "Stmt")` takes the first and nothing mentions the rest.
  A two-account file silently becomes a one-account file, which is the
  completeness failure `Pacs008.count_agrees` exists to catch in the sibling
  format.

### PCK-138 · A pacs.008 with no transactions is a defect
- **Area:** `iso20022.py::parse_pacs008`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a header-only document
- **Steps:** parse
- **Expected:** a defect saying the document carries no credit transfers;
  `transaction_total` is zero and `count_agrees` reflects the stated count
- **Why:** an empty batch that "agrees" with a stated count of zero is the
  quietest way for a feed to stop.

### PCK-139 · MT and MX produce the same field names for the same facts
- **Area:** `swift.py::payment` vs `iso20022.py::Transaction.to_dict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an MT103 and the pacs.008 it was translated into
- **Steps:** compare the key sets of the two rows
- **Expected:** `reference`, `amount`, `currency`, `value_date`,
  `debtor_agent_bic`/`sender_bic` line up as the module claims
- **Why:** the stated reason both parsers exist in this shape — the `mt-to-mx`
  reconciliation template depends on it, and "two parsers with two vocabularies
  would have made that a mapping exercise". `swift.payment` emits
  `sender_bic`, `ordering_institution` and `beneficiary`;
  `iso20022.Transaction` emits `debtor_agent_bic`, `debtor_name` and
  `creditor_name`. Establish which pairs are meant to be joined.

## COBOL copybooks and EBCDIC — `packs/banking/cobol.py`

### PCK-140 · A copybook parses into fields with byte offsets
- **Area:** `cobol.py::parse_copybook`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a copybook with `PIC X(10)`, `PIC S9(7)V99 COMP-3` and
  `PIC 9(4)`
- **Steps:** parse; read offsets and `record_length`
- **Expected:** offsets 0, 10, 15; record length 19
- **Why:** every other case measures a deviation from correct offsets, and a
  wrong offset produces "not an error but a record full of neighbouring fields'
  bytes".

### PCK-141 · COMP-3 storage length is digits ÷ 2 + 1
- **Area:** `cobol.py::_stored_length`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `S9(7)V99` (9 digits), `S9(5)` (5), `9(4)` (4), `9(8)V99` (10)
- **Expected:** 5, 3, 3, 6 bytes
- **Why:** the odd/even boundary is where packed-decimal length calculations go
  wrong, and every field after a wrong one is misaligned.

### PCK-142 · COMP/BINARY storage follows the COBOL table
- **Area:** `cobol.py::_stored_length`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** 4, 5, 9, 10 digits declared `COMP`
- **Expected:** 2, 4, 4, 8 bytes
- **Why:** halfword/fullword/doubleword boundaries at 4 and 9 digits; the
  wrong side of either shifts the rest of the record.

### PCK-143 · `unpack_comp3` reads sign nibbles C, D and F
- **Area:** `cobol.py::unpack_comp3`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `b'\x12\x34\x5C'`, `b'\x12\x34\x5D'`, `b'\x12\x34\x5F'`, each
  with `scale=2`
- **Expected:** `123.45`, `-123.45`, `123.45`
- **Why:** "a reader that ignores the nibble turns every credit into a debit —
  and the figures still look entirely reasonable".

### PCK-144 · An invalid nibble is None, not a plausible number
- **Area:** `cobol.py::unpack_comp3`
- **Type:** regression
- **Priority:** P1
- **Precondition:** none
- **Steps:** `b'\xA2\x34\x5C'` (nibble `A`) and `b'\x12\x34\x5A'` (sign `A`)
- **Expected:** `None` from both
- **Why:** the comment records the bug this replaced: `str(0xA)` is `"10"` and
  `"10" > "9"` is False, so every invalid nibble passed and produced a
  plausible number from rubbish. That is what a mis-offset field looks like.

### PCK-145 · `unpack_comp3` on empty and single-byte input
- **Area:** `cobol.py::unpack_comp3`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `b''`, `b'\x0C'`, `b'\x5C'`
- **Expected:** `None`; `Decimal(0)`; `Decimal(5)`
- **Why:** the loop over `data[:-1]` is empty for a one-byte field, which is a
  legal `PIC S9(1) COMP-3` and the smallest thing this can be handed.

### PCK-146 · The implied decimal point is applied
- **Area:** `cobol.py::read_record`, `Field.scale`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `PIC S9(7)V99` holding `123456789`
- **Steps:** read the record
- **Expected:** `1234567.89`
- **Why:** "a reader that does not apply `V` reports every amount a hundred
  times too big, and the figure looks entirely reasonable".

### PCK-147 · Zoned-decimal overpunch signs are read
- **Area:** `cobol.py::_display_number`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `'1234}'`, `'1234J'`, `'1234R'`, `'1234{'`, `'1234A'`, `'1234-'`,
  `'1234+'`, each signed with scale 0
- **Expected:** `-12340`, `-12341`, `-12349`, `12340`, `12341`, `-1234`, `1234`
- **Why:** "a reader that strips non-digits loses it, and the amount changes
  sign without changing magnitude — which reconciles to exactly twice the error
  and is routinely misread as a duplicate".

### PCK-148 · An overpunch on an unsigned field is not decoded
- **Area:** `cobol.py::_display_number`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `PIC 9(5)` (unsigned) holding `1234}`
- **Steps:** read the record
- **Expected:** `None`, because `1234}` is not a number for an unsigned field
- **Why:** the sign branch is guarded by `signed`, so an unsigned field with an
  overpunch falls through to `isdigit()` and returns None — which is right, and
  needs to stay right, because the alternative is a silent sign flip.

### PCK-149 · OCCURS on a group multiplies the span
- **Area:** `cobol.py::parse_copybook`, `_close`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a 05-level group `OCCURS 12` containing two elementary
  items, followed by another field
- **Steps:** parse; read the following field's offset and `record_length`
- **Expected:** the following field starts after 12 × the group's span
- **Why:** "getting it wrong shifts every subsequent field and produces records
  full of their neighbours' bytes".

### PCK-150 · OCCURS on the last elementary item under-states the record length
- **Area:** `cobol.py::Copybook.record_length`, `Field.end`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a copybook whose final elementary item is
  `PIC 9(2) OCCURS 12`
- **Steps:** `record_length`
- **Expected:** the full 24 bytes of the array
- **Why:** `Field.end` is `offset + length` for **one** occurrence, and
  `record_length` is `max(field.end)`. The cursor advances correctly for
  intervening fields, so only the last one is wrong — by which point
  `read_records` divides the file into records that are 22 bytes short and
  every record after the first is misaligned.

### PCK-151 · `read_record` returns only the first occurrence of an OCCURS field
- **Area:** `cobol.py::read_record`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an elementary `PIC 9(2) OCCURS 12`
- **Steps:** read a record
- **Expected:** twelve values, or one value with the array documented as
  unsupported
- **Why:** the chunk is `record[field.offset:field.end]` — one occurrence —
  while the offsets skip all twelve. Eleven twelfths of a monthly-balance array
  is silently unreadable, and nothing says so.

### PCK-152 · A REDEFINES shares bytes and does not advance the cursor
- **Area:** `cobol.py::parse_copybook`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a field redefining an earlier one, followed by a third
- **Steps:** parse
- **Expected:** the redefining field has the earlier field's offset; the third
  field starts after the *original*, counted once
- **Why:** counting a redefinition's bytes twice pushes everything after it,
  and REDEFINES is on almost every real copybook.

### PCK-153 · A REDEFINES naming a field that is not above it warns
- **Area:** `cobol.py::parse_copybook`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `05 B REDEFINES NOSUCH PIC X(4).`
- **Steps:** parse; read `warnings`
- **Expected:** a warning naming both fields, and the offset falls back to the
  current cursor
- **Why:** a typo'd REDEFINES target silently changes the layout, and the
  warning is the only signal.

### PCK-154 · A redefining *group* returns the cursor to where it was
- **Area:** `cobol.py::_close`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a group REDEFINES with children, followed by another field
- **Steps:** parse
- **Expected:** the following field resumes after what preceded the group, not
  after the borrowed bytes
- **Why:** the comment says carrying one offset gets exactly one of the two
  cases right; this is the case that distinguishes them.

### PCK-155 · An 88-level condition name contributes no bytes
- **Area:** `cobol.py::parse_copybook`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an `88 STATUS-OPEN VALUE 'O'.` between two fields
- **Steps:** parse
- **Expected:** the following field's offset is unchanged
- **Why:** a condition name is a named value of the field above it; counting it
  as a field shifts the record.

### PCK-156 · A column-7 comment line is not ignored
- **Area:** `cobol.py::parse_copybook`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a copybook in fixed format with sequence numbers, e.g.
  `000100* THIS IS A COMMENT`
- **Steps:** parse; read `warnings`
- **Expected:** recognised as a comment
- **Why:** the code only strips comments when the *lstripped* line starts with
  `*`, which is the free-format spelling. A real mainframe copybook carries the
  comment indicator in column 7 after a six-digit sequence number, and every
  such line becomes an "ignored, not a copybook line" warning — noise that
  buries the warnings that matter.

### PCK-157 · An unreadable PICTURE refuses the whole copybook
- **Area:** `cobol.py::_picture`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `PIC A(5)` or `PIC ZZZ9.99`
- **Steps:** `parse_copybook`
- **Expected:** `ValidationError` naming the clause, with a remedy listing the
  supported forms
- **Why:** "a picture this cannot read means every field after it is at the
  wrong offset, so continuing would produce a whole file of plausible rubbish —
  which is worse than refusing the copybook". Note that alphabetic `A(n)` and
  edited pictures are ordinary in real copybooks, so this refusal is reachable.

### PCK-158 · The codepage is required, and named in the refusal
- **Area:** `cobol.py::read_record`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `read_record(data, book, codepage="")`
- **Expected:** `ValidationError` listing `COMMON_CODEPAGES` and saying the
  codepages differ on `@ # $` and the accented letters
- **Why:** "a default here would work in testing and corrupt one field in
  production", and the field it corrupts is the one holding an identifier.

### PCK-159 · cp037 and cp273 differ on the characters an identifier uses
- **Area:** `cobol.py::read_record`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a record holding EBCDIC bytes for `@`, `#`, `$` and `Ä`
- **Steps:** read it under cp037 and under cp273
- **Expected:** different text, demonstrating the parameter matters
- **Why:** the module's central claim. A counterfactual that shows the two
  codepages disagree is what makes the required argument defensible.

### PCK-160 · An unknown codepage is refused with the field named
- **Area:** `cobol.py::read_record`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `codepage="cp9999"`
- **Expected:** `ValidationError` naming the field and the codepage, raised
  from the `LookupError`
- **Why:** a `LookupError` reaching a terminal is the Q-28 shape, and the
  error carries the field name so the operator knows where the file stopped.

### PCK-161 · A short field is None, not padded
- **Area:** `cobol.py::read_record`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a record one byte short of the last field
- **Steps:** read it
- **Expected:** that field is `None`
- **Why:** "a padded field is a value that was never sent, and it will be
  checked as though it were".

### PCK-162 · A file that does not divide into whole records
- **Area:** `cobol.py::read_records`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a file of 2.5 records
- **Steps:** `read_records`
- **Expected:** two rows and one complaint naming the record number and both
  byte counts
- **Why:** "a file with one short record still yields the rest — and the short
  record is a finding a control can assert on rather than an exception that
  lost the batch".

### PCK-163 · A copybook describing no fields is refused
- **Area:** `cobol.py::read_records`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an empty copybook, or one of only group items
- **Steps:** `read_records(data, book, codepage='cp037')`
- **Expected:** `ValidationError` saying a record has no length
- **Why:** dividing by a zero record length is an infinite loop or an empty
  result, and an empty result reads as a clean file.

### PCK-164 · A binary field's sign follows the PICTURE
- **Area:** `cobol.py::read_record`, `usage == 'binary'`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `PIC S9(4) COMP` holding `0xFFFF`
- **Steps:** read the record
- **Expected:** `-1`, not `65535`
- **Why:** `int.from_bytes(..., signed=field.signed)` is the only thing between
  a negative balance and a very large positive one.

## Concepts — `packs/banking/concepts.py`

### PCK-165 · Seventeen concepts ship, each with an identifying property
- **Area:** `concepts.py::CONCEPTS`, `Concept.__post_init__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** import the module; count `CONCEPTS`; assert each has
  `identifying`
- **Expected:** 17, matching docs/12's stated "seventeen-concept ontology";
  every one has at least one identifying property
- **Why:** "a concept with no identifying property matches every table with the
  right shape, and would be reported as a confident match" — and the guard runs
  at import, so a bad edit is a hard failure rather than a bad recognition.

### PCK-166 · Every declared semantic type resolves to a validator
- **Area:** `concepts.py::Property.__post_init__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** import the module with a validator renamed
- **Expected:** `ValueError` at import naming the property and listing the
  known types
- **Why:** "a property naming a validator that does not exist is a loud failure
  here rather than a property that silently never matches" — the "derive, never
  restate" rule made enforceable.

### PCK-167 · No spelling means two properties of one concept
- **Area:** `concepts.py::Concept.__post_init__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** add `account_id` as an alias of a second property on `Account`
- **Expected:** `ValueError` at import saying the spelling "spells two
  properties, so a column carrying it would be counted twice"
- **Why:** a double-counted column inflates `matched` and can promote a
  POSSIBLE to a RECOGNISED.

### PCK-168 · Recognition of a clean Account
- **Area:** `concepts.py::recognise`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `recognise('Account', ['account_id','currency','account_status'])`
- **Expected:** `RECOGNISED`, three matched, no missing identifying or defining
- **Why:** the happy path, and the case every threshold is measured against.

### PCK-169 · A missing identifying property is NOT_RECOGNISED
- **Area:** `concepts.py::recognise`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `recognise('Account', ['currency','account_status'])`
- **Expected:** `NOT_RECOGNISED`, with the reason naming `account_id` and
  saying "without which this is not Account"
- **Why:** "an Account without an account identifier is a report about
  accounts, not a set of accounts".

### PCK-170 · An identifier alone is POSSIBLE, never RECOGNISED
- **Area:** `concepts.py::recognise`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `recognise('Account', ['account_id'])`
- **Expected:** `POSSIBLE` with the reason about identifiers appearing on every
  referencing table
- **Why:** "`account_id` alone appears on a payment, a fee, a statement line
  and an audit record" — the second most common source of a confident wrong
  answer after name matching.

### PCK-171 · A missing defining property is POSSIBLE, not a refusal
- **Area:** `concepts.py::recognise`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `recognise('Exposure', ['counterparty_id','as_of_date','net_notional'])`
  — omitting `netting_set`
- **Expected:** `POSSIBLE`, `missing_defining == ('netting_set',)`
- **Why:** "their absence is a finding about the dataset … but it does not
  refute the recognition", and the Exposure boundary says the netting set is the
  thing whose absence understates a breach.

### PCK-172 · Three states, never two
- **Area:** `concepts.py::Standing`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** produce all three standings; check `Recognition.__bool__`
- **Expected:** `bool()` is True only for RECOGNISED; POSSIBLE is
  distinguishable from NOT_RECOGNISED in `to_dict`
- **Why:** the two-state version "collapses 'this is not an Account' and 'this
  might be an Account and I cannot tell' into one answer, and they call for
  opposite actions".

### PCK-173 · Column names normalise across three spellings
- **Area:** `concepts.py::_normalise`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ACCT-NO`, `acct_no`, `AcctNo`, `Acct No`, ` account_id `
- **Expected:** all resolve to the same property
- **Why:** "a concept model that distinguished them would report a mainframe
  extract as unrecognisable".

### PCK-174 · No stemming and no edit distance
- **Area:** `concepts.py::_normalise`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `settlement_amount` against a concept declaring `settled_amount`
- **Expected:** no match
- **Why:** stated as a deliberate limitation — "the fix is an alias somebody
  wrote down, which is reviewable, rather than a threshold nobody can predict".
  A fuzzy matcher creeping in later is the regression.

### PCK-175 · Position, Balance and Exposure are not conflated
- **Area:** `concepts.py::identify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `identify(['as_of_date','account_id','amount','currency'])`
- **Expected:** more than one candidate returned, ranked, with none of them
  RECOGNISED on the strength of the shared shape alone
- **Why:** the module's headline warning: "a matcher that counts overlapping
  properties calls a table all three, at which point the concept model is worse
  than nothing".

### PCK-176 · `identify` returns every candidate, not a winner
- **Area:** `concepts.py::identify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** columns that fit both Trade and Position
- **Expected:** both returned, RECOGNISED before POSSIBLE, then by match count
- **Why:** "picking one silently is how a control ends up asserting a Position
  rule on trade rows".

### PCK-177 · `identify` returns nothing for an unrelated table
- **Area:** `concepts.py::identify`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `identify(['widget_colour','sprocket_count'])` and `identify([])`
- **Expected:** an empty tuple in both cases, and the caller can distinguish
  "nothing fits" from "nothing was tried"
- **Why:** an empty tuple with no reason is the `NoClassification` problem in
  the sibling module, solved there and not here.

### PCK-178 · `expected_types` is the concept model's output
- **Area:** `concepts.py::Recognition.expected_types`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a recognised Instrument
- **Steps:** read `expected_types`
- **Expected:** `isin → isin`, `cusip → cusip`, and no entry for properties
  with no semantic type
- **Why:** "the concept model's practical value is that recognising a table as a
  Trade tells you which column ought to validate as an ISIN".

### PCK-179 · `concept()` refuses a typo with a remedy, not a traceback
- **Area:** `concepts.py::concept`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `concept('Acount')`, `concept('')`, `concept('legal entity')`
- **Expected:** the third resolves (normalised); the first two raise
  `ValidationError` listing every concept name
- **Why:** "this is reached from the CLI with a name somebody typed, and a
  traceback is not an answer to a typo".

### PCK-180 · Every concept states what it is not
- **Area:** `concepts.py::Concept.boundary`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each of the 17, assert `boundary` is non-empty
- **Expected:** all 17 — or the exceptions are declared
- **Why:** `Product` ships with an empty `boundary` and an empty `relevance`,
  while the class docstring says the boundary is "written because the concepts
  that get confused in practice are confused by people, not only by matchers".
  `prama pack concepts Product` prints a concept with no limit stated.

### PCK-181 · `prama pack recognise` reports the reason, not just the answer
- **Area:** `cli/pack.py::PackRecogniseCommand`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama pack recognise account_id ccy`
- **Expected:** the standing, the reason, the matched and unmatched columns,
  and the expected semantic types
- **Why:** recognition produces a *proposal* under CON-007; a bare label with
  no reason is not something a steward can disagree with.

## Regimes, obligations and claims

### PCK-182 · Every shipped template produces PQL that parses
- **Area:** `regulatory.py::Template.bind` · `pql.parser.parse_control`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for all 17 templates in `REGIME_OBLIGATIONS` and all 9 in
  `OBLIGATIONS`, bind every `requires` role to a plausible identifier and parse
  the result
- **Expected:** all 26 parse
- **Why:** `RelationshipRequirement`'s own docstring says "a catalogue whose
  templates do not parse is a catalogue of promises" — and
  `gdpr-retention-floor` carries a comment recording that it shipped for four
  waves as PQL that could not compile.

### PCK-183 · `gdpr-retention-floor` compiles under the non-determinism guard
- **Area:** `regimes.py`, template `gdpr-retention-floor`
- **Type:** regression
- **Priority:** P1
- **Precondition:** none
- **Steps:** bind and run `prama control check` on it
- **Expected:** accepted — `$business_date` is not the clock
- **Why:** the recorded history: the template used `CURRENT_DATE`, the refusal
  was later extended to the bare spelling (finding Q-16), and the template did
  not parse from that moment until it was changed. A test binding it and
  parsing it is the counterfactual.

### PCK-184 · `emir-notional-sign` names a function that does not exist
- **Area:** `regimes.py`, template `emir-notional-sign`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `install_shipped()` has run
- **Steps:** bind the template and run `prama control check` on the result
- **Expected:** it resolves
- **Why:** the template emits
  `SATISFIES NOTIONAL_SIGN_MATCHES_SIDE({notional}, {side})`. The pack
  registers **`SIGN_MATCHES_SIDE`**, not `NOTIONAL_SIGN_MATCHES_SIDE` — this is
  finding H1's exact shape, one wave later and in the catalogue rather than the
  CLI.

### PCK-185 · `emir-notional-sign` passes its arguments in the wrong order
- **Area:** `regimes.py`, template `emir-notional-sign`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare the template's argument order against
  `SIGN_MATCHES_SIDE(side, quantity)` and its declared families `(TEXT, NUMBER)`
- **Expected:** side first, quantity second
- **Why:** the template passes `({notional}, {side})`. Even once the name is
  corrected, the arguments are reversed — and `_sign_matches_side` would then
  reject every row as UNSET because a notional is not `BUY/SELL/B/S`. Under the
  default unknown policy that is a control failing on 100% of rows on its first
  run.

### PCK-186 · `IS FRESH WITHIN {window}` binds to something the parser accepts
- **Area:** `regimes.py` templates `mifir-t1-report-arrives`,
  `aml-feed-continuity`; `obligations.py::freshness`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** bind `window` to `'24 HOURS'`, `'1d'`, `'24'` and `'1 DAY'`
- **Expected:** the grammar's own form (`<integer> MINUTES|HOURS|DAYS`)
  documented on the template; the others refused with the parser's remedy
- **Why:** `requires=("dataset","window")` says nothing about the shape, and a
  role whose value is a *fragment of syntax* rather than a column name is the
  one place `bind()`'s "refuses on a missing binding" guarantee does not help.

### PCK-187 · `reconciles-with` and `control-sum-agrees` cross datasets
- **Area:** `obligations.py` templates `reconciles-with`,
  `control-sum-agrees`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** bind `CHECK {dataset} SATISFIES {measure} = {counterpart_measure}`
  with the counterpart on another dataset and compile it
- **Expected:** a refusal naming the cross-dataset reference
- **Why:** `SATISFIES` is a per-row condition on one dataset. A
  `counterpart_measure` on a second dataset compiles to a column that does not
  exist — which on SQLite resolves to a string literal and reports `pass` over
  a thousand rows (finding Q-08).

### PCK-188 · `Template.bind` refuses a missing binding
- **Area:** `regulatory.py::Template.bind`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** bind `mifir-isin-valid` with only `dataset`
- **Expected:** `ValidationError` naming `isin` and saying a template with an
  unbound placeholder is not a control
- **Why:** "a control that names `{amount}` compiles to SQL that names a column
  called `{amount}`, and the failure surfaces at execution as a database error
  nobody connects to a template".

### PCK-189 · `Template.bind` with an extra binding
- **Area:** `regulatory.py::Template.bind`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** bind with a mapping containing three unused keys
- **Expected:** the extras ignored without error
- **Why:** `str.format(**columns)` tolerates extras and raises `KeyError` on a
  placeholder absent from `requires` — so a template whose `requires` is out of
  step with its own PQL raises a bare `KeyError` rather than the ValidationError
  the method promises.

### PCK-190 · A bound value containing a brace
- **Area:** `regulatory.py::Template.bind`
- **Type:** security
- **Priority:** P2
- **Precondition:** none
- **Steps:** bind `dataset` to `{isin}` and to `'; DROP TABLE x --`
- **Expected:** the value inserted literally and the resulting PQL refused by
  the parser, not re-expanded and not executed
- **Why:** `format` does not recurse, but the produced string goes to a parser
  that produces SQL; a dataset name arriving from a catalogue a customer
  controls is finding S5's threat model.

### PCK-191 · Every obligation ships something or says it does not
- **Area:** `regulatory.py::Obligation.__post_init__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** construct an obligation with no templates, relationships or
  `not_discharged`
- **Expected:** `ValueError` saying it "ships nothing that discharges it and
  does not say so"
- **Why:** "an obligation with no templates, no relationships and no stated gap
  is an entry that looks covered", and a catalogue entry reads as handled.

### PCK-192 · Every citation is marked unconfirmed
- **Area:** `regimes.py::_c` · `regulatory.py::Citation`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `prama pack claims`; count confirmed citations
- **Expected:** zero of 20 confirmed; every rendering carries "[unconfirmed
  against the published text]"
- **Why:** "an unverified article number that turns out to be wrong costs more
  credibility than having cited nothing", and the whole design of `Citation` is
  that confirmation cannot be a default argument.

### PCK-193 · A confirmed citation with nobody named is refused
- **Area:** `regulatory.py::Citation.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Citation(..., confirmed=True)` with no `confirmed_by`
- **Expected:** `ValueError` — "an unattributable confirmation is not one"
- **Why:** the only thing stopping a catalogue from marking itself verified.

### PCK-194 · `prama pack claims` names what the pack does not discharge
- **Area:** `cli/pack.py::PackClaimsCommand`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** run it; read `SUPPORTED_NOT_DISCHARGED` and `REGIME_SCOPE`
- **Expected:** the three dischargeable BCBS 239 principles, the supported-only
  ones, and every regime's boundary
- **Why:** "a pack that listed only what it covers invites a reader to assume
  the rest. Naming the boundary is what makes the covered part believable."

### PCK-195 · Six BCBS 239 principles are in neither list
- **Area:** `obligations.py::DISCHARGEABLE_PRINCIPLES`,
  `SUPPORTED_NOT_DISCHARGED`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** take the union of both and compare against P1–P14
- **Expected:** all fourteen accounted for
- **Why:** discharged is {P3,P4,P5}; supported-not-discharged is
  {P1,P2,P6,P7,P12}. **P8, P9, P10, P11, P13 and P14 appear nowhere**, while
  the module docstring says principles "1, 2 and 7 to 14" are supported. A
  reader counting the output finds eight of fourteen and has to infer the rest
  — which is the inference this data structure exists to prevent.

### PCK-196 · Each regime's scope names what it leaves alone
- **Area:** `regimes.py::REGIME_SCOPE`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** assert every regime in `REGIME_OBLIGATIONS` has a `REGIME_SCOPE`
  entry, and that each entry contains a "Not …" clause
- **Expected:** all seven regimes covered; BCBS 239 and ISO 20022 payments
  accounted for too
- **Why:** "a regime named in a catalogue reads as a regime handled, and for
  every one of these that is false". `REGIME_SCOPE` covers the seven in
  `regimes.py` and not the two in `obligations.py`.

### PCK-197 · The MiFIR under-reporting control points the right way
- **Area:** `regimes.py::mifir-t1-every-trade-reported`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a trade store with a trade absent from the report
- **Steps:** bind and run
- **Expected:** the trade is reported as a violation
- **Why:** the template's own note: "checking that every reported trade exists
  in the store finds over-reporting and cannot find under-reporting, which is
  the breach". A `REFERENCES` written in the wrong direction passes on exactly
  the data it exists to catch.

### PCK-198 · Coverage distinguishes unproven from clean
- **Area:** `regulatory.py::Catalogue.coverage`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** one regime; controls instantiated but no verdicts supplied
- **Expected:** `ADDRESSED_UNPROVEN`, `is_a_gap` True, label "controls exist
  and have not run in this period"
- **Why:** "a coverage report that collapsed the middle state into either
  neighbour would be useless in opposite directions: into the first it
  under-reports the estate, into the last it certifies work nobody did".

### PCK-199 · A partly-run obligation is not reported as proven clean
- **Area:** `regulatory.py::Catalogue.coverage`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an obligation with three controls, one passing and two with
  no verdict
- **Steps:** compute coverage
- **Expected:** something other than `PROVEN_CLEAN`, or `never_ran` surfaced
  prominently in the same sentence
- **Why:** the branch is `if never == len(controls)` … `else PROVEN_CLEAN`. One
  control passing out of three makes the whole obligation *proven clean* with
  `never_ran: 2` buried in a field. The three-state design fails at exactly the
  partial case it was built for.

### PCK-200 · An unaddressed obligation is a gap
- **Area:** `regulatory.py::Standing.is_a_gap`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** coverage for a regime with no controls instantiated
- **Expected:** every obligation `UNADDRESSED`; `Coverage.describe` leads with
  the count of unaddressed
- **Why:** "the number that matters at an examination is the count of
  obligations nothing addresses, and it belongs at the front".

### PCK-201 · Coverage over an unknown regime
- **Area:** `regulatory.py::Catalogue.coverage`, `of_regime`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `coverage('MiFID II', controls_by_template={})`
- **Expected:** a message saying no obligations are loaded, not an empty
  success
- **Why:** `describe()` handles the empty case explicitly — "no obligations are
  loaded, so nothing is covered" — and a typo'd regime name must not report a
  clean regime.

### PCK-202 · `of_principle` answers the auditor's literal question
- **Area:** `regulatory.py::Catalogue.of_principle`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `of_principle('P4')`
- **Expected:** every P4 obligation across all regimes, including the regime
  entries that carry a principle
- **Why:** "which controls address principle 4, and did they pass?" is the
  question the module exists to answer, and it must not be BCBS-239-only.

## Reference reconciliation templates — `packs/banking/reconciliations.py`

### PCK-203 · Nine templates ship and docs/12 §6 lists eleven
- **Area:** `reconciliations.py::TEMPLATES` vs `docs/12 §6`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the identities against the table
- **Expected:** the same set, or the two absent ones ("Risk system ↔ finance",
  "Legacy ↔ target during migration") marked as not shipped
- **Why:** the module docstring opens "docs/12 §6 lists eleven reconciliations
  every bank runs" and then ships nine. docs/12's own summary says nine, so the
  document disagrees with itself and the module quotes the wrong half.

### PCK-204 · Every template binds to a runnable definition
- **Area:** `reconciliations.py::ReconciliationTemplate.bind`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of the nine, bind every key role and the amount role on
  both sides, then run `Reconciliation` over two small row sets
- **Expected:** all nine produce a `Run` that completes
- **Why:** a template that cannot be instantiated is a promise, and the binding
  is where roles meet real column names.

### PCK-205 · A missing role is refused per side
- **Area:** `reconciliations.py::ReconciliationTemplate.bind`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** bind `subledger-to-gl` with `cost_centre` missing on the right
- **Expected:** `ValidationError` naming the side and the role
- **Why:** "a reconciliation with a mis-bound key matches nothing and reports
  every row on both sides as unmatched, which reads as a total outage rather
  than as a configuration error".

### PCK-206 · Binding with currency columns and no target currency refuses at run time
- **Area:** `reconciliations.py::bind` → `recon/engine.py::Reconciliation.run`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** bind any template with `left_currency_column='ccy'`,
  `right_currency_column='ccy'` and no `target_currency`; run it over rows
  carrying `EUR`
- **Expected:** either a refusal at *bind* time naming the missing target, or a
  run that compares like with like
- **Why:** the engine computes `target = target_currency or right.spec.currency
  or ""`, and `AmountNormaliser` then converts every non-empty currency to the
  empty string — so the run refuses with "no EUR/ rate", after the scan. The
  refusal is correct and arrives at the worst possible moment.

### PCK-207 · The declared tolerance reaches the classifier
- **Area:** `reconciliations.py::TEMPLATES` → `recon/classify.py::Classifier`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `position-to-custodian` (`_EXACT`) over a one-share difference;
  `front-office-to-subledger` (`_materiality(0.01)`) over a half-penny one
- **Expected:** a break in the first, none in the second
- **Why:** "a tolerance invented by an engineer is one operations will override
  on the first day", and the template's value is that the number is stated.

### PCK-208 · `subledger-to-gl` states a currency-specific tolerance it does not have
- **Area:** `reconciliations.py`, `subledger-to-gl.tolerance_rationale`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the rationale, then the tolerance
- **Expected:** the two agree
- **Why:** the rationale says "currency-specific materiality. A yen ledger has
  no minor unit, so a tolerance of one hundredth is a tolerance of nothing" —
  and the tolerance is `Tolerance(absolute=0.01, relative=0.0001)`, with no
  currency awareness anywhere in `Tolerance`. The sentence describes the defect
  it ships with.

### PCK-209 · `date_window` reaches the tolerance matcher
- **Area:** `reconciliations.py::bind` → `recon/match.py::ToleranceMatcher`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `cashbook-to-statement` (window 3) over a payment booked two days
  apart on the two sides
- **Expected:** one pair classified TIMING, not one missing and one extra
- **Why:** "matched exactly, every such row appears twice in the breaks … and
  the break total is double the real difference, which is zero".

### PCK-210 · Every template names an expected break taxonomy
- **Area:** `reconciliations.py::ReconciliationTemplate.expected_breaks`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** for all nine, assert `expected_breaks` is non-empty and
  `describe()` never prints "no taxonomy stated"
- **Expected:** all nine have one
- **Why:** "a reconciliation whose breaks are all 'genuine' has not been
  classified, and a queue of unexplained differences is one nobody works".

### PCK-211 · The shipped taxonomies are reachable kinds
- **Area:** `reconciliations.py::expected_breaks` vs
  `recon/classify.py::Classifier`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each template, construct data that produces each declared
  kind through the real classifier
- **Expected:** each declared kind is producible; the docs/12 table's extra
  names (fee, cancel/amend, unpresented, in-transit, corporate action) are
  either mapped to a `BreakKind` or removed from the document
- **Why:** a taxonomy a classifier cannot produce is a promise on a slide, and
  the ones in docs/12 §6 have no counterpart in `BreakKind` at all.

### PCK-212 · `template()` raises a bare KeyError
- **Area:** `reconciliations.py::template`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama pack reconciliation nosuch`
- **Expected:** a `ValidationError` listing the nine identities, as
  `concepts.concept()` does for the same situation
- **Why:** `concept()` carries a comment explaining why a `KeyError` is not an
  answer to a typo; `template()` in the same pack raises one. One of the two is
  wrong.

## Semantic-type validators — `classify/validators.py`

Twenty validators ship. CLS-001 to CLS-010 are the cross-cutting cases that
must hold for **every** one of them; CLS-011 onwards take each validator in
turn against published values.

### CLS-001 · Every validator is registered exactly once under its own name
- **Area:** `validators.py::default_registry`, `ValidatorRegistry.register`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `REGISTRY.names()`; register a second class claiming an existing
  name
- **Expected:** twenty names; the second registration raises `ValidationError`
  saying "a control saying IS VALID 'lei' must mean exactly one thing, or the
  same control changes meaning on a different node"
- **Why:** the name is what a control's meaning is keyed on, and a collision
  makes the same PQL mean two things in two processes.

### CLS-002 · A null is not invalid, for every validator
- **Area:** `validators.py::SemanticValidator.judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `judge(None)` on all twenty
- **Expected:** `VALID` from all twenty
- **Why:** "whether a missing value is acceptable is a completeness question
  that the attribute's optionality already answers; conflating the two would
  make every nullable identifier column fail its format control, and the format
  control would be turned off".

### CLS-003 · An empty or whitespace-only value is not invalid
- **Area:** `validators.py::SemanticValidator.judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `judge('')`, `judge('   ')`, `judge('\t\n')` on all twenty
- **Expected:** `VALID` from all sixty calls
- **Why:** the same reasoning as CLS-002 and the one the SQL side must match —
  finding Q-12 records `TREAT UNKNOWN AS PASS` not reaching `IS VALID` on
  SQLite because the REGEXP hook returned `False` for NULL against its own
  docstring.

### CLS-004 · Surrounding whitespace is stripped before judging
- **Area:** `validators.py::SemanticValidator.judge`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `judge(' US0378331005 ')` and `judge('US0378331005\n')`
- **Expected:** valid
- **Why:** a trailing newline from a CSV load is the commonest cause of a
  format control failing on every row, and the SQL screen — which does not
  strip — must be checked to agree (see CLS-009).

### CLS-005 · Internal whitespace is a failure
- **Area:** `validators.py` screens
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `judge('GB82 WEST 1234 5698 7654 32')` on `iban`;
  `judge('US 0378331005')` on `isin`
- **Expected:** invalid, failing the screen
- **Why:** the grouped form is how an IBAN is *printed* and a common way for
  one to arrive; refusing it is correct and must be a screen failure with the
  "not shaped like" reason, so the remedy tells a steward to strip spaces.

### CLS-006 · Lowercase input fails, and says it failed the screen
- **Area:** `validators.py::SemanticValidator.judge`, `screen_failure`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `judge('us0378331005')` on `isin`, `'de89370400440532013000'` on
  `iban`, `'deutdeff'` on `bic`
- **Expected:** invalid with `failed_screen=True` and the reason "is not shaped
  like an ISIN"
- **Why:** no validator upper-cases its input. That is a defensible choice —
  the standards are uppercase — but it means an estate whose warehouse
  lower-cases identifiers fails 100% of rows, and the distinction between a
  screen failure ("usually the wrong column entirely") and an algorithm failure
  is what tells a steward which.

### CLS-007 · Unicode look-alikes and non-ASCII are refused
- **Area:** `validators.py` screens
- **Type:** security
- **Priority:** P2
- **Precondition:** none
- **Steps:** an ISIN with a Cyrillic `А` (U+0410) for `A`; a full-width `０`;
  a value containing a zero-width space; `judge('é')` on all twenty
- **Expected:** invalid in every case, and no exception
- **Why:** `_expand` computes `ord(c) - 55` for any non-digit, so a Cyrillic
  letter produces a large number and the mod-97 arithmetic runs on it rather
  than refusing. The screen is what stops it, and the screen is `[A-Z]` —
  confirm it is not compiled with `re.UNICODE` semantics that widen it.

### CLS-008 · A 256-character value is refused without cost
- **Area:** `validators.py` screens · `plugins.py::PROBES`
- **Type:** performance
- **Priority:** P2
- **Precondition:** none
- **Steps:** `judge('x' * 256)` and `judge('9' * 100_000)` on all twenty
- **Expected:** invalid, bounded time, no exception
- **Why:** `PROBES` already contains `'x' * 256` for registered plugins; the
  shipped validators are not run against it, and a screen with a catastrophic
  backtracking shape would be a denial of service on a profiling scan.

### CLS-009 · The screen and the SQL screen accept the same values
- **Area:** `validators.py::screen` vs the compiled regex predicate
- **Type:** contract
- **Priority:** P1
- **Precondition:** SQLite, DuckDB and PostgreSQL
- **Steps:** for each validator, run its `screen_pattern` through each engine's
  regex facility over a corpus including the CLS-004 to CLS-008 values
- **Expected:** identical acceptance on all four implementations
- **Why:** the two-stage design rests on the screen being "a necessary
  condition that no valid value can fail". A screen that is stricter in SQL
  than in Python reports a violation on good data; one that is looser lets a
  row past the only check the warehouse runs.

### CLS-010 · A PATTERN validator's screen is the whole test; an ALGORITHM's is not
- **Area:** `validators.py::screen_is_complete`, `Expressibility`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `screen_is_complete` on all twenty; then compile
  `CHECK t.c IS VALID isin` and confirm the plan carries a residual stage
- **Expected:** True only for the eight PATTERN validators; every ALGORITHM
  validator's plan carries a residual
- **Why:** "`GB0000000000` passes every ISIN regex ever written and is not an
  ISIN, so the control would be green on a column of fabricated identifiers" —
  and finding T3 is the streaming path having dropped exactly that second
  stage.

### CLS-011 · ISIN accepts published identifiers
- **Area:** `validators.py::IsinValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `US0378331005` (Apple), `GB0002634946` (BAE Systems),
  `DE000BAY0017` (Bayer), `XS0629974352` (a Eurobond)
- **Expected:** all valid
- **Why:** the check digit is Luhn over the letter-expanded body; the two
  letters at the front are where an implementation that forgets to expand
  passes on numeric-prefixed ISINs and fails on every other.

### CLS-012 · ISIN rejects a wrong check digit and names the right one
- **Area:** `validators.py::IsinValidator.check`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `US0378331004`; `GB0000000000`
- **Expected:** invalid, reason "check digit is 4, should be 5 —
  US0378331005 would be valid"; `failed_screen` False
- **Why:** "'invalid ISIN' on a stewardship queue of four thousand rows is not
  a finding anybody can act on, whereas 'check digit is 7, should be 4' is a
  typo somebody can fix in ten seconds". `GB0000000000` is the fabricated
  identifier the whole cascade is built around.

### CLS-013 · ISIN rejects wrong length and wrong charset
- **Area:** `validators.py::IsinValidator.screen_pattern`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `US037833100` (11), `US03783310055` (13), `US037833100A` (letter
  check digit), `1S0378331005` (digit country)
- **Expected:** all invalid, `failed_screen=True`
- **Why:** the shape is nine alphanumerics between two letters and one digit,
  and each of these breaks exactly one clause of that.

### CLS-014 · SEDOL accepts a published identifier and applies the weights
- **Area:** `validators.py::SedolValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `0263494` (BAE Systems); then `0263495`
- **Expected:** valid; invalid with "check digit is 5, should be 4"
- **Why:** weights `1,3,1,7,3,9` over six characters — a transposed weight
  passes about one value in ten and fails the rest, which looks like dirty data
  rather than a broken validator.

### CLS-015 · SEDOL rejects a vowel
- **Area:** `validators.py::SedolValidator.screen_pattern`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `B0AKT98`, `0263A94`
- **Expected:** invalid, screen failure
- **Why:** "vowels are excluded by the scheme, which is a genuine part of the
  check rather than a nicety: it is what stops a SEDOL being confused with a
  truncated ticker".

### CLS-016 · CUSIP accepts a published identifier
- **Area:** `validators.py::CusipValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `037833100` (Apple); `459200101` (IBM)
- **Expected:** valid
- **Why:** the modified-Luhn doubles *odd* positions and sums the digits of the
  product; doubling the even ones is the classic transcription error and
  produces a validator that rejects most real CUSIPs.

### CLS-017 · CUSIP accepts `*`, `@` and `#` with their scheme values
- **Area:** `validators.py::CusipValidator.check`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** a CUSIP containing `*` (36), `@` (37) and `#` (38)
- **Expected:** valid where the check digit is right
- **Why:** these three characters appear in private-placement CUSIPs, they are
  in the screen, and their numeric values are three constants nobody re-derives.

### CLS-018 · CUSIP rejects a wrong check digit
- **Area:** `validators.py::CusipValidator.check`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `037833101`
- **Expected:** invalid, "check digit is 1, should be 0"
- **Why:** one digit away from a real security, which is what a fat-fingered
  reference-data load produces.

### CLS-019 · FIGI accepts a published identifier
- **Area:** `validators.py::FigiValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `BBG000BLNNH6` (IBM); `BBG000B9XRY4` (Apple)
- **Expected:** valid
- **Why:** the scheme's structure — no vowels in the first two characters, `G`
  in the third — is in the screen because it "rejects the overwhelming majority
  of wrong-column values", and getting the reserved position wrong rejects
  every FIGI there is.

### CLS-020 · FIGI rejects a vowel in the prefix and a wrong third character
- **Area:** `validators.py::FigiValidator.screen_pattern`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ABG000BLNNH6`, `BBX000BLNNH6`
- **Expected:** invalid, screen failure
- **Why:** the two structural rules; a screen missing either admits a large
  class of non-FIGIs at 12 characters.

### CLS-021 · LEI accepts published identifiers, including interim-era ones
- **Area:** `validators.py::LeiValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `HWUPKR0MPOU8FGXBT394`, `7LTWFZYICNSX8D621K86`
- **Expected:** both valid
- **Why:** the docstring names these two as live CICI-era LEIs carrying letters
  in positions 5-6, which is why the screen deliberately does **not** enforce
  the `00` reservation. "A screen that rejected them would report a violation
  on perfectly good reference data, which is the one thing a necessary
  condition must never do."

### CLS-022 · LEI rejects a fabricated identifier of the right shape
- **Area:** `validators.py::LeiValidator.check`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `HWUPKR0MPOU8FGXBT395`; `AAAAAAAAAAAAAAAAAA00`
- **Expected:** invalid, reason naming the first eighteen characters
- **Why:** round 1 recorded twelve fabricated LEIs with valid shape and wrong
  check digits producing `indeterminate` with the residual named. That is the
  central thesis; this is its unit.

### CLS-023 · LEI rejects non-digit check characters and wrong length
- **Area:** `validators.py::LeiValidator.screen_pattern`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `HWUPKR0MPOU8FGXBT39A` (letter check), 19 characters, 21
  characters
- **Expected:** invalid, screen failure
- **Why:** ISO 17442 is exactly twenty with two trailing digits, and a
  20-character internal party key is the thing a `lei`-named column most often
  actually holds.

### CLS-024 · `_mod97` chunking equals the whole-integer modulo
- **Area:** `validators.py::_mod97`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for a thousand random digit strings of length 1 to 60, compare
  `_mod97(s)` with `int(s) % 97`
- **Expected:** identical every time
- **Why:** the seven-digit chunking is a performance decision on a function
  used "on batches of millions of values"; a boundary error in the chunk size
  is wrong for one length class in seven and correct elsewhere, which is
  invisible to a handful of examples.

### CLS-025 · IBAN accepts published identifiers from several countries
- **Area:** `validators.py::IbanValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `GB82WEST12345698765432`, `DE89370400440532013000`,
  `FR1420041010050500013M02606`, `NO9386011117947` (15, the shortest)
- **Expected:** all valid
- **Why:** the rearrangement — move the first four characters to the end, then
  expand, then mod-97 — has two places to get the direction wrong, and a
  validator that reversed it passes roughly one IBAN in 97.

### CLS-026 · IBAN rejects a wrong check digit
- **Area:** `validators.py::IbanValidator.check`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `GB82WEST12345698765433`, `DE88370400440532013000`
- **Expected:** invalid, "the check digits do not verify"
- **Why:** a single altered digit is what a rekeyed payment instruction looks
  like.

### CLS-027 · IBAN enforces the country-specific length
- **Area:** `validators.py::IbanValidator.LENGTHS`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** a 21-character `DE` IBAN whose mod-97 happens to verify
- **Expected:** invalid, "a DE IBAN is 22 characters; this one is 21"
- **Why:** "omitting this check accepts a truncated account number whose mod-97
  happens to land on 1 once in 97 times" — and a truncated account number is
  the failure mode of a fixed-width extract.

### CLS-028 · IBAN rejects a country that does not issue one
- **Area:** `validators.py::IbanValidator.check`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `US64SVBKUS6S3300958879`, `ZZ00...`
- **Expected:** invalid, "US does not issue IBANs, or is not a country code"
- **Why:** a US "IBAN" is a thing systems manufacture, and the reason is the
  part a steward acts on.

### CLS-029 · The IBAN country table matches ISO 3166 and declares its extras
- **Area:** `validators.py::IbanValidator.LENGTHS` vs
  `codelists.ISO_3166`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** set-difference the two
- **Expected:** every difference explained
- **Why:** `XK` (Kosovo) is in `LENGTHS` and not in `ISO_3166` — correctly, it
  is user-assigned — but nothing says so, and an `IBAN_COUNTRY` result fed to
  `IN CODELIST iso3166` reports every Kosovan IBAN as a violation. Two lists in
  one product that disagree without a note is how a drift becomes a finding.

### CLS-030 · IBAN length table covers the countries an estate will see
- **Area:** `validators.py::IbanValidator.LENGTHS`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** count the entries; check a recent addition (e.g. `SO`, `FK`, `MN`,
  `NI`, `DJ`, `RU`)
- **Expected:** either present, or the refusal reason distinguishes "not in our
  table" from "does not issue IBANs"
- **Why:** the reason string conflates the two, so a country added to the
  registry after this table was written is reported to a steward as a country
  that does not issue IBANs — a wrong statement about the world.

### CLS-031 · BIC accepts 8 and 11 characters
- **Area:** `validators.py::BicValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `DEUTDEFF`, `DEUTDEFF500`, `NEDSZAJJXXX`
- **Expected:** all valid
- **Why:** both lengths are in use; a validator accepting only 11 fails every
  head-office BIC.

### CLS-032 · BIC rejects 9, 10 and 12 characters, and digits in the bank code
- **Area:** `validators.py::BicValidator.screen_pattern`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `DEUTDEFF5`, `DEUTDEFF50`, `DEUTDEFF5000`, `DEUT1EFF`
- **Expected:** all invalid
- **Why:** ISO 9362 is 4 letters + 2 letters + 2 alphanumerics + optional 3;
  the optional-group boundary is where a regex admits 9 and 10.

### CLS-033 · BIC has no check digit, and says so
- **Area:** `validators.py::BicValidator`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** `screen_is_complete`; `describe()`; the `beyond_shape` default
- **Expected:** complete in SQL; `beyond_shape` is not quoted in a generated
  control's reason
- **Why:** the default `beyond_shape` is "a value of the right shape can still
  fail it", which is **false** for a `PatternValidator` — and it is inherited
  by all eight of them. A generated control saying so under a BIC check is the
  wrong-sentence defect `beyond_shape`'s own docstring warns about.

### CLS-034 · MIC accepts real market identifiers
- **Area:** `validators.py::MicValidator`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `XNYS`, `XLON`, `XETR`, `BATE`
- **Expected:** valid
- **Why:** a MIC is the venue a MiFIR report is rejected on; four uppercase
  alphanumerics is the whole standard.

### CLS-035 · MIC accepts anything of the right shape
- **Area:** `validators.py::MicValidator`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ZZZZ`, `0000`
- **Expected:** valid, and the limitation visible — shape is not membership
- **Why:** the ISO 10383 register is a *list*, so a MIC control that only
  checks shape passes a venue code that does not exist. Either a code list
  ships or the gap is stated; a four-character screen presented as "ISO 10383"
  overclaims.

### CLS-036 · ABA routing accepts a published number
- **Area:** `validators.py::AbaRoutingValidator`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `021000021` (JPMorgan Chase), `011000015` (FRB Boston)
- **Expected:** valid
- **Why:** the 3-7-1 weights repeat three times; an off-by-one in the weight
  cycle passes roughly a tenth of numbers.

### CLS-037 · ABA rejects a wrong checksum and a wrong length
- **Area:** `validators.py::AbaRoutingValidator`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `021000022`; `02100002`; `0210000210`
- **Expected:** all invalid; the first an algorithm failure, the others screen
  failures
- **Why:** the screen/algorithm distinction routes a whole-column problem
  differently from a single bad value.

### CLS-038 · UTI accepts an LEI-prefixed identifier
- **Area:** `validators.py::UtiValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `7LTWFZYICNSX8D621K86` + `TRADE0001`
- **Expected:** valid
- **Why:** the UTI is the key EMIR pairing turns on, and `emir-uti-valid` is a
  shipped critical control.

### CLS-039 · A bare 20-character LEI is not a UTI
- **Area:** `validators.py::UtiValidator.screen_pattern`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `7LTWFZYICNSX8D621K86` alone (20 characters); a 53-character value
- **Expected:** both invalid — the pattern is 20 + 1…32, so 21 to 52
- **Why:** the docstring says "LEI-prefixed, up to 52 characters" and the
  pattern's lower bound is 21. The boundary is unstated and a 20-character UTI
  is what a truncated field produces.

### CLS-040 · A UTI whose prefix is not a valid LEI still passes
- **Area:** `validators.py::UtiValidator`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** `AAAAAAAAAAAAAAAAAA00TRADE1`
- **Expected:** valid, and the limitation stated
- **Why:** `UtiValidator` is a `PatternValidator`, so `screen_is_complete` is
  True and the compiler emits a regex and calls the job done — over an
  identifier whose first twenty characters are an LEI that could be verified.
  The product's own thesis says a shape is not a proof.

### CLS-041 · UPI accepts twelve alphanumerics and rejects anything else
- **Area:** `validators.py::UpiValidator`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `QZ2XBR7JZ0N2`; then 11 and 13 characters; then lowercase
- **Expected:** valid, then three refusals
- **Why:** ANNA-DSB UPIs are shape-only here, and the overlap with a 12-character
  ISIN is the ambiguity the classifier's `_reconcile` exists for (CLS-070).

### CLS-042 · GTIN accepts all four lengths
- **Area:** `validators.py::GtinValidator`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `4006381333931` (13), `036000291452` (12), `96385074` (8), a
  valid 14
- **Expected:** all valid
- **Why:** the 3-weight lands on the rightmost body digit whatever the length,
  which is why the parity is taken from the end; a from-the-start
  implementation is right for two lengths and wrong for the other two.

### CLS-043 · GTIN rejects a wrong check digit at each length
- **Area:** `validators.py::GtinValidator.check`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** alter the final digit of each of the four above
- **Expected:** invalid at each length
- **Why:** the parity argument in CLS-042 needs its counterfactual, or a
  from-the-start implementation passes the test by accident on two lengths.

### CLS-044 · NPI applies Luhn over the 80840 prefix
- **Area:** `validators.py::NpiValidator`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** `1234567893`; then `1234567890`
- **Expected:** valid; invalid
- **Why:** the constant prefix is the whole trick, and Luhn over the bare ten
  digits gives a different answer — so a validator that forgot it would pass a
  different tenth of the space.

### CLS-045 · A payment card number validates by Luhn and is marked sensitive
- **Area:** `validators.py::CreditCardValidator`, `semantic.SENSITIVE_TYPES`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** `4111111111111111`; `4111111111111112`; then classify a column of
  them
- **Expected:** valid, invalid, and a `SENSITIVE_CONTENT` conflict on the
  classification
- **Why:** "detecting one is usually a discovery that cardholder data is
  somewhere it was not supposed to be", and the conflict is what stops a sample
  of it reaching evidence or a model.

### CLS-046 · Card numbers at 12 and 19 digits
- **Area:** `validators.py::CreditCardValidator.screen_pattern`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** an 11-digit Luhn-valid number, a 12-digit one, a 19-digit one, a
  20-digit one
- **Expected:** the inner two accepted by the screen, the outer two refused
- **Why:** ISO/IEC 7812 permits 12 to 19; a screen one digit either way changes
  which columns get flagged as holding cardholder data.

### CLS-047 · Email accepts ordinary addresses and rejects the RFC exotica
- **Area:** `validators.py::EmailValidator`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `a@b.co`, `first.last+tag@sub.example.co.uk`; then
  `"quoted string"@example.com`, `a@b`, `a@-b.com`, `a@b-.com`, `@b.com`,
  `a@@b.com`, a 65-character local part
- **Expected:** the first two valid, the rest invalid
- **Why:** "the complete grammar accepts quoted strings and comments that no
  mail system in this decade will deliver to, and a validator that accepts them
  reports a clean column that bounces". The hyphen-at-the-edge cases are what
  the inner label pattern exists for.

### CLS-048 · UUID accepts both cases and rejects the braced and unhyphenated forms
- **Area:** `validators.py::UuidValidator`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `123e4567-e89b-12d3-a456-426614174000`, its uppercase form;
  then `{123e4567-...}`, the 32-character unhyphenated form, and a
  `urn:uuid:` prefix
- **Expected:** the first two valid, the rest invalid
- **Why:** all three rejected forms are how UUIDs actually arrive from .NET,
  from a database export and from a URN field, and each is a whole-column
  failure that looks like data corruption.

### CLS-049 · ULID accepts Crockford base32 and rejects I, L, O and U
- **Area:** `validators.py::UlidValidator`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `01ARZ3NDEKTSV4RRFFQ69G5FAV`; then one containing `I`; then one
  starting with `8`
- **Expected:** valid, invalid, invalid
- **Why:** the leading character is bounded to `[0-7]` because a ULID's
  timestamp cannot overflow, and the four excluded letters are the ones that
  survive transcription. Prama's own identifiers are ULIDs.

### CLS-050 · ISO 8601 date rejects a date that does not exist
- **Area:** `validators.py::Iso8601DateValidator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `2026-02-30`, `2026-13-01`, `2026-00-10`, `2026-01-00`,
  `2026-04-31`
- **Expected:** all invalid, each with a reason naming the month or the day
  limit
- **Why:** "a date can have the right shape and not exist — 2026-02-30 is the
  case this catches", and a bad date silently becomes a bad business date.

### CLS-051 · ISO 8601 date handles leap years and century rules
- **Area:** `validators.py::Iso8601DateValidator.check`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `2024-02-29`, `2023-02-29`, `2000-02-29`, `1900-02-29`,
  `2100-02-29`
- **Expected:** valid, invalid, valid, invalid, invalid
- **Why:** the `% 400` clause is exercised by exactly two of these, and a
  validator with only the `% 4` rule is right for 96 years in a century.

### CLS-052 · ISO 8601 date rejects a timestamp and a non-hyphen separator
- **Area:** `validators.py::Iso8601DateValidator.screen_pattern`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `2026-03-02T00:00:00Z`, `2026/03/02`, `20260302`, `26-03-02`
- **Expected:** all invalid, screen failures
- **Why:** the screen is exactly ten characters; a column of timestamps
  declared `iso_date` fails 100% of rows, which is the `contradicts_declaration`
  case rather than a per-row defect.

### CLS-053 · IPv4 rejects an octet above 255 and a leading zero
- **Area:** `validators.py::Ipv4Validator`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `10.0.0.1`, `255.255.255.255`, `256.0.0.1`, `010.0.0.1`,
  `10.0.0.01`, `10.0.0`
- **Expected:** first two valid, the rest invalid with reasons
- **Why:** "a leading zero is read as octal by some resolvers and as decimal by
  others, so the same string routes two ways. That is a defect wherever it
  appears, not a formatting nicety."

### CLS-054 · Hex colour has no authority and accepts both forms
- **Area:** `validators.py::HexColourValidator`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** `#1a2b3c`, `1a2b3c`, `#1A2B3C`, `#1a2`, `#1a2b3c4`
- **Expected:** the first three valid, the last two invalid; `describe()`
  reads sensibly with an empty `authority`
- **Why:** `authority` is empty for exactly one validator, and `describe()`
  says "an identifier check that cannot name its authority is folklore" — so
  the generated control's reason for this one needs reading.

### CLS-055 · An unknown validator name is refused with the vocabulary
- **Area:** `validators.py::ValidatorRegistry.get`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `REGISTRY.get('nino')`; `CHECK t.c IS VALID nino` through
  `prama control check`
- **Expected:** `ValidationError` listing all twenty and saying "an unknown
  semantic type would compile to a check that passes everything, so it is
  refused here instead"
- **Why:** the refusal's own reason is the failure mode, and the CLI path must
  produce it rather than a traceback.

### CLS-056 · A validator with no name is refused at registration
- **Area:** `validators.py::ValidatorRegistry.register`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** register a subclass with `name = ""`
- **Expected:** `ValidationError` with the remedy "Set the class-level `name`"
- **Why:** a nameless validator is unreachable from PQL and would sit in the
  registry looking installed.

### CLS-057 · Re-registering the identical class is idempotent
- **Area:** `validators.py::ValidatorRegistry.register`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** register two instances of the same class under the same name
- **Expected:** accepted, no error
- **Why:** the guard is `type(existing) is not type(validator)`, which permits
  this on purpose — entry-point loading can present the same distribution
  twice — and the permitted case must not become a refusal.

## Code lists — `classify/codelists.py`

### CLS-058 · `iso4217` resolves membership as of a date
- **Area:** `codelists.py::CodeList.as_of`, `contains`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `contains('EUR')` with no date, and with dates in 2021 and 2026
- **Expected:** True in all three
- **Why:** the base case for every version-boundary test below.

### CLS-059 · ZWL is valid in 2023 and absent in 2025
- **Area:** `codelists.py::_ISO4217_2024`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `contains('ZWL', when=2023-06-01)`, `when=2024-04-04`,
  `when=2024-04-05`, `when=2025-03-30`, `when=2025-03-31`
- **Expected:** True, True, True, True, **False**
- **Why:** the effective date is 2024-04-05, so 04-04 and 04-05 are the two
  sides of the boundary — of the version, not of ZWL's validity. "A control that
  resolves the currency list to whatever is current today reports last year's
  perfectly correct data as invalid."

  Both the third step's expectation and the fourth step's *date* were wrong until
  round 4, and the second error was hidden by the first. The outgoing code is
  retired one version **after** its replacement arrives, deliberately and with a
  comment saying so: the 2024-04-05 version adds ZWG and keeps ZWL; the
  2025-03-31 version retires it. Removing it in the same step is how a correct
  payment file gets rejected mid-transition, which is what `CLS-062` fixed.

  So ZWL is valid at 2024-04-05, and the original fourth probe — 2025-01-01,
  chosen to mean "in 2025" — still falls inside the 2024 version, where ZWL is
  also valid. Correcting only the third step would have left this case asserting
  `False` on a date where the answer is `True`, for a different reason than the
  one it started with. The probe now straddles the real retirement boundary,
  2025-03-30 and 2025-03-31, which is what the case was always trying to test.

### CLS-060 · ZWG is absent before 2024-04-05 and present after
- **Area:** `codelists.py::_ISO4217_2024`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `contains('ZWG', when=2024-04-04)` and `when=2024-04-05`
- **Expected:** False then True
- **Why:** the other half of CLS-059, and the case that distinguishes a list
  that resolves by date from one that returns the union of everything.

### CLS-061 · ANG and XCG at the 2025-03-31 boundary
- **Area:** `codelists.py::_ISO4217_2025`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `contains('ANG', when=2025-03-30)`, `when=2025-03-31`;
  `contains('XCG', ...)` at the same two dates
- **Expected:** ANG True then **True**; XCG False then True
- **Why:** the second real version change the module ships, and the one that
  tests whether the version machinery generalises past a single hard-coded
  transition.

  ANG expected `False` at the boundary until round 4, for the same reason
  `CLS-059` did: the 2025 version adds XCG and keeps ANG, and ANG is retired in
  2026. XCG's half of this case — absent before the boundary, present after — is
  what actually exercises the version machinery, and it is unchanged. Together
  with `CLS-059` this now asserts the transition rule in both directions: the
  incoming code appears at its version, the outgoing one survives it.

### CLS-062 · The outgoing code is removed in the same step as the incoming one
- **Area:** `codelists.py::_ISO4217_2024`, `_ISO4217_2025` vs their own comment
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the comment above `_ISO4217_2024`, then check whether ZWL is
  in the same version that introduces ZWG
- **Expected:** the code matches the comment
- **Why:** the comment says "both transitions ran with the outgoing code still
  accepted for a period, **which is why the outgoing code is not removed in the
  same step** — removing it early is how a correct payment file gets rejected".
  The code removes ZWL and ANG in exactly that step. The SLL/SLE transition
  three lines above does it the way the comment describes. One of the two
  behaviours is wrong and the comment says which.

### CLS-063 · SLL survives the 2023 version and SLE is added
- **Area:** `codelists.py::_ISO4217_2023`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `contains('SLL', when=2023-06-01)`, `contains('SLE', ...)`
- **Expected:** both True
- **Why:** the transitional overlap the module docstring describes, and the
  counterexample to CLS-062.

### CLS-064 · HRK is withdrawn on euro adoption and the note says so
- **Area:** `codelists.py::_ISO4217_2023`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `contains('HRK', when=2022-12-31)` and `when=2023-01-01`
- **Expected:** True then False; the version's `note` mentions HRK
- **Why:** a Croatian payment booked in 2022 must not be reported as carrying
  an invalid currency in a 2026 replay.

### CLS-065 · CUC is removed with no note
- **Area:** `codelists.py::_ISO4217_2023`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** diff `_ISO4217_2021` against `_ISO4217_2023`; read the version's
  `note`
- **Expected:** every difference explained in the note
- **Why:** the note says "SLE added for Sierra Leone; HRK withdrawn on euro
  adoption" and the version also drops **CUC**. The reason a `note` field
  exists is "so a disputed membership can be settled by looking at the source",
  and an unexplained removal cannot be.

### CLS-066 · A date before the earliest version is refused, not defaulted
- **Area:** `codelists.py::CodeList.as_of`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ISO_4217.as_of(date(2020,12,31))`
- **Expected:** `ValidationError` naming the earliest state and saying "a
  control cannot be replayed against a list that did not exist … or accept that
  this run is not reproducible and say so"
- **Why:** silently falling back to the earliest version would make a 2005
  replay look reproducible. This is the one place the product admits it cannot
  answer.

### CLS-067 · `as_of(None)` returns the newest, and that is the authoring default
- **Area:** `codelists.py::CodeList.as_of`, `latest`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `as_of()` and `as_of(date.today())`
- **Expected:** the same version; the docstring's warning that this is "right
  for authoring a control and wrong for replaying one" is honoured by callers
- **Why:** every caller that omits the date has silently chosen the authoring
  behaviour — see PCK-050 for `_zero_decimal`, which does exactly that.

### CLS-068 · Versions out of order are refused at construction
- **Area:** `codelists.py::CodeList.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct a list whose second version predates its first; and one
  with no versions
- **Expected:** `ValidationError` in both cases
- **Why:** `as_of` walks forward and `break`s on the first later date, so an
  out-of-order list resolves to the wrong version silently.

### CLS-069 · Two versions sharing an effective date
- **Area:** `codelists.py::CodeList.as_of`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** construct a list with two versions on the same date; resolve on
  that date
- **Expected:** a refusal at construction, or a documented last-wins rule
- **Why:** `dates == sorted(dates)` permits duplicates, and the loop keeps
  assigning — so the answer is last-wins by declaration order, which is not
  stated anywhere.

### CLS-070 · Case-insensitivity is honoured by `contains` and not by `in`
- **Area:** `codelists.py::CodeList.contains` vs
  `CodeListVersion.__contains__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `SIDE.contains('buy')`; `'buy' in SIDE.latest`
- **Expected:** the same answer from both
- **Why:** `contains` upper-cases for a case-insensitive list; the version's own
  `__contains__` does not. Two membership tests on one object disagreeing is
  exactly the H1 shape, and `__contains__` is the more natural spelling.

### CLS-071 · A case-sensitive list rejects lowercase
- **Area:** `codelists.py::CodeList.contains`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ISO_4217.contains('usd')`
- **Expected:** False
- **Why:** ISO 4217 codes are uppercase by definition, and a warehouse that
  lower-cases them is a whole-column finding rather than a per-row one — the
  distinction `contradicts_declaration` exists to make.

### CLS-072 · `zero_decimal_currencies` holds the seventeen zero-minor-unit codes
- **Area:** `codelists.py::ISO_4217_MINOR_UNITS`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** check JPY, KRW, VND, CLP, ISK present; EUR, USD, KWD absent
- **Expected:** as stated
- **Why:** `MINOR_UNITS_OK` inlines this list into SQL at registration, so a
  wrong member is a wrong control on every payment in that currency. KWD has
  *three* minor units and being absent here is correct — the check only claims
  the zero case.

### CLS-073 · Every code in every list is a subset of what it claims to be
- **Area:** `codelists.py::_codes`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** assert every `iso4217` code matches `^[A-Z]{3}$`, every `iso3166`
  code `^[A-Z]{2}$`, and that the block-parsed sets have the expected sizes
- **Expected:** no malformed member; sizes stated
- **Why:** the lists are written as whitespace blocks "so a code silently added
  or dropped in a review would stand out" — a size assertion is what makes that
  true in CI rather than in a reviewer's eye.

### CLS-074 · `iso3166` ships one version and cannot answer an as-of question
- **Area:** `codelists.py::ISO_3166`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ISO_3166.as_of(date(2026,1,1))` and `as_of(date(2021,1,1))`
- **Expected:** the same set, and the single-version limitation visible to a
  reader
- **Why:** the module's whole thesis is dated snapshots, and a list with one
  version silently answers every date identically — which is right today and
  will be wrong the first time a country code changes.

### CLS-075 · An unknown list is refused with the vocabulary
- **Area:** `codelists.py::CodeListRegistry.get`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `CODELISTS.get('iso4127')`; `CHECK t.ccy IN CODELIST iso4127`
- **Expected:** `ValidationError` listing the four known lists and saying "an
  unresolved list would compile to a membership test against nothing"
- **Why:** finding Q-14 records `compile` refusing `IN CODELIST` with a false
  remedy while `run` executed it — so the two paths' refusals need pinning
  together.

### CLS-076 · Registering a list twice silently replaces it
- **Area:** `codelists.py::CodeListRegistry.register`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** register a second `CodeList(name='iso4217', ...)` with three codes
- **Expected:** a refusal, as `ValidatorRegistry.register` gives for the same
  situation
- **Why:** `self._lists[name] = code_list` overwrites without a word. The
  sibling registry in the same package refuses because "a control saying IS
  VALID 'lei' must mean exactly one thing"; the identical argument applies to
  `IN CODELIST 'iso4217'` and is not made.

### CLS-077 · `resolve` flattens every list as of one date
- **Area:** `codelists.py::CodeListRegistry.resolve`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `resolve(date(2023,6,1))`; compare `iso4217` against
  `resolve()` today
- **Expected:** four lists in both; ZWL present in the first and absent in the
  second
- **Why:** "the IR wants values, not references, because a plan has to mean one
  fixed thing" — this is where the as-of decision is frozen into a plan, and
  the plan id is what makes a verdict replayable.

### CLS-078 · `resolve` on a date before any list existed
- **Area:** `codelists.py::CodeListRegistry.resolve`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `resolve(date(2019,1,1))`
- **Expected:** a refusal naming the list and the date, not a partial dict
- **Why:** the dict comprehension calls `as_of` per list, so the first failure
  aborts the whole resolve — which is correct — but the error names one list
  when several may be affected, and a plan half-resolved is not a plan.

## The inference cascade — `classify/semantic.py`

### CLS-079 · A checksum beats a name
- **Area:** `semantic.py::SemanticClassifier.classify`, `_reconcile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column called `party_ref` holding 400 valid LEIs
- **Steps:** classify
- **Expected:** `lei`, stage `CHECKSUM`, `is_evidence` True, confidence 1.0
- **Why:** "a check digit is proof … a column name is not proof of anything",
  and the cascade stops at the first stage that produces evidence.

### CLS-080 · A name that disagrees with the content is reported, not resolved
- **Area:** `semantic.py::_reconcile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column called `lei` holding 400 valid ISINs
- **Steps:** classify
- **Expected:** `isin`, with a `NAME_CONTRADICTED` conflict naming both
- **Why:** "where the two disagree, the disagreement is reported rather than
  resolved" — the most valuable thing in the module.

### CLS-081 · A column of `GB0000000000` names the refutation, not the fit
- **Area:** `semantic.py::_reconcile`, `_measure`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a column called `isin` holding 50 copies of `GB0000000000`
- **Steps:** classify
- **Expected:** a `NAME_CONTRADICTED` conflict as the **first** conflict,
  saying the values have an ISIN's shape and not its check digit, and that this
  "looks like fabricated or placeholder data"; `upi` may be the top fit but is
  not the headline
- **Why:** the case the whole `_reconcile` method was written for. "Ranking by
  fit alone gets this exactly backwards, because the fabricated values fit the
  weaker type perfectly *by virtue of* failing the stronger one."

### CLS-082 · A declared type the data refutes is questioned, not enforced
- **Area:** `semantic.py::contradicts_declaration`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column declared `lei` in which 3% of values verify
- **Steps:** `contradicts_declaration(sample, 'lei')`
- **Expected:** a `Conflict` saying a control generated from this declaration
  would fail on 97% of rows on its first run
- **Why:** "the most useful single thing this module does" — generating the
  control would bury the discovery under an alert that gets switched off.

### CLS-083 · A declaration the data supports produces no conflict
- **Area:** `semantic.py::contradicts_declaration`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column declared `lei` in which 99% verify
- **Steps:** the same call
- **Expected:** `None`
- **Why:** the counterfactual. A check that always fires is a check nobody
  reads, and the 50% floor is the line.

### CLS-084 · Nothing is concluded from fewer than eight values
- **Area:** `semantic.py::MINIMUM_SAMPLE`, `_content_candidates`, `_refusal`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a column with 7 valid ISINs and one with 8
- **Steps:** classify both
- **Expected:** the first returns `NoClassification` with the "only 7 populated
  values" reason; the second classifies
- **Why:** "six ISINs verifying is a one-in-a-million coincidence; two is a
  Tuesday" — and `contradicts_declaration` uses the same floor, so a small
  sample cannot refute a declaration either.

### CLS-085 · An empty column and a column of nulls are distinguished
- **Area:** `semantic.py::_refusal`, `ColumnSample.populated`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a sample of ten `None`s, and one of ten blank strings
- **Steps:** classify both
- **Expected:** "the column has no populated values to test" in both, distinct
  from "N values were tested against M types and none matched"
- **Why:** "'twelve types were tried and none fitted' and 'nothing was tried
  because there were four values' are different situations, and collapsing them
  sends a steward looking at a column that was never examined".

### CLS-086 · A numeric physical type rules out letter-bearing types
- **Area:** `semantic.py::_requires_letters`, `_NUMERIC_PHYSICAL`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a `DECIMAL(18,2)` column of numbers
- **Steps:** classify; read `attempted`
- **Expected:** ISIN, LEI, BIC and the rest of the letter-bearing types absent
  from `attempted`; `gtin`, `npi`, `aba_routing`, `card_number` still tried
- **Why:** "testing them spends a pass to produce a guaranteed no, and then
  reports '12 types attempted' when only four were ever possible".

### CLS-087 · `_requires_letters` is decided from the screen pattern
- **Area:** `semantic.py::_requires_letters`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** apply it to every shipped validator
- **Expected:** exactly the types that genuinely need letters
- **Why:** the implementation is `any(c.isalpha() for c in screen_pattern)`,
  and every pattern contains regex letters — `\d` contains `d`, `[A-Z]{2}`
  contains `A` and `Z`. `iso_date`'s pattern is `^\d{4}-\d{2}-\d{2}$`, whose
  only alphabetic character is the `d` of `\d`, so a date column on a numeric
  physical type is skipped for the wrong reason. Establish which types this
  actually excludes.

### CLS-088 · Confidence is derived from the chance rate, not assigned
- **Area:** `semantic.py::_confidence_from_chance`, `_CHANCE_RATES`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** 400 LEI hits at chance 1/97; 10 ISIN hits at chance 0.1; 1 hit
- **Expected:** 1.0, ≈0.9999999999, and a value derived from the single hit —
  never a hand-set constant
- **Why:** "four hundred values satisfying a mod-97 check is not a 0.9 — it is a
  number with four hundred zeros after the decimal point". Derived numbers are
  the product's rule; an assigned one drifts.

### CLS-089 · Confidence is computed in logs and does not underflow
- **Area:** `semantic.py::_confidence_from_chance`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** 15, 16, 320 and 100_000 hits at chance 0.1
- **Expected:** monotone non-decreasing; exactly 1.0 only past the stated
  threshold; no `OverflowError` or `ValueError`
- **Why:** the docstring says the direct form "underflows at about 320 values
  and would silently return a confidence of exactly 1 for a sample of 15" —
  which is a claim about a specific sample size and is testable.

### CLS-090 · A PATTERN type's confidence is capped below certainty
- **Area:** `semantic.py::_chance_rate`, `_confidence_from_chance`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 10,000 values matching the `bic` screen
- **Steps:** classify; read `confidence` and `may_auto_apply`
- **Expected:** confidence at most 0.85; `may_auto_apply` **False**
- **Why:** "the screen was the whole test, so satisfying it is not independent
  evidence"; the 0.85 cap sits deliberately below the 0.99 auto-apply bar, so
  no pattern-only type can ever generate a control without review. That
  relationship between two constants is the property, not either number.

### CLS-091 · A model stage can never auto-apply
- **Area:** `semantic.py::Classification.may_auto_apply`
- **Type:** security
- **Priority:** P1
- **Precondition:** an adjudicator returning a `MODEL`-stage classification
  with confidence 1.0 and `Fit.CLEAN`
- **Steps:** read `may_auto_apply` and `is_evidence`
- **Expected:** both False, unconditionally
- **Why:** `CON-007` and `NFR-AI-002`. "A model's guess about what a column
  means is a fine thing to show somebody and an unacceptable thing to start
  alerting on", and `tests/architecture/test_layering.py::TestModelVerdicts` is what
  keeps it true.

### CLS-092 · An adjudicator may not invent a type
- **Area:** `semantic.py::SemanticAdjudicator.adjudicate`, `_vocabulary`
- **Type:** security
- **Priority:** P1
- **Precondition:** an adjudicator returning `semantic_type='national_id'`
- **Steps:** classify
- **Expected:** refused or discarded — the vocabulary is closed
- **Why:** the abstract method says "choose from *vocabulary*, or decline.
  Never invent a type", and nothing in the classifier checks the answer against
  the vocabulary it passed in.

### CLS-093 · The cascade runs to a useful answer with no model at all
- **Area:** `semantic.py::SemanticClassifier` with `adjudicator=None`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an air-gapped configuration
- **Steps:** classify a corpus of identifier columns
- **Expected:** every column that a deterministic stage can settle is settled;
  the rest return `NoClassification` with a reason
- **Why:** "an air-gapped deployment gets the first four stages and loses
  nothing that produces a verdict" — the stated reason the adjudicator is an
  ABC.

### CLS-094 · Fit thresholds: clean, contaminated, mixed
- **Area:** `semantic.py::_fit`, `CLEAN_HIT_RATE`, `MINIMUM_HIT_RATE`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** columns at hit rates 1.00, 0.99, 0.98, 0.80, 0.79, 0.50,
  0.49
- **Steps:** classify each
- **Expected:** CLEAN at ≥0.99, CONTAMINATED from 0.80, MIXED below;
  **nothing at all** below 0.50
- **Why:** each boundary changes what happens next — MIXED blocks a control,
  CONTAMINATED means "the minority is the finding", and below the floor the
  type is not proposed. Three thresholds, six boundaries.

### CLS-095 · A contaminated column is classified and the minority is the finding
- **Area:** `semantic.py::Fit.CONTAMINATED`, `supports_a_control`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 95 valid ISINs and 5 fabricated ones
- **Steps:** classify
- **Expected:** `isin`, CONTAMINATED, `supports_a_control` True,
  `violating_fraction` 0.05
- **Why:** "this is the outcome that makes classification worth doing at all".

### CLS-096 · A mixed column supports no control
- **Area:** `semantic.py::Fit.MIXED.supports_a_control`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 60 ISINs and 40 IBANs in one column
- **Steps:** classify
- **Expected:** MIXED; `supports_a_control` False; `is_evidence` False
- **Why:** "usually two things in one column, which is a worse problem than bad
  values and needs a person, not a control".

### CLS-097 · An ambiguity between two equal fits is named
- **Area:** `semantic.py::_is_ambiguous`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a column of 12-character alphanumerics where `upi` and
  `figi` fit within 2%
- **Steps:** classify
- **Expected:** an `AMBIGUOUS` conflict naming both, with both as candidates
- **Why:** "it is one of these two is a legitimate answer, and collapsing it to
  a single guess loses the useful part".

### CLS-098 · Ambiguity is judged only within a stage
- **Area:** `semantic.py::_is_ambiguous`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a CHECKSUM fit at 0.99 and a PATTERN fit at 0.99
- **Steps:** classify
- **Expected:** no ambiguity conflict
- **Why:** "a check digit beating a pattern is not a close call, however
  similar the hit rates, because one of them is evidence".

### CLS-099 · A code-list classification carries the version it resolved against
- **Area:** `semantic.py::_score_codelist`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a currency column, classifier constructed with
  `as_of=date(2023,6,1)`
- **Steps:** classify; read the rationale
- **Expected:** it names the effective date `2023-01-01` and the code count of
  that version
- **Why:** the same replay argument as the code lists themselves: a
  classification whose membership set cannot be reproduced is a suggestion.

### CLS-100 · A two-value code list is nearly meaningless evidence
- **Area:** `semantic.py::_score_codelist`, `_space`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a column of `BUY`/`SELL`; and a column of a single repeated
  value
- **Steps:** classify both
- **Expected:** low confidence on the first; exactly 0.5 on the second
  (`distinct > 1` is False)
- **Why:** "membership of a two-value list is nearly meaningless", and a single
  distinct value carries no evidence at all however many rows there are.

### CLS-101 · The name lexicon speaks only when the content stages do not
- **Area:** `semantic.py::classify`, `_from_name`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column called `isin` holding four values
- **Steps:** classify
- **Expected:** stage `NAME`, `fit` CONTAMINATED, `hit_rate` 0.0, `examined` 0,
  confidence 0.4, and a rationale saying "No value in it confirmed this … so
  this is a suggestion, not a finding"
- **Why:** "a name match cannot be CLEAN: nothing was measured", and
  `is_evidence` must be False at 0.4.

### CLS-102 · The name lexicon prefers the longest hint
- **Area:** `semantic.py::_match_name`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `counterparty_lei`, `currency_code`, `settlement_ccy`,
  `trade_date`, `trade_id`, `security_id`
- **Expected:** `lei`, `iso4217`, `iso4217`, `iso_date`, `uti`, `isin`
- **Why:** the docstring's own examples. `trade_id → uti` and
  `security_id → isin` are surprising and load-bearing: they are what a
  generated control will assert.

### CLS-103 · A name matching no hint returns nothing
- **Area:** `semantic.py::_match_name`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `widget_colour`, `zip`, `description`, `''`
- **Expected:** `None` for all four
- **Why:** the lexicon is "small on purpose: a large lexicon is a large surface
  for confident wrong answers", and a substring match that fired on `zip` for
  the `ip` hint would be exactly that.

### CLS-104 · A name hint naming an unknown type is discarded
- **Area:** `semantic.py::_from_name`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a `NAME_HINTS` entry for a type absent from both registries
- **Steps:** classify a column whose name matches it
- **Expected:** no classification from the name stage
- **Why:** the `known` check exists for this; without it a name stage would
  propose a type nothing can validate and the generated control would refuse at
  compile time.

### CLS-105 · Every `NAME_HINTS` key names a real type
- **Area:** `semantic.py::NAME_HINTS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** every key against `VALIDATORS.names() | CODELISTS.names()`
- **Expected:** all 21 resolve
- **Why:** the same "derive, never restate" rule `concepts.Property` enforces at
  import — and this module does not enforce it at all.

### CLS-106 · `candidates()` returns every content-based fit
- **Area:** `semantic.py::SemanticClassifier.candidates`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a column of valid ISINs
- **Steps:** `candidates(sample)`
- **Expected:** `isin` first, with any other type clearing the floor behind it,
  ranked by stage then hit rate then confidence
- **Why:** the UI offers the alternatives, and a ranking that put a pattern
  above a checksum would offer the weaker answer first.

### CLS-107 · A sensitive type produces a conflict, not a silent classification
- **Area:** `semantic.py::_score_validator`, `SENSITIVE_TYPES`
- **Type:** security
- **Priority:** P1
- **Precondition:** columns of card numbers, IBANs, emails and NPIs
- **Steps:** classify each
- **Expected:** a `SENSITIVE_CONTENT` conflict on all four, saying to confirm
  masking "before any sample of it is retained in evidence or sent to a model"
- **Why:** the conflict is the only thing standing between a discovery of
  misplaced cardholder data and a sample of it in an evidence bundle.

### CLS-108 · A sensitive classification cannot auto-apply
- **Area:** `semantic.py::may_auto_apply`
- **Type:** security
- **Priority:** P1
- **Precondition:** a clean column of valid IBANs at confidence 1.0
- **Steps:** read `may_auto_apply`
- **Expected:** False — the sensitivity conflict blocks it
- **Why:** `may_auto_apply` requires `not self.conflicts`, so this holds only
  because the conflict is attached. Removing the conflict silently enables
  auto-generation over cardholder data.

## The plugin purity gate — `classify/plugins.py`

### CLS-109 · A clean third-party validator is admitted with provenance
- **Area:** `plugins.py::PluginRegistry.admit`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a validator importing only `re` and `prama.core.errors`
- **Steps:** `admit(validator, distribution='acme-validators')`
- **Expected:** a `Provenance` with the module, the distribution and a
  32-character implementation hash
- **Why:** the happy path, and the case that broke when `compile` was banned by
  name — "a gate that refuses the honest case is not a stricter gate, it is a
  broken one".

### CLS-110 · An ordinary `re.compile` is not refused
- **Area:** `plugins.py::FORBIDDEN_DYNAMIC`, `scan_source`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a validator using `re.compile(...)`
- **Steps:** admit it
- **Expected:** admitted
- **Why:** finding H3's lesson. Banning `compile` by name "refused every
  shipped validator"; the builtin and the method are told apart by AST shape,
  and a test pins that the honest case survives.

### CLS-111 · The builtin `compile`, `exec` and `eval` are refused
- **Area:** `plugins.py::FORBIDDEN_DYNAMIC`
- **Type:** security
- **Priority:** P1
- **Precondition:** validators calling each as a bare name
- **Steps:** admit each
- **Expected:** refused, naming the call and "running generated code is
  arbitrary code execution"
- **Why:** the other side of CLS-110; the shape distinction has to reject as
  well as permit.

### CLS-112 · `__import__` is refused
- **Area:** `plugins.py::FORBIDDEN_DYNAMIC`
- **Type:** security
- **Priority:** P1
- **Precondition:** a validator calling `__import__("socket")`
- **Steps:** admit
- **Expected:** refused
- **Why:** finding H3. "Dynamic imports were invisible to a scan keyed on
  `ast.Import`."

### CLS-113 · `importlib.import_module` is refused as an attribute call
- **Area:** `plugins.py::FORBIDDEN_DYNAMIC_ATTRIBUTES`
- **Type:** security
- **Priority:** P1
- **Precondition:** a validator calling `importlib.import_module(name)`
- **Steps:** admit
- **Expected:** refused
- **Why:** the second spelling of the same evasion.

### CLS-114 · A bare `import_module` call evades the gate
- **Area:** `plugins.py::scan_source`
- **Type:** security
- **Priority:** P1
- **Precondition:** a validator doing
  `from importlib import import_module` then `import_module("socket")`
- **Steps:** admit
- **Expected:** refused
- **Why:** the call is an `ast.Name`, and `import_module` is only in
  `FORBIDDEN_DYNAMIC_ATTRIBUTES`, which is consulted for `ast.Attribute` alone.
  `importlib` itself is not in `FORBIDDEN`. This is the third spelling of the
  evasion H3 closed twice.

### CLS-115 · A clock import is refused under each banned spelling
- **Area:** `plugins.py::FORBIDDEN`, `FORBIDDEN_CALLS`
- **Type:** security
- **Priority:** P1
- **Precondition:** validators using `import time; time.gmtime()`,
  `datetime.now()`, `datetime.utcnow()`, `time.monotonic()`,
  `time.perf_counter()`, `time.time_ns()`, `date.today()`
- **Steps:** admit each
- **Expected:** all refused, naming "reading the clock makes a control
  unreplayable"
- **Why:** finding H3 exactly — `time` was absent from the ban list for four
  releases while two design documents recorded the guarantee as built.

### CLS-116 · `datetime` itself is not banned
- **Area:** `plugins.py::FORBIDDEN_CALLS` docstring
- **Type:** regression
- **Priority:** P1
- **Precondition:** a validator doing `datetime.strptime(value, "%Y-%m-%d")`
- **Steps:** admit
- **Expected:** admitted
- **Why:** "a date-format validator legitimately parses one, and refusing the
  module would refuse the validator. What is banned is asking it what time it
  is."

### CLS-117 · A clock call spelled through a different name is still refused
- **Area:** `plugins.py::scan_source`
- **Type:** security
- **Priority:** P2
- **Precondition:** `from time import time as ticks` then `ticks()`
- **Steps:** admit
- **Expected:** refused
- **Why:** the `FORBIDDEN` module scan catches `from time import ...` via
  `ImportFrom.module`, which is the belt to the call-scan's braces — confirm
  the belt holds when the call name is aliased away.

### CLS-118 · Network, filesystem and randomness are refused
- **Area:** `plugins.py::FORBIDDEN`
- **Type:** security
- **Priority:** P1
- **Precondition:** validators importing `socket`, `urllib.request`,
  `requests`, `httpx`, `subprocess`, `os`, `os.path`, `pathlib`, `random`,
  `secrets`
- **Steps:** admit each
- **Expected:** all refused, each naming the guarantee it trips
- **Why:** "somebody whose plugin is refused needs to know which guarantee they
  tripped, not merely that they tripped one".

### CLS-119 · Gaps in the ban list are established
- **Area:** `plugins.py::FORBIDDEN`
- **Type:** security
- **Priority:** P2
- **Precondition:** validators importing `io`, `shutil`, `tempfile`,
  `asyncio`, `platform`, `getpass`, `ctypes`, `multiprocessing`, `sqlite3`,
  `ssl`, `ftplib`, `smtplib`, `importlib`
- **Steps:** admit each
- **Expected:** a stated position on each — refused, or documented as permitted
- **Why:** the list is an allowlist by omission. `shutil.copy`, `tempfile`,
  `sqlite3.connect` and `ftplib` all reach the filesystem or the network under
  names the scan does not know, and the module's claim is "no clock, no
  network, no filesystem, no model".

### CLS-120 · A model client is refused under CON-007
- **Area:** `plugins.py::FORBIDDEN`, `FORBIDDEN_PRAMA`
- **Type:** security
- **Priority:** P1
- **Precondition:** validators importing `openai`, `anthropic`, `prama.llm`
- **Steps:** admit each
- **Expected:** refused, naming CON-007
- **Why:** "a model output would then determine a pass or fail verdict on
  data", which is the one thing the architecture forbids outright.

### CLS-121 · `prama.core.errors` is not banned by a prefix match
- **Area:** `plugins.py::FORBIDDEN_PRAMA`, `scan_source`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a validator importing `prama.core.errors`
- **Steps:** admit
- **Expected:** admitted
- **Why:** the comment records that matching the root "made `prama.llm` ban
  `prama.core.errors` — which every validator imports, so every validator was
  refused".

### CLS-122 · a package whose name merely starts with a banned one is not caught
- **Area:** `plugins.py::scan_source`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a hypothetical package whose name extends a banned prefix
  without a dot — write it as `prama.llm` + `x`; it does not exist, and must not
  be spelled as though it does, because the documentation guard reads a dotted
  name as a claim that the module is there
- **Steps:** admit a validator importing it
- **Expected:** admitted — the match is `name == banned or
  name.startswith(banned + ".")`
- **Why:** the exact-or-dotted-prefix rule is the fix for CLS-121, and its
  boundary is worth pinning so a later "simplification" to `startswith` does
  not reintroduce the mass refusal.

### CLS-123 · Impurity in a sibling helper is found
- **Area:** `plugins.py::forbidden_imports`, `_local_imports`
- **Type:** security
- **Priority:** P1
- **Precondition:** a validator importing `helpers`, where `helpers.py` sits
  beside it and imports `socket`
- **Steps:** admit
- **Expected:** refused, with the reason saying "(reached through helpers.py)"
- **Why:** finding H3's third evasion, "the simplest of the three": the scan
  read only the validator's own file.

### CLS-124 · Impurity in a sub-package helper is not found
- **Area:** `plugins.py::_local_imports`
- **Type:** security
- **Priority:** P1
- **Precondition:** a validator doing `from .helpers.impure import check`,
  where `helpers/impure.py` imports `socket`
- **Steps:** admit
- **Expected:** refused
- **Why:** `_local_imports` resolves only `root / f"{name}.py"` for the *last*
  dotted segment, so a helper one directory down is invisible. The evasion H3
  closed is still open one package level deeper.

### CLS-125 · The helper walk terminates on a cycle
- **Area:** `plugins.py::forbidden_imports`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two sibling helpers importing each other
- **Steps:** admit
- **Expected:** terminates; the `seen` set prevents revisiting
- **Why:** mutually importing helpers are ordinary, and an unbounded walk here
  hangs the registration path.

### CLS-126 · Only the validator's own distribution is walked
- **Area:** `plugins.py::forbidden_imports`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a validator importing a large third-party package that sits
  elsewhere on the path
- **Steps:** admit; measure
- **Expected:** bounded — the standard library and site-packages are not walked
- **Why:** stated as a deliberate limit: "that is an unbounded scan, and the
  ban list already names the ones that matter at the point the validator
  reaches for them".

### CLS-127 · A file that does not parse scans clean
- **Area:** `plugins.py::scan_source`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a helper beside the validator with a syntax error
- **Steps:** `scan_source(path)` and `admit(validator)`
- **Expected:** the refusal is explicit about having been unable to scan
- **Why:** `scan_source` returns `[]` on `SyntaxError`, and `[]` means
  "nothing forbidden". The docstring says "a scan that silently returns
  'nothing forbidden' for it would be worse than no scan" and then returns
  exactly that; the claim that "the loader refuses it on import instead" is
  true only for a module Python actually imports — a helper the validator does
  not import at run time is scanned and never loaded.

### CLS-128 · Determinism is checked twice on every probe
- **Area:** `plugins.py::check_determinism`, `PROBES`
- **Type:** security
- **Priority:** P1
- **Precondition:** a validator whose answer depends on a module-level counter
- **Steps:** admit
- **Expected:** `ValidationError` "gave two answers for the same input"
- **Why:** "import scanning catches the obvious sources of non-determinism.
  This catches the rest — a cached global, a set iteration order, a validator
  that mutates itself."

### CLS-129 · A validator that raises on an empty string is refused
- **Area:** `plugins.py::check_determinism`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a validator whose `check` indexes `value[0]`
- **Steps:** admit
- **Expected:** refused, with the remedy "raising means the first blank in
  production takes the control down instead of failing the row"
- **Why:** `''` is the first probe, and a blank is the first thing a real
  column contains.

### CLS-130 · The probe set does not include a null
- **Area:** `plugins.py::PROBES`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a validator whose `judge` override raises on `None`
- **Steps:** admit
- **Expected:** refused
- **Why:** `PROBES` is seven strings and no `None`, while `judge(None)` is a
  documented contract (CLS-002) and a plugin may override `judge`. The one
  input every nullable column contains is the one input never probed.

### CLS-131 · The implementation hash is per class, not per module
- **Area:** `plugins.py::implementation_hash`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two validators in one module
- **Steps:** hash both; edit one; hash both again
- **Expected:** different hashes; only the edited one changes
- **Why:** "editing one would change the identity of controls using the other
  nine" — and the hash is folded into the plan id, so it changes what past
  evidence means.

### CLS-132 · A validator whose source cannot be read is refused
- **Area:** `plugins.py::implementation_hash`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a validator class built with `type()` at run time
- **Steps:** admit
- **Expected:** `ValidationError` — "an implementation nobody can hash is one
  whose changes nobody can detect"
- **Why:** hashing it as empty would give every dynamically-built validator the
  same identity, which is worse than refusing.

### CLS-133 · One bad distribution does not take the others down
- **Area:** `plugins.py::load_entry_points`
- **Type:** functional
- **Priority:** P1
- **Precondition:** three advertised validators, the middle one importing
  `socket`
- **Steps:** `load_entry_points(registry)`
- **Expected:** two admitted and registered; one refused with an ERROR log
  naming it
- **Why:** "a refusal nobody sees is a validator silently missing from every
  control that named it".

### CLS-134 · A refused plugin is visible somewhere other than a log
- **Area:** `plugins.py::load_entry_points`
- **Type:** negative
- **Priority:** P2
- **Precondition:** the same three
- **Steps:** after loading, ask the product which validators are available and
  which were refused
- **Expected:** the refusal is discoverable without reading the log
- **Why:** the function catches `Exception` and logs; the return value carries
  only the admitted. A control naming the refused type then fails at check time
  with "no validator named", and nothing connects the two.

### CLS-135 · `prama validators scan` does not exist
- **Area:** `plugins.py::scan_source` docstring
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** run the command the docstring names
- **Expected:** the docstring names a command that exists, or says it does not
- **Why:** finding Q-07. The docstring now records the absence honestly — this
  case exists so the AST guard that reads every `remedy=` literal is extended
  to docstrings, which is where this one hid for four waves.

## Matching — `recon/match.py`

### RCN-001 · Two sides that agree match one-to-one
- **Area:** `match.py::Matcher.match`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 100 rows each, identical keys
- **Steps:** `Matcher(key).match(left, right)`
- **Expected:** 100 pairs, no unmatched, `match_rate == 1.0`,
  `looks_misconfigured` False, `aggregated_pairs == 0`
- **Why:** the baseline every rate below is measured against.

### RCN-002 · A match key with mismatched column counts is refused
- **Area:** `match.py::MatchKey.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `MatchKey(left=('a','b'), right=('a',))`
- **Expected:** `ValueError` — "a match key pairs columns, so the two must
  correspond"
- **Why:** `zip(..., strict=True)` in `render` would raise later and further
  from the cause; the constructor is where a mapping error belongs.

### RCN-003 · A match key with no columns is refused
- **Area:** `match.py::MatchKey.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `MatchKey(left=(), right=())`
- **Expected:** `ValueError` — "matches every row against every other, which is
  not a reconciliation"
- **Why:** an empty key groups everything under `()`, producing one pair
  containing both entire datasets and a comparison of two grand totals.

### RCN-004 · Integer and text keys collide as one key
- **Area:** `match.py::_key_part`
- **Type:** functional
- **Priority:** P1
- **Precondition:** left holds `account_id` as `int`, right as `str`
- **Steps:** match
- **Expected:** they pair
- **Why:** "the most common cause of a zero-match reconciliation: one side
  reads a column as an integer and the other as text, the keys never collide,
  and every row on both sides is reported as unmatched".

### RCN-005 · A round Decimal key does not render in exponent form
- **Area:** `match.py::_key_part`
- **Type:** regression
- **Priority:** P1
- **Precondition:** left holds `Decimal('1000')` and `Decimal('250')`, right
  holds `'1000'` and `'250'`
- **Steps:** match
- **Expected:** both pair
- **Why:** the recorded bug — `normalize()` "strips trailing zeros by raising
  the exponent, so 1000 renders as '1E+3' … the keys then never collide — for
  round numbers only, so a reconciliation matches most of its rows and reports
  the rest as breaks on both sides".

### RCN-006 · A float key with a fractional text counterpart
- **Area:** `match.py::_key_part`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** left `1.0` (float), right `'1.0'` (text)
- **Steps:** match
- **Expected:** a stated answer
- **Why:** the numeric branch normalises `1.0` to `'1'`; the text branch leaves
  `'1.0'` alone. The docstring's claim is "so 1 and '1' are the same key" —
  `1.0` and `'1.0'` are not, and a decimal key column read as text on one side
  is the same defect class the function exists to fix.

### RCN-007 · A boolean key is not the string "True"
- **Area:** `match.py::_key_part`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** left `True`, right `'True'`
- **Steps:** match
- **Expected:** no match, and the behaviour documented
- **Why:** `bool` is excluded from the numeric branch deliberately (it is an
  `int` and would render as `'1'`), so a flag key behaves differently from
  every other type in the function.

### RCN-008 · A null key component is preserved as a distinct key
- **Area:** `match.py::_key_part`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** rows with `None` in a key column on both sides
- **Steps:** match
- **Expected:** they group together under a key containing `None`, and the fact
  is visible — not silently indistinguishable from an empty string
- **Why:** `_key_part(None)` returns `None` while `_key_part('')` returns `''`,
  so a side that loads nulls as blanks matches nothing; and a key column full
  of nulls collapses the whole side into one pair.

### RCN-009 · Whitespace is stripped from a text key
- **Area:** `match.py::_key_part`
- **Type:** functional
- **Priority:** P2
- **Precondition:** left `' REF001 '`, right `'REF001'`
- **Steps:** match
- **Expected:** they pair
- **Why:** a fixed-width extract pads; the strip is the only thing between that
  and a total mismatch. Case is *not* folded — establish that too.

### RCN-010 · A repeated key aggregates rather than pairing arbitrarily
- **Area:** `match.py::Pair.cardinality`, `is_aggregated`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one GL row against twenty sub-ledger rows on one key
- **Steps:** match
- **Expected:** one pair, `MANY_TO_ONE`, `is_aggregated` True
- **Why:** "pairing them row by row produces one match and nineteen phantom
  missing records", which is the ordinary shape of the work.

### RCN-011 · The four cardinalities are distinguished
- **Area:** `match.py::Cardinality`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 1:1, N:1, 1:N and N:M groups
- **Steps:** read `cardinality` on each pair
- **Expected:** `ONE_TO_ONE`, `MANY_TO_ONE`, `ONE_TO_MANY`, `MANY_TO_MANY`;
  `needs_aggregation` False only for the first
- **Why:** N:M is where an aggregate comparison says least, and the break must
  say it was between totals.

### RCN-012 · An aggregated comparison is recorded on the break
- **Area:** `match.py::Pair.is_aggregated` → `classify.Break.aggregated`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a many-to-one pair that breaks
- **Steps:** read the break's description
- **Expected:** "These are totals: the key repeats, so the comparison is
  between sums rather than rows"
- **Why:** "a total matching says less than twenty rows matching and the
  difference matters when somebody is chasing one posting".

### RCN-013 · The match rate is the headline when it is poor
- **Area:** `match.py::MatchReport.looks_misconfigured`, `describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a 62% match rate with four thousand breaks
- **Steps:** `Run.headline()`
- **Expected:** the match rate first, saying to look at it "before the 4,000
  breaks, which are mostly downstream of it"
- **Why:** "a reconciliation reporting four thousand breaks at a 62% match rate
  is not a data quality problem; it is a configuration problem, and saying so
  before anybody opens the break list saves the week they would otherwise spend
  on it".

### RCN-014 · The 0.9 threshold is a boundary, not a gradient
- **Area:** `match.py::POOR_MATCH_RATE`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** match rates of 0.899, 0.900 and 0.901
- **Steps:** read `looks_misconfigured`
- **Expected:** True, False, False
- **Why:** the strict `<` is what makes exactly 90% acceptable, and the
  threshold changes which of two sentences an operator reads first.

### RCN-015 · Two empty sides report a perfect match
- **Area:** `match.py::MatchReport.match_rate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** both sides empty
- **Steps:** match; read `match_rate`, `looks_misconfigured`, and the resulting
  `Run.is_clean`
- **Expected:** a stated empty-scope answer, not a clean reconciliation
- **Why:** `match_rate` returns `1.0` when the total is zero, so
  `looks_misconfigured` is False, `Population` is empty and `is_clean` is True.
  Two feeds that both failed to arrive reconcile perfectly. This is finding
  Q-09 — "the paths that decide *nothing to report* are weaker than the paths
  that decide *something to report*" — in the reconciliation engine.

### RCN-016 · One empty side reports everything as missing
- **Area:** `match.py::Matcher.match`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 500 rows on the left, none on the right
- **Steps:** match; run
- **Expected:** `match_rate == 0.0`, `looks_misconfigured` True, 500 MISSING
  breaks, and the headline naming the match rate rather than the break count
- **Why:** a feed that did not arrive must not read as five hundred data
  defects.

### RCN-017 · The tolerance matcher pairs adjacent days
- **Area:** `match.py::ToleranceMatcher`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one row booked 2026-03-02 on the left and 2026-03-03 on the
  right, window 1
- **Steps:** match
- **Expected:** one pair with `matched_key` set and `matched_by_tolerance` True
- **Why:** without it "every such row appears twice in the breaks — once as
  missing on the left and once as extra on the right — and the break total is
  double the real difference, which is zero".

### RCN-018 · An exact match is never displaced by a near one
- **Area:** `match.py::ToleranceMatcher.match`
- **Type:** functional
- **Priority:** P1
- **Precondition:** left has 03-02 and 03-03; right has 03-02 and 03-03
- **Steps:** match with window 1
- **Expected:** two exact pairs; neither `matched_by_tolerance`
- **Why:** "the near component is matched greedily and only when nothing
  matched it exactly, so a system that *does* agree on the date is never
  quietly paired with the wrong day".

### RCN-019 · The near match prefers the closer offset
- **Area:** `match.py::ToleranceMatcher._nearby`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an unmatched left key on 03-03; unmatched right keys on
  03-02 and 03-05, window 3
- **Steps:** match
- **Expected:** paired with 03-02 — offset 1 before offset 3
- **Why:** the offset loop runs outward from 1, and `+1` is tried before `-1`.
  Which of two equidistant candidates wins is a real decision and is unstated.

### RCN-020 · A greedy near match can strand a better pairing
- **Area:** `match.py::ToleranceMatcher.match`
- **Type:** negative
- **Priority:** P2
- **Precondition:** left keys on 03-02 and 03-03; right key on 03-03 only, with
  the left 03-03 row unmatched exactly for some other key component
- **Steps:** match with window 1
- **Expected:** the pairing chosen is deterministic and the alternative is
  either taken or reported
- **Why:** `remaining_right.pop()` consumes a candidate permanently, and the
  left keys are iterated in `repr`-sorted order — so the first left row takes
  the partner the second would have matched exactly, producing one timing pair
  and one phantom break.

### RCN-021 · A non-date near component is not shifted
- **Area:** `match.py::_shift`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a key whose last component is a reference string, window 1
- **Steps:** match with a `ToleranceMatcher`
- **Expected:** no near matches; the behaviour equals the exact matcher
- **Why:** `_shift` returns `None` for anything that is not a date or an
  ISO date string, so a tolerance matcher on a non-date key silently degrades
  to an exact one — which is safe and is worth being visible, because an
  operator who configured a window expects it to do something.

### RCN-022 · A `datetime` key component is deliberately not shifted
- **Area:** `match.py::_shift`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** key components typed `datetime`
- **Steps:** match with a window
- **Expected:** no near matching, documented
- **Why:** the branch returns `None` explicitly. Shifting a timestamp by a day
  keeps the time-of-day, so two systems stamping different times would still
  not collide — the refusal is right and undocumented.

### RCN-023 · `aggregate` refuses a null amount
- **Area:** `match.py::aggregate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** three rows, one with a null amount
- **Steps:** `aggregate(rows, 'amount')`
- **Expected:** `ValueError` saying treating it as zero "would turn a missing
  value into a value difference of exactly the wrong size"
- **Why:** the rule this package states most often, and `aggregate` is exported
  as public API.

### RCN-024 · `aggregate` and the engine implement the same rule differently
- **Area:** `match.py::aggregate` vs `engine.py::Reconciliation._total`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same rows
- **Steps:** compare the two paths on a side containing a null amount
- **Expected:** one behaviour, or two documented behaviours with the reason
- **Why:** `aggregate` **raises**; `_total` counts the unvalued rows, appends
  an explanatory step and returns `None`. The engine does not call `aggregate`
  at all. Two implementations of one rule is the drift this codebase's
  "derive, never restate" rule exists to prevent, and `_total`'s own comment
  says `match.aggregate` "states the rule this module then failed to follow".

### RCN-025 · `aggregate` on an empty row set
- **Area:** `match.py::aggregate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `aggregate([], 'amount')`
- **Expected:** `Decimal(0)`, and a caller that can tell it from a genuine zero
- **Why:** a side with no rows totalling zero is the empty-scope problem again,
  one level down.

## Normalisation — `recon/normalise.py`

### RCN-026 · An amount is converted at the rate for the business date
- **Area:** `normalise.py::AmountNormaliser.normalise`, `RateSource.get`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a EUR/USD rate for 2026-03-02
- **Steps:** normalise a EUR amount with `when=2026-03-02`, target USD
- **Expected:** converted; the step names the rate, the source and the as-of
  date
- **Why:** "a reconciliation that converts last month's balances at today's
  rate is wrong, and the error is invisible: the breaks look like ordinary
  differences".

### RCN-027 · A missing rate is a refusal, not a fallback
- **Area:** `normalise.py::RateSource.get`, `Unavailable`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a rate source with no EUR/USD rate for the date
- **Steps:** normalise
- **Expected:** `Unavailable` naming both currencies and the date, and the
  message explaining that a bank holiday is a legitimate gap and a vendor
  outage is not
- **Why:** "a missing FX rate cannot become 1.0 (which silently reconciles
  euros against dollars), nor the latest rate (which makes the run
  irreproducible), nor zero".

### RCN-028 · A refusal aborts the whole run, not part of it
- **Area:** `engine.py::Reconciliation.run`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a rate missing for one pair out of a hundred
- **Steps:** run
- **Expected:** `Run.completed` False, `refusal` set, `population` empty, and
  `rates_used` carrying what was resolved before the failure
- **Why:** "a reconciliation missing some of its rows is not a smaller
  reconciliation, it is a wrong one, and the total it reports would be quoted".

### RCN-029 · Carry-forward is off by default and recorded when on
- **Area:** `normalise.py::RateSource._lookup`, `_describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a rate present only for 2026-02-27; business date
  2026-03-02
- **Steps:** with `carry_forward_days=0`, then `=3`
- **Expected:** refusal; then a rate whose source says "carried forward from
  2026-02-27" and whose `as_of` is the earlier date
- **Why:** "filling them is a business decision … making that choice inside a
  converter would bury it, so the choice is a constructor argument and the
  answer is recorded either way".

### RCN-030 · An inverted rate says it was derived
- **Area:** `normalise.py::RateSource.get`
- **Type:** functional
- **Priority:** P1
- **Precondition:** only a USD/EUR rate
- **Steps:** ask for EUR/USD
- **Expected:** `1/rate`, with the source saying "inverted from USD/EUR"
- **Why:** "a break traced back to a rate should show whether the number was
  quoted or derived".

### RCN-031 · A zero rate is refused rather than inverted
- **Area:** `normalise.py::RateSource.get`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a USD/EUR rate of zero
- **Steps:** ask for EUR/USD
- **Expected:** `Unavailable` — not `ZeroDivisionError`
- **Why:** a zero rate in a vendor file is a real thing, and a division error
  reaching a run is an exception where a refusal belongs.

### RCN-032 · An identity conversion needs no rate
- **Area:** `normalise.py::RateSource.get`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty rate source
- **Steps:** `get('EUR','EUR', when)`
- **Expected:** rate 1, source "identity"
- **Why:** a same-currency reconciliation must not require a rate table, and
  the identity source is what tells a reader no conversion happened.

### RCN-033 · Currency codes are case-folded on lookup and on the row
- **Area:** `normalise.py::RateSource.add`, `get`, `AmountNormaliser`
- **Type:** functional
- **Priority:** P2
- **Precondition:** rates added as `('eur','usd',...)`; rows carrying `'eur'`
- **Steps:** normalise
- **Expected:** resolved
- **Why:** a warehouse that lower-cases currency codes must not make every rate
  lookup a refusal.

### RCN-034 · A per-row currency with no target currency converts to nothing
- **Area:** `normalise.py::AmountNormaliser.normalise`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `AmountSpec(currency_column='ccy')`, `target_currency=''`
- **Steps:** normalise a EUR row
- **Expected:** a refusal naming the missing target currency, raised where the
  configuration is made rather than mid-scan
- **Why:** `if currency and currency != self._target` is True when the target
  is `''`, so the normaliser asks for a `EUR/` rate and fails with a message
  about a missing rate — which sends the reader to the rate table when the
  fault is the definition. See PCK-206: every template binding takes this path.

### RCN-035 · An unparseable amount is refused with the value quoted
- **Area:** `normalise.py::AmountNormaliser.normalise`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a row holding `'1,234.56'` in the amount column
- **Steps:** normalise
- **Expected:** `ValidationError` quoting the value and saying to correct the
  source "rather than letting it become a break of unknown size"
- **Why:** thousands separators are what a CSV export produces, and
  `Decimal('1,234.56')` raises.

### RCN-036 · A null amount is None, not an error and not zero
- **Area:** `normalise.py::AmountNormaliser.normalise`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a row with no amount
- **Steps:** normalise
- **Expected:** `Normalised(value=None)` with no steps
- **Why:** the engine counts these separately and refuses to total the side;
  raising here would make a missing amount an outage.

### RCN-037 · Sign inversion, scale, conversion and rounding apply in order
- **Area:** `normalise.py::AmountNormaliser.normalise`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `AmountSpec(invert_sign=True, scale=Decimal(1000),
  currency='EUR', scale_places=2)`, target USD
- **Steps:** normalise `1.2345`
- **Expected:** four steps in that order, each naming what it did, and the
  final value equal to applying them in that order
- **Why:** rounding after conversion and rounding before it differ by up to a
  minor unit on every row, and "the first question about any break is 'is this
  real, or did we translate it wrong?'".

### RCN-038 · Rounding is half-to-even
- **Area:** `normalise.py::AmountNormaliser.normalise`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `scale_places=2`
- **Steps:** normalise `1.005`, `1.015`, `1.025`
- **Expected:** `1.00`, `1.02`, `1.02`
- **Why:** "rounding half up instead introduces a systematic upward bias that
  shows as a small persistent break on every large population".

### RCN-039 · A scale of 1000 means the ledger is in thousands
- **Area:** `normalise.py::AmountSpec.scale`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a side stated in thousands
- **Steps:** normalise `12.5`
- **Expected:** `12500`, with a step saying "scaled by 1000 to units"
- **Why:** a factor of a thousand between two sides is a break of 99.9% of
  value that reads as a total mismatch.

### RCN-040 · `scale_places=0` is not the same as `None`
- **Area:** `normalise.py::AmountSpec.scale_places`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the same amount under `None` and under `0`
- **Steps:** normalise `1.4` and `1.5`
- **Expected:** `None` compares at full precision; `0` quantises to `1` and `2`
- **Why:** `if spec.scale_places is not None` is the guard, and a truthiness
  test there would silently drop integer rounding.

### RCN-041 · An unmapped code is a refusal, not a pass-through
- **Area:** `normalise.py::CodeNormaliser.normalise`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a mapping without `'XX'`
- **Steps:** `normalise('XX')`
- **Expected:** `Unavailable` saying an unmapped code passed through "would
  appear in the break population as a missing record, and the afternoon spent
  investigating it would be spent on the wrong thing"
- **Why:** the whole reason the class exists.

### RCN-042 · `covers` finds the gap before the run
- **Area:** `normalise.py::CodeNormaliser.covers`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a mapping and a set of observed codes
- **Steps:** `covers({'GB','XX','ZZ'})`
- **Expected:** `('XX','ZZ')`, sorted
- **Why:** "a reconciliation that fails halfway through on an unmapped code has
  already spent the scan".

### RCN-043 · A mapped code that equals its input records no step
- **Area:** `normalise.py::CodeNormaliser.normalise`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a mapping of `'GB' → 'GB'`
- **Steps:** normalise `'GB'` and `'gb'`
- **Expected:** the first records no step; the second's behaviour is stated
- **Why:** the guard is `mapped == str(value)` before the upper-casing, so
  `'gb'` records a "gb mapped to GB" step while `'GB'` records none — the same
  value producing two different audit trails.

### RCN-044 · A null code passes through as null
- **Area:** `normalise.py::CodeNormaliser.normalise`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `normalise(None)`
- **Expected:** `Normalised(value=None)`, no refusal
- **Why:** a null is a completeness finding, not a mapping gap, and refusing it
  here would abort a run over a nullable column.

## Classification — `recon/classify.py`

### RCN-045 · Two sides within tolerance are not a break
- **Area:** `classify.py::Classifier.classify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=0.01, relative=0.0001)`
- **Steps:** classify `100.00` against `100.005`
- **Expected:** `None`
- **Why:** the baseline; every kind below is a difference that survived this.

### RCN-046 · Both bounds must be breached
- **Area:** `classify.py::_within_tolerance` → `Tolerance.permits`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=0.01, relative=0.0001)`
- **Steps:** a difference of 0.02 on a value of 1,000,000 (inside the relative
  bound, outside the absolute)
- **Expected:** no break
- **Why:** "a penny or a basis point, whichever is larger" — the convention
  finance already uses, and inverting it makes every large value break.

### RCN-047 · A sign-convention break is named as one
- **Area:** `classify.py::Classifier.classify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** left `1000`, right `-1000`
- **Steps:** classify
- **Expected:** `SIGN`, with the reason "the break is twice the value and none
  of it is real"; `is_configuration` True
- **Why:** "the single most common configuration mistake and the easiest to
  spot … a break of exactly twice the value is not a data problem, and
  reporting it as one sends somebody to the wrong system".

### RCN-048 · A duplicate is an exact multiple
- **Area:** `classify.py::_exact_multiple`
- **Type:** functional
- **Priority:** P1
- **Precondition:** left `1000`, right `2000`; then `3000`; then `4000`
- **Steps:** classify each
- **Expected:** `DUPLICATE` naming 2x, 3x and 4x, and the larger side named
- **Why:** "a break that is exactly double is a posting counted twice rather
  than an amount that is wrong".

### RCN-049 · A 5x difference is not a duplicate
- **Area:** `classify.py::_exact_multiple`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** left `1000`, right `5000`
- **Steps:** classify
- **Expected:** `GENUINE`
- **Why:** the candidate list stops at 4 on purpose — beyond that the multiple
  is coincidence, and a five-fold difference is a real disagreement.

### RCN-050 · A near-multiple within the tolerance is still a duplicate
- **Area:** `classify.py::MULTIPLE_TOLERANCE`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** left `1000.00`, right `2000.05`
- **Steps:** classify
- **Expected:** `DUPLICATE` — "loose enough to survive a rounding difference on
  top of a duplication"
- **Why:** and `2000.5` must not be, or an ordinary break is mistaken for one.

### RCN-051 · A zero on either side is not a multiple
- **Area:** `classify.py::_exact_multiple`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** left `0`, right `1000`
- **Steps:** classify
- **Expected:** not `DUPLICATE`; no `DivisionByZero`
- **Why:** the guard is explicit, and a zero side is the ordinary shape of a
  reversed posting.

### RCN-052 · A rounding break is smaller than the stated precision
- **Area:** `classify.py::_is_rounding`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `rounding_places=2`, a difference of `0.01`
- **Steps:** classify with a tolerance that does not absorb it
- **Expected:** `ROUNDING`, naming the two decimal places
- **Why:** the cheapest remaining explanation before genuine, and one nobody
  should work.

### RCN-053 · Rounding is not claimed when no precision was declared
- **Area:** `classify.py::_is_rounding`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `rounding_places=None`
- **Steps:** classify a one-penny difference
- **Expected:** `GENUINE`
- **Why:** claiming rounding with no declared precision is inventing an
  explanation, which is the one thing the classifier must not do.

### RCN-054 · Timing is taken from the matcher, not inferred
- **Area:** `classify.py::Classifier.classify`, `timing=`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a pair found only by the tolerance matcher
- **Steps:** classify
- **Expected:** `TIMING`, `clears_itself` True, with the reason naming the
  adjacent day
- **Why:** "the matcher knows and the comparison cannot: a pair found only by
  looking at the adjacent day is the same item recognised on two dates".

### RCN-055 · Timing is checked before sign and duplicate
- **Area:** `classify.py::Classifier.classify` ordering
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a tolerance-matched pair whose two sides also sum to zero
- **Steps:** classify
- **Expected:** `TIMING` — the order in the method is the specification
- **Why:** the cheapest *sufficient* reason is the stated rule, and the
  ordering decides which of two explanations a queue shows. A reversal booked
  the next day would otherwise be reported as a configuration fault.

### RCN-056 · Only timing clears itself
- **Area:** `classify.py::BreakKind.clears_itself`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** every kind
- **Expected:** True for `TIMING` alone
- **Why:** "a hundred-million-euro timing break is less urgent than a
  thousand-euro genuine one", which is what stops a queue being triaged by
  size.

### RCN-057 · Sign, duplicate and FX are configuration faults
- **Area:** `classify.py::BreakKind.is_configuration`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** every kind
- **Expected:** True for exactly those three
- **Why:** "routing them to a data steward wastes the steward's day and leaves
  the setup wrong".

### RCN-058 · A record on one side only is MISSING or EXTRA
- **Area:** `classify.py::Classifier.classify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a left-only key and a right-only key
- **Steps:** classify each
- **Expected:** `MISSING` and `EXTRA`, each saying "until it is known whether
  it is late or absent, its whole value is the break"
- **Why:** the whole value being the break is what makes an unmatched row look
  like a hundred-percent difference, and why RCN-013 exists.

### RCN-059 · A row present with no amount is GENUINE, not MISSING
- **Area:** `classify.py::Classifier.classify`, the `unvalued` branch
- **Type:** functional
- **Priority:** P1
- **Precondition:** a pair whose left side has three rows carrying no amount
- **Steps:** classify
- **Expected:** `GENUINE`, with the reason naming the unvalued rows — not "the
  record is not on the left"
- **Why:** "saying 'not on the left' about a row that is plainly on the left
  sends somebody to look for a missing feed instead of at the posting in front
  of them".

### RCN-060 · The unvalued branch is detected by a substring
- **Area:** `classify.py::Classifier.classify`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a normalisation step whose text happens to contain
  "carry no"
- **Steps:** classify a genuinely missing record
- **Expected:** `MISSING`
- **Why:** the branch is `next((s for s in normalisation if "carry no" in s),
  "")` — a classification keyed on a prose fragment produced elsewhere. Editing
  `_total`'s message silently changes the break kind, which is the definition
  of a restated rule.

### RCN-061 · A population sharing one ratio is reattributed to FX
- **Area:** `classify.py::attribute_to_fx`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 25 genuine breaks whose right/left ratio is 1.0873 ± 0.05%
- **Steps:** `attribute_to_fx(breaks)`
- **Expected:** all 25 become `FX`, with the reason naming the ratio and the
  count
- **Why:** "one break explained by an exchange rate is arithmetic and could be
  anything. Four hundred breaks whose right side is 1.0873 times the left is a
  missing conversion."

### RCN-062 · Fewer than twenty candidates is left alone
- **Area:** `classify.py::FX_POPULATION`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 19 and 20 breaks at the same ratio
- **Steps:** `attribute_to_fx`
- **Expected:** unchanged at 19; reattributed at 20
- **Why:** the threshold is the whole claim, and at 19 the module says the
  evidence does not exist.

### RCN-063 · A ratio near 1 is not an exchange rate
- **Area:** `classify.py::attribute_to_fx`
- **Type:** negative
- **Priority:** P1
- **Precondition:** 25 breaks whose ratio is 1.0005
- **Steps:** `attribute_to_fx`
- **Expected:** unchanged
- **Why:** a population of small proportional differences is a rounding or a
  fee, and calling it a rate sends a team to look at a rate table.

### RCN-064 · A split population is not reattributed
- **Area:** `classify.py::attribute_to_fx`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 25 breaks, 12 at one ratio and 13 at another
- **Steps:** `attribute_to_fx`
- **Expected:** unchanged — the `close` set must be more than half
- **Why:** two rates in one population is two findings, and reattributing the
  larger half hides the smaller.

### RCN-065 · Only genuine breaks are candidates for FX
- **Area:** `classify.py::attribute_to_fx`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 25 breaks already classified `SIGN`, at a shared ratio
- **Steps:** `attribute_to_fx`
- **Expected:** unchanged
- **Why:** the cheapest sufficient explanation is already attached; overwriting
  it would re-route a configuration fault to a rate investigation.

### RCN-066 · Breaks are reattributed by identity, not by value
- **Area:** `classify.py::attribute_to_fx`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two breaks with identical field values at the shared ratio,
  plus twenty-three others
- **Steps:** `attribute_to_fx`
- **Expected:** both reattributed
- **Why:** the `explained` set holds `id(item)`, so two equal frozen dataclasses
  are still distinct objects — but a caller that deduplicated the list upstream
  would collapse them, and `id()` reuse after garbage collection is a real
  hazard in a long-lived worker.

### RCN-067 · A population summary leads with what is not genuine
- **Area:** `classify.py::Population.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 400 breaks of which 390 are timing
- **Steps:** `describe()`
- **Expected:** the total, the breakdown by cause, the genuine count and total,
  and the configuration-fault count with the instruction to fix them first
- **Why:** "four thousand breaks of which three thousand nine hundred are
  timing differences that clear tomorrow is a completely different situation
  from four thousand genuine ones".

### RCN-068 · The summary's pluralisation is inverted for configuration faults
- **Area:** `classify.py::Population.describe`
- **Type:** negative
- **Priority:** P3
- **Precondition:** one configuration fault, then two
- **Steps:** `describe()`
- **Expected:** "1 points at" → "1 point at"; "2 point at" → "2 point at"
- **Why:** the expression is `'points' if len(faults) == 1 else 'point'` — the
  two arms are the wrong way round. It is cosmetic, and it is on the sentence
  an operator reads first every morning.

### RCN-069 · `needs_a_person` is worst first by value
- **Area:** `classify.py::Population.needs_a_person`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a mixed population
- **Steps:** read the property
- **Expected:** timing excluded; the rest sorted by descending magnitude
- **Why:** a queue ordered by anything else is one somebody works from the
  bottom.

### RCN-070 · An empty population says the two sides agree
- **Area:** `classify.py::Population.describe`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** no breaks
- **Steps:** `describe()`; `Run.is_clean`
- **Expected:** "the two sides agree" — and `Run.headline` must not say it when
  the match rate was poor or the run refused
- **Why:** `is_clean` is `completed and not genuine`, so a run with four
  hundred MISSING breaks and no genuine ones is "clean". Establish what a
  consumer of that flag sees.

### RCN-071 · `Break.difference` when one side is absent
- **Area:** `classify.py::Break.difference`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a MISSING break with `left=1000, right=None`
- **Steps:** read `difference` and `magnitude`
- **Expected:** `-1000` and `1000`
- **Why:** `total_difference` sums these, so the sign convention decides
  whether a missing record and an extra one of the same value cancel in the
  population total — which they must not.

### RCN-072 · `Break.describe` on a null side does not crash on formatting
- **Area:** `classify.py::Break.describe`
- **Type:** negative
- **Priority:** P2
- **Precondition:** MISSING and EXTRA breaks
- **Steps:** `describe()` on each
- **Expected:** "1,000.00 on the left and nothing on the right" and its mirror
- **Why:** `f"{None:,.2f}"` raises, and the branch that avoids it is the only
  thing between a break list and a `TypeError` in a report renderer.

## Reconciliation workflow — `recon/workflow.py`

### RCN-073 · Ageing runs from first sighting, not from today
- **Area:** `workflow.py::Item.age`, `seen_again`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a break observed on 40 consecutive days
- **Steps:** `age(day_40)`
- **Expected:** 39 or 40 days — not 0
- **Why:** "a system that stamps each detection with today's date reports it as
  new every morning … everything is one day old", which is what makes a queue
  impossible to prioritise.

### RCN-074 · A break that stops appearing is cleared, not deleted
- **Area:** `workflow.py::BreakQueue.observe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a break present on day 1 and absent on day 2
- **Steps:** observe both days; read the item
- **Expected:** state `CLEARED`, still in the queue, `last_seen` day 2
- **Why:** "'we had four hundred breaks and they cleared' and 'we had four
  hundred breaks' are the same sentence in a system that forgets, and only one
  of them is reassuring".

### RCN-075 · Clearing is inferred, not announced
- **Area:** `workflow.py::BreakQueue.observe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a run reporting a subset of the previous run's breaks
- **Steps:** observe
- **Expected:** everything open and absent is cleared in the same pass
- **Why:** "no reconciliation tells you a break has gone — it simply stops
  reporting it, and a queue that waits to be told never closes anything".

### RCN-076 · A cleared break that returns keeps its original age
- **Area:** `workflow.py::Item.seen_again`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a break on day 1, absent days 2–90, present on day 91
- **Steps:** observe; read state and `age(day_91)`
- **Expected:** a stated answer
- **Why:** `seen_again` reopens it as `OPEN` while leaving `first_seen` at day
  1, so a break that cleared and recurred three months later enters the `90+`
  ageing bucket on its first day back. "The first-seen date does not move,
  which is the point" is right for a *continuously* re-detected break and
  wrong for a recurrence.

### RCN-077 · An accepted break that stops appearing stays accepted forever
- **Area:** `workflow.py::BreakQueue.observe`, `outstanding`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a break accepted with a reason, then absent from every
  subsequent run
- **Steps:** observe ten more runs; read `outstanding()`
- **Expected:** it either clears or is distinguishable from a live accepted
  item
- **Why:** the clearing loop is guarded by `item.state.is_open`, and `ACCEPTED`
  is not open — so an accepted item is never cleared and appears on every
  certificate from then on, inflating `accepted_total` with a break that has
  gone away.

### RCN-078 · The five states and `is_open`
- **Area:** `workflow.py::State.is_open`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** every state
- **Expected:** open for `OPEN`, `ASSIGNED`, `EXPLAINED`; not for `CLEARED` or
  `ACCEPTED`
- **Why:** `open_items`, `stale`, `ageing` and `by_owner` all key on it, and an
  accepted item counted as open would appear in the stale escalation.

### RCN-079 · Assignment, explanation and acceptance leave an audit trail
- **Area:** `workflow.py::Item.assigned_to`, `explained`, `accepted`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an open item
- **Steps:** assign, explain, accept in turn
- **Expected:** three comments, each with its author and timestamp; the state
  advancing each time; the item still immutable (each returns a new `Item`)
- **Why:** the certificate quotes the acceptance reason a year later, and a
  mutable item would let it be rewritten.

### RCN-080 · Accepting without a reason is refused
- **Area:** `workflow.py::Item.accepted`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an open item
- **Steps:** `accepted(by='alice', at=..., reason='   ')`
- **Expected:** `ValueError` — "a carried break with no explanation is
  indistinguishable from one nobody looked at, and the certificate has to tell
  them apart"
- **Why:** the certificate's whole value is that the residue is explained.

### RCN-081 · Stale is age, not amount
- **Area:** `workflow.py::Item.is_stale`, `BreakQueue.stale`
- **Type:** functional
- **Priority:** P1
- **Precondition:** items aged 29, 30 and 31 days, all small
- **Steps:** `stale(as_of)`
- **Expected:** the 30- and 31-day items, oldest first
- **Why:** "a small break nobody has explained in a month is a process that is
  not working, and the amount is beside the point" — and `>=` makes 30 the
  boundary.

### RCN-082 · A cleared or accepted item is never stale
- **Area:** `workflow.py::Item.is_stale`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a 90-day-old accepted item
- **Steps:** `stale(as_of)`
- **Expected:** absent
- **Why:** an accepted break is expected to persist; escalating it every day
  would train somebody to ignore the escalation.

### RCN-083 · The ageing buckets partition the open items
- **Area:** `workflow.py::BreakQueue.ageing`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** items aged 0, 7, 8, 30, 31, 90, 91
- **Steps:** `ageing(as_of)`
- **Expected:** 2, 2, 2, 1 across the four buckets; the counts sum to
  `len(open_items())`
- **Why:** a bucket boundary that double-counts or drops an item makes the
  number a manager reads wrong by exactly the boundary cases.

### RCN-084 · Unassigned items are counted as unassigned
- **Area:** `workflow.py::BreakQueue.by_owner`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a queue with three unowned items
- **Steps:** `by_owner()`
- **Expected:** an `"unassigned"` entry of 3
- **Why:** a by-owner report that silently omitted them would show a queue
  everybody is on top of.

### RCN-085 · A certificate states the residue, not that everything was fine
- **Area:** `workflow.py::certify`, `Certificate.render`
- **Type:** functional
- **Priority:** P1
- **Precondition:** four outstanding items, two accepted
- **Steps:** certify; render
- **Expected:** the outstanding count and total, the accepted total and the
  unexplained total as separate figures, each item listed with its state and
  either its acceptance reason or its age
- **Why:** "a certificate that can only be issued clean is a certificate nobody
  issues".


### RCN-086 · A clean certificate says nothing was outstanding
- **Area:** `workflow.py::Certificate.is_clean`, `render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty queue, and a queue whose every item cleared
- **Steps:** certify both
- **Expected:** "Nothing was outstanding at period end." in both — and the
  match rate still stated
- **Why:** an empty queue and a queue that worked look identical here, and the
  match rate is the only thing that distinguishes "nothing broke" from "nothing
  was compared".

### RCN-087 · The certificate hash covers the numbers and excludes the signature
- **Area:** `workflow.py::Certificate.content_hash`
- **Type:** security
- **Priority:** P1
- **Precondition:** a certificate
- **Steps:** hash it; change `signed_by`; hash again; change
  `unexplained_total`; hash again
- **Expected:** unchanged after the first edit, changed after the second
- **Why:** "a certificate whose numbers were edited after signing does not
  verify" — and finding T11 is the precedent for a hash computed over whatever
  the object currently holds verifying against itself.

### RCN-088 · The hash is stable across process runs and dict ordering
- **Area:** `workflow.py::Certificate.content_hash` · `core.pjson.canonical`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same certificate built twice with items added in
  different orders
- **Steps:** compare hashes
- **Expected:** identical — `certify` sorts the outstanding items
- **Why:** a hash that depends on insertion order cannot be verified a year
  later by anybody who rebuilt the queue.

### RCN-089 · Accepted and unexplained totals sum to the outstanding total
- **Area:** `workflow.py::certify`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a mixed queue including negative differences
- **Steps:** certify
- **Expected:** `accepted_total + unexplained_total == outstanding_total`
  exactly, in `Decimal`
- **Why:** "a single number would let an accepted residue and an unexplained
  one look identical", and the three are printed side by side.

### RCN-090 · Outstanding items are ordered by magnitude then key
- **Area:** `workflow.py::certify`
- **Type:** functional
- **Priority:** P2
- **Precondition:** items of equal magnitude
- **Steps:** certify twice
- **Expected:** the same order both times
- **Why:** the certificate is hashed; a non-deterministic order would make two
  identical period-ends produce two different hashes.

### RCN-091 · A certificate can be signed by nobody
- **Area:** `workflow.py::certify`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `certify(..., signed_by='')`
- **Expected:** a refusal
- **Why:** the class docstring calls it "a document somebody signs at month end
  and an auditor can read a year later". Nothing checks that a signer was
  named, and `signed_by` is outside the content hash — so an unsigned
  certificate verifies exactly as well as a signed one.

## The engine and n-way — `recon/engine.py`, `recon/nway.py`

### RCN-092 · A run records every rate it used
- **Area:** `engine.py::Reconciliation.run`, `Run.rates_used`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a multi-currency reconciliation
- **Steps:** run; read `rates_used`
- **Expected:** every conversion's detail, with the source and the as-of date
- **Why:** "the record that makes the run reproducible, and the first thing to
  look at when a cleared break reappears".

### RCN-093 · Two runs of one definition over one dataset agree
- **Area:** `engine.py::Reconciliation.run`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same inputs and business date
- **Steps:** run twice; compare `to_dict()`
- **Expected:** identical, including break order
- **Why:** "a run is reproducible or it is not evidence", and break ordering
  falls out of `sorted(..., key=repr)` in the matcher — which must be pinned,
  not assumed.

### RCN-094 · Normalise-then-sum, not sum-then-normalise
- **Area:** `engine.py::Reconciliation._total`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a many-to-one pair whose left rows are in EUR and GBP
- **Steps:** run
- **Expected:** each row converted before the sum
- **Why:** "summing first and converting the total is cheaper and wrong
  whenever the rows are in more than one currency — it converts a meaningless
  mixed-currency sum at one rate and produces a total that looks plausible".

### RCN-095 · A side with an unvalued row has no total
- **Area:** `engine.py::Reconciliation._total`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a pair whose right side has one row with no amount
- **Steps:** run
- **Expected:** the right total is `None`, a step names the count, and the
  break is `GENUINE` with that reason
- **Why:** "dropping the row makes the total wrong by exactly the missing
  amount — so the side reconciles, or breaks by a number that looks like a
  value difference, when the finding is that a posting has no amount at all".

### RCN-096 · The target currency defaults to the right side's
- **Area:** `engine.py::Reconciliation.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `Definition(target_currency='')` with
  `right.spec.currency='USD'`
- **Steps:** run over a EUR left side
- **Expected:** converted to USD, and the choice visible on the run
- **Why:** an implicit target is a decision nobody made; it must at least be
  recorded on the result so a break can be traced to it.

### RCN-097 · The matcher is chosen by `date_window`
- **Area:** `engine.py::Reconciliation.run`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `date_window=0` and `date_window=1`
- **Steps:** run both over the same adjacent-day data
- **Expected:** a plain `Matcher` and two breaks in the first; a
  `ToleranceMatcher` and one timing pair in the second
- **Why:** zero is falsy, so the branch is `if definition.date_window` — which
  is correct and makes zero and unset the same thing.

### RCN-098 · N-way names the odd side out
- **Area:** `nway.py::reconcile_n_way`, `_odd_one_out`
- **Type:** functional
- **Priority:** P1
- **Precondition:** three sides; the middle disagrees on one key
- **Steps:** reconcile
- **Expected:** one `Disagreement` with `odd_side` naming the middle and
  `consensus` the agreed value
- **Why:** "run as three pairwise reconciliations that is three break
  populations, and a record missing from the middle system appears in two of
  them — so the same problem is counted twice".

### RCN-099 · Three sides all disagreeing names nobody
- **Area:** `nway.py::_odd_one_out`, `Disagreement.all_disagree`
- **Type:** functional
- **Priority:** P1
- **Precondition:** three different totals on one key
- **Steps:** reconcile
- **Expected:** `odd_side` empty, `consensus` None, `all_disagree` True, and
  the description saying "which is not one system being wrong and needs a
  person"
- **Why:** "empty when they all disagree, which is a different and worse
  situation".

### RCN-100 · A two-against-two tie names nobody
- **Area:** `nway.py::_odd_one_out`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** four sides, two at 100 and two at 200
- **Steps:** reconcile
- **Expected:** `all_disagree`, no odd side
- **Why:** "with four sides two agreeing is a tie that names nothing.
  Reporting a tie as an odd-one-out would send somebody to a system chosen by
  iteration order."

### RCN-101 · Two sides passed to the n-way engine
- **Area:** `nway.py::reconcile_n_way`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** exactly two sides that disagree
- **Steps:** reconcile
- **Expected:** a refusal, or a disagreement with no odd side and the reason
  saying two sides cannot have a majority
- **Why:** the docstring says "three or more" and there is no guard.
  `_odd_one_out` skips every candidate because `len(others) < 2`, so the result
  is `all_disagree` — technically true and unhelpful, and a caller who reduced
  to two sides gets no warning.

### RCN-102 · One side passed to the n-way engine
- **Area:** `nway.py::reconcile_n_way`, `_all_agree`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a single side
- **Steps:** reconcile
- **Expected:** a refusal
- **Why:** `_all_agree` over one position is vacuously True, so every key
  "agrees" and the summary reads "all 1 sides agree across 4,000 keys" — a
  reconciliation that could not have failed.

### RCN-103 · A key missing from one side is reported as missing
- **Area:** `nway.py::Disagreement.missing_from`, `describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a key absent from the second of three sides
- **Steps:** reconcile
- **Expected:** `missing_from` naming it; the description saying where it is
  present and where it is not
- **Why:** this is the case pairwise running counts twice.

### RCN-104 · A key both missing from one side and disputed between the others
- **Area:** `nway.py::reconcile_n_way`
- **Type:** negative
- **Priority:** P2
- **Precondition:** three sides; one missing, two with different totals
- **Steps:** reconcile
- **Expected:** both facts reported
- **Why:** the `continue` after the missing branch means the value disagreement
  between the remaining two is never computed, and `describe()` reports only
  the absence. Two findings become one.

### RCN-105 · `by_odd_side` identifies a broken system
- **Area:** `nway.py::NWayResult.by_odd_side`, `describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one side odd on 400 of 500 keys
- **Steps:** reconcile; `describe()`
- **Expected:** that side named with its count, and the sentence saying it
  "points at that system rather than at the records"
- **Why:** "the number that identifies a broken system rather than a broken
  record … and no pairwise view makes it visible".

### RCN-106 · A tie in `by_odd_side` is broken deterministically
- **Area:** `nway.py::NWayResult.describe`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** two sides each odd on 200 keys
- **Steps:** `describe()` twice in separate processes
- **Expected:** the same side named both times, or both named
- **Why:** `max(odd, key=...)` returns the first maximum in dict order, which
  follows the input mapping — so the sentence blaming a system is decided by
  how the caller built the dict.

### RCN-107 · Roll-forward catches an unexplained restatement
- **Area:** `nway.py::check_roll_forward`
- **Type:** functional
- **Priority:** P1
- **Precondition:** opening 1000, movements 50, closing 1100
- **Steps:** `check_roll_forward([entry], tolerance)`
- **Expected:** one `GENUINE` break, with the reason saying both balances may
  be correct and what is missing is a movement
- **Why:** "the failure this catches is invisible to any single-period control
  … something was restated and nobody said so".

### RCN-108 · A roll-forward that balances produces nothing
- **Area:** `nway.py::check_roll_forward`
- **Type:** functional
- **Priority:** P1
- **Precondition:** opening 1000, movements 100, closing 1100
- **Steps:** check
- **Expected:** no breaks
- **Why:** the counterfactual; a check that fires on a balancing roll-forward
  is one that gets switched off on day one.

### RCN-109 · A zero expected balance uses a magnitude of one
- **Area:** `nway.py::check_roll_forward`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** opening -50, movements 50, closing 5
- **Steps:** check with a relative-only tolerance
- **Expected:** a break, and the relative bound applied against something
  meaningful
- **Why:** `float(entry.expected or 1)` substitutes 1 when the expected balance
  is zero, so a relative tolerance of 0.1% becomes a tolerance of 0.001 — a
  silent switch to an absolute bound nobody configured.

### RCN-110 · `opening_from` carries yesterday's close
- **Area:** `nway.py::opening_from`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a restated opening balance in the source
- **Steps:** build a roll-forward from the source's own opening, and from
  `opening_from(previous_closing)`
- **Expected:** the first passes and the second breaks
- **Why:** "a roll-forward built on an opening balance re-read from the source
  rather than carried from the previous close cannot detect a restatement at
  all: the restated opening agrees with the restated closing, and the check
  passes over exactly the thing it exists to catch". The counterfactual is the
  test.

## Data contracts — `contract/`

### CTR-001 · An ODCS contract imports as a declaration
- **Area:** `contract/odcs.py::load`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a v3 contract with one schema and five properties
- **Steps:** `load(contract)`
- **Expected:** a `DatasetDeclaration` with five attributes, the name taken
  from the schema, `purpose` from `description.purpose` and `description` from
  `description.usage`
- **Expected also:** `defaulted` names criticality, grain and rhythm
- **Why:** the base case, and the mapping that a round trip must preserve.

### CTR-002 · What did not come across is listed, not counted
- **Area:** `contract/odcs.py::Imported.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a contract carrying `slaProperties`, `team`, `roles`,
  `support` and `price`
- **Steps:** `load`; `describe()`
- **Expected:** all five named individually with the reason "Prama has no field
  for it"
- **Why:** "an importer that silently discarded half a contract would produce a
  declaration that looks complete and generates a third of the controls it
  should".

### CTR-003 · A defaulted value is reported before an ignored one
- **Area:** `contract/odcs.py::Imported.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a contract with both
- **Steps:** `describe()`
- **Expected:** the defaults first
- **Why:** "a defaulted value is a number that will appear on a screen as
  though somebody chose it" — criticality TIER_4 assigned by default is a
  decision nobody made.

### CTR-004 · A contract with no schema imports nothing and says why
- **Area:** `contract/odcs.py::load`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a contract with no `schema` key
- **Steps:** `load`; then `prama contract import`
- **Expected:** `declaration is None`, one ignored reason, and exit 3 from the
  CLI
- **Why:** an empty declaration silently created would be a dataset nobody
  declared.

### CTR-005 · A multi-schema contract names what it left behind
- **Area:** `contract/odcs.py::load`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a contract with four schema objects
- **Steps:** `load`
- **Expected:** the first imported; an ignored entry saying three further
  schema objects were not, with the instruction to import them separately
- **Why:** "a contract describing four tables imported as one is three datasets
  nobody declared".

### CTR-006 · Quality blocks on the other schemas are lost without mention
- **Area:** `contract/quality.py::controls_from`
- **Type:** negative
- **Priority:** P1
- **Precondition:** the same four-schema contract, each schema carrying quality
  blocks
- **Steps:** `controls_from(contract)`
- **Expected:** the other schemas' blocks refused by name, or the omission
  reported
- **Why:** `controls_from` reads `schemas[0]` only. `load` at least *names*
  the schemas it dropped; the quality importer drops their checks in silence,
  and `QualityImport.offered` then undercounts what the contract promised.

### CTR-007 · A criticality on the contract maps to a tier
- **Area:** `contract/odcs.py::_criticality`
- **Type:** functional
- **Priority:** P2
- **Precondition:** contracts with `critical`, `high`, `medium`, `low`
- **Steps:** `load` each
- **Expected:** TIER_1 to TIER_4; no `defaulted` entry for criticality
- **Why:** the one field that *is* mapped, and the only one that keeps its
  entry out of the defaults list.

### CTR-008 · An unrecognised criticality falls back and says so
- **Area:** `contract/odcs.py::_criticality`, `load`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `criticality: "very high"`
- **Steps:** `load`
- **Expected:** TIER_4, and criticality listed in `defaulted`
- **Why:** "guessing a tier from a description would produce a criticality
  nobody assigned and controls nobody agreed to" — the value must not be
  silently dropped *and* absent from the defaults list.

### CTR-009 · An ODCS type not in the mapping is kept as text and reported
- **Area:** `contract/odcs.py::_attribute`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a property with `logicalType: "money"`
- **Steps:** `load`
- **Expected:** the attribute imported with no semantic type; an ignored entry
  naming the column and the type
- **Why:** "a type quietly coerced is a control generated against the wrong
  family".

### CTR-010 · `required` becomes optionality
- **Area:** `contract/odcs.py::_attribute`
- **Type:** functional
- **Priority:** P1
- **Precondition:** properties with `required: true`, `false` and absent
- **Steps:** `load`
- **Expected:** MANDATORY, OPTIONAL, OPTIONAL
- **Why:** mandatory drives the null control and the CI gate's
  `mandatory_with_nulls` check; an inverted mapping either fails every row or
  checks nothing.

### CTR-011 · Precision and scale survive
- **Area:** `contract/odcs.py::_attribute`, `_property`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `precision: 18, scale: 2`
- **Steps:** import, export, re-import
- **Expected:** both preserved; the exported `logicalType` is `number`
- **Why:** a numeric attribute exported as `string` comes back with no
  arithmetic family, and the controls derived from it change.

### CTR-012 · A declaration exported and re-imported is the same declaration
- **Area:** `contract/odcs.py::dump`, `load`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a declaration with name, purpose, description, criticality,
  tags and five attributes
- **Steps:** `load(dump(declaration))`
- **Expected:** field-by-field equality for everything ODCS carries
- **Why:** "round-tripping is a property, not a hope. Anything that survives
  one direction and not the other is a field somebody will lose on the first
  migration."

### CTR-013 · Purpose and usage do not swap on a round trip
- **Area:** `contract/odcs.py::load`, `dump`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a declaration whose purpose and description differ
- **Steps:** round-trip twice
- **Expected:** stable after both
- **Why:** the recorded bug: "the earlier version reached for the schema
  object's own description as a fallback for one of them, which made a round
  trip *swap* the two — stable under a single comparison and wrong on the
  second". One round trip is not the test; two is.

### CTR-014 · A semantic type does not survive the round trip
- **Area:** `contract/odcs.py::_logical_type`, `_TYPE_TO_SEMANTIC`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a declaration whose `lei` column carries `semantic_type='lei'`
- **Steps:** `load(dump(declaration))`; read the attribute's semantic type and
  the `ignored` list
- **Expected:** either preserved, or lost **and reported**
- **Why:** `_logical_type` maps anything that is not `date`/`timestamp` to
  `string`, and `_TYPE_TO_SEMANTIC['string']` is `''`. The LEI declaration —
  the thing every identifier control is derived from — is silently deleted by an
  export/import cycle, and `ignored` says nothing because `string` *is* a type
  ODCS defines. This is the exact failure the module's docstring promises not
  to have.

### CTR-015 · A malformed contract does not raise a bare exception
- **Area:** `contract/odcs.py::load`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `{"schema": {"name": "x"}}` (a mapping where a list is
  expected); `{"schema": ["orders"]}` (a list of strings); `{"schema": [null]}`
- **Steps:** `load` each; then `prama contract import` on the same files
- **Expected:** a `ValidationError` naming the shape problem, not
  `AttributeError: 'str' object has no attribute 'get'`
- **Why:** finding Q-28 — twenty-two tracebacks reached the terminal from the
  CLI, "mostly directory where a file is expected and malformed documents".
  `schemas[0]` is indexed and `.get` called with no type check.

### CTR-016 · `is_complete` is only true when nothing was lost
- **Area:** `contract/odcs.py::Imported.is_complete`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a contract that imports cleanly
- **Steps:** read `is_complete`
- **Expected:** False for every real contract, because grain and rhythm are
  always defaulted
- **Why:** if the flag can never be true it is not carrying information; if it
  can, the conditions need stating.

### CTR-017 · Every mapped library rule produces parseable PQL
- **Area:** `contract/quality.py::LIBRARY_RULES`, `_library`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of the eleven rules, build a minimal block and parse the
  emitted control
- **Expected:** all eleven parse
- **Why:** a quality importer that emits PQL the product refuses is the H1
  shape, and the `{column}`/dataset joining logic builds the string by hand.

### CTR-018 · A text rule is refused and named
- **Area:** `contract/quality.py::_absorb`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `type: text` block
- **Steps:** `controls_from`
- **Expected:** refused, with the reason "it is prose with no executable
  content, and a control built from it would check nothing while appearing on a
  coverage report as though it did"
- **Why:** the strongest version of the product's central argument, applied to
  somebody else's document.

### CTR-019 · A SQL rule is refused with its query preserved
- **Area:** `contract/quality.py::_absorb`, `_shorten`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `type: sql` block with a 200-character query
- **Steps:** `controls_from`
- **Expected:** refused; the query truncated to 60 characters with an ellipsis
  and still recognisable
- **Why:** "refused, **with the query preserved** so somebody can rewrite it as
  PQL rather than hunt for it".

### CTR-020 · A custom rule is routed to the importer that owns it
- **Area:** `contract/quality.py::ROUTABLE_ENGINES`
- **Type:** functional
- **Priority:** P1
- **Precondition:** custom blocks for `soda`, `sodaCL`, `great-expectations`,
  `dbt`
- **Steps:** `controls_from`
- **Expected:** all four routed, each naming the `prama control import --from`
  command; the hyphen and the case both normalised
- **Why:** "the block is *routed* to that importer rather than reimplemented
  here", and every named command must exist (finding Q-07's rule).

### CTR-021 · A custom rule for an unknown engine is refused by name
- **Area:** `contract/quality.py::_absorb`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a custom block with `engine: montecarlo`, and one with no
  engine
- **Steps:** `controls_from`
- **Expected:** refused, naming the engine or "an unnamed engine", with the
  reason about running somebody else's implementation
- **Why:** "a plausible control passes review — it looks like the others — and
  then quietly checks something else".

### CTR-022 · An unmapped library rule lists what is mapped
- **Area:** `contract/quality.py::_library`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `rule: referentialIntegrity`
- **Steps:** `controls_from`
- **Expected:** refused, with the eleven mapped names listed
- **Why:** the list is "deliberately short: a rule here is one somebody
  checked", and the refusal is where a reader learns the boundary.

### CTR-023 · A threshold is a tolerance, and `mustBeLessThan` is one lower
- **Area:** `contract/quality.py::_threshold`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `duplicateCount` with `mustBeLessThan: 10`, and with
  `mustBeLessOrEqualTo: 10`
- **Steps:** `controls_from`
- **Expected:** `AT MOST 9 ROWS` and `AT MOST 10 ROWS`
- **Why:** "`duplicateCount` with `mustBeLessThan: 10` is not 'no duplicates':
  it is a control that tolerates nine. Getting that wrong by one makes a
  contract the producer satisfies fail against a consumer who imported it."

### CTR-024 · No threshold means the strictest reading
- **Area:** `contract/quality.py::_threshold`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `nullCount` with no comparator; `nullPercent` with none
- **Steps:** `controls_from`
- **Expected:** `AT MOST 0 ROWS` and `BELOW 0%`
- **Why:** "the strictest reading, and the one a contract without a number
  means" — and the percent/count split has to follow the rule name's suffix.

### CTR-025 · A strict percentage bound is refused rather than loosened
- **Area:** `contract/quality.py::_threshold`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `nullPercent` with `mustBeLessThan: 2`
- **Steps:** `controls_from`
- **Expected:** refused, saying PQL's `BELOW` is inclusive and "importing it
  would accept a value the contract forbids"
- **Why:** "a strict bound on a rate has no representable predecessor, so it is
  reported rather than silently made inclusive" — the one place the module
  refuses rather than rounds.

### CTR-026 · `mustBe` other than zero is refused
- **Area:** `contract/quality.py::_threshold`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `duplicateCount` with `mustBe: 5`
- **Steps:** `controls_from`
- **Expected:** refused — "a control asserts a bound rather than an equality —
  a population that happens to have fewer violations would fail"
- **Why:** an exact count is a test-suite idiom and a strange thing to want in
  a control estate.

### CTR-027 · A lower bound on failures is refused
- **Area:** `contract/quality.py::_threshold`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `invalidCount` with `mustBeGreaterThan: 0`
- **Steps:** `controls_from`
- **Expected:** refused — it "asks for *at least* that many failures, which is
  not something a control can assert"
- **Why:** inverting it would produce a control nobody wrote.

### CTR-028 · A non-numeric threshold is refused with the value quoted
- **Area:** `contract/quality.py::_threshold`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `mustBeLessThan: "ten"`
- **Steps:** `controls_from`
- **Expected:** refused, quoting the value
- **Why:** a YAML contract is hand-written, and a quoted number is what a
  hand-written one contains.

### CTR-029 · A `rowCount` range is inclusive on both ends
- **Area:** `contract/quality.py::_render`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `rowCount` with `mustBeGreaterOrEqualTo: 900000` and
  `mustBeLessThan: 1200000`
- **Steps:** `controls_from`
- **Expected:** a maximum of 1,199,999, or a refusal
- **Why:** `HAS ROW COUNT BETWEEN … AND …` is inclusive, and `mustBeLessThan`
  is not. The module refuses this very off-by-one for violation counts
  (CTR-023) and for percentages (CTR-025) and then commits it for row counts —
  a contract forbidding exactly 1,200,000 rows imports as one permitting it.

### CTR-030 · `rowCount` with only one bound is refused
- **Area:** `contract/quality.py::_render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `rowCount` with only a minimum
- **Steps:** `controls_from`
- **Expected:** refused — "a row-count rule needs both a minimum and a
  maximum"
- **Why:** the shipped `row-count-plausible` template's note says a range is
  the point, because "a population that doubled overnight is as much a defect
  as one that halved".

### CTR-031 · A freshness window's unit is assumed to be days
- **Area:** `contract/quality.py::_render`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `freshness` with `mustBeLessThan: 4` meaning four hours
- **Steps:** `controls_from`
- **Expected:** a refusal, or the unit read from the contract
- **Why:** the code renders `f"{window} day"` unconditionally. A four-hour
  freshness promise imports as a four-day one — a control twenty-four times
  looser than the contract, silently, on the dimension where lateness is the
  defect.

### CTR-032 · `validValues` renders as PQL literals with quotes escaped
- **Area:** `contract/quality.py::_render`, `_literal`
- **Type:** security
- **Priority:** P1
- **Precondition:** `validValues: ["GBP", "O'Brien", 5, true]`
- **Steps:** `controls_from`; parse the emitted control
- **Expected:** `'GBP', 'O''Brien', 5, TRUE`, and the control parses
- **Why:** an unescaped apostrophe in a contract a producer wrote is an
  injection into a string the product then compiles to SQL.

### CTR-033 · A pattern containing a slash is refused
- **Area:** `contract/quality.py::_render`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `pattern: "^/api/.*$"`
- **Steps:** `controls_from`
- **Expected:** refused, naming the delimiter clash
- **Why:** "PQL delimits a pattern with slashes, and escaping is a decision
  somebody should make deliberately rather than have guessed here" — and an
  unescaped one would terminate the pattern and leave the rest as syntax.

### CTR-034 · A column rule with no column is refused
- **Area:** `contract/quality.py::_library`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a `nullCount` block at the schema level
- **Steps:** `controls_from`
- **Expected:** refused — "this rule is about a column and the block names
  none"
- **Why:** the alternative is `CHECK orders. IS NOT NULL`, which does not
  parse, and a refusal that arrives at parse time names the wrong thing.

### CTR-035 · `uniqueCount` is treated as a violation count
- **Area:** `contract/quality.py::LIBRARY_RULES`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `uniqueCount` with `mustBeGreaterThan: 100`
- **Steps:** `controls_from`
- **Expected:** a refusal whose reason is right
- **Why:** `uniqueCount` counts *distinct values*, not violations, so
  `counts_violations=True` makes "at least 100 distinct values" report as
  "asks for at least that many failures". A wrong reason on an import report is
  worse than no reason, since the report is what somebody signs off (the same
  argument the Soda importer makes for its freshness special case).

### CTR-036 · The import report states how many of how many
- **Area:** `contract/quality.py::QualityImport.describe`, `offered`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a contract with eleven quality blocks, four of which map
- **Steps:** `describe()`
- **Expected:** "4 of 11 … 7 did not import:" with all seven named
- **Why:** "a contract promising eleven checks and yielding four is a
  conversation with the producer, and it needs the seven named".

### CTR-037 · Quality blocks are reported even without `--controls`
- **Area:** `cli/contract.py::ContractImportCommand`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a contract with quality blocks
- **Steps:** `prama contract import c.yaml`
- **Expected:** the quality summary printed
- **Why:** "importing the schema while silently taking on none of the checks is
  the failure this whole module is about".

### CTR-038 · `prama contract import --json` emits one document
- **Area:** `cli/contract.py::ContractImportCommand`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a valid contract
- **Steps:** `--json`; parse the output
- **Expected:** valid JSON carrying both the declaration summary and the
  `quality` block; exit 0
- **Why:** finding Q-37 — `--json` emitting prose on an error breaks the JSON
  contract at the CI integration point. This command's failure path returns
  exit 3 with JSON, and the malformed-file path (CTR-015) must too.

### CTR-039 · `prama contract export` writes a contract that validates
- **Area:** `cli/contract.py::ContractExportCommand`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a declared dataset
- **Steps:** export to a file; re-import with `prama contract import`
- **Expected:** the round trip holds; `apiVersion` is `3.0.0`
- **Why:** "a contract with no version is one no consumer can validate
  against", and the export is the product's public face.

### CTR-040 · Export refuses an unknown dataset and an unset tenant
- **Area:** `cli/contract.py::ContractExportCommand`
- **Type:** negative
- **Priority:** P1
- **Precondition:** no `tenancy.default_tenant`
- **Steps:** export with no `--tenant`; then with a valid tenant and a bad slug
- **Expected:** two `ValidationError`s, the second naming
  `prama estate export` as the remedy
- **Why:** finding Q-17 — `--tenant` accepted a non-existent id on seven of
  eight commands and reported a plausible empty result at exit 0. Confirm this
  one refuses.

### CTR-041 · The diff reports the schema before the rows
- **Area:** `contract/diff.py::Diff.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two row sets differing by a renamed column
- **Steps:** `compare(..., key=['id'])`
- **Expected:** the schema difference first, on its own, then the row counts
- **Why:** "comparing rows across two different column sets produces a diff
  where everything changed, and the one fact that explains it — a column was
  renamed — is buried under ten thousand rows".

### CTR-042 · A changed row names the columns that changed
- **Area:** `contract/diff.py::compare`, `RowChange`
- **Type:** functional
- **Priority:** P1
- **Precondition:** rows differing in one column
- **Steps:** compare
- **Expected:** each `RowChange` naming the column with its before and after
- **Why:** "'4,120 rows differ' is a number nobody can act on".

### CTR-043 · `columns_that_changed` counts every row, not the examples
- **Area:** `contract/diff.py::changed_by_column`, `columns_that_changed`
- **Type:** regression
- **Priority:** P1
- **Precondition:** 10,000 differing rows where the first 100 by key differ in
  `settlement_date` and the other 9,900 in `notional`
- **Steps:** compare with the default limit; read `columns_that_changed`
- **Expected:** `notional` first
- **Why:** finding C10 exactly. "It reported 'changes are in settlement_date'
  and never mentioned the column that changed in 99% of rows. The summary line
  then added 'examples are capped and the counts are not' — true of the counts,
  false of this."

### CTR-044 · A capped diff says it was capped
- **Area:** `contract/diff.py::Diff.truncated`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 100 and 101 changed rows; 101 added keys; 101 removed keys
- **Steps:** compare with `limit=100`
- **Expected:** `truncated` False at 100, True at 101, and True when either the
  added or the removed list overflows
- **Why:** "a bound presented as a total is the most dangerous number here".

### CTR-045 · Without a key there is no changed row
- **Area:** `contract/diff.py::compare`, `Diff.comparable`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two row sets in different orders
- **Steps:** compare with no key
- **Expected:** `comparable` False; `changed == 0`; the message saying "nothing
  here says a row *changed*, because nothing says which row is which"
- **Why:** the alternative is "a positional comparison that reports every row
  as changed the moment an ordering differs".

### CTR-046 · A keyless diff of reordered identical rows reports no difference
- **Area:** `contract/diff.py::compare`, `_freeze`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same 100 rows shuffled
- **Steps:** compare with no key
- **Expected:** 0 added, 0 removed, 100 unchanged
- **Why:** the set comparison is the whole point of the keyless mode.

### CTR-047 · A keyless diff over unhashable values
- **Area:** `contract/diff.py::_freeze`
- **Type:** negative
- **Priority:** P2
- **Precondition:** rows whose values include a list (a JSON column read from
  `.jsonl`)
- **Steps:** compare with no key
- **Expected:** a refusal naming the column, not `TypeError: unhashable type`
- **Why:** `prama contract diff` reads `.jsonl` and `.json` directly, so a
  nested value reaches `_freeze` from the CLI.

### CTR-048 · A keyless diff deduplicates and says so
- **Area:** `contract/diff.py::compare`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a left side with three identical rows and a right side with
  one
- **Steps:** compare with no key
- **Expected:** the duplicate collapse is visible in the output
- **Why:** the set comparison reports 0 added, 0 removed and 1 unchanged over
  four rows — a two-row loss reported as no difference.

### CTR-049 · Duplicate keys are counted and named as a broken comparison
- **Area:** `contract/diff.py::compare`, `duplicate_keys_left/right`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a left side with two rows sharing a key
- **Steps:** compare with that key
- **Expected:** `duplicate_keys_left == 1`, and the message saying "this
  comparison is between the wrong pairs"
- **Why:** "a key that is not unique is not a key, and a diff computed on one
  is arithmetic on the wrong pairs" — and the dict keeps the last row, so the
  earlier one is silently discarded.

### CTR-050 · A key column absent from the rows collapses everything
- **Area:** `contract/diff.py::_key_of`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `--key id` where no row has an `id`
- **Steps:** compare
- **Expected:** a refusal naming the missing column
- **Why:** `row.get(name)` yields `(None,)` for every row, so all rows collapse
  onto one key, `duplicate_keys` equals the row count minus one, and the diff
  compares two arbitrary rows. A typo'd `--key` produces a confident wrong
  answer.

### CTR-051 · Only shared columns are compared
- **Area:** `contract/diff.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column present only on the right
- **Steps:** compare
- **Expected:** it appears in `schema.added` and not in any `RowChange`
- **Why:** "comparing a column that exists on one side reports every shared row
  as changed, which is the schema difference said a second time and much less
  clearly".

### CTR-052 · `--ignore` drops a column from the value comparison
- **Area:** `contract/diff.py::compare`
- **Type:** functional
- **Priority:** P2
- **Precondition:** rows differing only in `loaded_at`
- **Steps:** compare with `ignore=['loaded_at']`, keyed and keyless
- **Expected:** identical in both modes
- **Why:** "a load timestamp differs on every row of every reload, and a diff
  dominated by it hides everything else".

### CTR-053 · A retype is reported only where both sides declare a type
- **Area:** `contract/diff.py::compare_schema`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a column typed on one side and untyped on the other
- **Steps:** `compare_schema`
- **Expected:** not reported as a retype
- **Why:** "a type declared on one side and not the other is not a change of
  type, it is a change of how much is known — and reporting it as a retype
  sends somebody looking for a migration that never happened".

### CTR-054 · Mixed-type keys sort without raising
- **Area:** `contract/diff.py::_sortable`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a key column holding both integers and strings, and some
  nulls
- **Steps:** compare
- **Expected:** sorted output, no `TypeError`
- **Why:** "sorting raw tuples raises the moment a key column holds both an
  integer and a string, which is exactly what a mid-migration dataset looks
  like" — the case the tool is most used for.

### CTR-055 · `prama contract diff` exits 3 on any difference
- **Area:** `cli/contract.py::ContractDiffCommand`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two files differing in one row
- **Steps:** run; check `$?`; then run over identical files
- **Expected:** 3 then 0, in both text and `--json` modes
- **Why:** "the exit code is the interface", and a build gating on it needs 3
  to mean "your change did this" rather than "the checker fell over".

### CTR-056 · `prama contract check` exits 3 on a missing column
- **Area:** `cli/contract.py::ContractCheckCommand`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a contract promising four columns; data carrying three
- **Steps:** run; check `$?`
- **Expected:** exit 3, with "BREACH — promised column(s) absent" naming the
  one
- **Why:** "a removed column breaks every consumer".

### CTR-057 · An added column is a breach unless allowed
- **Area:** `cli/contract.py::ContractCheckCommand`
- **Type:** functional
- **Priority:** P1
- **Precondition:** data carrying an extra column
- **Steps:** run with and without `--allow-additions`
- **Expected:** exit 3 with "BREACH"; then exit 0 with "note"
- **Why:** "treating them alike either blocks harmless changes — after which
  the gate is disabled — or lets through the one change that matters".

### CTR-058 · A required column holding an empty value is a breach
- **Area:** `cli/contract.py::ContractCheckCommand`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a mandatory column present with one null and one `''`
- **Steps:** run
- **Expected:** exit 3, naming the column
- **Why:** "the contract's `required` is a promise about values, not only about
  the column existing, and checking only the header would pass a table of
  nulls".

### CTR-059 · A check over no rows establishes nothing, loudly
- **Area:** `cli/contract.py::ContractCheckCommand`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty `.jsonl`, an empty `.csv`, and `{"rows": []}`
- **Steps:** run each, in text and `--json`
- **Expected:** exit 3 in all six, and the JSON payload carries the
  no-rows fact rather than only `breached: true`
- **Why:** "a contract check over no rows passes every test it can run and has
  established nothing" — and in JSON mode the loud sentence is not emitted at
  all, so a CI job reading the payload cannot tell an empty file from a missing
  column.

### CTR-060 · The checker's own failures exit 1, not 3
- **Area:** `cli/contract.py`, `_load`, `_rows`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a contract path that does not exist; a `.json` holding a
  bare string; a directory passed where a file is expected
- **Steps:** run each; check `$?`
- **Expected:** exit 1 with a `ValidationError`, never 3 and never a traceback
- **Why:** "a single non-zero code makes a broken checker look like a broken
  change", and finding Q-28 records directories-where-a-file-is-expected as the
  commonest traceback source.

### CTR-061 · CSV rows arrive as text and the check accounts for it
- **Area:** `cli/contract.py::_rows`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a CSV whose mandatory numeric column holds `0`
- **Steps:** `prama contract check`
- **Expected:** not a breach — `'0'` is a value
- **Why:** `csv.DictReader` yields strings, and the emptiness test is
  `row.get(name) in (None, "")`. A CSV's empty cell is `''` and its zero is
  `'0'`; a JSON file's zero is `0`, which is also not in the tuple. Confirm the
  two input formats agree.

### CTR-062 · The example sets are capped in the CLI too
- **Area:** `cli/contract.py::ContractDiffCommand`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 500 changed rows
- **Steps:** run
- **Expected:** ten examples printed, the counts exact, and the truncation
  stated
- **Why:** the command prints `[:10]` of an already-capped list, so a reader
  sees ten of a hundred of five hundred; only one of those three numbers is
  labelled.

## Importers — `importers/`

### IMP-001 · The three shipped importers resolve by name
- **Area:** `importers/__init__.py::importer`, `IMPORTERS`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `importer('dbt')`, `'soda'`, `'great_expectations'`,
  `'great-expectations'`, `'GREAT EXPECTATIONS'`
- **Expected:** the first four resolve (hyphen and case normalised); the fifth
  is refused
- **Why:** `prama control import --from` takes this string, and the hyphen form
  is what `contract/quality.py::ROUTABLE_ENGINES` tells a user to type.

### IMP-002 · An unknown source is refused with the list
- **Area:** `importers/__init__.py::importer`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `importer('montecarlo')`
- **Expected:** `RegistryError` listing the three available
- **Why:** the remedy is where a user learns the boundary, and a `KeyError`
  reaching a terminal is finding Q-28.

### IMP-003 · Every result reports three things
- **Area:** `importers/spi.py::ImportResult.render`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an import with controls, caveats and unmapped constructs
- **Steps:** `render()`
- **Expected:** the count imported, every caveat, and every unmapped construct
  named individually
- **Why:** "the honest answer has three parts, and an importer that gives fewer
  than three is selling something".

### IMP-004 · Nothing left behind is stated explicitly
- **Area:** `importers/spi.py::ImportResult.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a file every construct of which imports
- **Steps:** `render()`
- **Expected:** "Nothing was left behind."
- **Why:** the absence of an "unmapped" section is ambiguous; the sentence is
  what makes a clean import readable as clean.

### IMP-005 · `is_complete` ignores caveats
- **Area:** `importers/spi.py::ImportResult.is_complete`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an import with no unmapped constructs and four caveats
- **Steps:** read `is_complete`
- **Expected:** a stated meaning
- **Why:** `is_complete` is `not self.unmapped`, so an import where every
  control's meaning changed — nulls now counting as violations — reports
  complete. The three-part promise is reduced to two in the one field a caller
  is most likely to branch on.

### IMP-006 · An unmapped construct carries its source verbatim
- **Area:** `importers/spi.py::Unmapped`
- **Type:** functional
- **Priority:** P1
- **Precondition:** any refusal
- **Steps:** read `source`
- **Expected:** the original name or check text, findable by grep in the source
  file
- **Why:** "verbatim, so it can be found again" — a paraphrased name sends
  somebody hunting.

### IMP-007 · An importer emitting bad PQL raises rather than reporting
- **Area:** `importers/spi.py::Collector.control`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a source construct whose expression is carried across
  unchanged and does not parse — for example a dbt
  `expression_is_true` with `expression: "amount > 0 AND"`
- **Steps:** import the file
- **Expected:** the construct reported as unmapped, and the rest of the file
  still imported
- **Why:** `Collector.control` calls `parse_control` and lets the
  `PqlSyntaxError` escape, so one un-parseable expression aborts the whole
  import. The package's own rule is that a construct Prama cannot handle is
  *reported*, and a four-hundred-test migration must not be lost to one of
  them.

### IMP-008 · Every imported control says where it came from
- **Area:** `importers/spi.py::because`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an import from each of the three sources
- **Steps:** read every control's `BECAUSE`
- **Expected:** "Imported from …" naming the tool and the object
- **Why:** "six months after a migration, 'why does this exist' is answered by
  the control itself rather than by whoever remembers the old tool".

### IMP-009 · An origin containing an apostrophe is escaped
- **Area:** `importers/spi.py::because`, `quote`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a SodaCL check whose text contains `'`
- **Steps:** import; parse the emitted control
- **Expected:** the apostrophe doubled; the control parses
- **Why:** the docstring records this exact bug — "handing back an unescaped
  string for a caller to interpolate is an invitation to emit PQL that does not
  parse, which is what happened the first time this existed".

### IMP-010 · A dbt schema.yml imports `unique` and `not_null`
- **Area:** `importers/dbt.py::_column_test`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a model with both tests on a column
- **Steps:** import
- **Expected:** `CHECK model.col IS NOT NULL` and
  `CHECK model HAS UNIQUE KEY (col)`, the second carrying the grain caveat
- **Why:** "dbt's `unique` asserts this column alone is distinct … if the
  declared grain is wider, the control is weaker than the grain".

### IMP-011 · `accepted_values` carries the nulls caveat
- **Area:** `importers/dbt.py::NULL_CAVEAT`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an `accepted_values` test
- **Steps:** import
- **Expected:** the control, plus a caveat naming
  `TREAT UNKNOWN AS PASS` as the way to keep dbt's behaviour exactly
- **Why:** "an imported `accepted_values` will find rows dbt never reported —
  which is the point of migrating, and is also a surprise if nobody says it in
  advance". And the remedy names a real PQL clause, which must be checked.

### IMP-012 · `accepted_values` with no values is refused
- **Area:** `importers/dbt.py::_column_test`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `accepted_values: {}`
- **Steps:** import
- **Expected:** unmapped, with the remedy "Give the permitted values, or drop
  the test"
- **Why:** `IN ()` does not parse, and a silently dropped test is lost coverage.

### IMP-013 · `relationships` resolves `ref()` and `source()`
- **Area:** `importers/dbt.py::_dereference`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `to: "ref('accounts')"` and `to: "source('raw','accounts')"`
- **Steps:** import
- **Expected:** both resolve to `accounts`
- **Why:** the two spellings are both ordinary, and an unresolved one produces
  `REFERENCES ref('accounts').id`, which does not parse.

### IMP-014 · A versioned `ref` resolves to the version, not the model
- **Area:** `importers/dbt.py::_dereference`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `to: "ref('accounts', v=2)"`
- **Steps:** import
- **Expected:** `accounts`
- **Why:** `parts[-1]` takes the *last* comma-separated fragment, which is
  correct for `source(schema, table)` and wrong for a versioned `ref` — the
  control then references a dataset called `v=2`.

### IMP-015 · `relationships` without both a target and a field is refused
- **Area:** `importers/dbt.py::_relationship`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a test with `to` and no `field`
- **Steps:** import
- **Expected:** unmapped, naming what was missing
- **Why:** half a reference is a control pointing at a dataset with no column.

### IMP-016 · `accepted_range` refuses a one-sided or exclusive range
- **Area:** `importers/dbt.py::_range`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `min_value` only; then both with `inclusive: false`
- **Steps:** import each
- **Expected:** both unmapped — the first with a remedy naming the comparison
  to write, the second saying "an exclusive range would change which rows fail"
- **Why:** `BETWEEN` is inclusive, and importing an exclusive range as one
  changes which rows fail — the same off-by-one class as CTR-023 and CTR-029.

### IMP-017 · `not_null_proportion` is inverted and the caveat says so
- **Area:** `importers/dbt.py::_proportion`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `at_least: 0.95`
- **Steps:** import
- **Expected:** `IS NOT NULL BELOW 5%`, with a caveat stating both readings
- **Why:** "dbt states the proportion that must be present; Prama states the
  proportion that may be missing. The same threshold, read from the other end."
  Inverting it by accident is a control that fires on 95% of rows.

### IMP-018 · `not_null_proportion` with an out-of-range value
- **Area:** `importers/dbt.py::_proportion`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `at_least: 95` (a percentage, not a proportion);
  `at_least: 0`
- **Steps:** import
- **Expected:** a refusal for the first, or a control whose threshold is not
  `BELOW -9400%`
- **Why:** `(1.0 - 95) * 100` is negative, and nothing bounds the input. A
  percentage written where a proportion is expected is the single most likely
  mistake in that field.

### IMP-019 · `unique_combination_of_columns` imports as a grain
- **Area:** `importers/dbt.py::_model_test`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a model test naming three columns
- **Steps:** import
- **Expected:** `HAS UNIQUE KEY (a, b, c)`, no caveat
- **Why:** this is the one that genuinely matches Prama's grain, and it must
  not carry the weaker-than-grain caveat that `unique` does.

### IMP-020 · `expression_is_true` carries the dialect caveat
- **Area:** `importers/dbt.py::_model_test`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an expression using a warehouse-specific function
- **Steps:** import
- **Expected:** the control, with a caveat saying the expression "was written
  for dbt's warehouse dialect and has not been checked against the engine this
  control will run on"
- **Why:** finding C4 is the precedent — `%` and `/` mean different things on
  different engines, so a carried-across expression is a control whose verdict
  depends on where it runs.

### IMP-021 · A package-prefixed test name is recognised
- **Area:** `importers/dbt.py::_base`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `dbt_utils.accepted_range` and `dbt_expectations.expect_…`
- **Steps:** import
- **Expected:** the first recognised by its last segment; the second refused as
  a package test
- **Why:** "`dbt_utils.accepted_range` and `accepted_range` are one test", and
  the boundary of that claim is where a package test is silently treated as a
  known one.

### IMP-022 · A custom test is refused and never approximated
- **Area:** `importers/dbt.py::_refuse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `assert_positive_amount`
- **Steps:** import
- **Expected:** unmapped, with the remedy "Prama will not guess: an
  approximated control passes review and then checks something else"
- **Why:** the package's central rule, stated at the point it bites.

### IMP-023 · A test in an unexpected shape is not silently swallowed
- **Area:** `importers/dbt.py::_split`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a test written as a two-key mapping, e.g.
  `{accepted_values: {...}, config: {...}}`
- **Steps:** import
- **Expected:** unmapped with a readable name
- **Why:** `_split` returns `("", {})` for a multi-key mapping, so the test is
  reported as "dbt test  on orders" — an empty name that cannot be found in the
  file, which is what `Unmapped.source`'s verbatim rule exists to prevent.

### IMP-024 · Sources, seeds and snapshots are all read
- **Area:** `importers/dbt.py::read`, `_model`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a schema.yml with all four sections, each carrying tests
- **Steps:** import
- **Expected:** controls from all four; a source's tables imported by their own
  names
- **Why:** a migration that silently skipped `sources` would lose the tests on
  the raw layer, which is where most `not_null` tests live.

### IMP-025 · `data_tests` is accepted alongside `tests`
- **Area:** `importers/dbt.py::_model`, `_column`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a schema.yml using the newer `data_tests` key
- **Steps:** import
- **Expected:** the same controls
- **Why:** dbt renamed the key, and a file using it would import as zero tests
  with no unmapped entries — a silent clean result over a full suite.

### IMP-026 · A file that is not a dbt schema is refused
- **Area:** `importers/dbt.py::read`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a list, a string, `None`, and an empty document
- **Steps:** import each
- **Expected:** unmapped "this is not a dbt schema file" with the remedy for
  the non-dict cases; a stated answer for the empty dict
- **Why:** an empty dict passes the type check and imports zero controls with
  nothing unmapped — "Nothing was left behind" over a file nobody read.

### IMP-027 · A SodaCL count check imports with its threshold
- **Area:** `importers/soda.py::_metric`, `_threshold`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `missing_count(account_id) = 0` and `= 5`
- **Steps:** import
- **Expected:** `IS NOT NULL` with no threshold, then `AT MOST 5 ROWS`
- **Why:** zero is the strict default and anything else is a tolerance the
  producer chose.

### IMP-028 · SodaCL's `<` is imported as an inclusive bound
- **Area:** `importers/soda.py::_threshold`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `missing_count(account_id) < 5`
- **Steps:** import
- **Expected:** `AT MOST 4 ROWS`, or a refusal
- **Why:** `_threshold` treats `<` and `<=` identically, so a check the
  producer satisfies with four failures imports as one that permits five. The
  sibling module `contract/quality.py` adjusts by one for exactly this and
  explains why in its docstring; this one does not.

### IMP-029 · A duplicate-count threshold is silently dropped
- **Area:** `importers/soda.py::_metric`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `duplicate_count(trade_id) < 10`
- **Steps:** import
- **Expected:** the tolerance preserved, or the check refused
- **Why:** the `base == "duplicate"` branch emits `HAS UNIQUE KEY (...)` and
  never uses `threshold`, which was computed two lines above. A check the
  producer satisfies with nine duplicates becomes a control that fails on the
  first — the migration tightens a promise without saying so.

### IMP-030 · A percentage threshold becomes `BELOW n%`
- **Area:** `importers/soda.py::_threshold`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `invalid_percent(ccy) <= 2 %` and `missing_percent(x) = 0`
- **Steps:** import
- **Expected:** `BELOW 2%`, then `BELOW 0%`
- **Why:** the `%` suffix and the metric-name suffix are two independent ways
  of saying the same thing, and both have to work. The precondition used a
  **strict** `<`, which `_threshold` refuses on purpose and reports rather than
  importing: a strict bound on a rate has no representable predecessor, so
  treating it as `BELOW` would silently widen the control. The contract importer
  refuses the same shape for the same reason. A case asserting the widening would
  have required the importer to guess.

### IMP-031 · A lower bound on failures is refused
- **Area:** `importers/soda.py::_threshold`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `missing_count(x) > 0`
- **Steps:** import
- **Expected:** unmapped, saying it "asserts that data is broken rather than
  that it is sound"
- **Why:** "a legitimate thing to write in a test suite and a strange thing to
  want in a control estate, so it is reported rather than inverted into
  something nobody wrote".

### IMP-032 · `freshness` is a control, not a failure count
- **Area:** `importers/soda.py::_freshness`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `freshness(as_of) < 1d`
- **Steps:** import
- **Expected:** `IS FRESH WITHIN 1440 MINUTES`, with the caveat about SodaCL
  measuring from now
- **Why:** the recorded bug — "reporting it through the count logic produced an
  explanation that was simply untrue: it called a legitimate freshness bound 'a
  lower bound on failures'. A wrong reason on an import report is worse than no
  reason, since the report is what somebody signs off."

### IMP-033 · Duration units are read
- **Area:** `importers/soda.py::_duration_minutes`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `30m`, `4h`, `1d`, `90min`, `2hr`
- **Steps:** import each
- **Expected:** 30, 240, 1440, 90, 120 minutes
- **Why:** the suffixes are sorted longest-first so `min` is not read as `m`
  with a stray `in`; a shorter-first order gives 90 minutes for `90min` by luck
  and fails on `2hr`.

### IMP-034 · An unreadable duration is refused with a remedy
- **Area:** `importers/soda.py::_freshness`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `freshness(as_of) < 1w`; `< yesterday`
- **Steps:** import
- **Expected:** unmapped, with "Durations are written like 30m, 4h or 1d"
- **Why:** a week is a legitimate SodaCL duration and is not in the table, so
  this refusal fires on real files — the remedy is what makes it actionable.

### IMP-035 · An upper bound is the only freshness direction accepted
- **Area:** `importers/soda.py::_freshness`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `freshness(as_of) > 1d`
- **Steps:** import
- **Expected:** unmapped, saying only an upper bound has a meaning
- **Why:** a lower bound on staleness asserts the data must be old.

### IMP-036 · A row-count comparison is rewritten as an inclusive bound
- **Area:** `importers/soda.py::_row_count`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `row_count > 100`, `>= 100`, `< 100`, `<= 100`, `= 100`
- **Steps:** import each
- **Expected:** `AT LEAST 101`, `AT LEAST 100`, `AT MOST 99`, `AT MOST 100`,
  and a refusal for the last with a remedy naming the range form
- **Why:** "a row count is a whole number, so an exclusive bound is exactly an
  inclusive one on the next integer. Rewriting it that way is an identity
  rather than an approximation." Compare IMP-028, where the same reasoning was
  not applied.

### IMP-037 · `row_count >= 0` does not become a control that cannot fire
- **Area:** `importers/soda.py::_row_count`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `row_count > -1`; `row_count >= 0`
- **Steps:** import
- **Expected:** refused or flagged
- **Why:** the comment says the rewrite "avoids emitting AT LEAST 0, which
  asserts nothing at all and which the linter would rightly report as a control
  that can never fire" — `>= 0` reaches it directly and `> -1` reaches it by
  arithmetic.

### IMP-038 · `row_count between` imports as a range
- **Area:** `importers/soda.py::_between`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `row_count between 100 and 200`; `missing_count(x) between
  1 and 5`
- **Steps:** import
- **Expected:** the first becomes `HAS ROW COUNT BETWEEN 100 AND 200`; the
  second is unmapped
- **Why:** a between-range on a violation count has no direct PQL form and
  approximating it would change which rows fail.

### IMP-039 · A reference check imports as `REFERENCES`
- **Area:** `importers/soda.py::_reference`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `values in (account_id) must exist in accounts (account_id)`
- **Steps:** import
- **Expected:** `CHECK ds.account_id REFERENCES accounts.account_id`
- **Why:** the one multi-word SodaCL form the importer recognises, and it must
  be matched before the metric regex sees `values` as a metric name.

### IMP-040 · An `invalid` check needs its validity definition
- **Area:** `importers/soda.py::_invalid`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `invalid_count(ccy) = 0` with no `valid values`,
  `valid regex` or `valid min`/`max`
- **Steps:** import
- **Expected:** unmapped, with the remedy "Soda takes validity from a column
  configuration elsewhere in the scan. Bring that definition across with the
  check."
- **Why:** this is the commonest SodaCL shape and the one where a guess would
  produce a control that checks nothing while looking like the others.

### IMP-041 · An `invalid` check with each validity form
- **Area:** `importers/soda.py::_invalid`
- **Type:** functional
- **Priority:** P2
- **Precondition:** blocks carrying `valid values`, `valid regex`, and
  `valid min`/`valid max`
- **Steps:** import each
- **Expected:** `IN (...)`, `MATCHES /.../`, `BETWEEN … AND …`, each with the
  threshold attached
- **Why:** three shapes and one threshold placement; the `.strip()` on the
  result is what keeps a missing threshold from leaving a double space that
  changes nothing and a present one from being dropped.

### IMP-042 · A non-`checks for` block is refused by name
- **Area:** `importers/soda.py::read`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a `configurations for`, a `filter`, and a `for each dataset`
  block
- **Steps:** import
- **Expected:** each unmapped, with the remedy saying they are declared
  elsewhere in Prama and are not controls
- **Why:** a scan file is mostly not checks, and silently skipping the rest
  would make the offered count meaningless.

### IMP-043 · An unrecognised check form is refused, not approximated
- **Area:** `importers/soda.py::_check`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `anomaly score for row_count < default`;
  `schema: {fail: {when required column missing: [x]}}`
- **Steps:** import
- **Expected:** both unmapped, quoting the check text
- **Why:** "a partial parser that fell back to 'close enough' on an unfamiliar
  check would import something plausible, and a plausible control is worse than
  a missing one".

### IMP-044 · A GE suite imports the expectations it maps
- **Area:** `importers/great_expectations.py::_expectation`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a suite with `to_not_be_null`, `to_be_unique`,
  `to_be_in_set`, `to_be_between`, `to_match_regex`, and the two row-count ones
- **Steps:** import
- **Expected:** a control for each, with the null caveat on the value
  expectations
- **Why:** "GE ignores nulls in most value expectations … so an imported
  expectation finds rows the suite never reported".

### IMP-045 · `mostly` becomes a threshold read from the other end
- **Area:** `importers/great_expectations.py::_tolerance`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `mostly: 0.99`, `1.0`, absent
- **Steps:** import
- **Expected:** `BELOW 1%`, no threshold, no threshold — with the caveat on the
  first stating both readings
- **Why:** "the same threshold, and easy to invert by accident".

### IMP-046 · A non-numeric `mostly` is silently dropped
- **Area:** `importers/great_expectations.py::_tolerance`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `mostly: "0.99"` as a string is fine; `mostly: null` and
  `mostly: "high"`
- **Steps:** import
- **Expected:** the malformed value reported, not discarded
- **Why:** `_tolerance` returns `("", "")` on a `ValueError`, so an
  unreadable tolerance becomes **no** tolerance — a strictly tighter control
  than the suite, imported with no caveat and no unmapped entry. Every other
  threshold path in this package refuses rather than tightens.

### IMP-047 · `to_be_unique` and `compound_columns_to_be_unique` differ
- **Area:** `importers/great_expectations.py::_expectation`
- **Type:** functional
- **Priority:** P1
- **Precondition:** both expectations
- **Steps:** import
- **Expected:** the first carries the weaker-than-grain caveat; the second does
  not
- **Why:** "importing the first as though it were the second would silently
  weaken the control".

### IMP-048 · An exclusive bound is refused
- **Area:** `importers/great_expectations.py::_between`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `strict_min: true`
- **Steps:** import
- **Expected:** unmapped, "an exclusive bound would change which rows fail"
- **Why:** the third occurrence of the inclusive/exclusive rule in this
  catalogue (with IMP-016 and CTR-025), and the one place all three agree.

### IMP-049 · A one-sided range is refused with a remedy that is right
- **Area:** `importers/great_expectations.py::_between`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `min_value: 0` only; `max_value: 100` only
- **Steps:** import
- **Expected:** unmapped, with a remedy naming the comparison — and for the
  `max_value`-only case the remedy must say `<`, not `>`
- **Why:** the remedy is
  `f"CHECK {dataset}.{column} > {low if low is not None else high}"`, which
  emits `> 100` for a maximum-only bound. Following it literally inverts the
  check. Three shipped remedies already named commands that did not exist; this
  one names the wrong operator.

### IMP-050 · Row-count expectations accept one or both bounds
- **Area:** `importers/great_expectations.py::_row_count`
- **Type:** functional
- **Priority:** P2
- **Precondition:** min only, max only, both, neither
- **Steps:** import each
- **Expected:** `AT LEAST`, `AT MOST`, `BETWEEN`, and an unmapped entry
- **Why:** the one place a one-sided bound *is* expressible, which is why
  `_between` refuses it for columns and this does not for rows.

### IMP-051 · The dataset name comes from the suite name's last segment
- **Area:** `importers/great_expectations.py::read`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `expectation_suite_name: "warehouse.orders.critical"`; and
  a suite with neither name key
- **Steps:** import
- **Expected:** a dataset a control can be bound to, and the derivation visible
- **Why:** `.split(".")[-1]` gives `critical`, not `orders`; and a suite with
  no name at all gives the literal dataset `dataset`. Every control in the file
  is then written against a table that does not exist, and all of them parse.

### IMP-052 · A GE suite is read as JSON, not YAML
- **Area:** `importers/great_expectations.py::_parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `.json` suite and a YAML file
- **Steps:** `read_text` on each
- **Expected:** the JSON imports; the YAML fails with a readable error
- **Why:** the base class parses YAML and this importer overrides it; YAML is a
  superset of JSON, so the override exists to make the failure honest rather
  than to make it work.

### IMP-053 · An unmapped expectation names the risk of guessing
- **Area:** `importers/great_expectations.py::_expectation`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `expect_column_values_to_be_increasing`
- **Steps:** import
- **Expected:** unmapped with the remedy "several expectations differ from one
  another by a single keyword argument, and the wrong one looks exactly as
  convincing"
- **Why:** the honest reason, stated where it matters.

### IMP-054 · Whitespace collapse does not corrupt a control
- **Area:** `importers/great_expectations.py`, the `.replace("  ", " ")` calls
- **Type:** negative
- **Priority:** P2
- **Precondition:** an `in_set` whose values contain two consecutive spaces,
  e.g. `"NEW  YORK"`
- **Steps:** import; compare the emitted literal against the source
- **Expected:** the value preserved
- **Why:** the collapse is applied to the whole control string to tidy a
  missing threshold, and it rewrites data inside string literals. A value in a
  contract becomes a different value in the control derived from it.

### IMP-055 · `merged_with` combines two results without losing anything
- **Area:** `importers/spi.py::ImportResult.merged_with`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two results from different files
- **Steps:** merge
- **Expected:** controls, unmapped and caveats concatenated; `source_format`
  taken from the first non-empty
- **Why:** a dbt project is many schema.yml files, and a merge that dropped one
  file's unmapped list would report a complete migration.

## Catalogue integration — `integrate/`

### INT-001 · A badge with no date is refused at construction
- **Area:** `integrate/catalog.py::Badge.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `Badge(dataset='x', standing=HEALTHY, established_at='')`
- **Expected:** `ValidationError` — '"Trusted" on a table nobody has checked
  since March reads as current, and a reader has no way to tell'
- **Why:** "a badge without a date is a lie by omission", and this is the only
  place it is enforced.

### INT-002 · The rendered sentence is dated and scoped
- **Area:** `integrate/catalog.py::Badge.render`
- **Type:** functional
- **Priority:** P1
- **Precondition:** badges with `coverage='full'` and `coverage='partial'`
- **Steps:** `render()`
- **Expected:** the date always; ", over the rows examined (partial)" only on
  the second
- **Why:** "'passed' over the rows examined is a narrower claim than 'passed'".

### INT-003 · A failing badge names how many controls failed
- **Area:** `integrate/catalog.py::Badge.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 3 of 11 controls failing
- **Steps:** `render()`
- **Expected:** "checked and failing … — 3 of 11 control(s) failing"
- **Why:** a catalogue reader deciding whether to use the table needs the
  proportion, not the word.

### INT-004 · Five standings, and silence is not health
- **Area:** `integrate/catalog.py::Standing`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** every standing's `label` and `is_reassuring`
- **Expected:** `is_reassuring` True only for HEALTHY; every label a full
  sentence a non-technical reader can act on
- **Why:** "the temptation is to publish passes and stay quiet otherwise, which
  leaves a table looking unassessed when it is actually failing. Silence and
  health must not render the same."

### INT-005 · An uncovered dataset gets a badge
- **Area:** `integrate/catalog.py::badges_from`
- **Type:** functional
- **Priority:** P1
- **Precondition:** ten datasets, nine with records
- **Steps:** `badges_from(latest, datasets=..., established_at=...)`
- **Expected:** ten badges, the tenth `UNCOVERED` with the detail "no control
  covers this dataset"
- **Why:** "a catalogue showing a badge on nine tables and nothing on the tenth
  invites a reader to assume the tenth is fine".

### INT-006 · `UNPROVEN` is never produced
- **Area:** `integrate/catalog.py::badges_from`, `Standing.UNPROVEN`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dataset whose controls exist and have not run in the
  window
- **Steps:** `badges_from`
- **Expected:** `UNPROVEN`
- **Why:** the standing is defined, labelled, and constructed by nothing.
  `badges_from` has three outcomes — FAILING, NOT_ESTABLISHED, HEALTHY — so a
  dataset whose controls have not run in the window either carries a stale
  record and reads HEALTHY, or has no record and reads UNCOVERED. The middle
  state that `regulatory.Standing` treats as the whole point of the design is
  unreachable here.

### INT-007 · Failing beats not-established beats healthy
- **Area:** `integrate/catalog.py::badges_from`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a dataset with one `fail`, one `indeterminate` and three
  `pass` records
- **Steps:** `badges_from`
- **Expected:** `FAILING`, `failing_controls == 1`, `controls == 5`
- **Why:** the precedence is the whole of the badge's meaning, and an
  `indeterminate` must never be absorbed into a pass.

### INT-008 · The narrowest coverage wins
- **Area:** `integrate/catalog.py::badges_from`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two records, one `full` and one sampled
- **Steps:** `badges_from`
- **Expected:** `coverage == 'partial'`
- **Why:** "a dataset whose badge said 'full' because one control scanned
  everything, while another only sampled, would be claiming more than was
  established".

### INT-009 · The evidence reference points at an arbitrary record
- **Area:** `integrate/catalog.py::badges_from`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a FAILING dataset with five records, the failing one not
  first
- **Steps:** read `evidence_reference`
- **Expected:** the reference answers "show me" for the *failing* verdict
- **Why:** the code takes `records[0].record_hash`, and the order comes from
  iterating a dict of latest records. "The first response to a badge somebody
  disagrees with is 'show me', and a badge that cannot answer gets ignored from
  then on" — answering with a passing control's evidence is worse than not
  answering.

### INT-010 · A catalogue that cannot store a date is refused wholesale
- **Area:** `integrate/catalog.py::CatalogTarget.publish`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a target whose `supports` omits `established_at`
- **Steps:** publish forty badges
- **Expected:** nothing written; forty refusals, all with the same reason; the
  report saying "Nothing was written — all 40 refused for the same reason"
- **Why:** "refused wholesale rather than written undated. A badge without a
  date reads as current forever" — and the same-reason collapse stops a
  systemic problem looking like forty unlucky tables.

### INT-011 · A field the catalogue cannot store is reported as dropped
- **Area:** `integrate/catalog.py::CatalogTarget.publish`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the Alation target, which cannot store
  `evidence_reference`
- **Steps:** publish
- **Expected:** `dropped_fields == ('evidence_reference',)`, and the report
  saying those are "absent from it rather than shown as blank"
- **Why:** "so nobody reads an absent link as 'there was no evidence'".

### INT-012 · One rejected badge does not stop the rest
- **Area:** `integrate/catalog.py::CatalogTarget.publish`
- **Type:** functional
- **Priority:** P1
- **Precondition:** forty badges, one of which the target rejects
- **Steps:** publish
- **Expected:** 39 written, one refused by name, `complete` False
- **Why:** "a catalogue rejecting one table must not leave the other
  thirty-nine unwritten, because those thirty-nine then show yesterday's
  verdict with today's confidence".

### INT-013 · A partial write names the stale tables first
- **Area:** `integrate/catalog.py::WriteReport.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** seven refusals out of forty, for mixed reasons
- **Steps:** `describe()`
- **Expected:** the seven named first (five and an ellipsis), then the written
  count
- **Why:** "stale-but-present is worse than absent: it is a figure people act
  on".

### INT-014 · Nothing offered is stated, not reported as complete
- **Area:** `integrate/catalog.py::WriteReport.describe`, `complete`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `publish([])`
- **Steps:** `describe()`; read `complete`
- **Expected:** "nothing was written, because nothing was offered"; and
  `complete` is True, which must be reconciled with that sentence
- **Why:** `written == attempted` is `0 == 0`, so an empty publish reports a
  complete write-back. A scheduled job whose query returned nothing reports
  success.

### INT-015 · A residency refusal is per badge, not per run
- **Area:** `integrate/catalog.py::CatalogTarget.publish`, `Gate`
- **Type:** security
- **Priority:** P1
- **Precondition:** a gate refusing one jurisdiction; forty badges, three of
  them in it
- **Steps:** publish with the gate
- **Expected:** 37 written, 3 refused with the residency message
- **Why:** "a residency breach is not a reason to leave forty tables stale".

### INT-016 · A target with no region is not treated as domestic
- **Area:** `integrate/catalog.py::CatalogTarget.region`
- **Type:** security
- **Priority:** P1
- **Precondition:** a target with `region=''`, a tenant with a residency rule
- **Steps:** publish with a gate
- **Expected:** refused — "an unstated destination is not a domestic one"
- **Why:** the docstring makes this claim about the field; the enforcement is
  in `Gate.require`, and the two need testing together.

### INT-017 · The badge carries the subject's jurisdiction
- **Area:** `integrate/catalog.py::Badge.jurisdiction`
- **Type:** security
- **Priority:** P2
- **Precondition:** badges with and without a jurisdiction
- **Steps:** publish with a gate
- **Expected:** the one with no jurisdiction is handled explicitly, not
  defaulted to permitted
- **Why:** "the residency question is about the *subject*, and an egress that
  knows its destination but not its subject's home cannot answer it" —
  `badges_from` never sets it.

### INT-018 · Collibra writes to a mapped asset id, never a name
- **Area:** `integrate/vendors.py::CollibraTarget.write`
- **Type:** security
- **Priority:** P1
- **Precondition:** a badge for a dataset with no mapping
- **Steps:** publish
- **Expected:** refused with the reason "two systems in one estate can have a
  table with the same name, and a name-keyed write puts a trading badge on a
  finance table"
- **Why:** a cross-system mis-write is a wrong quality statement on somebody
  else's table, which is worse than no statement.

### INT-019 · An unmapped Alation object is refused
- **Area:** `integrate/vendors.py::AlationTarget.write`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a badge for an unmapped dataset; and one whose object id is
  `0`
- **Steps:** publish
- **Expected:** the first refused; the second **written** — `0` is a valid id
- **Why:** the guard is `if object_id is None`, deliberately not a truthiness
  test. An id of zero refused would be a table nobody can badge.

### INT-020 · DataHub constructs a URN and cannot verify it
- **Area:** `integrate/vendors.py::DataHubTarget.urn_for`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a `platform`/`env` pair that does not match the ingestion
  job's
- **Steps:** publish
- **Expected:** a refusal, or a report that the target could not confirm the
  dataset exists
- **Why:** the adapter's own docstring: "a URN that differs by its environment
  segment creates a second, empty dataset rather than failing, and the badge
  lands on a dataset nobody looks at". Unlike the other two targets, there is no
  mapping and no refusal path — the risk is documented and unmitigated.

### INT-021 · An unreachable target refuses every badge with one reason
- **Area:** `integrate/vendors.py::_VendorTarget._send`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a transport raising `ConnectionError`
- **Steps:** publish forty badges
- **Expected:** forty refusals collapsed into one sentence naming the reason
- **Why:** the systemic-problem collapse in `WriteReport.describe`, exercised
  through a real adapter.

### INT-022 · A missing asset is not created
- **Area:** `integrate/vendors.py::_VendorTarget._send`
- **Type:** security
- **Priority:** P1
- **Precondition:** a transport raising `LookupError`
- **Steps:** publish
- **Expected:** refused, naming the dataset and saying "Prama does not create
  assets, because an estate defined in two places disagrees with itself"
- **Why:** the `LookupError` branch exists solely for this, and the distinction
  between it and a generic failure is what makes the refusal actionable.

### INT-023 · Nothing in the adapters opens a socket
- **Area:** `integrate/vendors.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** import scan over the module
- **Expected:** no `socket`, `http`, `requests` or `httpx` import
- **Why:** "the transport is injected. Nothing here opens a socket, which is
  what lets all three be tested — and lets a deployment substitute a client
  with its own mTLS, proxy, retry and rate-limit policy already applied."

### INT-024 · None of the three is verified against a live server
- **Area:** `integrate/vendors.py` module docstring
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the request shapes against each vendor's published API;
  confirm the caveat is reproduced wherever the adapters are advertised
- **Expected:** the caveat appears in the user-facing docs, not only in the
  source
- **Why:** "what is verified here is the adapter's own behaviour — what it
  sends, what it drops, and what it refuses — not that a real Collibra accepts
  it. That distinction is recorded rather than left to be assumed from the
  presence of a test suite."

### INT-025 · The reference target exercises the contract without a licence
- **Area:** `integrate/catalog.py::RecordingTarget`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** run the full `publish` contract against `RecordingTarget` with
  every `supports` combination and a `refuse` list
- **Expected:** the same behaviour the three vendor adapters show
- **Why:** "an SPI whose only implementation is behind a vendor's login is an
  SPI nobody can test" — this is the conformance harness, and it has to cover
  the paths the vendors take.

### INT-026 · A manifest that drops a dataset never deletes it
- **Area:** `integrate/operator.py::plan`
- **Type:** security
- **Priority:** P1
- **Precondition:** a stored dataset absent from the manifest
- **Steps:** `plan(spec, stored)`
- **Expected:** `ORPHANED`, no delete verb anywhere in the plan
- **Why:** "removing a dataset from a manifest means the manifest stopped
  mentioning it, which is not the same as the business retiring it. Deletion
  would take its controls and its evidence with it, and evidence is the thing
  this product exists to keep."

### INT-027 · A person's declaration is a conflict, not an overwrite
- **Area:** `integrate/operator.py::plan`
- **Type:** security
- **Priority:** P1
- **Precondition:** a stored dataset with no `managedBy`, differing from the
  manifest
- **Steps:** `plan`
- **Expected:** `CONFLICT`, naming the differing fields
- **Why:** "the Kubernetes instinct is that desired state wins, and applied
  here it would silently overwrite a declaration a business owner made in the
  console — the one place the product insists a human states meaning".

### INT-028 · The operator's own declaration is amended
- **Area:** `integrate/operator.py::plan`, `MANAGED_BY`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a stored dataset with `managedBy: prama-operator`
- **Steps:** `plan`
- **Expected:** `AMEND` with the differing fields named
- **Why:** the counterpart of INT-027, and the reason the stamp is applied on
  the way in rather than afterwards.

### INT-029 · Only the declared fields are compared
- **Area:** `integrate/operator.py::COMPARED`, `plan`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a stored dataset carrying an owner and a rhythm the
  manifest does not mention
- **Steps:** `plan`
- **Expected:** `UNCHANGED`
- **Why:** "the console holds facts a manifest never carries — an owner, a
  rhythm — and treating their absence as a difference would make every dataset
  conflict forever".

### INT-030 · A list-valued field compares by value, not identity
- **Area:** `integrate/operator.py::_normalise`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `grain: [a, b]` on both sides, one as a list and one as a
  tuple; then `[a, b]` against `[b, a]`
- **Steps:** `plan`
- **Expected:** the first `UNCHANGED`; the second a difference
- **Why:** a grain's column order is meaningful, and normalising to a tuple
  preserves it — normalising to a set would not, and would hide a real change.

### INT-031 · A manifest entry with no name
- **Area:** `integrate/operator.py::plan`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `datasets: [{description: "x"}]`
- **Steps:** `plan`
- **Expected:** a refusal or a named problem
- **Why:** `str(item.get("name",""))` makes the key `''`, so the plan says
  `CREATE` for a dataset called "" — and the controller then applies it.

### INT-032 · Ready is never claimed over a conflict
- **Area:** `integrate/operator.py::Plan.conditions`, `is_settled`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a plan with one conflict and every write applied
- **Steps:** `conditions(generation=3, applied=n)`
- **Expected:** `status: "False"`, reason `NeedsDecision`
- **Why:** "a status of Ready over that is a lie the cluster will repeat every
  thirty seconds".

### INT-033 · Planned-but-not-applied is distinct from applied-and-clean
- **Area:** `integrate/operator.py::Plan.conditions`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a settled plan with two writes
- **Steps:** `conditions(applied=None)` and `conditions(applied=2)`
- **Expected:** `NotApplied`/False, then `Reconciled`/True
- **Why:** "a condition that conflated them would report Ready on a reconcile
  that never ran" — the dry-run and the real run share this function.

### INT-034 · A partial apply is reported as partial
- **Area:** `integrate/operator.py::Plan.conditions`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a plan with forty writes, twelve applied
- **Steps:** `conditions(applied=12)`
- **Expected:** `PartiallyApplied`, not Ready, with the message "12 of 40
  write(s) landed; the rest are in a state nobody knows"
- **Why:** "twelve of forty applied and *stated as twelve* is recoverable;
  twelve of forty reported as forty is not".

### INT-035 · The plan's summary leads with the conflicts
- **Area:** `integrate/operator.py::Plan.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 2 conflicts, 3 orphans, 18 unchanged
- **Steps:** `describe()`
- **Expected:** the conflicts first, named
- **Why:** "a summary leading with '18 unchanged' buries them", and they are
  the only part a human must act on.

### INT-036 · A failed write stops the batch and says where
- **Area:** `integrate/controller.py::Controller.reconcile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a store whose fifth apply raises
- **Steps:** reconcile
- **Expected:** `applied == 4`, `failed_at` naming the fifth dataset, the
  remaining writes not attempted, and the status condition `WriteFailed`
- **Why:** "continuing past a failure produces a resource whose status counts
  successes and whose cluster holds an unknown mixture".

### INT-037 · Status is written on the failing path
- **Area:** `integrate/controller.py::Controller._write_status`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a failing apply
- **Steps:** reconcile; read the resource's status
- **Expected:** written, with `observedGeneration`, the applied count, and the
  conflict and orphan counts
- **Why:** "a reconcile that hit a conflict and wrote no status leaves the
  resource looking untouched, and the operator appears not to be running".

### INT-038 · `observedGeneration` is the generation that was read
- **Area:** `integrate/controller.py::Controller.reconcile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a manifest whose generation changes during the reconcile
- **Steps:** reconcile
- **Expected:** the status names the generation read at the top
- **Why:** "a status saying Ready is a statement about a version somebody can
  point at, rather than about whichever version happens to be current when the
  write lands".

### INT-039 · A terminating resource is left alone
- **Area:** `integrate/controller.py::Controller.reconcile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a resource with a `deletionTimestamp`
- **Steps:** reconcile
- **Expected:** skipped, no status write, no applies
- **Why:** "writing status onto something that is going away … at best does
  nothing and at worst blocks the deletion" — the one documented exception to
  status-on-every-path.

### INT-040 · A manifest with no tenant is skipped and says so
- **Area:** `integrate/controller.py::Controller.reconcile`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a spec with no `tenant`
- **Steps:** reconcile
- **Expected:** skipped with the reason, and the status written
- **Why:** unlike the deletion case, this one *does* write status — an
  operator staring at a resource needs to see why nothing happened.

### INT-041 · A status-write failure aborts the remaining resources
- **Area:** `integrate/controller.py::Controller.reconcile_all`
- **Type:** negative
- **Priority:** P1
- **Precondition:** three resources, the first of which fails its status write
- **Steps:** `reconcile_all`
- **Expected:** the other two still reconciled, or the abort documented
- **Why:** `_write_status` raises `ClusterError`, and `reconcile_all` builds a
  tuple by comprehension — so one resource's transient status failure silently
  skips every resource after it, on a loop whose whole contract is "a failure
  in one must not take the others down".

### INT-042 · Nothing here can approve or activate anything
- **Area:** `integrate/operator.py` module claim · `controller.py::_payload`
- **Type:** security
- **Priority:** P1
- **Precondition:** a manifest attempting to set an approval, a control state
  or a suppression
- **Steps:** reconcile
- **Expected:** the extra keys are not applied as approvals
- **Why:** "a cluster admin with `kubectl` must not be able to make a control
  pass". `_payload` returns `{**declared, "managedBy": MANAGED_BY}` — the whole
  manifest fragment, unfiltered — so what the store accepts from it is the only
  boundary, and the claim is made here while the enforcement is elsewhere.

### INT-043 · A reconcile is idempotent
- **Area:** `integrate/controller.py::Controller.reconcile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a manifest already applied
- **Steps:** reconcile twice
- **Expected:** the second produces no writes, all `UNCHANGED`, and Ready
- **Why:** the error remedy promises it — "Kubernetes will call this again, and
  the reconcile is idempotent" — and the loop runs every thirty seconds
  forever.

## Lineage — `lineage/`

### LIN-001 · A column must be qualified
- **Area:** `lineage/graph.py::Column.parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `Column.parse('amount')`; `Column.parse('schema.table.amount')`;
  `Column.parse('.amount')`
- **Expected:** the first raises with the reason "two columns called `amount`
  in different tables become one node and the graph is wrong everywhere"; the
  second gives dataset `schema.table`; the third raises
- **Why:** an unqualified node merges two tables' columns, which produces an
  impact list naming a report that does not read the column at all.

### LIN-002 · Each transform's attenuation is what it claims
- **Area:** `lineage/graph.py::Transform.attenuation`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read all six
- **Expected:** identity 1.0, rename 1.0, derived 0.7, aggregated 0.35, filter
  0.9, join key 0.8
- **Why:** these six constants decide every impact list. "An impact analysis
  that treats these alike produces a list of four hundred 'affected' assets,
  which is the same as producing no list."

### LIN-003 · A filter is barely attenuated
- **Area:** `lineage/graph.py::Transform.FILTER`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a chain of three filter edges
- **Steps:** blast radius
- **Expected:** 0.9³ ≈ 0.73 at the end — still well above the floor
- **Why:** "a wrong filter changes the population rather than a value, and a
  missing population is not a diluted problem". An aggregate at 0.35 dilutes
  much faster, which is the intended asymmetry.

### LIN-004 · The strongest path to a node wins
- **Area:** `lineage/graph.py::LineageGraph.blast_radius`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a node reachable directly (identity) and through an
  aggregate
- **Steps:** blast radius
- **Expected:** impact 1.0, depth 1, and the path showing the direct edge
- **Why:** "reporting the attenuated figure because it was discovered first
  would understate it" — and breadth-first discovery finds the short path
  first only when the graph is well-behaved.

### LIN-005 · A longer but stronger path replaces a shorter weaker one
- **Area:** `lineage/graph.py::blast_radius`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a node reachable in one aggregated hop (0.35) and in three
  identity hops (1.0)
- **Steps:** blast radius
- **Expected:** impact 1.0, depth 3, and the three-edge path
- **Why:** the counterfactual to LIN-004; a first-wins implementation passes
  LIN-004 by accident and fails this.

### LIN-006 · A cycle terminates
- **Area:** `lineage/graph.py::blast_radius`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a three-node cycle of identity edges
- **Steps:** blast radius with the default floor
- **Expected:** terminates; each node reached once
- **Why:** "a table feeding a table that feeds it back through a different path
  is an ordinary warehouse, not a modelling error, and a traversal that assumes
  a DAG will find out in production". Note that a cycle of *pure identity*
  edges never attenuates, so termination depends entirely on the
  strictly-stronger revisit rule and on the depth limit.

### LIN-007 · A cycle of identity edges terminates by depth, not by attenuation
- **Area:** `lineage/graph.py::blast_radius`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a two-node identity cycle
- **Steps:** blast radius; read `truncated`
- **Expected:** terminates, and whether it reports truncation is stated
- **Why:** the comment says "cycles terminate because attenuation is at most 1
  and a revisit only continues when it is strictly stronger, which cannot
  happen forever" — which holds for attenuation *below* 1 and for the
  strictly-greater test. With `IDENTITY` at exactly 1.0 the first claim does
  nothing and only the second is load-bearing. Worth pinning as the reason.

### LIN-008 · Traversal stops at the depth limit and says so
- **Area:** `lineage/graph.py::MAXIMUM_DEPTH`, `BlastRadius.truncated`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a chain of 15 identity edges
- **Steps:** blast radius with the default
- **Expected:** 12 nodes reached, `truncated` True, and the summary saying "a
  graph deeper than that has a modelling problem worth looking at on its own"
- **Why:** a silently truncated impact list is one that says a report is not
  affected when it is.

### LIN-009 · `truncated` is set even when nothing lay beyond
- **Area:** `lineage/graph.py::blast_radius`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a chain of exactly 12 identity edges, the last node having
  no outgoing edges
- **Steps:** blast radius
- **Expected:** `truncated` False — the traversal reached the edge of the
  graph, not the limit
- **Why:** the loop sets `truncated = True` whenever a frontier item's depth
  reaches the maximum, regardless of whether that node has any outgoing edges.
  A complete answer is reported as incomplete, and the summary tells the reader
  their warehouse has a modelling problem.

### LIN-010 · Below-floor nodes are counted, not listed
- **Area:** `lineage/graph.py::IMPACT_FLOOR`, `below_floor`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a graph where 380 nodes fall below 1%
- **Steps:** blast radius
- **Expected:** they are absent from `reached` and the count appears in the
  summary
- **Why:** "a column contributing a thousandth of an aggregate is not
  'affected' in any sense the reader means, and including it is how an impact
  list becomes something nobody opens".

### LIN-011 · `below_floor` counts edges, not columns
- **Area:** `lineage/graph.py::blast_radius`
- **Type:** negative
- **Priority:** P2
- **Precondition:** one below-floor column reachable by five separate paths
- **Steps:** blast radius; read `below_floor`
- **Expected:** 1
- **Why:** the counter increments on every traversal that falls below the
  floor, so one column reachable five ways is reported as five. The summary
  says "380 more are downstream at under 1%", which is a statement about
  columns and is computed over edges. The same over-count class as finding C10.

### LIN-012 · The floor boundary is exact
- **Area:** `lineage/graph.py::blast_radius`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** paths giving carried impact of exactly 0.01, and just below
- **Steps:** blast radius
- **Expected:** the 0.01 node included (`carried < floor` is strict), the other
  excluded
- **Why:** the strictness decides which of two adjacent nodes an incident
  report mentions, and floating-point products of attenuations land on the
  boundary more often than they should.

### LIN-013 · The origin is not in its own blast radius
- **Area:** `lineage/graph.py::blast_radius`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a self-loop on the origin column
- **Steps:** blast radius
- **Expected:** a stated answer
- **Why:** the frontier starts at the origin with impact 1.0 and `best` is
  populated only from edge targets — so a self-loop puts the origin into its
  own reached set at depth 1, and the impact list says a column is affected by
  itself.

### LIN-014 · An empty graph and an unknown origin
- **Area:** `lineage/graph.py::blast_radius`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty graph; a column not in the graph
- **Steps:** blast radius on both
- **Expected:** "nothing downstream of x" in both — and a caller can tell
  "nothing reads this" from "this column is not in the graph"
- **Why:** the two answers are identical and mean opposite things: one says the
  column is a leaf, the other says the lineage was never scanned.

### LIN-015 · `worst` ranks by impact then name
- **Area:** `lineage/graph.py::BlastRadius.worst`
- **Type:** functional
- **Priority:** P2
- **Precondition:** ten reached nodes, three at equal impact
- **Steps:** `worst(5)`
- **Expected:** highest impact first, ties broken by qualified name,
  deterministic across runs
- **Why:** an incident report that reorders between two runs of the same query
  is one nobody trusts.

### LIN-016 · A reached node renders its route
- **Area:** `lineage/graph.py::Reached.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a three-hop path
- **Steps:** `describe()`
- **Expected:** "x at 34% of the defect, 3 hops away: a.b → c.d → e.f → g.h"
- **Why:** "the path taken, so the answer can be checked rather than trusted",
  and the pluralisation of "hop" is on the sentence somebody reads at seven in
  the morning.

### LIN-017 · `sources_of` returns upstream columns nearest first
- **Area:** `lineage/graph.py::sources_of`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column with two direct and three indirect sources
- **Steps:** `sources_of(column)`
- **Expected:** the two direct ones first, then the others, deterministic
- **Why:** "the nearest cause is the likeliest, and a ranked list beats a set
  when somebody has twenty minutes".

### LIN-018 · `sources_of` terminates on a cycle and bounds its depth
- **Area:** `lineage/graph.py::sources_of`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an upstream cycle; and a chain deeper than the limit
- **Steps:** `sources_of`
- **Expected:** terminates; the depth truncation is visible to the caller
- **Why:** the upstream traversal has no `truncated` flag at all, so a root
  cause thirteen hops up is simply absent with nothing said.

### LIN-019 · `paths` finds every route
- **Area:** `lineage/graph.py::paths`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two distinct routes from a source to a target
- **Steps:** `list(paths(source, target))`
- **Expected:** both
- **Why:** "'why does this number depend on that one?' often has two answers,
  and showing one of them is how somebody fixes a path and finds the number
  still wrong".

### LIN-020 · `paths` does not loop on a cycle
- **Area:** `lineage/graph.py::paths`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a cycle between the source and the target
- **Steps:** enumerate the paths
- **Expected:** finite; the `visited` set prevents revisiting a node on one
  path
- **Why:** the visited set is per-path rather than global, which is correct for
  path enumeration and is the expensive kind of correct — bound the count too.

### LIN-021 · `paths` does not continue through the target
- **Area:** `lineage/graph.py::paths`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a graph where the target feeds a node that feeds the target
  again
- **Steps:** enumerate
- **Expected:** a stated answer
- **Why:** the loop yields and `continue`s when it sees the target, so a route
  that passes *through* the target and returns to it is never found — right for
  most questions, and unstated.

### LIN-022 · The table-level view is derived
- **Area:** `lineage/graph.py::dataset_edges`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column graph with intra-table and inter-table edges
- **Steps:** `dataset_edges()`
- **Expected:** only the inter-table pairs, deduplicated, order stable
- **Why:** "a table graph maintained beside a column graph drifts from it, and
  the drift is invisible until an impact analysis names a table nothing
  actually reads".

### LIN-023 · Orphans are columns nothing reads
- **Area:** `lineage/graph.py::orphans`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a graph with a leaf column, a source column and an isolated
  one
- **Steps:** `orphans()`
- **Expected:** the leaf only — a source column with outgoing edges is not an
  orphan
- **Why:** "an orphan is either dead weight to be retired or a gap in the
  lineage, and both are worth knowing. It is also the number that tells you how
  complete the graph is."

### LIN-024 · The orphan rate says how complete the graph is
- **Area:** `lineage/graph.py::orphans`, `columns`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a graph where 80% of columns are orphans
- **Steps:** compute the ratio
- **Expected:** the product surfaces it somewhere — "a warehouse where eighty
  percent of columns are orphans has not been scanned properly"
- **Why:** the docstring makes the claim and nothing computes the number.

### LIN-025 · `merge` keeps duplicate edges deliberately
- **Area:** `lineage/graph.py::merge`, `LineageGraph.__len__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two scanners producing the same edge
- **Steps:** merge; read `len(graph)` and the blast radius
- **Expected:** the edge counted twice in `len`, and the traversal unaffected
- **Why:** "two scanners agreeing is worth knowing and the traversal takes the
  strongest path anyway" — but `len(graph)` is then an edge count that
  over-reports, and it is the obvious number to put on a coverage screen.

### LIN-026 · A merged graph's blast radius equals the union's
- **Area:** `lineage/graph.py::merge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two graphs with overlapping and disjoint edges
- **Steps:** compare `merge([a,b]).blast_radius(x)` against a graph built from
  the union of their edges
- **Expected:** identical
- **Why:** "the union is the only complete picture", and a merge that dropped
  an edge would produce an impact list missing a consumer.

### LIN-027 · SQL lineage reads a simple INSERT … SELECT
- **Area:** `lineage/sql.py::SqlLineage.extract`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `INSERT INTO t (a, b) SELECT x, y FROM s`
- **Steps:** extract
- **Expected:** two edges, `s.x → t.a` and `s.y → t.b`, both IDENTITY
- **Why:** the base case, and the one where target-column positional mapping
  from the INSERT list is exercised.

### LIN-028 · An aliased expression names its target column
- **Area:** `lineage/sql.py::_split_alias`, `_implied_name`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `SELECT sum(amount) AS total, price FROM trades`
- **Steps:** extract
- **Expected:** `trades.amount → t.total` as AGGREGATED, and
  `trades.price → t.price` as IDENTITY
- **Why:** the implicit-name case is what makes a bare column edge possible at
  all, and the alias is what names an expression's output.

### LIN-029 · An expression with no alias and no obvious name is a gap
- **Area:** `lineage/sql.py::_statement`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `SELECT a + b FROM s` with no INSERT column list
- **Steps:** extract
- **Expected:** an `unnamed_output` gap quoting the expression
- **Why:** "a lineage graph that quietly drops a CASE expression looks the same
  as one that handled it, and the impact analysis built on it is wrong in a way
  nobody can see".

### LIN-030 · `discount(` is read as an aggregate
- **Area:** `lineage/sql.py::_transform`, `_AGGREGATES`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `SELECT discount(price) AS p FROM t`; and
  `SELECT checksum(x) AS c FROM t`
- **Steps:** extract; read the transform
- **Expected:** `DERIVED`
- **Why:** the test is `any(f"{name}(" in lowered for name in _AGGREGATES)`, a
  substring match with no word boundary. `discount(` contains `count(` and
  `checksum(` contains `sum(`, so both are classified `AGGREGATED` — which
  attenuates the edge to 0.35 and can push a genuinely affected column below
  the impact floor. An incident report then omits a consumer.

### LIN-031 · A cast and a coalesce are renames
- **Area:** `lineage/sql.py::_transform`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `CAST(a AS TEXT)` and `COALESCE(a, 0)`
- **Steps:** extract
- **Expected:** `RENAME` for both — attenuation 1.0
- **Why:** "still essentially the same value", so a defect arrives intact and
  the impact list must say so.

### LIN-032 · An ambiguous unqualified column is reported, not guessed
- **Area:** `lineage/sql.py::_references`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `SELECT amount FROM a JOIN b ON a.id = b.id` with no schema
- **Steps:** extract
- **Expected:** an `ambiguous` gap naming both candidates and saying "supply
  the schema and this resolves"; no edge
- **Why:** "picking one produces an edge that is wrong half the time".

### LIN-033 · A schema resolves the ambiguity
- **Area:** `lineage/sql.py::SqlLineage(schema=…)`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same SQL with a schema saying only `a` has `amount`
- **Steps:** extract
- **Expected:** one edge from `a.amount`, no gap
- **Why:** the counterfactual to LIN-032, and the reason the schema parameter
  exists.

### LIN-034 · A single source resolves an unqualified column
- **Area:** `lineage/sql.py::_references`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `INSERT INTO t SELECT amount FROM s`
- **Steps:** extract
- **Expected:** one edge from `s.amount`
- **Why:** "refusing here would make the parser useless on exactly the simple
  views that make up most of a legacy estate".

### LIN-035 · Every table after the first in a join is found
- **Area:** `lineage/sql.py::_FROM`, `_ALIAS_STOP`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `FROM a JOIN b ON … LEFT JOIN c ON …`
- **Steps:** `_sources`
- **Expected:** all three tables and their aliases
- **Why:** the recorded bug — "without the lookahead, `FROM a JOIN b` matches
  with alias='JOIN', the regex consumes it, and `finditer` resumes past the
  joined table — so every table after the first was silently dropped and the
  extractor produced a confident half-graph".

### LIN-036 · Every keyword in `_ALIAS_STOP` is exercised
- **Area:** `lineage/sql.py::_ALIAS_STOP`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `FROM a WHERE`, `FROM a GROUP BY`, `FROM a UNION`,
  `FROM a CROSS JOIN b`, `FROM a USING (x)`, `FROM a ORDER BY`
- **Steps:** `_sources` for each
- **Expected:** no keyword captured as an alias
- **Why:** each omission from the list is a silently dropped table, and the
  list is nineteen words long with no test naming them individually.

### LIN-037 · An alias colliding with a table name
- **Area:** `lineage/sql.py::_sources`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `FROM orders o JOIN customers orders`
- **Steps:** `_sources`; extract
- **Expected:** a gap or a stated resolution
- **Why:** `sources[alias] = table` and `sources[table] = table` write into one
  dict, so the second table's alias overwrites the first table's own name and
  every unaliased reference to `orders` resolves to `customers`. Every edge
  from that statement is then wrong and none of them is reported as a gap.

### LIN-038 · A statement with no target is a gap, not an edge
- **Area:** `lineage/sql.py::_statement`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a bare `SELECT a FROM b`
- **Steps:** extract
- **Expected:** a `no_target` gap — "a bare SELECT tells you what was read and
  not where it went"
- **Why:** producing an edge to nowhere would put a phantom node in the graph.

### LIN-039 · A VALUES insert is not a parse failure
- **Area:** `lineage/sql.py::_statement`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `INSERT INTO t (a) VALUES (1)`
- **Steps:** extract
- **Expected:** a `no_source` gap, not `unparsed`
- **Why:** "it genuinely has no lineage … and classifying it as unparsed would
  put it in the pile of things somebody should go and improve the parser for" —
  and `understood` is computed from the `unparsed` count.

### LIN-040 · `understood` reflects statements that produced nothing
- **Area:** `lineage/sql.py::Extraction.understood`
- **Type:** functional
- **Priority:** P1
- **Precondition:** ten statements, three unparsed
- **Steps:** read `understood`
- **Expected:** 0.7
- **Why:** "a scanner that parsed forty percent of a package and says nothing
  is worse than one that parsed forty percent and says so, because the graph it
  produces looks complete".

### LIN-041 · A WHERE clause produces filter edges
- **Area:** `lineage/sql.py::_filter_edges`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `INSERT INTO t SELECT a FROM s WHERE region = 'EU'`
- **Steps:** extract
- **Expected:** an edge `s.region → t.*` with `FILTER`
- **Why:** "a lineage graph that only follows the SELECT list misses it
  entirely, so the impact analysis says the filter column has no consumers".

### LIN-042 · The `*` filter target is a real node
- **Area:** `lineage/sql.py::_filter_edges`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the graph from LIN-041
- **Steps:** `columns_of('t')`; `orphans()`; `blast_radius` from the filter
  column
- **Expected:** a stated meaning for `t.*`
- **Why:** the synthetic node appears in `columns`, in `columns_of`, in
  `orphans` and in every impact list as "t.\*" — a column name no reader will
  recognise and no catalogue will resolve.

### LIN-043 · A CTE is not resolved to its underlying tables
- **Area:** `lineage/sql.py::_statement`, `_SELECT`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `INSERT INTO t WITH c AS (SELECT a FROM s) SELECT a FROM c`
- **Steps:** extract
- **Expected:** either resolved through the CTE, or a gap saying the CTE was
  not followed
- **Why:** `_SELECT` is non-greedy to the **first** `from`, so the CTE's own
  SELECT is what gets parsed and the outer one is not. A CTE is the ordinary
  shape of a modern warehouse view, and the graph produced is wrong with no
  gap recorded.

### LIN-044 · A subquery in the SELECT list
- **Area:** `lineage/sql.py::_SELECT`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `INSERT INTO t SELECT (SELECT max(x) FROM u) AS m, a FROM s`
- **Steps:** extract
- **Expected:** a gap, or correct edges
- **Why:** the same non-greedy-to-first-`from` problem: the SELECT body is cut
  at the subquery's `FROM`, so `a` is never seen and the target column list is
  misaligned.

### LIN-045 · A UNION is read as one statement
- **Area:** `lineage/sql.py::_statement`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `INSERT INTO t SELECT a FROM s1 UNION ALL SELECT a FROM s2`
- **Steps:** extract
- **Expected:** edges from both sides, or a gap naming the UNION
- **Why:** only the first SELECT is matched, so the second branch's source
  table contributes no edges and nothing is reported. The impact analysis then
  says `s2` feeds nothing.

### LIN-046 · Statement splitting survives a semicolon in a string
- **Area:** `lineage/sql.py::extract`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a statement containing `WHERE note = 'a;\nb'`
- **Steps:** extract
- **Expected:** one statement
- **Why:** the split is on `;\s*(?:\n|$)`, which a semicolon-newline inside a
  literal satisfies — producing two fragments, one of which is unparsed, and a
  `understood` figure that says the file is worse than it is.

### LIN-047 · Quoted and bracketed identifiers are cleaned
- **Area:** `lineage/sql.py::_clean`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `INSERT INTO [dbo].[Orders]`, `"schema"."table"`,
  `` `db`.`t` ``
- **Steps:** `_target`
- **Expected:** the delimiters removed and the dotted name preserved
- **Why:** a target name carrying a bracket becomes a dataset nothing else in
  the estate is called, and the graph silently forks.

### LIN-048 · A T-SQL procedure's statements are extracted
- **Area:** `lineage/scan.py::ProceduralSqlScanner`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `CREATE PROCEDURE … AS BEGIN … INSERT … SELECT … END`
- **Steps:** scan
- **Expected:** edges attributed to the procedure name as `produced_by`
- **Why:** "the lineage in those systems is the lineage that matters, because
  it is where the reporting layer actually comes from".

### LIN-049 · Dynamic SQL is reported, not ignored
- **Area:** `lineage/scan.py::ProceduralSqlScanner.opaque`
- **Type:** functional
- **Priority:** P1
- **Precondition:** procedures using `EXEC(@sql)`, `sp_executesql`,
  `EXECUTE IMMEDIATE`, and a cursor opened over a variable
- **Steps:** scan each
- **Expected:** a `dynamic_sql` gap for each, saying "this is where the
  interesting lineage usually hides"
- **Why:** "a graph that silently omits it is complete-looking and wrong".

### LIN-050 · The procedural stripper removes a CASE's END
- **Area:** `lineage/scan.py::_strip_procedural`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a procedure containing
  `SELECT CASE WHEN a > 0 THEN b ELSE c END AS d FROM t`
- **Steps:** scan
- **Expected:** the CASE expression parsed and an edge produced
- **Why:** the pattern `\b(begin|end)\b\s*;?` strips every `END`, including the
  one closing a CASE — and the stripper's own docstring says it is
  "conservative on purpose … because a stripper that removes too much turns a
  readable statement into an unparseable one and the loss is silent". A CASE is
  the single most common expression in a reporting procedure.

### LIN-051 · A `DECLARE` block does not swallow the statement after it
- **Area:** `lineage/scan.py::_strip_procedural`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a PL/SQL block whose `DECLARE` section has no terminating
  semicolon before the first statement
- **Steps:** scan
- **Expected:** the following statements still extracted
- **Why:** `\bdeclare\b[^;]*;` consumes everything up to the next semicolon, so
  a declaration section written without one eats the first real statement.

### LIN-052 · Comments are stripped before parsing
- **Area:** `lineage/scan.py::_strip_procedural`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a procedure with `--` and `/* */` comments, including one
  containing the word `FROM`
- **Steps:** scan
- **Expected:** the commented text contributes no sources
- **Why:** a commented-out join is a table the graph would otherwise claim is
  read.

### LIN-053 · A comment marker inside a string literal
- **Area:** `lineage/scan.py::_strip_procedural`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `WHERE note = 'a -- b'`
- **Steps:** scan
- **Expected:** the literal preserved, or a gap
- **Why:** the comment regex has no string awareness, so the rest of the line
  is deleted — silently changing a WHERE clause and therefore the filter edges
  derived from it.

### LIN-054 · A file with no routine is still scanned
- **Area:** `lineage/scan.py::ProceduralSqlScanner.scan`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a plain SQL file
- **Steps:** scan
- **Expected:** edges extracted; `units_found == 1` with the count's meaning
  clear
- **Why:** `max(1, len(routines))` reports one unit for a file containing none,
  so `coverage` is computed against an invented denominator.

### LIN-055 · An ETL mapping is read with the configured shape
- **Area:** `lineage/scan.py::XmlMappingScanner`
- **Type:** functional
- **Priority:** P1
- **Precondition:** XML in the documented PowerCenter shape
- **Steps:** scan with `POWERCENTER`
- **Expected:** one edge per connector, with the instance names as datasets
- **Why:** the base case for a scanner whose whole design is configurability.

### LIN-056 · A wrong shape reports misconfiguration, not emptiness
- **Area:** `lineage/scan.py::XmlMappingScanner.scan`
- **Type:** functional
- **Priority:** P1
- **Precondition:** DataStage XML scanned with the SSIS shape
- **Steps:** scan
- **Expected:** `misconfigured` set, naming the element looked for, the element
  count and a sample of the tags actually present
- **Why:** "turns 'this does not work' into 'the configuration is wrong, here
  is what was in the file', and the second is a morning's work rather than a
  procurement problem".

### LIN-057 · A genuinely empty file is not reported as misconfigured
- **Area:** `lineage/scan.py::XmlMappingScanner.scan`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `<root/>`
- **Steps:** scan
- **Expected:** no `misconfigured` — the guard is `len(list(root.iter())) > 1`
- **Why:** "distinguished from an empty file, because one is a bug and the
  other is a fact".

### LIN-058 · Malformed XML is a gap and a misconfiguration
- **Area:** `lineage/scan.py::XmlMappingScanner.scan`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a truncated export; a binary file
- **Steps:** scan
- **Expected:** an `unparsed` gap and a `misconfigured` message; no exception
- **Why:** a repository export that failed halfway is what an evaluation
  actually hands this.

### LIN-059 · Coverage can exceed one or go negative
- **Area:** `lineage/scan.py::ScanResult.coverage`
- **Type:** negative
- **Priority:** P1
- **Precondition:** one mapping containing five incomplete links
- **Steps:** scan; read `coverage`
- **Expected:** a fraction between 0 and 1
- **Why:** `units_unread` is set to the number of *gaps* while `units_found` is
  the number of *mappings*, so five bad links in one mapping give
  `(1 - 5) / 1 = -4.0` and the summary prints "-400% complete". The two
  counters measure different things.

### LIN-060 · An incomplete link is reported with its context
- **Area:** `lineage/scan.py::XmlMappingScanner.scan`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a connector missing `TOFIELD`
- **Steps:** scan
- **Expected:** a gap naming the mapping, the element and both attributes, and
  saying it may be the shape or a genuinely unbound link
- **Why:** the ambiguity is real and stating it is what makes the gap
  actionable.

### LIN-061 · The SSIS shape maps a lineage id, not a column name
- **Area:** `lineage/scan.py::SSIS`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** an SSIS package in the documented shape
- **Steps:** scan; read the edges' source column names
- **Expected:** the limitation stated — the source is a numeric lineage id
- **Why:** `from_attribute="lineageId"` produces `Column(name='73')`, which
  joins to nothing in the estate and appears in an impact list as a number.
  The shape is declared unverified, and this is the specific way it is wrong.

### LIN-062 · Every scanner states what it was verified against
- **Area:** `lineage/scan.py::Scanner.verified_against`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** read it on all six from `default_scanners`
- **Expected:** non-empty on each, and each distinguishing "verified" from
  "written against the documentation"
- **Why:** "a capability list that does not distinguish 'verified' from
  'written against the documentation' is a capability list that will be quoted
  in a procurement document".

### LIN-063 · A scan result's coverage sentence is present when it matters
- **Area:** `lineage/scan.py::ScanResult.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a scan with unread units
- **Steps:** `describe()`
- **Expected:** "the graph from this source is N% complete and anything built
  on it should say so"
- **Why:** "coverage is reported, always", and a graph that looks complete is
  the failure the whole module is written against.
