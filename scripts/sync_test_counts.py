#!/usr/bin/env python3
"""Keep advertised test counts honest, or refuse.

A number in a document is a claim, and a claim about a test suite is the easiest
kind to be wrong about — it rots every time somebody adds a test and nobody
rereads the prose. `docs/18` calls this out as DishtaYantra's discipline worth
porting, and until now the script it named did not exist.

So: numbers in documentation are **derived from a green run**, never typed.

    python3 scripts/sync_test_counts.py --check    # refuse if any claim is stale
    python3 scripts/sync_test_counts.py --write    # update them from a real run

A claim is marked in the prose like this:

    The suite is at <!--tests-->4,182 passing<!--/tests--> today.

`--write` replaces what is between the markers with what pytest actually
reports. `--check` compares and exits non-zero on a disagreement, which is what
CI and the pre-commit hook run.

**It runs the suite rather than trusting a cached number.** A script that read
the last recorded figure and compared it with the documents would keep two
copies of the same claim in step with each other and out of step with the code.

**A skipped test is not a passing one, and both are reported.** A suite whose
count is stable because forty tests quietly started skipping is the failure this
exists to catch, so the marker carries both figures.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Documents that may carry a derived count. Listed rather than globbed: a file
#: appearing here is a deliberate decision to let it make a numeric claim.
DOCUMENTS = (
    "README.md",
    "QUICKSTART.md",
    "CLAUDE.md",
    "docs/19-implementation-roadmap.md",
    "docs/15-evaluation-benchmark-methodology.md",
    "docs/18-technology-stack.md",
)

MARKER = re.compile(r"(<!--tests-->)(.*?)(<!--/tests-->)", re.DOTALL)

#: pytest's own summary line, which is the only place the real number lives.
SUMMARY = re.compile(r"(\d+) passed(?:, (\d+) skipped)?")


def measure() -> tuple[int, int]:
    """Run the base suite and read its summary. Raises if it is not green.

    Deliberately not `--collect-only`: collecting counts tests that exist, and
    the claim is about tests that *pass*. A suite with nine failures collects
    exactly as many as a green one.
    """
    # A fixed environment, so the number does not depend on which containers
    # happen to be running. With PostgreSQL up the suite reports seventeen more
    # passes and seventeen fewer skips than without — a figure that moves with
    # ambient state is sampled rather than derived, and two people would
    # advertise different numbers for the same commit.
    #
    # The base suite is the honest one to publish: it is what a fresh clone
    # gets. The skip count is published alongside precisely so the difference is
    # visible rather than hidden.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("PRAMA_TEST_")}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    match = None
    for line in reversed(result.stdout.splitlines()):
        match = SUMMARY.search(line)
        if match:
            break
    if match is None or result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-15:])
        raise SystemExit(
            "the suite is not green, so there is no number to advertise.\n"
            "A count taken from a red run is a claim about a product that does "
            f"not work.\n\n{tail}"
        )
    return int(match.group(1)), int(match.group(2) or 0)


def rendered(passed: int, skipped: int) -> str:
    if skipped:
        return f"{passed:,} passing, {skipped:,} skipped"
    return f"{passed:,} passing"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="refuse if a claim is stale")
    group.add_argument("--write", action="store_true", help="update claims from a real run")
    args = parser.parse_args(argv)

    marked = [
        (path, text)
        for path in DOCUMENTS
        if (text := (ROOT / path).read_text(encoding="utf-8")) and MARKER.search(text)
    ]
    if not marked:
        # Not an error, and worth saying: a repository with no marked claims is
        # one where this script has nothing to keep honest, not one that passed.
        print("no document carries a <!--tests--> marker; nothing to keep in step")
        return 0

    passed, skipped = measure()
    current = rendered(passed, skipped)
    stale: list[str] = []

    for path, text in marked:
        updated = MARKER.sub(lambda m: f"{m.group(1)}{current}{m.group(3)}", text)
        if updated == text:
            continue
        if args.write:
            (ROOT / path).write_text(updated, encoding="utf-8")
            print(f"updated {path}")
        else:
            for found in MARKER.finditer(text):
                if found.group(2) != current:
                    stale.append(f"{path}: says {found.group(2)!r}, the suite says {current!r}")

    if stale:
        print("\n".join(stale), file=sys.stderr)
        print(
            "\nRun: python3 scripts/sync_test_counts.py --write",
            file=sys.stderr,
        )
        return 1
    print(f"every advertised count matches the suite: {current}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
