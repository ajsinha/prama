"""Print artefacts: the documents that leave the building.

A screen is read by someone who can click into it. A pack is read by an auditor
six months later with nothing but the paper, so it has to carry its own
context — what it covers, what it was generated from, and above all **what it
does not cover**. That last one is the whole difference between an attestation
and a marketing document, and it is the one every tool of this kind omits.

Rendered as self-contained HTML with a print stylesheet rather than through a
PDF engine. WeasyPrint and its relatives pull in cairo, pango and their system
packages, which is a serious dependency to add to an on-premises install for a
job the browser already does correctly; "Print to PDF", or a headless Chrome in
the deployment, produces the same bytes. The trade is real and it is stated
here rather than discovered later: there is no server-side PDF *file* until a
deployment adds a renderer.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path
from typing import Any

import jinja2

from prama.core.clock import utc_now
from prama.version import PRODUCT_NAME, PRODUCT_TAGLINE, VERSION

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
    undefined=jinja2.StrictUndefined,
)


@dataclasses.dataclass(frozen=True, slots=True)
class Coverage:
    """What a pack looked at, and what it did not.

    Both numbers, always, and the second one rendered whether or not it is
    zero. A pack listing forty datasets is a claim about forty datasets; the
    reader cannot tell whether that is the estate or a fifth of it, and every
    tool of this kind lets them assume the former.
    """

    #: What the pack reports on.
    included: int
    #: What exists and is not in it, and why.
    excluded: int = 0
    exclusion_reason: str = ""

    @property
    def total(self) -> int:
        return self.included + self.excluded

    @property
    def is_complete(self) -> bool:
        return self.excluded == 0

    def describe(self) -> str:
        if self.is_complete:
            return f"All {self.included} covered."
        share = (self.included / self.total * 100) if self.total else 0.0
        return (
            f"{self.included} of {self.total} covered ({share:.0f}%). "
            f"{self.excluded} excluded: {self.exclusion_reason or 'no reason recorded'}."
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Provenance:
    """Where a document came from, printed on the document.

    An artefact that cannot say which build produced it, from which tenant, at
    which instant, is not evidence — it is a screenshot. The version is read
    from ``prama.version``, which is the only authority.
    """

    tenant_id: str
    generated_at: datetime = dataclasses.field(default_factory=utc_now)
    generated_by: str = ""
    version: str = VERSION

    @property
    def stamp(self) -> str:
        return self.generated_at.strftime("%Y-%m-%d %H:%M:%SZ")


@dataclasses.dataclass(frozen=True, slots=True)
class Artefact:
    """A rendered document."""

    title: str
    html: str
    provenance: Provenance

    @property
    def filename(self) -> str:
        """A name that sorts and does not collide.

        Date first so a directory of packs sorts chronologically, and the
        instant included because two packs for the same estate on the same day
        are a normal thing to produce and silently overwriting the first is not.
        """
        slug = "".join(
            character.lower() if character.isalnum() else "-" for character in self.title
        ).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        return f"{self.provenance.generated_at.strftime('%Y%m%d-%H%M%S')}-{slug}.html"

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / self.filename
        path.write_text(self.html, encoding="utf-8")
        return path


def _render(template: str, *, title: str, provenance: Provenance, **context: Any) -> Artefact:
    html = _environment.get_template(template).render(
        title=title,
        provenance=provenance,
        product_name=PRODUCT_NAME,
        tagline=PRODUCT_TAGLINE,
        stylesheet=(TEMPLATES_DIR / "print.css").read_text(encoding="utf-8"),
        **context,
    )
    return Artefact(title=title, html=html, provenance=provenance)


def declaration_pack(
    *,
    provenance: Provenance,
    datasets: list[dict[str, Any]],
    coverage: Coverage,
    gaps: dict[str, list[str]] | None = None,
) -> Artefact:
    """What the business says its data is.

    The artefact a regulator's first question asks for, and the one a
    physical-first tool cannot produce: it is a record of *declarations*, so it
    includes the datasets nobody has connected to. Those are the interesting
    rows.
    """
    return _render(
        "declaration_pack.html",
        title="Declaration pack",
        provenance=provenance,
        datasets=datasets,
        coverage=coverage,
        gaps=gaps or {},
        undeclared_grain=sum(1 for d in datasets if not d.get("has_grain")),
        unconnected=sum(1 for d in datasets if not d.get("is_bound")),
    )


def control_pack(
    *,
    provenance: Provenance,
    controls: list[dict[str, Any]],
    coverage: Coverage,
    unsatisfiable: list[dict[str, Any]] | None = None,
) -> Artefact:
    """Every control, its reason, and the SQL it becomes.

    The SQL is included because the point of the document is that the platform
    is inspectable rather than trusted: a reader who cannot see the query is
    being asked to take the verdict on faith, which is the thing Prama exists
    to stop doing.
    """
    return _render(
        "control_pack.html",
        title="Control pack",
        provenance=provenance,
        controls=controls,
        coverage=coverage,
        unsatisfiable=unsatisfiable or [],
    )
