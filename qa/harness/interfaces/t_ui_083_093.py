import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.web.builder import build, render_and_verify, QUESTIONS, _values, _number
from prama.core.errors import ValidationError

# UI-083: refuses a control with no reason
bad83 = {}
for because in ["", "   "]:
    try:
        build(dataset="t", rule="not_null", column="a", because=because)
        bad83[repr(because)] = "did not raise"
    except ValidationError as e:
        if "reason" not in str(e).lower() and "alert quotes" not in e.remedy.lower():
            bad83[repr(because)] = f"wrong message: {e}"
record("UI-083", "PASS" if not bad83 else "FAIL", f"bad={bad83}")

# UI-084: every builder rule is reachable and produces valid PQL
minimal_answers = {
    "not_null": {"column": "a"},
    "in_list": {"column": "a", "values": "X,Y"},
    "matches": {"column": "a", "pattern": "^[A-Z]+$"},
    "between": {"column": "a", "lower": "1", "upper": "10"},
    "unique_key": {"columns": "a,b"},
    "row_count": {"minimum": "1"},
    "references": {"column": "a", "reference_dataset": "other", "reference_column": "id"},
    "fresh": {"due_time": "09:00", "calendar": "TARGET2"},
}
bad84 = {}
QUESTIONS_KEYS = [q.key for q in QUESTIONS]
for key in QUESTIONS_KEYS:
    answers = minimal_answers.get(key, {})
    try:
        c = build(dataset="t", rule=key, because="why", **answers)
        text = render_and_verify(c)
        from prama.pql.parser import parse_control
        from prama.pql.types import TypeChecker, Catalogue
        parsed = parse_control(text)
        findings = list(TypeChecker(Catalogue()).check(parsed, source=text))
        # type errors (not 'unchecked') would mean it doesn't type-check
        real_errors = [f for f in findings if f.level not in ("unchecked",)]
        if real_errors:
            bad84[key] = f"type errors: {real_errors}"
    except Exception as e:
        bad84[key] = f"{type(e).__name__}: {e}"
record("UI-084", "PASS" if not bad84 else "FAIL", f"n_rules={len(QUESTIONS_KEYS)} bad={bad84}")

# UI-085: the round-trip check is a real check (simulate a broken renderer)
from prama.pql.ast import Control
import dataclasses

class BrokenControl:
    """A stand-in whose .render() does not reparse to something equal to itself."""

    def render(self):
        return "CHECK t.a IS NOT NULL BECAUSE 'placeholder text that will not match'"

    def __eq__(self, other):
        return False  # simulate a renderer whose output never reparses equal


try:
    render_and_verify(BrokenControl())
    ui85_result = "FAIL"
    ui85_detail = "render_and_verify did not raise for a control that does not read back equal"
except ValidationError as e:
    ui85_result = "PASS" if "does not read back" in str(e).lower() or "does not read back" in str(getattr(e, "message", "")).lower() else "FAIL"
    ui85_detail = str(e)
record("UI-085", ui85_result, ui85_detail)

# UI-086: _values refuses empty and repeating lists
bad86 = {}
for text, expect_refused in [("", True), (",", True), ("A,A", True), ("A, A", True)]:
    try:
        _values(text)
        if expect_refused:
            bad86[repr(text)] = "did not raise"
    except ValidationError:
        pass
record("UI-086", "PASS" if not bad86 else "FAIL", f"bad={bad86}")

# UI-087: _values with a value containing a comma
try:
    result87 = _values('"Smith, John"')
    items = [lit.value for lit in result87.items]
    ok87_silent_split = items == ["Smith, John"]
except ValidationError:
    ok87_silent_split = None  # refused, which is also acceptable
result_plain = _values("Smith, John")
items_plain = [lit.value for lit in result_plain.items]
record(
    "UI-087",
    "FAIL" if items_plain == ["Smith", "John"] else "PASS",
    f"'Smith, John' (unquoted, the natural thing to type) -> {items_plain} -- the split is unconditional "
    f"on ',' with no quoting support, so a permitted value containing a comma is silently split into two",
)

# UI-088: between with bounds reversed
try:
    build(dataset="t", rule="between", column="a", lower="10", upper="1", because="x")
    ui88 = "FAIL"
    detail88 = "did not raise for lower=10 upper=1"
except ValidationError as e:
    ui88 = "PASS" if "never pass" in str(e).lower() or "never pass" in e.remedy.lower() else "FAIL"
    detail88 = str(e)
record("UI-088", ui88, detail88)

# UI-089: between and row_count with equal bounds
bad89 = {}
try:
    build(dataset="t", rule="between", column="a", lower="5", upper="5", because="x")
except Exception as e:
    bad89["between-equal"] = str(e)
try:
    build(dataset="t", rule="row_count", minimum="5", maximum="5", because="x")
except Exception as e:
    bad89["row_count-equal"] = str(e)
record("UI-089", "PASS" if not bad89 else "FAIL", f"bad={bad89}")

# UI-090: _number refuses units, separators, empty; nan/inf refused
bad90 = {}
for text in ["1,000", "10%", "£5", "1e400", "nan", "inf", ""]:
    try:
        val = _number(text, what="x")
        bad90[repr(text)] = f"ACCEPTED as {val}"
    except ValidationError:
        pass
    except OverflowError as e:
        bad90[repr(text)] = f"uncaught OverflowError: {e}"
record("UI-090", "PASS" if not bad90 else "FAIL", f"bad={bad90}")

# UI-091: tolerated_percent outside 0-100
bad91 = {}
for pct, expect_ok in [("-1", False), ("0", True), ("100", True), ("101", False)]:
    try:
        build(dataset="t", rule="not_null", column="a", because="x", tolerated_percent=pct)
        if not expect_ok:
            bad91[pct] = "accepted but should be refused"
    except ValidationError:
        if expect_ok:
            bad91[pct] = "refused but should be accepted"
record("UI-091", "PASS" if not bad91 else "FAIL", f"bad={bad91}")

# UI-092: row_count with neither bound
try:
    build(dataset="t", rule="row_count", because="x")
    ui92 = "FAIL"
    detail92 = "did not raise with both minimum and maximum empty"
except ValidationError as e:
    ui92 = "PASS" if "minimum" in str(e).lower() and "maximum" in str(e).lower() else "FAIL"
    detail92 = str(e)
record("UI-092", ui92, detail92)

print("done ui builder batch")
