"""The case studies in Help: a card for each, and each study's README rendered as its page.

The READMEs are the source. The catalogue (number, title, what the study uses,
what it is for) is read from the table in `case-studies/README.md`, so a study
appears in Help when it appears there and nothing else has to be kept in step.
A link from one study to another opens that study's page; a link to a file in
a study opens it in the repository; a link to the design corpus opens its Help
page.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
import threading
from typing import Any

import markdown

from prama.web.help_catalog import REPO_ROOT, _relink

ROOT = REPO_ROOT / "case-studies"
REPOSITORY = "https://github.com/ajsinha/prama/blob/main/case-studies"
_ROW = re.compile(
    r"^\|\s*\*{0,2}(\d+)\*{0,2}\s*\|\s*\[([^\]]+)\]\(([\w-]+)/\)\s*\|([^|]*)\|([^|]*)\|", re.M
)
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def catalog() -> list[dict[str, str]]:
    """Every study listed in the index whose folder carries a README, in order."""
    index = ROOT / "README.md"
    if not index.is_file():
        return []
    out = []
    for number, title, folder, uses, about in _ROW.findall(index.read_text(encoding="utf-8")):
        if (ROOT / folder / "README.md").is_file():
            out.append(
                {
                    "num": number,
                    "title": title.strip(),
                    "slug": folder,
                    "uses": re.sub(r"\*+|`", "", uses).strip(),
                    "about": re.sub(r"\*+|`", "", about).strip(),
                }
            )
    return sorted(out, key=lambda s: int(s["num"]))


def _links(html: str, slug: str) -> str:
    def fix(match: re.Match[str]) -> str:
        href = match.group(1)
        if href.startswith(("http://", "https://", "#", "mailto:", "/")):
            return match.group(0)
        other = re.fullmatch(r"\.\./([\w-]+)/?", href)
        if other and (ROOT / other.group(1) / "README.md").is_file():
            return f'href="/help/case-studies/{other.group(1)}"'
        target = href[3:] if href.startswith("../") else f"{slug}/{href}"
        return f'href="{REPOSITORY}/{target}" target="_blank" rel="noopener"'

    return re.sub(r'href="([^"]+)"', fix, html)


def render(slug: str) -> dict[str, Any]:
    """{"html", "toc", "title"} for a study's README. Raises FileNotFoundError if absent."""
    path = ROOT / slug / "README.md"
    mtime = path.stat().st_mtime
    with _lock:
        hit = _cache.get(slug)
        if hit and hit[0] == mtime:
            return hit[1]
    source = path.read_text(encoding="utf-8")
    title = next((ln[2:].strip() for ln in source.splitlines() if ln.startswith("# ")), slug)
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    html = md.convert(source)
    html = re.sub(r"<h1[^>]*>.*?</h1>", "", html, count=1, flags=re.S)  # the page has its own
    html = _links(_relink(html, path.parent), slug)
    html = html.replace("<table>", '<div class="table-responsive"><table class="table table-sm">')
    html = html.replace("</table>", "</table></div>")
    rendered = {"html": html, "toc": getattr(md, "toc", ""), "title": title}
    with _lock:
        _cache[slug] = (mtime, rendered)
    return rendered
