"""Moved to `prama_kernel.delegates.registry`, the kernel shared with the standalone agent.

This path is kept as an alias of that same module, so the server's imports and
its tests are unchanged and there is one copy of the code. New code imports
`prama_kernel.delegates.registry`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

import sys

from prama_kernel.delegates import registry as _kernel
from prama_kernel.delegates.registry import *  # noqa: F403  (the names, for type checkers)

sys.modules[__name__] = _kernel
