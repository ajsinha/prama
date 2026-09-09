"""A conversational agent that reads and proposes, and cannot change anything.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.assistant.agent import MAX_STEPS, Answer, Assistant
from prama.assistant.safety import (
    FENCE_CLOSE,
    FENCE_OPEN,
    SYSTEM,
    Attempt,
    Fenced,
    Leak,
    Trust,
    Turn,
    detect,
    fence,
    redact,
    scan_output,
)
from prama.assistant.tools import (
    Argument,
    Capability,
    Estate,
    Result,
    Tool,
    ToolRegistry,
    default_registry,
    read_only_registry,
)

__all__ = [
    "FENCE_CLOSE",
    "FENCE_OPEN",
    "MAX_STEPS",
    "SYSTEM",
    "Answer",
    "Argument",
    "Assistant",
    "Attempt",
    "Capability",
    "Estate",
    "Fenced",
    "Leak",
    "Result",
    "Tool",
    "ToolRegistry",
    "Trust",
    "Turn",
    "default_registry",
    "detect",
    "fence",
    "read_only_registry",
    "redact",
    "scan_output",
]
