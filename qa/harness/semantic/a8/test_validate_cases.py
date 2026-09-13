"""IND-001..016 -- induce/validate.py"""
from __future__ import annotations

import dataclasses

from prama.induce.validate import (
    Gate, Rejection, SandboxResult, Validated, Validator, MAXIMUM_VIOLATION_RATE,
    SANDBOX_ROWS, _hostile_values, _subject_of, _strip_fencing,
)
from prama.pql.types import Catalogue
from prama.pql.parser import parse_control

CATALOGUE = Catalogue.of(trades={"side": "text", "qty": "number", "ccy": "text", "lei": "text"})
ROWS = [{"side": "BUY", "qty": 10, "ccy": "EUR", "lei": "5493001KJTIIGC8Y1R12"}] * 60


def V(**kw):
    return Validator(catalogue=CATALOGUE, codelists={"iso4217": ("EUR", "USD")}, **kw)


def sep(cid):
    print(f"\n=== {cid} ===")


# IND-001
sep("IND-001")
good = V().validate("CHECK trades.side IN ('BUY', 'SELL')", ROWS)
assert isinstance(good, Validated)
try:
    Validated(control=good.control, plan=good.plan, sandbox=good.sandbox, passed=(Gate.PARSE,))
    print("NO EXCEPTION RAISED -- FAIL")
except ValueError as e:
    msg = str(e)
    print("ValueError:", msg)
    print("names missing gates:", all(g.value in msg for g in Gate if g is not Gate.PARSE))
    print("mentions 'comment':", "comment" in msg)

# IND-002 -- five gates, in order, first failure stops
sep("IND-002")
candidates = {
    Gate.PARSE: "not pql at all",
    Gate.TYPE_CHECK: "CHECK trades.nope IS NOT NULL",
    Gate.COMPILE: "CHECK trades.ccy IN CODELIST 'iso4217_extended'",
    Gate.SANDBOX: "CHECK trades.side = 'SELL'",
    Gate.COUNTERFACTUAL: "CHECK trades.side MATCHES /.*/",
}
for expect_gate, text in candidates.items():
    outcome = V().validate(text, ROWS)
    ok = isinstance(outcome, Rejection) and outcome.gate is expect_gate
    print(expect_gate, "->", type(outcome).__name__, getattr(outcome, "gate", None), "MATCH" if ok else "MISMATCH")

# IND-003
sep("IND-003")
outcome = V().validate("Sure! Here is a control that checks the amount is positive.", ROWS)
print(type(outcome).__name__, outcome.gate if isinstance(outcome, Rejection) else None)
print("detail:", outcome.detail if isinstance(outcome, Rejection) else None)

# IND-004
sep("IND-004")
fenced_closed = "```pql\nCHECK trades.qty > 0\n```"
fenced_open = "```pql\nCHECK trades.qty > 0"
needs_edit = "CHECK trades.qty >> 0"
r1 = V().validate(fenced_closed, ROWS)
r2 = V().validate(fenced_open, ROWS)
r3 = V().validate(needs_edit, ROWS)
print("closed fence:", type(r1).__name__)
print("open fence:", type(r2).__name__)
print("needs edit:", type(r3).__name__, getattr(r3, "gate", None))

# IND-005
sep("IND-005")
outcome = V().validate("CHECK trades.counterparty_name IS NOT NULL", ROWS)
print(type(outcome).__name__, outcome.gate, outcome.detail)

# IND-006
sep("IND-006")
no_cat = Validator(catalogue=None)
outcome = no_cat.validate("CHECK trades.qty > 0", ROWS)
print(type(outcome).__name__)
if isinstance(outcome, Validated):
    print("passed:", [g.value for g in outcome.passed])
    print("TYPE_CHECK in passed:", Gate.TYPE_CHECK in outcome.passed)
else:
    print("gate:", outcome.gate, outcome.detail)

# IND-007
sep("IND-007")
outcome = V().validate("CHECK trades.ccy IN CODELIST 'iso4217_extended'", ROWS)
print(type(outcome).__name__, getattr(outcome, "gate", None))

# IND-008
sep("IND-008")
rows50 = [{"side": "SELL", "qty": 1, "ccy": "EUR", "lei": "x"}] * 50 + \
         [{"side": "BUY", "qty": 1, "ccy": "EUR", "lei": "x"}] * 50
rows51 = [{"side": "SELL", "qty": 1, "ccy": "EUR", "lei": "x"}] * 51 + \
         [{"side": "BUY", "qty": 1, "ccy": "EUR", "lei": "x"}] * 49
r50 = V().validate("CHECK trades.side = 'BUY'", rows50)
r51 = V().validate("CHECK trades.side = 'BUY'", rows51)
print("50%:", type(r50).__name__, getattr(r50, "gate", None))
print("51%:", type(r51).__name__, getattr(r51, "gate", None), getattr(r51, "detail", None))

