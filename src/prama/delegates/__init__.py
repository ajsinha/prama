"""DQ delegates: Python checks a bank writes, run under Prama's rules.

See `prama.delegates.spi` for the contract, `docs/design/dq-delegates.md` for
the design and `examples/delegates/` for a worked case study.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.delegates.spi import DqDelegate, Measurement, Parameter

__all__ = ["DqDelegate", "Measurement", "Parameter"]
