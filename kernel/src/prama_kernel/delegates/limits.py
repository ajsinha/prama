"""Resource limits for a sandboxed child process (POSIX).

Shared by the delegate sandbox and the server's code-intake worker, so both
children run under the same ceiling.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations


def limit_resources(cpu_seconds: int = 120, memory_bytes: int = 2 << 30) -> None:
    """Set in the child before it runs (POSIX only)."""
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
