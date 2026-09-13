"""Lineage out of the systems nobody wants to open.

docs/20 G2. Most of an enterprise's transformation logic is not in dbt. It is
in T-SQL stored procedures, PL/SQL packages, DB2 SQL PL, and ETL tools whose
last release was a decade ago — and the lineage in those systems is the lineage
that matters, because it is where the reporting layer actually comes from.

**What is verified here, and what is not, stated plainly.** The SQL dialects
are verified: T-SQL, PL/SQL and DB2 SQL PL are SQL with procedural wrappers
around it, the wrappers are removable, and the statements inside go through the
same extractor as everything else. Their tests run against real syntax.

The ETL formats are not verified against a real export, and cannot honestly be.
PowerCenter, DataStage and SSIS emit XML whose shape depends on the version,
the repository and in places the developer, and writing a parser against a
guess would produce something that looks like support and fails on first
contact — during somebody's evaluation. What ships is a **configurable**
mapping reader: the shape is expressed as element and attribute names, three
plausible configurations are provided as a starting point, and the class
reports what it found so a wrong configuration is visible in one run rather
than after a migration.

**Coverage is reported, always.** A scanner that parsed forty percent of a
package and says nothing is worse than one that parsed forty percent and says
so, because the graph it produces looks complete and the impact analysis built
on it is confidently wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import re
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar
from xml.etree import ElementTree

from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Extraction, Gap, SqlLineage


@dataclasses.dataclass(frozen=True, slots=True)
class ScanResult:
    """What a scanner found, and how much it could not read."""

    scanner: str
    source: str
    extraction: Extraction
    #: Units the scanner recognised — procedures, mappings, transformations.
    units_found: int = 0
    #: Units it recognised and could not read.
    units_unread: int = 0
    #: Set when the scanner is confident the configuration is wrong: it found
    #: the file and nothing in it. Distinguished from an empty file, because
    #: one is a bug and the other is a fact.
    misconfigured: str = ""

    @property
    def coverage(self) -> float:
        """The share of units this scanner read, between 0 and 1.

        Counted over *units*, not over gaps. `units_unread` is a count of gaps
        and a gap is column-level, so one unreadable mapping can produce five —
        and `(found - unread) / found` then reported a coverage of -400%, which
        printed as "read -4 of 1 units" (QA finding LIN-059).

        A Gap carries the statement it came from, so the units that failed can
        be counted properly rather than approximated by the failures.
        """
        if not self.units_found:
            return 0.0
        read = self.units_found - self.units_with_gaps
        return max(0.0, min(1.0, read / self.units_found))

    @property
    def units_with_gaps(self) -> int:
        """How many units produced at least one gap.

        A gap with no statement cannot be attributed, so it counts as its own
        unit — pessimistic, which is the right direction for a coverage figure.
        """
        attributed = {gap.statement for gap in self.extraction.gaps if gap.statement}
        unattributed = sum(1 for gap in self.extraction.gaps if not gap.statement)
        return min(self.units_found, len(attributed) + unattributed)

    def describe(self) -> str:
        if self.misconfigured:
            return f"{self.scanner} on {self.source}: {self.misconfigured}"
        head = (
            f"{self.scanner} read {self.units_found - self.units_with_gaps} of "
            f"{self.units_found} units in {self.source}, producing "
            f"{len(self.extraction.edges)} column edges"
        )
        if self.units_unread:
            head += (
                f". {self.units_unread} could not be read, so the graph from this "
                f"source is {self.coverage:.0%} complete and anything built on it "
                f"should say so"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanner": self.scanner,
            "source": self.source,
            "units_found": self.units_found,
            "units_unread": self.units_unread,
            "coverage": round(self.coverage, 4),
            "misconfigured": self.misconfigured,
            "extraction": self.extraction.to_dict(),
            "summary": self.describe(),
        }


class Scanner(abc.ABC):
    """Reads lineage out of one kind of legacy artefact."""

    name: ClassVar[str] = ""
    #: What this scanner has actually been tested against, in plain words. A
    #: capability list that does not distinguish "verified" from "written
    #: against the documentation" is a capability list that will be quoted in a
    #: procurement document.
    verified_against: ClassVar[str] = ""

    @abc.abstractmethod
    def scan(self, text: str, *, source: str = "") -> ScanResult:
        """Extract what can be extracted, and report what could not."""


# ---------------------------------------------------------------------------
# SQL dialects: verified
# ---------------------------------------------------------------------------


class ProceduralSqlScanner(Scanner):
    """SQL with a procedural wrapper around it.

    The three dialects that matter differ in how they declare a routine and
    hardly at all in the statements inside, which is why one class covers them:
    the wrapper is stripped, the statements go through the ordinary extractor,
    and anything the extractor could not read is reported by the extractor
    rather than swallowed here.
    """

    #: Where a routine begins, so the scanner can count units and attribute
    #: edges to the right job.
    routine: ClassVar[re.Pattern[str]] = re.compile(
        r"\bcreate\s+(or\s+(replace|alter)\s+)?(procedure|proc|function)\s+"
        r"(?P<name>[\w.\[\]\"]+)",
        re.IGNORECASE,
    )
    #: Constructs that carry logic the extractor cannot see through. Reported
    #: rather than ignored: dynamic SQL is where the interesting lineage hides,
    #: and a graph that silently omits it is complete-looking and wrong.
    opaque: ClassVar[tuple[tuple[str, str], ...]] = (
        (r"\bexec(ute)?\s*\(", "dynamic SQL assembled at run time"),
        (r"\bsp_executesql\b", "dynamic SQL via sp_executesql"),
        (r"\bexecute\s+immediate\b", "dynamic SQL via EXECUTE IMMEDIATE"),
        (r"\bopen\s+\w+\s+for\s+\w+\s*;", "a cursor opened over a variable"),
    )

    def __init__(
        self, *, dialect: str = "tsql", schema: Mapping[str, Sequence[str]] | None = None
    ) -> None:
        self._dialect = dialect
        self._sql = SqlLineage(schema=schema, dialect=dialect)
        self.name = f"{dialect}_procedural"  # type: ignore[misc]

    verified_against: ClassVar[str] = (
        "T-SQL, PL/SQL and DB2 SQL PL syntax written by hand for the tests. Not "
        "against a customer's repository, which is where the surprises are"
    )

    def scan(self, text: str, *, source: str = "") -> ScanResult:
        routines = list(self.routine.finditer(text))
        job = routines[0].group("name").strip('[]"') if routines else source

        gaps: list[Gap] = []
        for pattern, detail in self.opaque:
            for _ in re.finditer(pattern, text, re.IGNORECASE):
                gaps.append(
                    Gap(
                        kind="dynamic_sql",
                        detail=(
                            f"{detail} — the statement is built at run time and its "
                            f"lineage cannot be read from the source. This is where "
                            f"the interesting lineage usually hides"
                        ),
                        statement=source,
                    )
                )

        body = self._strip_procedural(text)
        extraction = self._sql.extract(body, job=job)
        combined = Extraction(
            edges=extraction.edges,
            gaps=(*extraction.gaps, *gaps),
            statements=extraction.statements,
        )
        return ScanResult(
            scanner=self.name,
            source=source,
            extraction=combined,
            units_found=max(1, len(routines)),
            units_unread=1 if (gaps and not extraction.edges) else 0,
        )

    @staticmethod
    def _strip_procedural(text: str) -> str:
        """Remove the wrapper so the statements inside can be parsed.

        Conservative on purpose: it removes the constructs that are definitely
        not SQL and leaves anything ambiguous alone, because a stripper that
        removes too much turns a readable statement into an unparseable one and
        the loss is silent.
        """
        without_comments = re.sub(r"--[^\n]*", " ", text)
        without_comments = re.sub(r"/\*.*?\*/", " ", without_comments, flags=re.DOTALL)
        patterns = (
            r"\bcreate\s+(or\s+(replace|alter)\s+)?(procedure|proc|function)\b[^;]*?\bas\b",
            r"\b(begin|end)\b\s*;?",
            r"\bdeclare\b[^;]*;",
            r"\bset\s+nocount\s+on\b\s*;?",
            r"\blanguage\s+sql\b",
        )
        body = without_comments
        for pattern in patterns:
            body = re.sub(pattern, " ", body, flags=re.IGNORECASE | re.DOTALL)
        return body


# ---------------------------------------------------------------------------
# ETL formats: configurable, and not verified against a real export
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class MappingShape:
    """Where the source and target columns live in one tool's XML.

    Expressed as names rather than hard-coded, because the three tools disagree
    with each other and each version disagrees with the last. A shape that is
    wrong shows up as zero mappings found on a file that plainly contains them,
    which is a fixable configuration rather than a rewrite.
    """

    name: str
    #: Element holding one transformation or mapping.
    mapping_element: str
    #: Element holding one field-to-field connection.
    link_element: str
    from_attribute: str
    to_attribute: str
    #: Attribute naming the instance a field belongs to, where the tool
    #: separates them.
    from_instance_attribute: str = ""
    to_instance_attribute: str = ""
    mapping_name_attribute: str = "NAME"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


#: Starting points, not certainties. Each is the shape the tool's documented
#: export uses; a real repository will differ in at least one of them, and the
#: scanner reporting zero mappings is how that is found in one run.
POWERCENTER = MappingShape(
    name="powercenter",
    mapping_element="MAPPING",
    link_element="CONNECTOR",
    from_attribute="FROMFIELD",
    to_attribute="TOFIELD",
    from_instance_attribute="FROMINSTANCE",
    to_instance_attribute="TOINSTANCE",
)

DATASTAGE = MappingShape(
    name="datastage",
    mapping_element="Job",
    link_element="Derivation",
    from_attribute="SourceColumn",
    to_attribute="TargetColumn",
    from_instance_attribute="SourceStage",
    to_instance_attribute="TargetStage",
    mapping_name_attribute="Identifier",
)

SSIS = MappingShape(
    name="ssis",
    mapping_element="pipeline",
    link_element="inputColumn",
    from_attribute="lineageId",
    to_attribute="name",
    mapping_name_attribute="refId",
)


class XmlMappingScanner(Scanner):
    """Field-to-field mappings out of an ETL tool's XML export.

    **Not verified against a real export**, and the class says so rather than
    implying otherwise. What it is verified to do is read the shape it is
    configured with and report clearly when that shape finds nothing — which
    turns "this does not work" into "the configuration is wrong, here is what
    was in the file", and the second is a morning's work rather than a
    procurement problem.
    """

    name: ClassVar[str] = "xml_mapping"
    verified_against: ClassVar[str] = (
        "XML in the documented shape of each tool, written for the tests. NOT "
        "against a customer repository export — the shapes vary by version and "
        "by repository, and a scanner claiming otherwise fails on first contact"
    )

    def __init__(self, shape: MappingShape) -> None:
        self._shape = shape

    def scan(self, text: str, *, source: str = "") -> ScanResult:
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as error:
            return ScanResult(
                scanner=f"{self.name}:{self._shape.name}",
                source=source,
                extraction=Extraction(
                    gaps=(Gap(kind="unparsed", detail=f"not XML: {error}", statement=source),)
                ),
                misconfigured=f"the file did not parse as XML: {error}",
            )

        shape = self._shape
        mappings = list(root.iter(shape.mapping_element))
        edges: list[Edge] = []
        gaps: list[Gap] = []

        for mapping in mappings:
            job = mapping.get(shape.mapping_name_attribute, source)
            for link in mapping.iter(shape.link_element):
                source_column = link.get(shape.from_attribute)
                target_column = link.get(shape.to_attribute)
                if not source_column or not target_column:
                    gaps.append(
                        Gap(
                            kind="incomplete_link",
                            detail=(
                                f"a {shape.link_element} in {job} has no "
                                f"{shape.from_attribute}/{shape.to_attribute}; either "
                                f"the shape is wrong for this export or the link is "
                                f"genuinely unbound"
                            ),
                            statement=source,
                        )
                    )
                    continue
                edges.append(
                    Edge(
                        source=Column(
                            dataset=link.get(shape.from_instance_attribute) or job,
                            name=source_column,
                        ),
                        target=Column(
                            dataset=link.get(shape.to_instance_attribute) or job,
                            name=target_column,
                        ),
                        transform=Transform.DERIVED,
                        produced_by=job,
                    )
                )

        misconfigured = ""
        if not mappings and len(list(root.iter())) > 1:
            # The file has content and none of it matched. Almost always the
            # shape rather than the file, and saying so turns "it does not
            # work" into a morning's work.
            misconfigured = (
                f"no <{shape.mapping_element}> elements were found, but the file "
                f"contains {len(list(root.iter()))} elements "
                f"({', '.join(sorted({e.tag for e in root.iter()})[:6])}...). The "
                f"shape configured for {shape.name} does not match this export"
            )

        return ScanResult(
            scanner=f"{self.name}:{shape.name}",
            source=source,
            extraction=Extraction(edges=tuple(edges), gaps=tuple(gaps), statements=len(mappings)),
            units_found=len(mappings),
            units_unread=sum(1 for _ in gaps),
            misconfigured=misconfigured,
        )


def default_scanners(
    schema: Mapping[str, Sequence[str]] | None = None,
) -> tuple[Scanner, ...]:
    """Everything that ships, with its verification status readable."""
    return (
        ProceduralSqlScanner(dialect="tsql", schema=schema),
        ProceduralSqlScanner(dialect="plsql", schema=schema),
        ProceduralSqlScanner(dialect="db2", schema=schema),
        XmlMappingScanner(POWERCENTER),
        XmlMappingScanner(DATASTAGE),
        XmlMappingScanner(SSIS),
    )
