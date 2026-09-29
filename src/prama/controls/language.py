"""PQL as a set of questions: is it sound, what does it say, what will run.

The answers the control studio, `prama control …` and the HTTP API all give.
Each used to be written inside the surface that asked it, so the console's
"compile" and the CLI's "compile" were two implementations of one question —
the arrangement that ends with an editor underlining something the compiler
accepts. They are written once here, and every surface renders what comes back.

Nothing here stores anything or reads any data. Checking, explaining and
compiling a control are functions of its text and of the estate's declared
schemas, which is why the API serves them under ``control:read``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.core.errors import PramaError, ValidationError
from prama.pql import parse
from prama.pql.analysis import LanguageService
from prama.pql.errors import PqlError
from prama.pql.types import Catalogue, Column, DatasetSchema

#: Assertion kinds a fused scan cannot answer, and how each one does run.
#: Shown beside the fused groups so a compiled suite never silently loses them.
UNFUSED: dict[str, str] = {
    "delegate": "a delegate: rows fetched, counted in Python",
    "custom_sql": "custom SQL: runs as written, not fused",
    "reconcile": "a reconciliation: both sides fetched, matched by the engine",
}


# ---------------------------------------------------------------------------
# The catalogue a control is checked against
# ---------------------------------------------------------------------------


async def catalogue_of(uow: Any, tenant_id: str) -> Catalogue:
    """The checker's catalogue, derived from the estate's declarations.

    Derived, never restated: what an editor checks against is what the business
    declared. A separately maintained catalogue would drift, and the drift
    would surface as a control that checks clean and then fails at execution —
    the worst possible place to find it.
    """
    catalogue = Catalogue()
    for version in await uow.datasets.list_current(tenant_id, limit=5000):
        attributes = await uow.attributes.for_dataset(version.dataset_id, tenant_id=tenant_id)
        catalogue = catalogue.with_dataset(
            DatasetSchema(
                name=version.slug,
                columns=tuple(
                    Column(a.name, getattr(a, "physical_type", "") or "") for a in attributes
                ),
            )
        )
    return catalogue


def catalogue_from_payload(payload: Any, *, where: str = "the catalogue") -> Catalogue:
    """A catalogue from the JSON `prama lsp catalogue` writes.

    ``{"datasets": {"name": {"column": "type", …}, …}}``. A payload without a
    ``datasets`` object is refused rather than read as empty: an empty
    catalogue silently turns every schema check off, and a caller who supplied
    one and got a clean result has been told their schemas were checked.
    """
    datasets = payload.get("datasets") if isinstance(payload, dict) else None
    if not isinstance(datasets, dict):
        raise ValidationError(
            f"{where} has no 'datasets' object",
            remedy="Rewrite it with `prama lsp catalogue`.",
            context={"where": where},
        )
    return Catalogue(
        datasets={
            name: DatasetSchema(
                name=name,
                columns=tuple(Column(c, str(t)) for c, t in (columns or {}).items()),
            )
            for name, columns in datasets.items()
        }
    )


# ---------------------------------------------------------------------------
# check · explain · format
# ---------------------------------------------------------------------------


def check(source: str, catalogue: Catalogue | None = None) -> dict[str, Any]:
    """Parse, type-check and lint; and explain what parsed.

    Every judgement comes from `LanguageService`, the module ``prama lsp``
    serves, so an editor, the studio and the API underline the same things.
    A text that does not parse has one finding and no controls, and says so
    rather than listing an empty result beside it.
    """
    service = LanguageService(catalogue or Catalogue())
    diagnostics = service.diagnostics(source)
    syntax = next((d for d in diagnostics if d.level == "error" and not d.control), None)
    if syntax is not None:
        return {
            "syntax_error": syntax.to_dict(),
            "controls": 0,
            "findings": [],
            "explanations": [],
            "errors": 1,
        }
    controls = parse(source).controls
    return {
        "syntax_error": None,
        "controls": len(controls),
        "findings": [d.to_dict() for d in diagnostics],
        "explanations": explanations(controls),
        "errors": sum(1 for d in diagnostics if d.level == "error"),
    }


def explanations(controls: Any) -> list[dict[str, str]]:
    """Each control as the sentence a data owner approves.

    Taken from the lowered plan's ``description``, which is generated from the
    IR — so the sentence is derived from the same structure the SQL is derived
    from, and the two cannot describe different controls.
    """
    from prama.ir.resolve import resolved

    out = []
    for index, control in enumerate(controls):
        label = control.name or f"control {index + 1}"
        try:
            out.append({"name": label, "sentence": resolved(control).description})
        except PramaError as exc:
            out.append({"name": label, "sentence": f"cannot be explained: {exc}"})
    return out


def explain(source: str) -> dict[str, Any]:
    """Every control in *source* as sentences, with its spreadsheet divergences."""
    try:
        controls = parse(source).controls
    except PqlError as exc:
        return {"syntax_error": position_of(exc), "controls": []}
    sentences = explanations(controls)
    return {
        "syntax_error": None,
        "controls": [
            {
                "control": head(control),
                "name": sentence["name"],
                "sentence": sentence["sentence"],
                "describes": control.describe(),
                "divergences": divergences(control),
            }
            for control, sentence in zip(controls, sentences, strict=True)
        ],
    }


def format_source(source: str) -> str:
    """The controls in canonical form, so a diff is about meaning."""
    return "\n\n".join(c.render() for c in parse(source).controls) + "\n"


def head(control: Any) -> str:
    """A control's first rendered line: how a finding names it."""
    return str(control.render().splitlines()[0])