# IND-009
sep("IND-009")
outcome = V().validate("CHECK trades.qty > 0", ())
print(type(outcome).__name__)
if isinstance(outcome, Validated):
    print("sandbox:", outcome.sandbox.to_dict())
else:
    print("gate:", outcome.gate, outcome.detail)

# IND-010
sep("IND-010")
big_rows = [{"side": "BUY", "qty": 10, "ccy": "EUR", "lei": "x"}] * 10000
outcome = V().validate("CHECK trades.side IN ('BUY', 'SELL')", big_rows)
print(type(outcome).__name__)
if isinstance(outcome, Validated):
    print("scanned:", outcome.sandbox.scanned, "<= 2000:", outcome.sandbox.scanned <= SANDBOX_ROWS)

# IND-011
sep("IND-011")
tautologies = [
    "CHECK trades SATISFIES qty IS NOT NULL OR qty IS NULL",
    "CHECK trades.qty > -999999999",
]
for text in tautologies:
    outcome = V().validate(text, ROWS)
    print(text, "->", type(outcome).__name__, getattr(outcome, "gate", None))
    if isinstance(outcome, Rejection):
        print("   detail:", outcome.detail)

# IND-012
sep("IND-012")
outcome = V().validate("CHECK trades.qty >= -1e308", ROWS)
print(type(outcome).__name__, getattr(outcome, "gate", None))
if isinstance(outcome, Rejection):
    print("detail:", outcome.detail)
    print('mentions "every row predicate":', "every row predicate" in outcome.detail)
# construct a SandboxResult that only catches the null probe, verify is_vacuous
sr = SandboxResult(scanned=10, violations=0, probes=1, probes_caught=1, value_probes=0, value_probes_caught=0)
print("is_vacuous when only null caught (value_probes=0):", sr.is_vacuous)

# IND-013
sep("IND-013")
outcome = V().validate("CHECK trades.lei IS NOT NULL", ROWS)
print(type(outcome).__name__)
if isinstance(outcome, Validated):
    sb = outcome.sandbox
    print("value_probes:", sb.value_probes, "value_probes_caught:", sb.value_probes_caught, "is_vacuous:", sb.is_vacuous)

# IND-014
sep("IND-014")
def probes_for(text):
    c = parse_control(text)
    return V()._probes(c, ROWS)

cases = {
    "in": "CHECK trades.side IN ('BUY', 'SELL')",
    "in_codelist": "CHECK trades.ccy IN CODELIST 'iso4217'",
    "matches": "CHECK trades.side MATCHES /^(BUY|SELL)$/",
    "is_valid": "CHECK trades.lei IS VALID 'lei'",
    "between": "CHECK trades.qty BETWEEN 1 AND 100",
    "comparison_num": "CHECK trades.qty > 5",
    "comparison_str": "CHECK trades.side = 'BUY'",
}
for name, text in cases.items():
    null_probe, value_probes = probes_for(text)
    print(name, "-> value probes:", value_probes)

# IND-015
sep("IND-015")
row_count_text = "CHECK trades HAS ROW COUNT BETWEEN 1 AND 1000"
outcome = V().validate(row_count_text, ROWS)
print(type(outcome).__name__)
if isinstance(outcome, Validated):
    print("value_probes:", outcome.sandbox.value_probes, "is_vacuous:", outcome.sandbox.is_vacuous)
    print("COUNTERFACTUAL in passed:", Gate.COUNTERFACTUAL in outcome.passed)
else:
    print("gate:", outcome.gate)

freshness_text = "CHECK trades IS FRESH WITHIN 30 MINUTES OF '06:30'"
outcome2 = V().validate(freshness_text, ROWS)
print("freshness:", type(outcome2).__name__)
if isinstance(outcome2, Validated):
    print("value_probes:", outcome2.sandbox.value_probes, "is_vacuous:", outcome2.sandbox.is_vacuous)

# IND-016
sep("IND-016")
# a probe whose value makes the evaluator raise: use IS VALID with a weird type,
# or force via a semantic-type check with a non-string. Try comparing a string
# column against a numeric hostile value that might raise in the evaluator.
c = parse_control("CHECK trades.qty > 5")
plan = V()._lowerer.control(c)
from prama.backend.reference import ReferenceEvaluator
# craft a probe row whose value is something exotic, e.g. an object that can't compare
class Uncomparable:
    def __gt__(self, other):
        raise TypeError("cannot compare")
    def __lt__(self, other):
        raise TypeError("cannot compare")
bad_row = [{"qty": Uncomparable()}]
try:
    result = ReferenceEvaluator().run(plan, bad_row)
    print("evaluator did not raise; violating_rows=", result.violating_rows)
except Exception as e:
    print("evaluator raised as expected:", type(e).__name__, e)
caught = V()._count_caught(plan, bad_row)
print("count_caught with a probe that raises:", caught, "(expect 0)")

print("\nDONE")
