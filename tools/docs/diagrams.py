"""
The diagrams of the architecture guide and the developer guides, drawn from code.

    python tools/docs/diagrams.py            # SVG into docs/assets/diagrams/
    python tools/docs/diagrams.py --check    # audit, and refuse a diagram not rebuilt

Each guide's diagrams live in their own module (``architecture.py`` for
docs/architecture, ``developer.py`` for docs/developer), each exporting
``DIAGRAMS``: functions returning a ``Canvas`` from tools/diagrams/canvas.py.
Documents embed them as ``../assets/diagrams/<name>.svg``, which renders on a
Git host, in an editor, and in the console's help centre alike.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "diagrams")]

import developer  # noqa: E402
from canvas import build  # noqa: E402

import architecture  # noqa: E402

OUT = HERE.parents[1] / "docs" / "assets" / "diagrams"
DIAGRAMS = [*architecture.DIAGRAMS, *developer.DIAGRAMS]

if __name__ == "__main__":
    names = [make().name for make in DIAGRAMS]
    clashes = {n for n in names if names.count(n) > 1}
    if clashes:
        sys.exit(f"two diagrams share a name: {sorted(clashes)}")
    sys.exit(build(DIAGRAMS, OUT, sys.argv))
