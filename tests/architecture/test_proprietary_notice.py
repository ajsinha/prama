"""Every source file carries the proprietary notice.

Prama is proprietary (LICENSE, NOTICE). A notice present on most files is a
notice somebody forgot on the rest, and the rest is what gets copied. This
guard makes the omission a build failure rather than a review comment.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Where Prama's own source lives. Third-party code under ``vendor/`` carries
#: its own licence and is excluded.
PATTERNS = (
    "src/**/*.py",
    "src/**/*.html",
    "src/**/*.css",
    "src/**/*.js",
    "src/**/*.md",
    "scripts/*",
    "schema/*.sql",
    ".githooks/*",
    "deploy/*",
    "deploy/**/*",
    "tests/**/*.py",
    "qa/regression-suite/**/*.py",
)


def _tracked() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--", *PATTERNS],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [REPO / f for f in out if "/vendor/" not in f and (REPO / f).is_file()]


def test_every_source_file_carries_the_notice() -> None:
    files = _tracked()
    assert len(files) > 500, "the pattern list reached almost nothing"
    missing = [
        str(f.relative_to(REPO))
        for f in files
        if f.stat().st_size and "Copyright" not in f.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not missing, (
        "these files lack the proprietary notice "
        "'Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.': "
        f"{missing}"
    )
