"""Evaluation suites: does this profile or template version behave, graded deterministically.

A suite is a YAML document: a purpose, optionally a template, and cases, each
with the values (or prompt) to send and what the answer must satisfy::

    name: explain-controls
    purpose: explain
    template: explain-control        # optional; its values go in `vars`
    cases:
      - name: a not-null control
        vars: {pql: "CHECK t.a IS NOT NULL"}
        expect:
          nonempty: true
          contains: ["null"]
          absent: ["DROP"]
          max_latency_ms: 20000

Graders are deterministic, every one: `nonempty`, `contains`, `absent`,
`matches` (a regular expression), `json_valid`, `json_keys`, `pql_parses`,
`max_latency_ms`. A model grading a model would make the gate as unreliable as
the thing it gates, so there is no such grader.

A run is recorded (`llm_eval_run`) against the exact profile version and
template version it exercised. With `llm.eval.gate_activation` on, that is
what lets a version become current. Every call the run makes goes through the
gateway, so it is budgeted and recorded like any other.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from prama.core.errors import ValidationError
from prama.llm.spi import Request, Response


def _pql_parses(text: str, want: Any) -> tuple[bool, str]:
    from prama.pql import parse

    try:
        parse(text.strip().strip("`").removeprefix("pql").strip())
        ok = True
    except Exception as exc:  # any refusal is a failed grade, with its reason
        return (not want), f"does not parse: {str(exc)[:120]}"
    return (ok == bool(want)), ""


def _json(text: str) -> Any:
    return json.loads(text.strip().strip("`").removeprefix("json").strip())


def _json_valid(text: str, want: Any) -> tuple[bool, str]:
    try:
        _json(text)
        return bool(want), ""
    except ValueError as exc:
        return (not want), f"not JSON: {exc}"


def _json_keys(text: str, keys: Any) -> tuple[bool, str]:
    try:
        value = _json(text)
    except ValueError:
        return False, "not JSON"
    missing = [k for k in keys if not isinstance(value, dict) or k not in value]
    return (not missing), f"missing keys: {', '.join(missing)}" if missing else ""


def _contains(text: str, needles: Any) -> tuple[bool, str]:
    missing = [n for n in needles if str(n).lower() not in text.lower()]
    return (not missing), f"missing: {', '.join(missing)}" if missing else ""


def _absent(text: str, needles: Any) -> tuple[bool, str]:
    present = [n for n in needles if str(n).lower() in text.lower()]
    return (not present), f"present: {', '.join(present)}" if present else ""


GRADERS: dict[str, Callable[[str, Any], tuple[bool, str]]] = {
    "nonempty": lambda text, want: ((bool(text.strip()) == bool(want)), "empty answer"),
    "contains": _contains,
    "absent": _absent,
    "matches": lambda text, pattern: (
        bool(re.search(str(pattern), text)),
        f"does not match /{pattern}/",
    ),
    "json_valid": _json_valid,
    "json_keys": _json_keys,
    "pql_parses": _pql_parses,
}


def grade(case: Mapping[str, Any], response: Response) -> tuple[bool, list[str]]:
    """Whether *response* satisfies every expectation of *case*, and what did not."""
    misses: list[str] = []
    if response.incomplete and not response.text:
        misses.append(f"no answer: {response.incomplete[:160]}")
    for name, want in (case.get("expect") or {}).items():
        if name == "max_latency_ms":
            if response.latency_ms > float(want):
                misses.append(f"took {response.latency_ms:.0f} ms, over {want}")
            continue
        grader = GRADERS.get(name)
        if grader is None:
            raise ValidationError(
                f"no grader called {name!r}",
                remedy=f"Graders: {', '.join(sorted([*GRADERS, 'max_latency_ms']))}.",
            )
        ok, why = grader(response.text, want)
        if not ok:
            misses.append(f"{name}: {why}")
    return not misses, misses


def suite_hash(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode("utf-8")).hexdigest()


async def run_suite(
    uow: Any,
    tenant_id: str,
    document: Mapping[str, Any],
    *,
    config: Any = None,
    profile_version: int | None = None,
    template_version: int | None = None,
    by: str | None = None,
    opener: Any = None,
) -> Any:
    """Run every case of the suite; record and return the `llm_eval_run`."""
    import asyncio

    from prama.llm.gateway import LlmGateway
    from prama.llm.templates import PromptTemplate, Variable
    from prama.llm.wiring import load_routes, persist

    purpose = str(document.get("purpose", "")).strip()
    cases = list(document.get("cases") or [])
    if not purpose or not cases:
        raise ValidationError(
            "a suite needs a purpose and at least one case",
            remedy="Give `purpose:` and `cases:` in the suite document.",
        )
    template = None
    template_row = None
    if document.get("template"):
        name = str(document["template"])
        versions = await uow.llm_governance.template_versions(tenant_id, name)
        chosen = (
            next((v for v in versions if v.version == template_version), None)
            if template_version is not None
            else (versions[-1] if versions else None)
        )
        template_row = await uow.llm_governance.template(tenant_id, name)
        if chosen is None or template_row is None:
            raise ValidationError(f"no template {name} to evaluate", remedy="Add it first.")
        template = PromptTemplate(
            name=name,
            system=chosen.system_text,
            body=chosen.body,
            variables=tuple(Variable(**v) for v in json.loads(chosen.variables_json)),
            version=chosen.version,
            template_id=template_row.id,
        )
    pinned = {purpose: profile_version} if profile_version is not None else None
    routes = await load_routes(
        uow,
        tenant_id,
        offline=bool(config.get_bool("llm.offline", False)) if config is not None else False,
        opener=opener,
        pinned=pinned,
    )
    route = routes.get(purpose)
    from prama.llm.gateway import MemoryLedger

    ledger = MemoryLedger()
    gateway = LlmGateway(routes, ledger, tenant_id=tenant_id, surface="eval", principal_id=by)
    report = []
    passed = 0
    for case in cases:
        if template is not None:
            request = template.render(dict(case.get("vars") or {}))
        else:
            request = Request(
                system=str(case.get("system", "")), prompt=str(case.get("prompt", ""))
            )
        response = await asyncio.to_thread(gateway.run, purpose, request)
        ok, misses = grade(case, response)
        passed += ok
        report.append({"case": case.get("name", ""), "passed": ok, "misses": misses})
    await persist(uow, tenant_id, ledger)
    return await uow.llm_governance.record_eval(
        tenant_id,
        suite=str(document.get("name", "suite"))[:128],
        suite_hash=suite_hash(document),
        purpose=purpose,
        profile_id=route.profile_id if route and route.profile_id else None,
        profile_version=route.version if route else None,
        template_id=template_row.id if template_row is not None else None,
        template_version=template.version if template is not None else None,
        cases=len(cases),
        passed=passed,
        status="passed" if passed == len(cases) else "failed",
        report_json=json.dumps(report),
        started_by=by,
        finished_at=None,
    )
