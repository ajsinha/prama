"""Language services for PQL: diagnostics, completion, hover, definition.

One implementation, two surfaces. The console's editor and the ``prama lsp``
server both call this module and neither of them contains any analysis of its
own — because two implementations of "is this column real" is precisely how an
editor comes to underline something the compiler accepts, and once that happens
people stop reading the underlines.

Everything here is a pure function of text plus a catalogue. No I/O, no
database, no connector: the caller supplies what the estate declares, and this
decides what to say about the text. That is what lets a stdio LSP server, an
HTTP endpoint and a unit test exercise identical code.

It also stops short of the IR. Explaining a control means lowering it, and the
language layer may not depend on the lowerer — ``tests/architecture`` enforces
that, and it caught this file importing ``prama.ir`` for exactly that
convenience. The console explains a control where it already compiles one; a
language server has no business lowering anything.

Three rules the services keep, and each of them costs a feature somebody would
otherwise expect:

* **Never invent a name.** Completion offers declared datasets, their declared
  columns and the function catalogue, and nothing else. A suggestion the estate
  cannot satisfy is worse than no suggestion, because it gets accepted.
* **Never guess a position.** A diagnostic without a location is reported
  without one. An editor will happily underline line 1 column 1 and send the
  reader to the wrong place, which is worse than underlining nothing.
* **Say what was not checked.** A control against an undeclared dataset is not
  clean; it is unchecked, and the two must not render the same. The ``unchecked``
  level exists for exactly that and is carried through rather than filtered out
  for tidiness.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from prama.pql import parse
from prama.pql.errors import Position, PqlError
from prama.pql.library import FUNCTIONS
from prama.pql.lint import Linter
from prama.pql.tokens import KEYWORDS
from prama.pql.types import Catalogue, TypeChecker

#: What counts as a word under the cursor. Dots included: ``positions.notional``
#: is one thing to a reader and asking about half of it answers the wrong
#: question.
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")

#: Completion kinds, in the LSP's own numbering so the protocol layer does no
#: translation. A mapping here and a second mapping there is how "keyword"
#: renders as a variable in one editor and a snippet in another.
KIND_KEYWORD = 14
KIND_FUNCTION = 3
KIND_FIELD = 5
KIND_CLASS = 7


@dataclasses.dataclass(frozen=True, slots=True)
class Diagnostic:
    """One problem, at a place, or at no place at all."""

    message: str
    #: ``error`` · ``warning`` · ``unchecked``. Not collapsed into two: a
    #: control that could not be checked against a schema is neither wrong nor
    #: verified, and reporting it as either is a lie in one direction or the
    #: other.
    level: str = "error"
    remedy: str = ""
    line: int = 0
    column: int = 0
    length: int = 0
    #: Which control it belongs to, when the text holds several.
    control: str = ""

    @property
    def has_position(self) -> bool:
        """Whether this can be pointed at.

        False is a real answer and is reported as one. An editor asked to
        underline an unlocated diagnostic will pick line 1 and send the reader
        somewhere the problem is not.
        """
        return self.line > 0

    @property
    def severity(self) -> int:
        """The LSP severity. ``unchecked`` is information, not a warning.

        A warning says "this is probably wrong"; unchecked says "nobody has
        looked". Rendering the second as the first trains people to dismiss
        both.
        """
        return {"error": 1, "warning": 2, "unchecked": 3}.get(self.level, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "level": self.level,
            "remedy": self.remedy,
            "line": self.line,
            "column": self.column,
            "length": self.length,
            "control": self.control,
            "severity": self.severity,
            "has_position": self.has_position,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Completion:
    label: str
    kind: int
    detail: str = ""
    documentation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "kind": self.kind,
            "detail": self.detail,
            "documentation": self.documentation,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Hover:
    """What a name means, in the words the estate used."""

    title: str
    body: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.title

    def markdown(self) -> str:
        return f"**{self.title}**\n\n{self.body}" if self.body else f"**{self.title}**"

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "body": self.body, "markdown": self.markdown()}


class LanguageService:
    """Everything an editor asks about a piece of PQL."""

    def __init__(self, catalogue: Catalogue | None = None) -> None:
        self._catalogue = catalogue or Catalogue()

    @property
    def catalogue(self) -> Catalogue:
        return self._catalogue

    # -- diagnostics --------------------------------------------------------

    def diagnostics(self, text: str) -> list[Diagnostic]:
        """Every problem in the text, not just the first.

        A checker that stopped at the first error would make somebody fix a
        control one message at a time, and each round trip is a chance to give
        up.
        """
        if not text.strip():
            return []
        try:
            program = parse(text)
        except PqlError as exc:
            return [_from_error(exc)]

        checker = TypeChecker(self._catalogue)
        linter = Linter()
        out: list[Diagnostic] = []
        # An undeclared dataset is one fact about the estate, not one fact per
        # control. Repeating it buries the findings that really are about a
        # control.
        said: set[str] = set()

        for index, control in enumerate(program.controls):
            label = control.name or f"control {index + 1}"
            for finding in checker.check(control, source=text):
                if finding.message in said:
                    continue
                said.add(finding.message)
                out.append(_from_finding(finding, label))
            for lint in linter.check(control):
                at = _at(getattr(lint, "position", None))
                out.append(
                    Diagnostic(
                        message=lint.message,
                        level="warning",
                        remedy=getattr(lint, "remedy", ""),
                        control=label,
                        line=at["line"],
                        column=at["column"],
                        length=at["length"],
                    )
                )
        return out

    # -- completion ---------------------------------------------------------

    def completions(self, text: str, line: int, column: int) -> list[Completion]:
        """What may legitimately be typed here.

        Never a name the estate cannot satisfy. After a dot the answer is that
        dataset's declared columns and nothing else — offering every column in
        the estate would produce a control that parses, type-checks against the
        wrong dataset and fails at compile time with a message about SQL.
        """
        prefix, qualifier = _context(text, line, column)
        if qualifier:
            schema = self._catalogue.get(qualifier)
            if schema is None:
                # Not "every column we know". A dataset nobody declared has no
                # columns to offer, and inventing some is how a control ends up
                # naming a column that has never existed.
                return []
            return [
                Completion(
                    label=col.name,
                    kind=KIND_FIELD,
                    detail=f"{qualifier}.{col.name}: {col.type_name or 'unknown type'}",
                    documentation=("nullable" if col.nullable else "declared never null"),
                )
                for col in schema.columns
                if col.name.lower().startswith(prefix.lower())
            ]

        lowered = prefix.lower()
        out: list[Completion] = [
            Completion(label=name, kind=KIND_CLASS, detail=f"dataset · {len(s.columns)} column(s)")
            for name, s in sorted(self._catalogue.datasets.items())
            if name.lower().startswith(lowered)
        ]
        out += [
            Completion(
                label=fn.name,
                kind=KIND_FUNCTION,
                detail=f"{fn.name}(…) → {fn.returns}",
                documentation=fn.summary,
            )
            for fn in (FUNCTIONS.find(name) for name in FUNCTIONS.names())
            if fn is not None and fn.name.lower().startswith(lowered)
        ]
        out += [
            Completion(label=word, kind=KIND_KEYWORD)
            for word in sorted(KEYWORDS)
            if word.lower().startswith(lowered)
        ]
        return out

    # -- hover --------------------------------------------------------------

    def hover(self, text: str, line: int, column: int) -> Hover:
        """What the name under the cursor means.

        Answered from the estate and the function catalogue, never from a
        glossary maintained beside them. A hover that described a column
        differently from the declaration would be the more readable of two
        answers and the wrong one.
        """
        word, qualifies = _word_at(text, line, column)
        if not word:
            return Hover(title="")

        if "." in word:
            dataset, _, field = word.rpartition(".")
            schema = self._catalogue.get(dataset)
            column_ = schema.column(field) if schema else None
            if column_ is not None:
                return Hover(
                    title=f"{dataset}.{column_.name}",
                    body=(
                        f"{column_.type_name or 'type not declared'} · "
                        f"{'nullable' if column_.nullable else 'declared never null'} · "
                        f"family {column_.family}"
                    ),
                )
            if schema is not None:
                return Hover(
                    title=f"{dataset}.{field}",
                    body=(
                        f"**Not a declared column of {dataset}.** "
                        + (
                            f"Did you mean `{schema.suggest(field)}`? "
                            if schema.suggest(field)
                            else ""
                        )
                        + f"Declared: {', '.join(schema.column_names) or 'none'}."
                    ),
                )
            return Hover(
                title=word,
                body=(
                    f"`{dataset}` is not declared, so nothing here has been checked "
                    "against a schema. A control written against it will parse and "
                    "will not be verified."
                ),
            )

        schema = self._catalogue.get(word)
        if schema is not None:
            return Hover(
                title=word,
                body=f"Declared dataset · {len(schema.columns)} column(s): "
                f"{', '.join(schema.column_names) or 'none declared'}.",
            )

        function = FUNCTIONS.find(word)
        if function is not None:
            lines = [function.summary, f"Returns {function.returns}."]
            if function.unsupported_on:
                lines.append("Not available on " + ", ".join(sorted(function.unsupported_on)) + ".")
            if function.excel_divergence:
                lines.append(f"Differs from Excel: {function.excel_divergence}")
            return Hover(title=f"{word.upper()}(…)", body=" ".join(lines))

        if word.upper() in KEYWORDS:
            return Hover(title=word.upper(), body="A PQL keyword.")
        if qualifies:
            # It is being used as a dataset — something follows a dot — and it
            # is not declared. Saying nothing here would leave the one case
            # somebody most needs a hover for as the one case with no hover.
            return Hover(
                title=word,
                body=(
                    f"`{word}` is not declared, so nothing written against it has "
                    "been checked against a schema. A control naming it will parse "
                    "and will not be verified."
                ),
            )
        return Hover(title="")


def _from_error(exc: PqlError) -> Diagnostic:
    at = _at(getattr(exc, "position", None))
    return Diagnostic(
        message=str(exc),
        level="error",
        remedy=getattr(exc, "remedy", ""),
        line=at["line"],
        column=at["column"],
        length=at["length"],
    )


def _from_finding(finding: Any, control: str) -> Diagnostic:
    at = _at(finding.position)
    return Diagnostic(
        message=finding.message,
        level=finding.level,
        remedy=finding.remedy,
        control=control,
        line=at["line"],
        column=at["column"],
        length=at["length"],
    )


def _at(position: Position | None) -> dict[str, int]:
    """A location, or zeros meaning "not located".

    Zeros rather than ones. One-one is a real place, and a diagnostic that
    claims it sends the reader to the top of the file to look for a problem
    that is somewhere else.
    """
    if position is None:
        return {"line": 0, "column": 0, "length": 0}
    return {
        "line": getattr(position, "line", 0) or 0,
        "column": getattr(position, "column", 0) or 0,
        "length": getattr(position, "length", 0) or 0,
    }


def _line_of(text: str, line: int) -> str:
    lines = text.splitlines()
    return lines[line - 1] if 1 <= line <= len(lines) else ""


def _context(text: str, line: int, column: int) -> tuple[str, str]:
    """The word being typed, and the dataset qualifying it if there is one."""
    source = _line_of(text, line)
    upto = source[: max(0, column - 1)]
    match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z0-9_]*)$", upto)
    if match:
        return match.group(2), match.group(1)
    word = re.search(r"([A-Za-z_][A-Za-z0-9_]*)$", upto)
    return (word.group(1) if word else ""), ""


def _word_at(text: str, line: int, column: int) -> tuple[str, bool]:
    """The name under the cursor, and whether it qualifies something.

    Truncated at the cursor's own segment: hovering ``positions`` in
    ``positions.notional`` asks about the dataset, hovering ``notional`` asks
    about the column. Returning the whole dotted name either way answers the
    second question both times, which is wrong in the half where somebody is
    checking a dataset name.

    The flag matters for the case with no answer anywhere else — a name used as
    a dataset that nobody declared. That is the one hover somebody most needs,
    and without the flag it is the one hover that comes back empty.
    """
    source = _line_of(text, line)
    for match in WORD.finditer(source):
        # Inclusive of the character just past the word: a cursor resting at the
        # end of a name is asking about that name, not about the space after it.
        if match.start() < column <= match.end() + 1:
            word = match.group(0).rstrip(".")
            cut = column - 1 - match.start()
            head = word[:cut]
            if "." in word and "." not in head:
                return word.split(".", 1)[0], True
            return word, False
    return "", False


__all__ = [
    "KIND_CLASS",
    "KIND_FIELD",
    "KIND_FUNCTION",
    "KIND_KEYWORD",
    "Completion",
    "Diagnostic",
    "Hover",
    "LanguageService",
]
