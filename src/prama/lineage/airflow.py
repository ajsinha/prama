"""Column lineage from the SQL an Airflow DAG carries, read from the syntax tree.

A DAG file is parsed with `ast`, never imported: importing a DAG runs it.
Every operator argument named `sql` that is a string literal (or a list of
them) is read by the SQL parser, with the task id as the job. What is not a
literal is a named gap: templated SQL (`{{ ... }}`) is not rendered, a query
built from a variable is not guessed at, and a procedure call names the
procedure whose own source carries the lineage.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import re

from prama.lineage.sql import Extraction, Gap, SqlLineage, split_statements

_CALL = re.compile(r"^\s*(?:EXEC(?:UTE)?|CALL)\s+([\w.\[\]\"]+)", re.IGNORECASE)


def _task(node: ast.Call, job: str) -> str:
    for keyword in node.keywords:
        if keyword.arg == "task_id" and isinstance(keyword.value, ast.Constant):
            return f"{job}:{keyword.value.value!s}"
    return job


def _literals(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.List | ast.Tuple):
        values = [_literals(e) for e in node.elts]
        if all(v is not None for v in values):
            return [s for v in values if v for s in v]
    return None


def extract(source: str, *, job: str = "", dialect: str = "ansi") -> list[Extraction]:
    """One extraction per SQL statement the DAG carries, plus one for its gaps."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        gap = Gap(kind="unparsed", detail=f"not valid Python: {exc.msg}", statement=job)
        return [Extraction(gaps=(gap,), statements=1)]
    reader = SqlLineage(dialect=dialect)
    out: list[Extraction] = []
    gaps: list[Gap] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "sql":
                continue
            task = _task(node, job)
            texts = _literals(keyword.value)
            if texts is None:
                gaps.append(
                    Gap(
                        kind="unread",
                        detail=f"line {node.lineno}: SQL built at run time is not read",
                        statement=task,
                    )
                )
                continue
            for text in texts:
                if text.strip().lower().endswith(".sql"):
                    continue  # a file in the same tree, read as SQL in its own right
                if "{{" in text or "{%" in text:
                    gaps.append(
                        Gap(
                            kind="templated",
                            detail=f"line {node.lineno}: templated SQL is not rendered",
                            statement=task,
                        )
                    )
                    continue
                for statement in split_statements(text):
                    if called := _CALL.match(statement):
                        gaps.append(
                            Gap(
                                kind="procedure_call",
                                detail=f"line {node.lineno}: calls {called.group(1)}; its "
                                "lineage is read from the procedure's own source",
                                statement=task,
                            )
                        )
                        continue
                    out.append(reader.extract(statement, job=task))
    if gaps or not out:
        out.append(Extraction(gaps=tuple(gaps), statements=0 if out else 1))
    return out
