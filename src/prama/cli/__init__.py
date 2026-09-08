"""The Prama command line.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.cli.base import Application, Command, CommandContext, CommandGroup
from prama.cli.main import main

__all__ = ["Application", "Command", "CommandContext", "CommandGroup", "main"]
