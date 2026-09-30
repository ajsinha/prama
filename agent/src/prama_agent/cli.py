"""``prama-agent``: enrol this machine, run the daemon, say how it is doing.

    prama-agent enrol  --server https://prama.example.com --token … --name eu-01 --state DIR
    prama-agent run    --config /etc/prama-agent/agent.yaml [--once]
    prama-agent status --config /etc/prama-agent/agent.yaml [--json]

Exit status: 0 success; 1 a failure the message explains; 2 a usage error;
3 the server refused this agent for good (a service manager should not restart
it — ``RestartPreventExitStatus=3``).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prama_kernel.agent.capability import AgentCapabilities
from prama_kernel.agent.spool import Spool
from prama_kernel.log import LoggingConfigurator

from prama_agent.config import AgentConfig, ServerSettings, load_config, server_settings
from prama_agent.link import FleetLink, SdkFleetLink
from prama_agent.state import (
    SPOOL,
    Identity,
    load_contact,
    load_identity,
    save_identity,
)
from prama_agent.version import VERSION

#: Builds the link to a server. Replaced in tests; the SDK in production.
LinkFactory = Callable[[ServerSettings], FleetLink]


def sdk_link(server: ServerSettings) -> FleetLink:
    return SdkFleetLink(server.url, verify=server.ca_bundle or True, timeout=server.timeout_seconds)


def main(argv: Sequence[str] | None = None, *, link_factory: LinkFactory | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    factory = link_factory or sdk_link
    try:
        if args.command == "enrol":
            return _enrol(args, factory)
        if args.command == "run":
            return _run(args, factory)
        return _status(args)
    except Exception as exc:
        message = getattr(exc, "message", None)
        remedy = getattr(exc, "remedy", None)
        if message is None:  # not one of ours: a bug, shown as one
            raise
        print(f"prama-agent: {message}", file=sys.stderr)
        if remedy:
            print(f"  next: {remedy}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prama-agent",
        description="The Prama agent: runs controls beside the data, reports findings.",
    )
    parser.add_argument("--version", action="version", version=f"prama-agent {VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)

    enrol = commands.add_parser("enrol", help="redeem a one-time token for an identity")
    enrol.add_argument("--server", required=True, help="the Prama server's URL")
    enrol.add_argument(
        "--token",
        default=os.environ.get("PRAMA_AGENT_TOKEN", ""),
        help="the enrolment token (or PRAMA_AGENT_TOKEN, which keeps it out of shell history)",
    )
    enrol.add_argument("--name", required=True, help="a name a person recognises, e.g. eu-01")
    enrol.add_argument("--state", required=True, type=Path, help="the state directory")
    enrol.add_argument("--config", type=Path, help="agent.yaml, to advertise its capabilities")
    enrol.add_argument("--ca-bundle", default="", help="a CA bundle to verify the server with")
    enrol.add_argument("--insecure", action="store_true", help="permit plain HTTP to a remote host")
    enrol.add_argument("--force", action="store_true", help="replace an existing identity")

    run = commands.add_parser("run", help="run the daemon")
    run.add_argument("--config", required=True, type=Path, help="agent.yaml")
    run.add_argument("--once", action="store_true", help="one cycle, then exit")

    status = commands.add_parser("status", help="identity, spool, gaps and last contact")
    status.add_argument("--config", required=True, type=Path, help="agent.yaml")
    status.add_argument("--json", action="store_true", help="as JSON")
    return parser


def _enrol(args: argparse.Namespace, factory: LinkFactory) -> int:
    if not args.token:
        print("prama-agent: --token (or PRAMA_AGENT_TOKEN) is required", file=sys.stderr)
        return 2
    server = server_settings(args.server, insecure=args.insecure, ca_bundle=args.ca_bundle)
    capabilities = AgentCapabilities()
    if args.config:
        from prama_agent.daemon import capabilities_for

        capabilities = capabilities_for(load_config(args.config))
    link = factory(server)
    try:
        answer = link.enrol(
            args.token, name=args.name, version=VERSION, capabilities=capabilities.to_dict()
        )
    finally:
        link.close()
    identity = Identity(
        agent_id=str(answer["agent_id"]),
        key_hex=str(answer["key"]),
        zone=str(answer.get("zone", "")),
        server=server.url,
        name=args.name,
        enrolled_at=datetime.now(UTC).isoformat(timespec="seconds"),
        poll_after_seconds=int(answer.get("poll_after_seconds", 30)),
    )
    path = save_identity(args.state, identity, replace=args.force)
    print(f"enrolled {identity.agent_id} in zone {identity.zone}; identity kept at {path} (0600)")
    return 0


def _run(args: argparse.Namespace, factory: LinkFactory) -> int:
    from prama_agent.daemon import Daemon

    config = load_config(args.config)
    LoggingConfigurator(level=config.log_level, fmt=config.log_format).apply()
    identity = load_identity(config.state_dir)
    _check_server(config, identity)
    link = factory(config.server)
    try:
        return Daemon(config, identity, link).run(once=args.once)
    finally:
        link.close()


def _check_server(config: AgentConfig, identity: Identity) -> None:
    if identity.server and identity.server.rstrip("/") != config.server.url:
        print(
            f"prama-agent: warning: enrolled with {identity.server} and configured for "
            f"{config.server.url}; the key is only valid on the server that issued it",
            file=sys.stderr,
        )


def status_of(config: AgentConfig) -> dict[str, Any]:
    """What ``status`` shows: nothing secret, all of it from the state directory."""
    identity = load_identity(config.state_dir)
    spool = Spool(capacity=config.spool_capacity, path=config.state_dir / SPOOL)
    contact = load_contact(config.state_dir)
    return {
        "version": VERSION,
        "identity": identity.public(),
        "zone": identity.zone,
        "server": config.server.url,
        "sources": [s.describe() for s in config.sources],
        "residency": config.residency.describe(),
        "spool": {
            "pending": len(spool),
            "oldest_sequence": next(iter(spool)).sequence if len(spool) else None,
            "capacity": config.spool_capacity,
        },
        "gaps": [g.render() for g in spool.gaps],
        "contact": contact.to_dict(),
    }


def _status(args: argparse.Namespace) -> int:
    report = status_of(load_config(args.config))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    identity = report["identity"]
    contact = report["contact"]
    lines = [
        f"agent       {identity['agent_id']} ({identity.get('name') or 'unnamed'})",
        f"zone        {report['zone']}",
        f"server      {report['server']}",
        f"sources     {'; '.join(report['sources'])}",
        f"residency   {report['residency']}",
        f"spool       {report['spool']['pending']} finding(s) pending "
        f"of {report['spool']['capacity']:,}",
        f"gaps        {len(report['gaps'])}",
        *(f"  - {gap}" for gap in report["gaps"]),
        f"last contact {contact['last_contact_at'] or 'never'}",
        f"last attempt {contact['last_attempt_at'] or 'never'}"
        + (
            f" ({contact['consecutive_failures']} failure(s): {contact['last_error']})"
            if contact["consecutive_failures"]
            else ""
        ),
    ]
    if contact["refused"]:
        lines.append(f"REFUSED     {contact['refused'].get('reason', '')} — re-enrol to continue")
    print("\n".join(lines))
    return 3 if contact["refused"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
