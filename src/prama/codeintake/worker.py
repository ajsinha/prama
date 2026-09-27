"""The sandboxed reader: a separate process that reads code and returns lineage.

Run by `prama.codeintake.service` as ``python -m prama.codeintake.worker ROOT
DIALECT`` with resource limits set before it starts: CPU seconds, address
space, open files, and no core dumps. A pathological file can exhaust its own
worker, never the server. Prints one JSON document on standard output.

It reads bytes and parses them. It never imports, executes or renders anything
it was given.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

#: The version of the reading logic, recorded on every unit it produced.
VERSION = "1"


def read(root: Path, dialect: str) -> dict[str, Any]:
    from prama.codeintake.inventory import READ, kind_of
    from prama.lineage.sql import SqlLineage, split_statements

    reader = SqlLineage(dialect=dialect)
    units: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        kind = kind_of(path)
        if kind not in READ:
            units.append(
                {"path": relative, "kind": kind, "statements": 0, "gaps": [], "read": False}
            )
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        statements = split_statements(text)
        gaps: list[dict[str, str]] = []
        for statement in statements:
            extraction = reader.extract(statement, job=relative)
            fell_back = any(g.kind == "regex_fallback" for g in extraction.gaps)
            gaps.extend({"kind": g.kind, "detail": g.detail} for g in extraction.gaps)
            for edge in extraction.edges:
                edges.append(
                    {
                        "unit": relative,
                        "source": [edge.source.dataset, edge.source.name],
                        "target": [edge.target.dataset, edge.target.name],
                        "transform": edge.transform.value,
                        "expression": edge.expression,
                        "fallback": fell_back,
                    }
                )
        units.append(
            {
                "path": relative,
                "kind": kind,
                "statements": len(statements),
                "gaps": gaps,
                "read": True,
            }
        )
    return {"version": VERSION, "units": units, "edges": edges}


def limit_resources(cpu_seconds: int = 120, memory_bytes: int = 2 << 30) -> None:
    """Set in the child before it runs (POSIX only)."""
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


if __name__ == "__main__":
    json.dump(read(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "ansi"), sys.stdout)
