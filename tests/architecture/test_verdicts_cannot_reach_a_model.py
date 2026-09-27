"""No module that produces a verdict can reach a model, through any import chain.

CON-007: AI never adjudicates. `test_layering.py` checks that no single module
both calls a model and says "verdict". That misses the indirect case: a
backend module importing a helper that imports `prama.llm`. This walks the
import graph from every verdict-producing package and requires that
`prama.llm` is unreachable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

#: The packages whose output is a pass/fail verdict, or the evidence of one.
VERDICT_PACKAGES = ("prama.backend", "prama.execute", "prama.evidence", "prama.ir")

MODEL_PACKAGE = "prama.llm"


def _module_of(path: Path) -> str:
    parts = path.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _graph() -> dict[str, set[str]]:
    modules = {_module_of(p): p for p in SRC.rglob("*.py")}
    graph: dict[str, set[str]] = {}
    for name, path in modules.items():
        found: set[str] = set()
        package = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = package.split(".")[: len(package.split(".")) - node.level + 1]
                    base = ".".join([*parent, base] if base else parent)
                found.add(base)
                found |= {f"{base}.{a.name}" for a in node.names}
        graph[name] = {m for m in found if m in modules}
    return graph


def _reach(graph: dict[str, set[str]], start: str) -> list[str] | None:
    """The import chain from *start* to the model package, or ``None``."""
    stack, seen = [(start, [start])], {start}
    while stack:
        current, chain = stack.pop()
        if current == MODEL_PACKAGE or current.startswith(MODEL_PACKAGE + "."):
            return chain
        for nxt in graph.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, [*chain, nxt]))
    return None


def test_no_verdict_module_reaches_a_model() -> None:
    graph = _graph()
    roots = [m for m in graph if m.startswith(VERDICT_PACKAGES)]
    assert len(roots) > 20, "the verdict packages were not found; the guard reaches nothing"
    chains = {root: chain for root in roots if (chain := _reach(graph, root))}
    assert not chains, "a verdict-producing module can import a model: " + "; ".join(
        " -> ".join(c) for c in list(chains.values())[:5]
    )


def test_the_guard_can_see_a_chain() -> None:
    """The counterfactual: a module that does reach the model package is found."""
    graph = _graph()
    assert _reach(graph, "prama.assistant.agent") is not None
