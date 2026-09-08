"""Reading and splitting the authoritative schema file.

Prama has no migrations. ``schema/sqlite.sql`` and ``schema/postgres.sql`` are
the authority for their engines, and this module is the only thing that reads
them. It does three jobs: read, split into executable statements, and describe
the objects declared — the last of which is what makes verification possible
without a second, hand-maintained description of the schema.

Statement splitting is deliberately simple, because the schema files are
deliberately simple: no procedural blocks, no dollar-quoting, no triggers. If a
future schema needs those, this splitter must grow a real tokenizer rather than
acquire special cases — the failure mode of a half-clever splitter is a
statement silently truncated at a semicolon inside a string literal.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path

from prama.core.errors import DatabaseError

_LINE_COMMENT = re.compile(r"--[^\n]*")
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9_]*))",
    re.IGNORECASE,
)
_CREATE_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX(?:\s+IF\s+NOT\s+EXISTS)?\s+"
    r"(?:\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9_]*))\s+ON\s+"
    r"(?:\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9_]*))",
    re.IGNORECASE,
)
#: One column definition, which may wrap onto continuation lines carrying an
#: inline CHECK. ``[\s\S]*`` rather than ``.*`` so the wrap does not silently
#: end the match and drop the column from the parsed schema — a defect that
#: would make verification quietly incomplete rather than loudly wrong.
_COLUMN = re.compile(
    r"^\s*(?:\"(?P<qname>[^\"]+)\"|(?P<name>[a-z_][a-z0-9_]*))\s+"
    r"(?P<type>VARCHAR\s*\(\s*\d+\s*\)|TEXT\b|INTEGER\b|REAL\b)(?P<rest>[\s\S]*)$",
    re.IGNORECASE,
)
_NOT_A_COLUMN = re.compile(
    r"^\s*(PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|CONSTRAINT)\b", re.IGNORECASE
)


@dataclasses.dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    type: str
    nullable: bool


@dataclasses.dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    columns: tuple[ColumnSpec, ...]
    indexes: tuple[str, ...] = ()

    def column(self, name: str) -> ColumnSpec | None:
        return next((c for c in self.columns if c.name == name), None)


@dataclasses.dataclass(frozen=True, slots=True)
class SchemaFile:
    """A parsed schema file: its statements, its shape, and its digest."""

    path: Path
    digest: str
    statements: tuple[str, ...]
    tables: tuple[TableSpec, ...]

    def table(self, name: str) -> TableSpec | None:
        return next((t for t in self.tables if t.name == name), None)

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.tables)

    @property
    def index_names(self) -> tuple[str, ...]:
        return tuple(sorted(i for t in self.tables for i in t.indexes))


class SchemaLoader:
    """Reads and parses an authoritative schema file."""

    def load(self, path: Path) -> SchemaFile:
        if not path.is_file():
            raise DatabaseError(
                f"authoritative schema file not found: {path}",
                code="DB.SCHEMA_FILE_MISSING",
                remedy=(
                    "Prama has no migrations; this file is the schema. Restore it from the "
                    "repository, or set database.schema_dir to where it lives."
                ),
                context={"path": str(path)},
            )
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        statements = self._split(text)
        tables = self._parse_tables(statements)
        return SchemaFile(path=path, digest=digest, statements=statements, tables=tables)

    # -- parsing -----------------------------------------------------------

    @staticmethod
    def _split(text: str) -> tuple[str, ...]:
        stripped = _LINE_COMMENT.sub("", text)
        parts = [s.strip() for s in stripped.split(";")]
        return tuple(p for p in parts if p)

    def _parse_tables(self, statements: tuple[str, ...]) -> tuple[TableSpec, ...]:
        tables: dict[str, list[ColumnSpec]] = {}
        indexes: dict[str, list[str]] = {}
        order: list[str] = []
        for statement in statements:
            table_match = _CREATE_TABLE.search(statement)
            if table_match:
                name = table_match.group(1) or table_match.group(2)
                tables[name] = self._parse_columns(statement)
                order.append(name)
                continue
            index_match = _CREATE_INDEX.search(statement)
            if index_match:
                index_name = index_match.group(1) or index_match.group(2)
                table_name = index_match.group(3) or index_match.group(4)
                indexes.setdefault(table_name, []).append(index_name)
        return tuple(
            TableSpec(
                name=name,
                columns=tuple(tables[name]),
                indexes=tuple(sorted(indexes.get(name, []))),
            )
            for name in order
        )

    @staticmethod
    def _parse_columns(statement: str) -> list[ColumnSpec]:
        body_start = statement.find("(")
        if body_start < 0:
            return []
        body = statement[body_start + 1 : statement.rfind(")")]
        columns: list[ColumnSpec] = []
        depth = 0
        current: list[str] = []
        segments: list[str] = []
        for char in body:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if char == "," and depth == 0:
                segments.append("".join(current))
                current = []
            else:
                current.append(char)
        if current:
            segments.append("".join(current))
        for segment in segments:
            line = segment.strip()
            if not line or _NOT_A_COLUMN.match(line):
                continue
            match = _COLUMN.match(line)
            if not match:
                continue
            rest = match.group("rest").upper()
            nullable = "NOT NULL" not in rest and "PRIMARY KEY" not in rest
            columns.append(
                ColumnSpec(
                    name=match.group("qname") or match.group("name"),
                    type=match.group("type").upper(),
                    nullable=nullable,
                )
            )
        return columns
