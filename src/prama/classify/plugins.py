"""Moved to `prama_kernel.plugins`, the kernel shared with the standalone agent.

This path is kept as an alias of that same module, so the server's imports and
its tests are unchanged and there is one copy of the code. New code imports
`prama_kernel.plugins`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

import sys

from prama_kernel import plugins as _kernel
from prama_kernel.plugins import *  # noqa: F403  (the names, for type checkers)

sys.modules[__name__] = _kernel
