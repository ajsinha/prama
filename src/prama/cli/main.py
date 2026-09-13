"""CLI entry point: ``prama``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sys

from prama.cli.base import Application
from prama.cli.commands import all_commands


def main(argv: list[str] | None = None) -> int:
    # Packs are installed inside `Application.run`, once `--config` has been
    # parsed and the effective configuration is known. They used to be
    # installed here, which was before argparse, so `plugins.disabled` could
    # not be read and a validator switched off in configuration stayed on in
    # the CLI while being off in the server. Recorded as Q-63; the asymmetry is
    # now gone rather than documented.
    return Application(all_commands()).run(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
