"""CLI entry point: ``prama``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sys

from prama.cli.base import Application
from prama.cli.commands import all_commands


def main(argv: list[str] | None = None) -> int:
    return Application(all_commands()).run(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
