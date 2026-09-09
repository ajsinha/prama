"""The function catalogue.

One declaration per function, carrying everything anybody needs to know about
it in one place: how it lowers on each engine, how the reference interpreter
computes it, what it does with an unknown, and exactly how it differs from what
a spreadsheet would do.

**The catalogue is the point, not the functions.** Before it, an unknown name
passed straight through to SQL — ``NONSENSE_FN(b)`` parsed, lowered, received a
plan id and compiled to ``WHERE (NONSENSE_FN("b") > 1)`` — while the reference
interpreter returned ``UNKNOWN`` for anything it did not recognise. The
compiler and the independent check that exists to catch the compiler being
wrong silently disagreed, which is the one condition the conformance suite
cannot tolerate.

Three rules make that impossible to reintroduce:

* **No function exists without a reference implementation.** It is a required
  field, so a function added without one does not construct. A test then runs
  every function's SQL against its reference implementation on the same inputs
  and requires agreement.
* **A function an engine cannot express is refused, never approximated.** The
  same rule the dialects already apply to regular expressions: the alternative
  is one control meaning two things on two engines, and nothing noticing.
* **A function that cannot replay does not exist.** ``NOW``, ``RAND`` and
  ``INDIRECT`` are refused by name, with the reason, because evidence that
  cannot be re-derived is not evidence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from typing import Any, Final

from prama.core.errors import ValidationError
from prama.pql.families import UNKNOWN

#: Every engine Prama compiles for. A function that names none of these in
#: ``unsupported_on`` is claimed to work on all of them, and the conformance
#: corpus checks that claim rather than believing it.
ENGINES: Final = ("postgresql", "duckdb", "sqlite")

#: ``VARIADIC`` as an upper bound. Spelled rather than ``-1`` so an arity of
#: ``(1, VARIADIC)`` reads as what it is.
VARIADIC: Final = 99

#: Functions refused by name, and why. Not "unsupported" — *refused*. Each of
#: these is expressible on every engine and each would make a control
#: unreplayable, which is a different and worse problem than a missing feature.
VOLATILE: Final[dict[str, str]] = {
    "NOW": "the current time",
    "TODAY": "the current date",
    "RAND": "a random number",
    "RANDBETWEEN": "a random number",
    "INDIRECT": "a reference resolved at evaluation time",
    "OFFSET": "a reference resolved at evaluation time",
}


class UnknownValue:
    """The three-valued logic's third value, as a singleton.

    ``None`` is not usable here: a function may legitimately return ``None`` as
    a value, and conflating "no value" with "cannot be determined" is how a
    control over an entirely null column passes for years.
    """

    _instance: UnknownValue | None = None

    def __new__(cls) -> UnknownValue:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return "UNKNOWN"

    def __bool__(self) -> bool:
        raise TypeError(
            "UNKNOWN has no truth value. Three-valued logic is the point: "
            "collapsing it to True or False here is how a null becomes a pass."
        )


#: The sentinel every reference implementation returns when it cannot decide.
UNSET: Final = UnknownValue()


@dataclasses.dataclass(frozen=True, slots=True)
class Function:
    """One function, and everything that is true of it."""

    name: str
    summary: str
    #: ``(minimum, maximum)``. ``VARIADIC`` as the maximum means unbounded.
    arity: tuple[int, int]
    returns: str
    #: Expected family per position. The last entry repeats for a variadic
    #: tail, so ``(NUMBER,)`` with arity ``(1, VARIADIC)`` means "numbers".
    argument_types: tuple[str, ...]
    #: The reference implementation. **Required.** A function without one does
    #: not exist, which is what stops the compiler and its independent check
    #: from drifting apart.
    evaluate: Callable[[list[Any]], Any]
    #: SQL, with ``{0}``, ``{1}`` … for the rendered arguments. The default for
    #: every engine unless overridden.
    sql: str = ""
    #: Per-engine SQL where the default will not do.
    sql_by_engine: dict[str, str] = dataclasses.field(default_factory=dict)
    #: Engines that cannot express this at all. A control using it is refused
    #: there rather than compiled to something close.
    unsupported_on: frozenset[str] = frozenset()
    #: Whether an unknown argument makes the result unknown. True for almost
    #: everything; ``IF``, ``COALESCE``, ``ISBLANK`` and the boolean connectives
    #: are the exceptions, and each of those has to say why.
    strict_unknown: bool = True
    #: Pushdown capabilities the engine must declare for this to compile.
    requires: frozenset[str] = frozenset()
    #: What separates the arguments in a ``{*}`` template, per engine. Comma
    #: for a function call; SQLite's concatenation is an *operator* and needs
    #: ``||``, which is why this is per-engine rather than one value.
    separator_by_engine: dict[str, str] = dataclasses.field(default_factory=dict)
    #: How this differs from what a spreadsheet would do. Printed by
    #: ``control explain``, because a divergence discovered in production is
    #: worth less than one stated on the control.
    excel_divergence: str = ""

    def __post_init__(self) -> None:
        if not self.sql and not self.sql_by_engine:
            raise ValidationError(
                f"the function {self.name} has no SQL form",
                remedy=(
                    "Give a `sql` template, or list every engine in "
                    "`unsupported_on` if it genuinely cannot be pushed down."
                ),
            )

    def supports(self, engine: str) -> bool:
        return engine not in self.unsupported_on

    def render(self, engine: str, arguments: Sequence[str]) -> str:
        """The SQL for one engine, or a refusal."""
        if not self.supports(engine):
            raise ValidationError(
                f"{engine} cannot express {self.name}",
                remedy=(
                    "Run this control on an engine that can, or express it "
                    "differently. Prama will not substitute something close: the "
                    "same control would then mean two different things on two "
                    "engines, and nothing would notice."
                ),
                context={"function": self.name, "engine": engine},
            )
        template = self.sql_by_engine.get(engine, self.sql)
        if "{*}" in template:
            # A variadic template: one placeholder for the whole joined
            # argument list, for functions like GREATEST that take any number.
            separator = self.separator_by_engine.get(engine, ", ")
            return template.replace("{*}", separator.join(arguments))
        return template.format(*arguments)

    def accepts(self, count: int) -> bool:
        low, high = self.arity
        return low <= count <= high

    def arity_words(self) -> str:
        low, high = self.arity
        if high >= VARIADIC:
            return f"at least {low} argument(s)"
        if low == high:
            return f"exactly {low} argument(s)"
        return f"between {low} and {high} arguments"

    def expected_type(self, position: int) -> str:
        if not self.argument_types:
            return UNKNOWN
        if position < len(self.argument_types):
            return self.argument_types[position]
        return self.argument_types[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "arity": list(self.arity),
            "returns": self.returns,
            "engines": [e for e in ENGINES if self.supports(e)],
            "strict_unknown": self.strict_unknown,
            "excel_divergence": self.excel_divergence,
        }


class FunctionRegistry:
    """Every function the language has, by name.

    A registry rather than a module-level dict so a deployment can add a
    domain-specific function without editing this file, and so the set can be
    enumerated for the console, for ``control explain`` and for the conformance
    corpus.
    """

    def __init__(self) -> None:
        self._functions: dict[str, Function] = {}

    def register(self, function: Function) -> None:
        name = function.name.upper()
        if name in VOLATILE:
            raise ValidationError(
                f"{name} cannot be a control function: it returns {VOLATILE[name]}",
                remedy=(
                    "A control has to replay: the same plan against the same snapshot "
                    "must produce the same verdict, or the evidence is not evidence. "
                    "Pass the value in as a parameter instead, where it is recorded "
                    "with the run."
                ),
                context={"function": name},
            )
        self._functions[name] = function

    def get(self, name: str) -> Function:
        try:
            return self._functions[name.upper()]
        except KeyError:
            if name.upper() in VOLATILE:
                raise ValidationError(
                    f"{name.upper()} is refused: it returns {VOLATILE[name.upper()]}",
                    remedy=(
                        "A control has to replay. Pass the value in as a parameter, "
                        "which is recorded with the run and reproduces exactly."
                    ),
                    context={"function": name},
                ) from None
            raise ValidationError(
                f"there is no function called {name.upper()}",
                remedy=(
                    "Available: "
                    + ", ".join(sorted(self._functions))
                    + ". An unrecognised name used to compile straight through to SQL "
                    "and fail at execution — or worse, succeed on an engine that "
                    "happened to have a function of that name."
                ),
                context={"function": name, "known": sorted(self._functions)},
            ) from None

    def find(self, name: str) -> Function | None:
        return self._functions.get(name.upper())

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._functions))

    def of_engine(self, engine: str) -> tuple[Function, ...]:
        return tuple(f for f in self._functions.values() if f.supports(engine))

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.upper() in self._functions

    def __len__(self) -> int:
        return len(self._functions)
