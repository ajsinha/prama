"""CLI entry point: ``prama``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sys

from prama.cli.base import Application
from prama.cli.commands import all_commands
from prama.packs import install_shipped


def main(argv: list[str] | None = None) -> int:
    # Before any command runs, so `prama control check` resolves the same
    # functions `prama pack list` advertises. See prama.packs.install_shipped.
    #
    # `plugins.disabled` is not honoured here and is honoured by `create_app`.
    # The asymmetry is real and is stated rather than hidden: this runs before
    # argparse, so `--config` is not yet known, and reading a configuration
    # file the caller may be about to override would be worse than not reading
    # one. Disabling a plugin is a deployment decision and the server is where
    # it takes effect. Recorded as Q-63.
    install_shipped()
    return Application(all_commands()).run(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
