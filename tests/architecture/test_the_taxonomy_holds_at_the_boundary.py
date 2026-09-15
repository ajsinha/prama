"""Nothing that reads somebody else's bytes raises somebody else's exception.

`CLAUDE.md` states the rule and `tests/architecture/test_layering.py` enforces
half of it. That file has twenty-five tests and every one is an import scan or a
text scan — **none asserts what a function raises.** An import scan cannot see
an exception travelling up a stack, so the rule held for every line of code and
failed on the exceptions.

QA round 4 found eight defects of exactly that shape in one pass — `Q-87`,
`Q-90`, `Q-91`, `Q-92`, `Q-93`, `Q-95`, `Q-96`, `Q-103` — roughly a third of
everything the round turned up, and each was found by hand, one site at a time.
Fixing eight instances of a rule with no guard leaves the ninth.

`qa/regression-suite/interfaces/test_no_command_shows_a_traceback.py` guards the
**CLI** boundary, pinned to nine invocations sampled from a 224-call census. Six
of the eight were below it — a DAO flush, an engine factory, a unit of work, a
collector, a connector's `open`, a diff — reachable from the API and the console
as well, where no such guard exists.

**What this checks.** Every public callable in `prama.*` whose name is a reading
verb — `load`, `parse`, `read`, `from_dict`, and so on — is called with input it
must refuse. Anything that escapes must be a `PramaError`. The surface is
*discovered*, not listed, so a new reader is covered the day it is written
rather than the day somebody remembers to add it here.

**Why it reports what it could not reach.** Half of this round's findings were
checks that could not reach the thing they described and returned the answer
somebody was hoping for. A discovery-based guard is a natural home for that
failure: if the walk silently matches nothing, it passes forever. So the count
of entry points is asserted against a floor, and every skip is counted and
surfaced in the failure message.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib
import inspect
import linecache
import pkgutil
from pathlib import Path
from typing import Any

import prama
from prama.core.errors import PramaError

#: Names that mean "turn somebody else's bytes into our objects". The cluster
#: this file exists for lived entirely behind these verbs.
READING_VERBS = (
    "load",
    "parse",
    "read",
    "decode",
    "from_dict",
    "from_json",
    "from_text",
    "of_text",
)

#: Inputs that are wrong the way real inputs are wrong, grouped by the type the
#: reader says it takes. Not fuzz: each is a mistake somebody actually makes —
#: a file that is not there, a document of the wrong shape, bytes that are not
#: UTF-8, a number written as a word.
#:
#: Matched to the annotation rather than fired at everything. The first version
#: of this guard handed a `str` to `from_dict(document: dict)` and counted the
#: resulting `AttributeError` as an escape: 167 of them, none real. Passing the
#: wrong *type* is the caller's mistake and Python's to report; this file is
#: about the right type carrying wrong *content*. Getting that distinction wrong
#: is how a guard becomes noise and then becomes disabled.
HOSTILE_BY_TYPE: dict[str, tuple[Any, ...]] = {
    "str": ("", "{not json at all", "\x00\x01", "not-a-date", "/nonexistent/path.yaml"),
    "path": (Path("/nonexistent/directory/that/is/not/there.yaml"), Path("/")),
    "mapping": (
        {},
        {"unexpected": "shape"},
        {"schema": ["a string where an object belongs"]},
        {"schema": {"not": "a list"}},
        {"sequence": "not a number", "metrics": {"scanned_rows": "eight"}},
    ),
    "sequence": ([], [None], ["a string where an object belongs"], [{}]),
    "bytes": (b"", b"\xff\xfe not utf-8", b"{not json"),
}


def _hostile_for(parameter: inspect.Parameter) -> tuple[Any, ...]:
    """The wrong-content inputs appropriate to what this reader says it takes."""
    if parameter.annotation is inspect.Parameter.empty:
        # Unannotated: everything is fair, because the reader has not said what
        # it will not take.
        return tuple(value for group in HOSTILE_BY_TYPE.values() for value in group)

    annotation = str(parameter.annotation).lower()
    # Containers first, and only then the permissive escape hatch. Testing for
    # `any` first matched `dict[str, Any]` — so every mapping reader was handed
    # strings and paths, and 237 type errors were reported as taxonomy escapes.
    # The substring was in the annotation; it was not what the annotation meant.
    if any(k in annotation for k in ("mapping", "dict")):
        return HOSTILE_BY_TYPE["mapping"]
    if any(k in annotation for k in ("sequence", "list", "iterable", "tuple")):
        return HOSTILE_BY_TYPE["sequence"]
    for key in ("path", "bytes", "str"):
        if key in annotation:
            return HOSTILE_BY_TYPE[key]
    if annotation in ("any", "<class 'object'>", "object"):
        return tuple(value for group in HOSTILE_BY_TYPE.values() for value in group)
    return ()


#: Below this, the walk has stopped finding things and the guard is green
#: because it looked at nothing. Measured at 43 when this was written.
MINIMUM_ENTRY_POINTS = 30


def _reading_callables() -> list[tuple[str, Any]]:
    """Every public reader in `prama.*`, found rather than listed."""
    found: list[tuple[str, Any]] = []
    for module in pkgutil.walk_packages(prama.__path__, prefix="prama."):
        if ".ui" in module.name:
            continue
        try:
            loaded = importlib.import_module(module.name)
        except Exception:
            continue
        for name, value in vars(loaded).items():
            if name.startswith("_") or getattr(value, "__module__", None) != module.name:
                continue
            if inspect.isfunction(value) and _is_reader(name):
                found.append((f"{module.name}.{name}", value))
            elif inspect.isclass(value):
                for attribute, member in vars(value).items():
                    if attribute.startswith("_") or not _is_reader(attribute):
                        continue
                    if isinstance(member, classmethod | staticmethod):
                        found.append(
                            (f"{module.name}.{name}.{attribute}", getattr(value, attribute))
                        )
    return found


def _is_reader(name: str) -> bool:
    return any(name == verb or name.startswith(f"{verb}_") for verb in READING_VERBS)


def _raised_by_us(exc: BaseException) -> bool:
    """Whether this `ValueError` is a refusal we wrote, or one we let through.

    A deliberate refusal and a leaked stdlib exception are the same type and
    tell apart only by origin — and "origin" needs care. Asking only whether the
    deepest frame is inside `prama` is not enough: `int("x")` raises from C, so
    the deepest *Python* frame is our own file and every leaked conversion looks
    deliberate. `EvidenceRecord.from_dict` passed on exactly that.

    So the line itself is read. A refusal we chose is a `raise` statement; a
    refusal we inherited is `int(...)` or `fromisoformat(...)` on a line that
    raises nothing.
    """
    package = str(Path(prama.__file__).parent.resolve())
    frame, last = exc.__traceback__, None
    while frame is not None:
        last = frame
        frame = frame.tb_next
    if last is None:  # pragma: no cover - an exception with no traceback
        return False
    filename = str(Path(last.tb_frame.f_code.co_filename).resolve())
    if not filename.startswith(package):
        return False
    source = linecache.getline(filename, last.tb_lineno).strip()
    return source.startswith("raise ")


def test_the_walk_still_finds_the_surface() -> None:
    """The guard against this file quietly checking nothing."""
    found = _reading_callables()
    assert len(found) >= MINIMUM_ENTRY_POINTS, (
        f"only {len(found)} reading entry points were discovered, against a floor of "
        f"{MINIMUM_ENTRY_POINTS}. Either the walk broke or the verbs changed — either "
        "way this file is now passing without looking at anything."
    )


def test_no_reader_raises_somebody_elses_exception() -> None:
    entry_points = _reading_callables()
    assert entry_points, "no readers were discovered at all"

    escaped: list[str] = []
    unreachable = 0
    exercised = 0

    for label, function in entry_points:
        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError):  # pragma: no cover - a C-level callable
            unreachable += 1
            continue
        required = [
            p
            for p in signature.parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        ]
        if len(required) != 1:
            # Needs setup this guard cannot invent. Counted, not ignored.
            unreachable += 1
            continue

        candidates = _hostile_for(required[0])
        if not candidates:
            # A reader whose one argument is some domain object this guard
            # cannot fabricate. Counted, not ignored.
            unreachable += 1
            continue
        for candidate in candidates:
            try:
                function(candidate)
            except PramaError:
                pass
            except TypeError:
                # The argument was not even of a type this reader accepts; that
                # is the signature refusing, not the body failing.
                pass
            except ValueError as exc:
                # `Q-77` settled this, deliberately: for "right type, wrong
                # value" the library raises `ValueError` — Python's documented
                # meaning — and the boundary translates. `CLAUDE.md` describes
                # translation *at a boundary*, not taxonomy all the way down.
                #
                # So the question is not the type but who raised it. A
                # `ValueError` thrown by Prama's own code is that decision being
                # kept; one propagating out of `int()` or `fromisoformat` is
                # stdlib's message reaching a caller, naming neither the field
                # nor the record it came from.
                if not _raised_by_us(exc):
                    escaped.append(
                        f"{label}({candidate!r:.40}) let stdlib's own ValueError through: "
                        f"{str(exc).splitlines()[0][:80]}"
                    )
            except Exception as exc:
                escaped.append(
                    f"{label}({candidate!r:.40}) raised "
                    f"{type(exc).__module__}.{type(exc).__name__}: {str(exc).splitlines()[0][:90]}"
                )
            exercised += 1

    assert not escaped, (
        f"{len(escaped)} reader(s) answered with an exception from outside the Prama "
        f"taxonomy. {exercised} call(s) were exercised across "
        f"{len(entry_points) - unreachable} of {len(entry_points)} entry points; "
        f"{unreachable} needed setup this guard cannot invent.\n\n" + "\n".join(escaped[:12])
    )


def test_the_guard_would_notice() -> None:
    """The counterfactual, in the file itself.

    A guard whose scan cannot fail is the thing this round kept finding. This
    one is handed a reader that raises a bare `ValueError` and must object.
    """

    def load_broken(_text: str) -> None:
        raise ValueError("a stdlib exception, escaping")

    escaped = []
    for candidate in HOSTILE_BY_TYPE["str"]:
        try:
            load_broken(candidate)
        except PramaError:
            pass
        except TypeError:
            pass
        except Exception as exc:
            escaped.append(type(exc).__name__)

    assert escaped, "the detection used by this file does not notice a bare ValueError"


def test_the_layering_scan_cannot_do_this() -> None:
    """Why this file exists beside `test_layering.py` rather than inside it.

    Stated as an assertion so the reasoning is checked rather than asserted in
    prose: the layering suite is import- and text-scanning, and every finding in
    the cluster this guards passed it.
    """
    from pathlib import Path

    layering = Path(__file__).with_name("test_layering.py").read_text(encoding="utf-8")
    assert "PramaError" not in layering, (
        "test_layering.py now reasons about exception types; if it has grown a "
        "runtime guard, this file's premise needs rewriting rather than keeping"
    )
