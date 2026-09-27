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
VERSION = "4"


def _extract(kind: str, text: str, relative: str, dialect: str) -> list[tuple[Any, str]]:
    """(extraction, method) pairs for one file's text."""
    from prama.lineage.scan import POWERCENTER, SSIS, ProceduralSqlScanner, XmlMappingScanner
    from prama.lineage.sql import SqlLineage, split_statements

    if kind == "pyspark":
        from prama.lineage import pyspark

        return [(pyspark.extract(text, job=relative), "code:pyspark_ast")]
    if kind == "pandas":
        from prama.lineage import pandas_ast

        return [(pandas_ast.extract(text, job=relative), "code:pandas_ast")]
    if kind == "airflow":
        from prama.lineage import airflow

        return [
            (
                extraction,
                "code:regex"
                if any(g.kind == "regex_fallback" for g in extraction.gaps)
                else "code:airflow_sql",
            )
            for extraction in airflow.extract(text, job=relative, dialect=dialect)
        ]
    if kind == "ssis":
        return [(XmlMappingScanner(SSIS).scan(text, source=relative).extraction, "code:ssis_xml")]
    if kind == "informatica":
        scanner = XmlMappingScanner(POWERCENTER)
        return [(scanner.scan(text, source=relative).extraction, "code:powercenter_xml")]
    if ProceduralSqlScanner.routine.search(text):
        # A stored procedure: the wrapper is stripped and dynamic SQL is
        # reported as a gap by the scanner rather than guessed at.
        flavour = dialect if dialect in ("tsql", "plsql", "db2") else "tsql"
        scanned = ProceduralSqlScanner(dialect=flavour).scan(text, source=relative)
        return [(scanned.extraction, f"code:{flavour}_procedure")]
    reader = SqlLineage(dialect=dialect)
    out = []
    for statement in split_statements(text):
        extraction = reader.extract(statement, job=relative)
        fell_back = any(g.kind == "regex_fallback" for g in extraction.gaps)
        out.append((extraction, "code:regex" if fell_back else "code:sqlglot"))
    return out


def read(root: Path, dialect: str) -> dict[str, Any]:
    from prama.codeintake.inventory import READ, kind_of

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
        gaps: list[dict[str, str]] = []
        statements = 0
        for extraction, method in _extract(kind, text, relative, dialect):
            statements += max(1, extraction.statements)
            gaps.extend({"kind": g.kind, "detail": g.detail} for g in extraction.gaps)
            for edge in extraction.edges:
                edges.append(
                    {
                        "unit": relative,
                        "source": [edge.source.dataset, edge.source.name],
                        "target": [edge.target.dataset, edge.target.name],
                        "transform": edge.transform.value,
                        "expression": edge.expression,
                        "method": method,
                    }
                )
        units.append(
            {"path": relative, "kind": kind, "statements": statements, "gaps": gaps, "read": True}
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
