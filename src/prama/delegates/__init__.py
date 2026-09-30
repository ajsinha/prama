"""DQ delegates: Python checks a bank writes, run under Prama's rules.

See `prama.delegates.spi` for the contract, `docs/design/dq-delegates.md` for
the design and `examples/delegates/` for a worked case study.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

import prama.telemetry.metrics  # noqa: F401  (registers the delegate outcome counter)
from prama.delegates.spi import DqDelegate, Measurement, Parameter

__all__ = ["DqDelegate", "Measurement", "Parameter"]