def position_of(exc: PqlError) -> dict[str, Any]:
    """A syntax error an editor can point at: line and column, or nothing.

    Never a guess. An editor will happily underline line 1 column 1 and send
    the reader to the wrong place, which is worse than underlining nothing.
    """
    position = getattr(exc, "position", None)
    return {
        "message": str(exc),
        "remedy": getattr(exc, "remedy", ""),
        "line": getattr(position, "line", None),
        "column": getattr(position, "column", None),
    }


def divergences(control: Any) -> list[str]:
    """How this control's functions differ from a spreadsheet, and where.

    Both kinds: a function whose *semantics* differ from Excel, and one an
    engine cannot run at all. An author writing a formula that will be refused
    on the estate's own engine should learn it now rather than at the first
    execution.
    """
    from prama.pql.library import FUNCTIONS

    notes: list[str] = []
    for name in sorted(function_names(control)):
        function = FUNCTIONS.find(name)
        if function is None:
            continue
        if function.excel_divergence:
            notes.append(f"{name} differs from Excel: {function.excel_divergence}")
        if function.unsupported_on:
            notes.append(
                f"{name} cannot run on "
                + ", ".join(sorted(function.unsupported_on))
                + " — the control will be refused there rather than approximated"
            )
    return notes


def function_names(node: Any) -> set[str]:
    """Every function called anywhere in a control, however deeply nested."""
    from prama.pql import ast as pql_ast

    found: set[str] = set()
    stack: list[Any] = [node]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, pql_ast.FunctionCall):
            found.add(current.name.upper())
        for value in getattr(current, "__slots__", ()) or ():
            child = getattr(current, value, None)
            if isinstance(child, pql_ast.Node):
                stack.append(child)
            elif isinstance(child, (tuple, list)):
                stack.extend(item for item in child if isinstance(item, pql_ast.Node))
    return found


# ---------------------------------------------------------------------------
# compile
# ---------------------------------------------------------------------------


