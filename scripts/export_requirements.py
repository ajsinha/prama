#!/usr/bin/env python3
"""Write requirements.txt and requirements-dev.txt from uv.lock, or check they match.

    python scripts/export_requirements.py --write    # after changing dependencies
    python scripts/export_requirements.py --check    # in the gate; exit 1 if stale

``uv.lock`` is the authority for what is installed: ``uv sync`` reproduces it
exactly. The requirements files exist for everyone who uses plain ``pip``, and
they are *derived* from the lock rather than written beside it, because a second
hand-kept list of versions drifts from the first in the flattering direction.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: file -> (the extras it carries, what it is for)
FILES: dict[str, tuple[tuple[str, ...], str]] = {
    "requirements.txt": (("serve",), "the server, the console and the API"),
    "requirements-dev.txt": (
        ("dev", "serve"),
        "the above, plus the tests, linters and type checker",
    ),
}

HEADER = """\
# {name}: {purpose}, pinned to exactly what uv.lock resolves.
#
#     python -m venv .venv && source .venv/bin/activate     # Python 3.12 or newer
#     pip install -r {name}
#
# GENERATED from uv.lock by scripts/export_requirements.py; do not edit by hand.
# Change a dependency in pyproject.toml, run `uv lock`, then
# `python scripts/export_requirements.py --write`. The gate refuses a stale copy.
# Optional extras (postgres, snowflake, kafka, ...) are added on top:
#     pip install -e ".[postgres]"
#
# Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""


def render(name: str) -> str:
    extras, purpose = FILES[name]
    command = ["uv", "export", "--frozen", "--no-hashes", "--format", "requirements-txt"]
    for extra in extras:
        command += ["--extra", extra]
    exported = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    # uv's own two-line banner names the command it ran; ours says why the file exists.
    body = "\n".join(
        line for line in exported.splitlines() if not line.startswith(("# This file", "#    uv"))
    )
    return HEADER.format(name=name, purpose=purpose) + body.lstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("--write", "--check"):
        print("usage: export_requirements.py --write | --check", file=sys.stderr)
        return 2
    if shutil.which("uv") is None:
        print("uv is not installed; the requirements files cannot be derived or checked")
        return 0 if argv[0] == "--check" else 1
    stale = []
    for name in FILES:
        wanted, path = render(name), ROOT / name
        if argv[0] == "--write":
            path.write_text(wanted, encoding="utf-8")
            print(f"wrote {name}")
        elif not path.is_file() or path.read_text(encoding="utf-8") != wanted:
            stale.append(name)
    if stale:
        print(
            f"stale against uv.lock: {', '.join(stale)}. "
            "Run: python scripts/export_requirements.py --write"
        )
        return 1
    if argv[0] == "--check":
        print(f"requirements files match uv.lock ({len(FILES)} checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
