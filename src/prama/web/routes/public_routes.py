"""The public pages: the landing page, the help centre, and About.

Adopted from Maya's ``home.py``: somebody who arrives at ``/`` without a
session sees what Prama is and how to get in, rather than being bounced to a
sign-in form for a product they have not been told the name of. A signed-in
person goes straight to the estate, which is where the work is.

Every page here is anonymous (``scope=None``). None of them reads the database
or reveals anything about the estate; they describe the product, and the
product's documentation is not a secret.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import FileResponse

from prama.core.errors import NotFoundError
from prama.report.themes import THEMES
from prama.security.scopes import SCOPES
from prama.version import SCHEMA_VERSION
from prama.web import about, help_catalog, help_subjects
from prama.web.rendering import NAVIGATION, render
from prama.web.routes.base import UiRoutes

#: Images the corpus embeds (diagrams, screenshots, the mark). A closed set:
#: ``help_catalog.asset`` refuses anything that resolves outside ``docs/assets``.
_ASSET_TYPES = {".svg": "image/svg+xml", ".png": "image/png"}


#: The declarations the landing page's hero types out, then proves. Each PQL
#: string is parsed by a test (tests/web/test_landing.py), so the hero cannot
#: show a control the language would refuse. The run figures are illustrative
#: and the page says so; one of the four fails, because a hero in which
#: everything passes is advertising, not evidence.
HERO_DECLARATIONS: tuple[dict[str, object], ...] = (
    {
        "said": "Every trade has a notional.",
        "pql": "CHECK trades.notional IS NOT NULL",
        "rows": 1_204_339,
        "violations": 0,
    },
    {
        "said": "One trade, one booking.",
        "pql": "CHECK trades.trade_id IS UNIQUE",
        "rows": 1_204_339,
        "violations": 0,
    },
    {
        "said": "Settlement follows the trade.",
        "pql": "CHECK trades.settle_date >= trades.trade_date",
        "rows": 1_204_339,
        "violations": 17,
    },
    {
        "said": "Every instrument has a valid ISIN.",
        "pql": "CHECK CONCEPT Instrument.ISIN IS VALID ISIN",
        "rows": 88_412,
        "violations": 0,
    },
)


class PublicRoutes(UiRoutes):
    """Landing, help and about."""

    def register(self) -> None:
        self.page("/", self.landing, name="home", scope=None)
        self.page("/about", self.about, name="about", scope=None)
        self.page("/about/competitive", self.competitive, name="competitive", scope=None)
        self.page("/legal", self.legal, name="legal", scope=None)
        self.page("/help", self.help_index, name="help_index", scope=None)
        self.page("/help/assets/{name:path}", self.help_asset, name="help_asset", scope=None)
        self.page("/help/images/{name:path}", self.help_image, name="help_image", scope=None)
        # Before /help/{slug}, which would otherwise read "case-studies" as a topic.
        self.page("/help/case-studies", self.case_studies, name="help_case_studies", scope=None)
        self.page("/help/case-studies/{slug}", self.case_study, name="help_case_study", scope=None)
        # Before /help/{slug}, which would otherwise read "library" as a topic.
        self.page("/help/library", self.help_library, name="help_library", scope=None)
        self.page("/help/{slug}", self.help_topic, name="help_topic", scope=None)

    async def landing(self, request: Request) -> Any:
        """What Prama is. Shown to everybody, signed in or not.

        It used to send a signed-in person straight on to /estate, so the brand
        in the header, which links here, looked broken to anyone using the
        console. Now the brand always reaches it, and the way back is the
        Console button in the header and the "Open the console" buttons here.
        """
        config = request.app.state.config
        # Numbers on the landing page are counted, never typed: a figure that
        # is restated here is one that is wrong the day after it is written.
        stats = {
            "areas": len(NAVIGATION),
            "themes": len(THEMES),
            "scopes": len(SCOPES),
            "help": len(help_catalog.BY_SLUG),
        }
        return render(
            request,
            "public/landing.html",
            public_nav=True,
            stats=stats,
            declarations=HERO_DECLARATIONS,
            single_tenant=bool(config.get_str("tenancy.default_tenant", "")),
        )

    async def about(self, request: Request) -> Any:
        from prama.web import case_studies

        # Counted from this build, never typed: a figure restated on a page is
        # wrong the day after it is written.
        facts = {
            "schema": SCHEMA_VERSION,
            "themes": ", ".join(theme.label for theme in THEMES),
            "help": len(help_catalog.BY_SLUG),
            "studies": len(case_studies.catalog()),
        }
        return render(request, "public/about.html", public_nav=True, facts=facts)

    async def competitive(self, request: Request) -> Any:
        """Where Prama sits among the categories, after Maya's /about/competitive."""
        return render(
            request,
            "public/competitive.html",
            public_nav=True,
            categories=about.CATEGORIES,
            rows=about.ROWS,
            shines=about.SHINES,
            behind=about.BEHIND,
            long_form="competitive-analysis",
        )

    async def legal(self, request: Request) -> Any:
        """The licence and the legal notice, read from the files that are the
        authority for them rather than paraphrased here."""
        documents = []
        for name in ("LICENSE", "NOTICE"):
            path = help_catalog.REPO_ROOT / name
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            documents.append({"name": name, "text": text})
        return render(
            request,
            "public/legal.html",
            public_nav=not request.session.get("principal_id"),
            documents=documents,
        )

    async def help_index(self, request: Request) -> Any:
        return render(
            request,
            "help/index.html",
            public_nav=not request.session.get("principal_id"),
            catalog=help_subjects.catalog(),
            documents=len(help_catalog.BY_SLUG),
            slugs=help_catalog.BY_SLUG,
            studies=_studies(),
        )

    async def help_library(self, request: Request) -> Any:
        """Every guide and document, by kind: the catalogue derived from the files."""
        return render(
            request,
            "help/library.html",
            public_nav=not request.session.get("principal_id"),
            sections=help_catalog.SECTIONS,
        )

    async def case_studies(self, request: Request) -> Any:
        from prama.web import case_studies

        return render(
            request,
            "help/case_studies.html",
            public_nav=not request.session.get("principal_id"),
            studies=case_studies.catalog(),
        )

    async def case_study(self, request: Request, slug: str) -> Any:
        from prama.web import case_studies

        studies = case_studies.catalog()
        study = next((s for s in studies if s["slug"] == slug), None)
        if study is None:
            raise NotFoundError(
                f"there is no case study called {slug!r}",
                remedy="The case studies are listed at /help/case-studies.",
                context={"slug": slug},
            )
        i = studies.index(study)
        return render(
            request,
            "help/case_study.html",
            public_nav=not request.session.get("principal_id"),
            study=study,
            doc=case_studies.render(slug),
            prev=studies[i - 1] if i else None,
            next=studies[i + 1] if i + 1 < len(studies) else None,
        )

    async def help_topic(self, request: Request, slug: str) -> Any:
        """A subject (help_subjects), or one guide or document (help_catalog)."""
        view = help_subjects.view(slug)
        if view is not None:
            opening = view["opening"]["entry"]
            return render(
                request,
                "help/subject.html",
                public_nav=not request.session.get("principal_id"),
                v=view,
                opening=help_catalog.render_entry(opening),
            )
        entry = help_catalog.BY_SLUG.get(slug)
        if entry is None:
            raise NotFoundError(
                f"there is no help topic called {slug!r}",
                remedy="/help lists every subject, and /help/library every document.",
                context={"slug": slug},
            )
        return render(
            request,
            "help/topic.html",
            public_nav=not request.session.get("principal_id"),
            entry=entry,
            rendered=help_catalog.render_entry(entry),
            sections=help_catalog.SECTIONS,
            part_of=help_subjects.subjects_reading(slug),
        )

    async def help_image(self, name: str) -> Any:
        """An image a document keeps beside itself, anywhere under ``docs/``."""
        return await self.help_asset(name, help_catalog.DOCS_DIR)

    async def help_asset(self, name: str, root: Path | None = None) -> Any:
        path = help_catalog.asset(name, root)
        media = _ASSET_TYPES.get(path.suffix.lower()) if path else None
        if path is None or media is None:
            raise NotFoundError(
                f"no such help asset: {name!r}",
                remedy="Help pages link their own images.",
                context={"name": name},
            )
        return FileResponse(path, media_type=media)


def _studies() -> list[dict[str, str]]:
    from prama.web import case_studies

    return case_studies.catalog()
