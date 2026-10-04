"""``python -m prama``: the same command line as ``prama``.

For an IDE run configuration in module mode, and for any environment where
the ``prama`` script is not on PATH but the interpreter is.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