def compile_source(
    source: str, dialect: str = "postgresql", *, fuse: bool = False
) -> dict[str, Any]:
    """The SQL each control becomes on *dialect*, and what it does not test.

    Each plan carries its residual: what the SQL screened but did not decide.
    A pass reported from an incomplete screen is a false assurance, and this is
    where the reader is told. A control that cannot be compiled for this
    dialect is named with the reason rather than omitted — "this engine cannot
    express this control" is a real answer, and a silently shorter list is not.

    With *fuse*, controls sharing a scope are grouped into one query each, as
    a run over that engine would scan them.
    """
    from prama.backend import compile_for
    from prama.ir.resolve import resolved

    try:
        program = parse(source)
    except PqlError as exc:
        return {"syntax_error": position_of(exc), "dialect": dialect, "plans": []}

    plans: list[dict[str, Any]] = []
    lowered: list[Any] = []
    for index, control in enumerate(program.controls):
        label = control.name or f"control {index + 1}"
        try:
            plan = resolved(control)
            compiled = compile_for(plan, dialect)
        except PramaError as exc:
            plans.append({"name": label, "control": head(control), "error": str(exc)})
            continue
        lowered.append(plan)
        plans.append(
            {
                "name": label,
                "control": head(control),
                "plan_id": plan.plan_id,
                "description": plan.description,
                "metric_query": compiled.metric_query,
                "sample_query": compiled.sample_query,
                "metric_names": list(compiled.metric_names),
                "parameters": list(compiled.parameters),
                "is_complete": compiled.is_complete,
                "residual_validators": [
                    {"validator": v, "column": c} for v, c in compiled.residual_validators
                ],
            }
        )
    result: dict[str, Any] = {"syntax_error": None, "dialect": dialect, "plans": plans}
    if fuse:
        result["fused"] = _fused(lowered, dialect)
    return result


def _fused(plans: list[Any], dialect: str) -> dict[str, Any]:
    from prama.backend.fuse import Fuser
    from prama.backend.sql import SqlCompiler

    fuser = Fuser(dialect)
    groups = [
        {
            "scope": group.describe(),
            "dataset": group.dataset,
            "controls": group.size,
            "sql": fuser.fuse(group, table=group.dataset).sql,
        }
        for group in fuser.group(plans)
    ]
    separate = [
        {
            "description": plan.description,
            "how": UNFUSED[plan.assertion_kind],
            "sql": SqlCompiler(dialect).compile(plan, table=plan.scope.dataset).metric_query,
        }
        for plan in plans
        if plan.assertion_kind in UNFUSED
    ]
    cost = fuser.cost(plans)
    return {"cost": cost.render(), **cost.to_dict(), "groups": groups, "separate": separate}


# ---------------------------------------------------------------------------
# Function coverage
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Coverage:
    """One engine's share of the function catalogue."""

    engine: str
    total: int
    refused: tuple[str, ...] = ()

    @property
    def pushes_down(self) -> int:
        return self.total - len(self.refused)

    @property
    def share(self) -> float:
        return self.pushes_down / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "total": self.total,
            "pushes_down": self.pushes_down,
            "share": self.share,
            "refused": list(self.refused),
        }


def function_coverage(engine: str = "") -> tuple[tuple[str, ...], list[Coverage]]:
    """The function catalogue, and how much of it each engine runs where the data is.

    A function that cannot be pushed down is refused, never approximated:
    approximating it would make the same control mean two things on two
    engines, and nothing would notice.
    """
    from prama.backend import DIALECTS
    from prama.pql.library import FUNCTIONS

    if engine and engine not in DIALECTS:
        raise ValidationError(
            f"no engine called {engine!r}",
            remedy=f"One of: {', '.join(sorted(DIALECTS))}.",
            context={"engine": engine},
        )
    names = tuple(FUNCTIONS.names())
    rows = []
    for each in [engine] if engine else sorted(DIALECTS):
        refused = sorted(
            name
            for name in names
            if (found := FUNCTIONS.find(name)) is not None and not found.supports(each)
        )
        rows.append(Coverage(engine=each, total=len(names), refused=tuple(refused)))
    return names, rows


__all__ = [
    "UNFUSED",
    "Coverage",
    "catalogue_from_payload",
    "catalogue_of",
    "check",
    "compile_source",
    "divergences",
    "explain",
    "explanations",
    "format_source",
    "function_coverage",
    "function_names",
    "head",
    "position_of",
]
