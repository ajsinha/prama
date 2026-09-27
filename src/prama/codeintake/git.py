"""Fetching a repository without trusting it.

`git` runs as a subprocess with a hardened configuration: no hooks
(`core.hooksPath=/dev/null`), no `file://` or `ext::` transports, no
submodules, no symlinks on disk, object checking on, a shallow clone of one
ref, no terminal prompt, and a wall-clock timeout. Nothing in the tree is ever
executed; the tree is read as bytes and then deleted.

Only `https` and `ssh` are accepted, and the host is resolved first: a private,
loopback, link-local or reserved address (a cloud metadata endpoint, an
internal service) is refused, which is the server-side request forgery a "clone
this URL" feature otherwise is. The resolution is checked once, before git
resolves again; a hostile DNS server could answer differently the second time,
and an `allowed_hosts` list is the complete answer for a deployment that needs
one.

Not a registered egress point, deliberately: a fetch sends the estate's data
nowhere. What leaves is a request and, when configured, a credential, to the
host the owner named. A credential is passed through git's environment
configuration, never its command line, where every user on the host could read
it in the process table.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import urllib.parse
from collections.abc import Sequence
from pathlib import Path

from prama.codeintake.archive import IntakeRefused, Limits, Snapshot
from prama.secrets.value import SecretValue

#: An scp-style SSH location, `git@host:org/repo.git`.
_SCP = re.compile(r"^(?P<user>[\w.-]+)@(?P<host>[\w.-]+):(?P<path>[^\s]+)$")


def _refuse(reason: str, url: str = "") -> IntakeRefused:
    return IntakeRefused(
        f"repository refused: {reason}",
        remedy="Use an https:// or ssh:// location on a public or allowed host.",
        context={"url": url[:200]},
    )


def host_of(url: str) -> str:
    """The host a git location names, or a refusal for a scheme Prama will not use."""
    scp = _SCP.match(url)
    if scp:
        return scp.group("host").lower()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "ssh"):
        raise _refuse(f"the scheme {parts.scheme or '(none)'!r} is not https or ssh", url)
    if not parts.hostname:
        raise _refuse("the location names no host", url)
    return parts.hostname.lower()


def check_location(
    url: str,
    *,
    allowed_hosts: Sequence[str] = (),
    resolve: bool = True,
) -> str:
    """The host, if *url* may be fetched from; otherwise a refusal naming why."""
    if url.startswith("-"):
        raise _refuse("a location may not begin with '-'", url)  # git option injection
    host = host_of(url)
    if allowed_hosts and host not in {h.lower() for h in allowed_hosts}:
        raise _refuse(f"{host} is not in codeintake.git.allowed_hosts", url)
    if resolve:
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:
            raise _refuse(f"{host} does not resolve", url) from exc
        for info in infos:
            address = ipaddress.ip_address(info[4][0])
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_reserved
                or address.is_multicast
                or address.is_unspecified
            ):
                raise _refuse(f"{host} resolves to a non-public address ({address})", url)
    return host


def fetch(
    url: str,
    ref: str,
    destination: Path,
    *,
    token: SecretValue | None = None,
    allowed_hosts: Sequence[str] = (),
    limits: Limits | None = None,
    timeout: float = 300.0,
    resolve: bool = True,
) -> Snapshot:
    """Clone one ref of *url* into *destination* and describe what arrived."""
    limits = limits or Limits()
    check_location(url, allowed_hosts=allowed_hosts, resolve=resolve)
    if not re.fullmatch(r"[\w./-]{1,255}", ref) or ref.startswith("-"):
        raise _refuse(f"{ref!r} is not a branch, tag or commit name", url)
    if shutil.which("git") is None:
        raise IntakeRefused(
            "git is not installed on this server",
            remedy="Install git, or upload the code as a ZIP instead.",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(destination.parent),  # no user or system configuration
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    if token is not None:
        # git reads extra configuration from these variables (git 2.31+).
        environment |= {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {token.reveal()}",
        }
    command = [
        "git",
        "-c", "core.hooksPath=/dev/null",
        "-c", "protocol.file.allow=never",
        "-c", "protocol.ext.allow=never",
        "-c", "transfer.fsckObjects=true",
        "-c", "core.symlinks=false",
        "clone", "--quiet", "--depth", "1", "--single-branch", "--no-recurse-submodules",
        "--branch", ref, "--", url, str(destination),
    ]  # fmt: skip
    try:
        # A fixed argv: the url and ref were validated above, and "--" ends options.
        completed = subprocess.run(
            command, env=environment, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise _refuse(f"the clone took longer than {timeout:.0f} s", url) from exc
    if completed.returncode != 0:
        shutil.rmtree(destination, ignore_errors=True)
        message = completed.stderr.decode("utf-8", errors="replace").strip()[-300:]
        raise _refuse(f"git could not fetch it: {message}", url)
    shutil.rmtree(destination / ".git", ignore_errors=True)
    return snapshot_of(destination, limits)


def snapshot_of(root: Path, limits: Limits) -> Snapshot:
    """Hash a received tree, applying the same limits as an archive."""
    files: dict[str, tuple[str, int]] = {}
    links: list[str] = []
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            links.append(relative)
            path.unlink()
            continue
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        if (
            size > limits.max_file
            or total > limits.max_uncompressed
            or len(files) >= limits.max_entries
        ):
            shutil.rmtree(root, ignore_errors=True)
            raise _refuse("the repository is larger than the intake limits")
        files[relative] = (hashlib.sha256(path.read_bytes()).hexdigest(), size)
        path.chmod(0o640)
    return Snapshot(root=root, files=files, symlinks=tuple(links))
