"""``agent.yaml``: what this agent may read, where it keeps its state, what may leave.

The file is read once, at start, and validated whole: every problem is reported
together, because an operator fixing a daemon's configuration over SSH should
not discover the second mistake only after restarting for the first.

**No credential is ever written in it.** A source's password or DSN is named by
the environment variable that holds it (``dsn_env``, ``password_env``), and the
loader refuses a file that carries one inline — a ``password:`` key, a DSN with
a password in it — rather than accepting it with a warning. A configuration file
is copied, backed up, pasted into tickets and committed by accident; the
environment of a service is not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from prama_kernel.agent.residency import ResidencyPolicy, SampleDisposition
from prama_kernel.agent.spool import DEFAULT_CAPACITY
from prama_kernel.errors import ConfigError, ValidationError

#: The engines an agent can execute on. What a source may name, and nothing else.
ENGINES = ("sqlite", "duckdb", "postgres")
#: Other names the server's compilers use for the same engine.
ENGINE_ALIASES = {"postgresql": "postgres", "pg": "postgres"}


def canonical_engine(name: str) -> str:
    """The engine a name means: ``postgresql`` and ``pg`` are ``postgres``."""
    lowered = name.lower()
    return ENGINE_ALIASES.get(lowered, lowered)


#: Keys that only ever hold a secret. Present under a source, they are refused.
_SECRET_KEYS = frozenset({"password", "passwd", "secret", "token", "api_key", "key"})
#: ``scheme://user:password@host`` — a password in a URL-style DSN.
_URL_PASSWORD = re.compile(r"^[a-z][a-z0-9+.-]*://[^/@:]+:[^/@]+@", re.IGNORECASE)
#: ``password=…`` in a libpq keyword DSN.
_KEYWORD_PASSWORD = re.compile(r"(^|\s)password\s*=", re.IGNORECASE)
_BINDING = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


@dataclasses.dataclass(frozen=True, slots=True)
class Source:
    """One source the agent may read, under the binding name assignments use."""

    binding: str
    engine: str
    #: A file, for sqlite and duckdb.
    path: str = ""
    #: A DSN with no password in it, for postgres.
    dsn: str = ""
    #: The environment variable holding the whole DSN, for postgres.
    dsn_env: str = ""
    #: The environment variable holding the password, added to ``dsn``.
    password_env: str = ""
    #: Datasets reachable through this source. Empty: whatever the binding holds.
    datasets: tuple[str, ...] = ()

    def describe(self) -> str:
        """Where it is, without anything secret: safe for logs and ``status``."""
        if self.engine == "postgres":
            where = f"$({self.dsn_env})" if self.dsn_env else self.dsn
            return f"{self.binding}: postgres {where}"
        return f"{self.binding}: {self.engine} {self.path}"


@dataclasses.dataclass(frozen=True, slots=True)
class ServerSettings:
    url: str
    #: A CA bundle to verify the server with, or empty for the system store.
    ca_bundle: str = ""
    #: Permit plain HTTP to a host that is not this machine.
    insecure: bool = False
    timeout_seconds: float = 30.0


@dataclasses.dataclass(frozen=True, slots=True)
class PollSettings:
    """How often to call, and how to back off when nobody answers."""

    #: The server's ``poll_after_seconds`` is honoured within these bounds.
    min_seconds: float = 5.0
    max_seconds: float = 300.0
    backoff_initial_seconds: float = 5.0
    backoff_max_seconds: float = 600.0


@dataclasses.dataclass(frozen=True, slots=True)
class AgentConfig:
    """A validated ``agent.yaml``."""

    server: ServerSettings
    state_dir: Path
    sources: tuple[Source, ...]
    residency: ResidencyPolicy
    poll: PollSettings = dataclasses.field(default_factory=PollSettings)
    spool_capacity: int = DEFAULT_CAPACITY
    report_batch: int = 500
    log_level: str = "INFO"
    log_format: str = "json"
    #: The ``delegates:`` section, passed through to the kernel's delegate host.
    delegates: dict[str, Any] = dataclasses.field(default_factory=dict)
    #: Whether ``residency.zone`` was written, or defaulted to the enrolled zone.
    zone_declared: bool = False

    def source(self, binding: str) -> Source | None:
        return next((s for s in self.sources if s.binding == binding), None)

    @property
    def engines(self) -> tuple[str, ...]:
        """Every name an assignment may give an engine this agent has."""
        names = {s.engine for s in self.sources}
        names |= {alias for alias, engine in ENGINE_ALIASES.items() if engine in names}
        return tuple(sorted(names))

    @property
    def datasets(self) -> tuple[str, ...]:
        """What the agent is confined to, or ``()`` when any source is unconfined."""
        if any(not s.datasets for s in self.sources):
            return ()
        return tuple(sorted({d for s in self.sources for d in s.datasets}))


def load_config(path: str | Path) -> AgentConfig:
    """Read and validate ``agent.yaml``. Raises `ConfigError` naming every problem."""
    import yaml

    location = Path(path)
    try:
        raw = yaml.safe_load(location.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ConfigError(
            f"the agent configuration {location} could not be read: {exc.strerror or exc}",
            remedy="Pass --config with the path of agent.yaml (see docs/agent/README.md).",
            context={"path": str(location)},
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"the agent configuration {location} is not valid YAML",
            remedy=f"Fix the syntax: {exc}",
            context={"path": str(location)},
        ) from exc
    return parse_config(raw, origin=str(location), base=location.parent)


def parse_config(raw: Any, *, origin: str = "agent.yaml", base: Path | None = None) -> AgentConfig:
    """Validate a parsed ``agent.yaml``. Relative paths resolve against *base*."""
    problems: list[str] = []
    if not isinstance(raw, Mapping):
        raise ConfigError(
            f"{origin} must be a mapping at the top level",
            remedy="Start from the example in docs/agent/README.md.",
            context={"origin": origin},
        )
    root = base or Path.cwd()

    server = _server(raw.get("server"), problems)
    state_text = str(raw.get("state_dir") or "").strip()
    if not state_text:
        problems.append("state_dir is required: where the identity and the spool are kept")
    state_dir = _resolve(state_text or ".", root)
    sources = _sources(raw.get("sources"), root, problems)
    residency, declared = _residency(raw.get("residency"), problems)
    poll = _poll(raw.get("poll"), problems)
    spool = _mapping(raw.get("spool"), "spool", problems)
    capacity = _int(spool.get("capacity", DEFAULT_CAPACITY), "spool.capacity", problems, low=1)
    batch = _int(spool.get("batch_size", 500), "spool.batch_size", problems, low=1)
    logging_section = _mapping(raw.get("logging"), "logging", problems)
    fmt = str(logging_section.get("format", "json")).lower()
    if fmt not in ("json", "text"):
        problems.append(f"logging.format is {fmt!r}; use json or text")
    delegates = _mapping(raw.get("delegates"), "delegates", problems)

    unknown = sorted(set(raw) - _TOP_LEVEL)
    if unknown:
        problems.append(f"unknown top-level key(s): {', '.join(unknown)}")
    if problems:
        raise ConfigError(
            f"{origin} has {len(problems)} problem(s): " + "; ".join(problems),
            remedy="Correct each one; docs/agent/README.md has the reference for every key.",
            context={"origin": origin},
        )
    assert residency is not None
    return AgentConfig(
        server=server,
        state_dir=state_dir,
        sources=sources,
        residency=residency,
        poll=poll,
        spool_capacity=capacity,
        report_batch=batch,
        log_level=str(logging_section.get("level", "INFO")).upper(),
        log_format=fmt,
        delegates=dict(delegates),
        zone_declared=declared,
    )


_TOP_LEVEL = frozenset(
    {"server", "state_dir", "sources", "residency", "poll", "spool", "logging", "delegates"}
)


def server_settings(url: str, *, insecure: bool = False, ca_bundle: str = "") -> ServerSettings:
    """The server section on its own, as ``enrol`` needs it, validated the same way."""
    problems: list[str] = []
    settings = _server({"url": url, "insecure": insecure, "ca_bundle": ca_bundle}, problems)
    if problems:
        raise ConfigError(
            "; ".join(problems),
            remedy="Pass --server with the https:// URL of the Prama server.",
            context={"url": url},
        )
    return settings


def _server(raw: Any, problems: list[str]) -> ServerSettings:
    if isinstance(raw, str):
        raw = {"url": raw}
    section = _mapping(raw, "server", problems)
    url = str(section.get("url") or "").strip().rstrip("/")
    if not url:
        problems.append("server.url is required: the Prama server this agent reports to")
        return ServerSettings(url="")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        problems.append(f"server.url {url!r} is not an http(s) URL")
    insecure = bool(section.get("insecure", False))
    if parts.scheme == "http" and not insecure and not _loopback(parts.hostname or ""):
        problems.append(
            f"server.url {url!r} is plain HTTP to another machine; findings and signatures "
            f"would cross the network readable. Use https://, or set server.insecure: true "
            f"on a network you trust"
        )
    timeout = _float(section.get("timeout_seconds", 30.0), "server.timeout_seconds", problems)
    return ServerSettings(
        url=url,
        ca_bundle=str(section.get("ca_bundle") or ""),
        insecure=insecure,
        timeout_seconds=timeout,
    )


def _sources(raw: Any, root: Path, problems: list[str]) -> tuple[Source, ...]:
    section = _mapping(raw, "sources", problems)
    if not section:
        problems.append("sources is required: at least one source this agent may read")
    found: list[Source] = []
    for binding, spec in section.items():
        name = str(binding)
        where = f"sources.{name}"
        if not _BINDING.match(name):
            problems.append(f"{where}: a binding name is letters, digits, '_', '.' or '-'")
        if not isinstance(spec, Mapping):
            problems.append(f"{where} must be a mapping with at least an engine")
            continue
        _refuse_inline_secrets(where, spec, problems)
        engine = canonical_engine(str(spec.get("engine") or ""))
        if engine not in ENGINES:
            problems.append(f"{where}.engine is {engine or 'missing'}; use {', '.join(ENGINES)}")
            continue
        datasets = spec.get("datasets") or ()
        if isinstance(datasets, str) or not all(isinstance(d, str) for d in datasets):
            problems.append(f"{where}.datasets must be a list of dataset names")
            datasets = ()
        path = str(spec.get("path") or "")
        dsn = str(spec.get("dsn") or "")
        dsn_env = str(spec.get("dsn_env") or "")
        password_env = str(spec.get("password_env") or "")
        if engine in ("sqlite", "duckdb"):
            if not path:
                problems.append(f"{where}.path is required for {engine}")
            if dsn or dsn_env or password_env:
                problems.append(f"{where}: {engine} reads a file; dsn/dsn_env do not apply")
            path = str(_resolve(path, root)) if path else ""
        else:
            if bool(dsn) == bool(dsn_env):
                problems.append(f"{where}: postgres needs exactly one of dsn or dsn_env")
            if path:
                problems.append(f"{where}: postgres is reached by DSN; path does not apply")
            if dsn_env and password_env:
                problems.append(f"{where}: password_env adds to dsn, not to dsn_env")
        found.append(
            Source(
                binding=name,
                engine=engine,
                path=path,
                dsn=dsn,
                dsn_env=dsn_env,
                password_env=password_env,
                datasets=tuple(datasets),
            )
        )
    return tuple(found)


def _refuse_inline_secrets(where: str, spec: Mapping[str, Any], problems: list[str]) -> None:
    for key in spec:
        if str(key).lower() in _SECRET_KEYS:
            problems.append(
                f"{where}.{key} is a credential written inline; name the environment "
                f"variable that holds it instead (password_env, dsn_env)"
            )
    dsn = str(spec.get("dsn") or "")
    if dsn and (_URL_PASSWORD.search(dsn) or _KEYWORD_PASSWORD.search(dsn)):
        problems.append(
            f"{where}.dsn carries a password inline; remove it and name the variable "
            f"that holds it with password_env, or put the whole DSN in dsn_env"
        )


def _residency(raw: Any, problems: list[str]) -> tuple[ResidencyPolicy | None, bool]:
    section = _mapping(raw, "residency", problems)
    if not section:
        problems.append(
            "residency is required: what may leave this machine (samples: withhold is the "
            "strictest, and a reasonable start)"
        )
        return None, False
    disposition = str(section.get("samples") or "").lower()
    valid = [d.value for d in SampleDisposition]
    if disposition not in valid:
        problems.append(f"residency.samples is {disposition or 'missing'}; use {', '.join(valid)}")
        return None, False
    zone = str(section.get("zone") or "")
    try:
        policy = ResidencyPolicy(
            zone=zone or "default",
            samples=SampleDisposition(disposition),
            never_send=_names(section.get("never_send"), "residency.never_send", problems),
            may_send=_names(section.get("may_send"), "residency.may_send", problems),
            max_sample_rows=_int(
                section.get("max_sample_rows", 50), "residency.max_sample_rows", problems, low=0
            ),
            investigate_at=str(section.get("investigate_at") or ""),
        )
    except ValidationError as exc:
        problems.append(f"residency: {exc.message} ({exc.remedy})")
        return None, False
    return policy, bool(zone)


def _poll(raw: Any, problems: list[str]) -> PollSettings:
    section = _mapping(raw, "poll", problems)
    default = PollSettings()
    settings = PollSettings(
        min_seconds=_float(section.get("min_seconds", default.min_seconds), "poll.min", problems),
        max_seconds=_float(section.get("max_seconds", default.max_seconds), "poll.max", problems),
        backoff_initial_seconds=_float(
            section.get("backoff_initial_seconds", default.backoff_initial_seconds),
            "poll.backoff_initial_seconds",
            problems,
        ),
        backoff_max_seconds=_float(
            section.get("backoff_max_seconds", default.backoff_max_seconds),
            "poll.backoff_max_seconds",
            problems,
        ),
    )
    if settings.min_seconds > settings.max_seconds:
        problems.append("poll.min_seconds is greater than poll.max_seconds")
    if settings.backoff_initial_seconds > settings.backoff_max_seconds:
        problems.append("poll.backoff_initial_seconds is greater than poll.backoff_max_seconds")
    return settings


def _mapping(raw: Any, where: str, problems: list[str]) -> Mapping[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        problems.append(f"{where} must be a mapping")
        return {}
    return raw


def _names(raw: Any, where: str, problems: list[str]) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str) or not all(isinstance(n, str) for n in raw):
        problems.append(f"{where} must be a list of column names")
        return ()
    return tuple(raw)


def _int(raw: Any, where: str, problems: list[str], *, low: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        problems.append(f"{where} must be a whole number")
        return low
    if value < low:
        problems.append(f"{where} must be at least {low}")
    return value


def _float(raw: Any, where: str, problems: list[str]) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        problems.append(f"{where} must be a number of seconds")
        return 1.0
    if value <= 0:
        problems.append(f"{where} must be greater than zero")
    return value


def _resolve(text: str, root: Path) -> Path:
    path = Path(os.path.expandvars(text)).expanduser()
    return path if path.is_absolute() else (root / path)


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
