"""The sandbox every piece of delegate code runs in: runs, vetting and admission.

One launcher, so the three cannot drift apart. A worker process gets:

* **resource limits** on CPU seconds, address space, open files and core dumps;
* **a clean environment**, an allowlist, so the server's DSNs and keys are not in it;
* **a network namespace** of its own where the host allows unprivileged ones;
* **one deadline** over both of its pipes, however it misbehaves.

The worker seals itself with an audit hook before it imports any delegate
(`prama_kernel.delegates.worker.seal`). What applied is named by `isolation_in_force`
and recorded with the evidence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import functools
import os
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from typing import Any

from prama_kernel.errors import ValidationError

#: The environment a sandboxed worker gets: nothing it could use to reach a
#: database or a provider. The parent's environment carries DSNs, API keys and
#: cloud credentials, and a delegate that could read it could send them anywhere.
_ENVIRONMENT = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"}
#: Passed through when set: how Python finds Prama, not a secret.
_PASSED_THROUGH = ("PYTHONPATH",)
#: The answer is one JSON document. Anything larger is not an answer.
_MAX_ANSWER = 64 << 20


@functools.lru_cache(maxsize=1)
def network_isolation() -> tuple[str, ...]:
    """The command prefix that puts the worker in a network namespace, if this host allows it.

    ``unshare --net --map-root-user`` gives the worker its own network stack
    with nothing in it: no interface up, no route, no DNS. It needs
    unprivileged user namespaces, which many hosts and most container runtimes
    disable, so it is probed once and used when it works. Where it does not,
    the audit hook in the worker still refuses sockets, and the evidence
    records which isolation applied.
    """
    unshare = shutil.which("unshare")
    if unshare is None or os.name != "posix":
        return ()
    prefix = (unshare, "--net", "--map-root-user")
    try:
        probe = subprocess.run([*prefix, "true"], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ()
    return prefix if probe.returncode == 0 else ()


def isolation_in_force(sandboxed: bool) -> str:
    """What stood between a delegate and the host, as the evidence records it."""
    if not sandboxed:
        return "none: in process"
    parts = ["separate process", "resource limits", "clean environment", "audit hook"]
    if network_isolation():
        parts.insert(1, "network namespace")
    return ", ".join(parts)


def exchange(process: Any, chunks: Iterable[bytes], timeout: float) -> bytes:
    """Feed *chunks* to the worker and collect its answer, all within *timeout*.

    One thread, two pipes, one deadline. Writing everything first and reading
    after would block for ever on a worker that stopped reading, and a deadline
    applied only once the answer arrived is no deadline for a worker that
    sleeps: a sleeping process uses no CPU, so the CPU limit never fires. The
    rows are still read from *chunks* only as the pipe accepts them, so the
    input is never held whole.
    """
    deadline = time.monotonic() + timeout
    source = iter(chunks)
    pending = b""
    output = bytearray()
    stdin, stdout = process.stdin, process.stdout
    in_fd, out_fd = stdin.fileno(), stdout.fileno()
    os.set_blocking(in_fd, False)
    os.set_blocking(out_fd, False)
    with selectors.DefaultSelector() as selector:
        selector.register(stdin, selectors.EVENT_WRITE)
        selector.register(stdout, selectors.EVENT_READ)
        writing = True
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise TimeoutError
            for key, _ in selector.select(timeout=remaining):
                if key.fileobj is stdout:
                    chunk = os.read(out_fd, 1 << 16)
                    if not chunk:
                        selector.unregister(stdout)
                    elif len(output) + len(chunk) > _MAX_ANSWER:
                        process.kill()
                        process.wait()
                        raise ValidationError(
                            "the delegate's answer is larger than any measurement",
                            remedy="A delegate returns counts and a few samples, not rows.",
                        )
                    else:
                        output += chunk
                elif writing:
                    if not pending:
                        pending = next(source, b"")
                        if not pending:
                            selector.unregister(stdin)
                            stdin.close()
                            writing = False
                            continue
                    try:
                        written = os.write(in_fd, pending)
                    except BrokenPipeError:
                        # The worker stopped reading: its answer says why.
                        selector.unregister(stdin)
                        stdin.close()
                        writing = False
                        continue
                    pending = pending[written:]
    try:
        process.wait(timeout=max(1.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise TimeoutError from None
    return bytes(output)


@dataclasses.dataclass(frozen=True, slots=True)
class Finished:
    """What a sandboxed worker returned."""

    returncode: int
    output: bytes
    errors: str


def run_isolated(
    arguments: list[str],
    *,
    chunks: Iterable[bytes] = (),
    timeout_s: float = 120,
    memory_mb: int = 2048,
) -> Finished:
    """Run ``python <arguments>`` in the sandbox, feeding it *chunks*.

    Raises `TimeoutError` past the deadline, with the worker already killed.
    """
    from prama_kernel.delegates.limits import limit_resources

    cpu, memory = int(timeout_s), memory_mb << 20

    def limits() -> None:
        limit_resources(cpu_seconds=cpu, memory_bytes=memory)

    home = tempfile.mkdtemp(prefix="prama-delegate-home-")
    environment = {
        **_ENVIRONMENT,
        "HOME": home,
        "TMPDIR": home,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        **{k: os.environ[k] for k in _PASSED_THROUGH if k in os.environ},
    }
    try:
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                [*network_isolation(), sys.executable, *arguments],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=errors,
                preexec_fn=limits if os.name == "posix" else None,
                env=environment,
            )
            try:
                output = exchange(process, chunks, timeout_s)
            except BaseException:
                process.kill()
                process.wait()
                raise
            errors.seek(0)
            stderr = errors.read().decode("utf-8", "replace")[-400:]
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return Finished(returncode=process.returncode, output=output, errors=stderr)
