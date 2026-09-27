"""What kind of code each file is, by name and a look at its first bytes.

The inventory is the denominator: a run reports what it read out of everything
it found, so "12 of 40 units understood" is visible rather than the 28 others
silently missing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

#: Kinds whose lineage this build reads, and what reads it.
READ: dict[str, str] = {
    "sql": "sqlglot",
    # The XML scanners are declared unverified against real exports
    # (prama.lineage.scan), so their edges are stored as inferred.
    "ssis": "ssis_xml",
    "informatica": "powercenter_xml",
}

_BY_SUFFIX: dict[str, str] = {
    ".sql": "sql",
    ".ddl": "sql",
    ".bteq": "sql",
    ".py": "python",
    ".ipynb": "notebook",
    ".dtsx": "ssis",
    ".cbl": "cobol",
    ".cob": "cobol",
    ".cpy": "cobol",
    ".jcl": "jcl",
    ".sh": "shell",
    ".ksh": "shell",
    ".scala": "scala",
    ".java": "java",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".xml": "xml",
}


def kind_of(path: Path) -> str:
    """A file's kind, refined by content where the suffix is not enough."""
    name = path.name.lower()
    if name == "dbt_project.yml":
        return "dbt_project"
    kind = _BY_SUFFIX.get(path.suffix.lower(), "other")
    if kind in ("python", "xml"):
        head = path.read_bytes()[:4096]
        if b"\x00" in head:
            return "binary"
        if kind == "python" and (b"from airflow" in head or b"import airflow" in head):
            return "airflow"
        if kind == "python" and b"pyspark" in head:
            return "pyspark"
        if kind == "xml" and b"POWERMART" in head.upper():
            return "informatica"
    return kind


def inventory(root: Path, files: dict[str, tuple[str, int]]) -> dict[str, list[str]]:
    """Paths grouped by kind."""
    grouped: dict[str, list[str]] = {}
    for relative in sorted(files):
        grouped.setdefault(kind_of(root / relative), []).append(relative)
    return grouped
