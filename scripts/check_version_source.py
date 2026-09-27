#!/usr/bin/env python3
"""The version is stated once. Every other copy must agree with it.

Adopted from Maya's ``version_single_source.py`` gate. ``src/prama/version.py``
is the only authority (CLAUDE.md). Two things are checked:

1. **No Python source restates it.** A literal equal to ``VERSION`` anywhere
   under ``src/`` other than ``version.py`` is a copy that will rot.
2. **The copies that must exist agree.** Helm needs a chart version and an
   image tag, and a few documents show a version in example output. Those are
   listed here and compared; a new copy elsewhere is not checked, so add it.

Exits 1 with the offending locations, 0 when everything agrees.

    python3 scripts/check_version_source.py [--root DIR]

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SEMVER = r"(\d+\.\d+\.\d+(?:[-+][\w.]+)?)"

#: Files that legitimately carry a copy, and how to find it in each.
COPIES: dict[str, tuple[str, ...]] = {
    "deploy/helm/prama/Chart.yaml": (rf"^version:\s*{SEMVER}", rf'^appVersion:\s*"?{SEMVER}"?'),
    "deploy/helm/prama/values.yaml": (rf'^\s*tag:\s*"?{SEMVER}"?',),
    "deploy/README.md": (rf"prama:{SEMVER}",),
    "QUICKSTART.md": (rf"Prama {SEMVER}",),
}


def authority(root: Path) -> str:
    text = (root / "src/prama/version.py").read_text(encoding="utf-8")
    match = re.search(rf'^VERSION:[^=]*=\s*"{SEMVER}"', text, re.MULTILINE)
    if not match:
        raise SystemExit("check_version_source: VERSION not found in src/prama/version.py")
    return match.group(1)


def problems(root: Path) -> list[str]:
    version = authority(root)
    found: list[str] = []
    literal = re.compile(rf"""["']{re.escape(version)}["']""")
    for path in sorted((root / "src").rglob("*.py")):
        if path.name == "version.py" and path.parent.name == "prama":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if literal.search(line):
                found.append(f"{path.relative_to(root)}:{number}: restates {version}")
    for name, patterns in COPIES.items():
        path = root / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern in patterns:
                for match in re.finditer(pattern, line):
                    stated = match.group(1)
                    if stated != version:
                        found.append(f"{name}:{number}: says {stated}, VERSION is {version}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    found = problems(Path(parser.parse_args().root))
    for line in found:
        print(line, file=sys.stderr)
    if found:
        print("\nversion.py is the one authority; make every copy agree with it.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
