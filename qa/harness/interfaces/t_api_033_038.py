import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api7.db"


def build_endpoint_index(app):
    from fastapi.routing import APIRoute
    from prama.api import API_PREFIX
    from prama.api.deps import get_caller

    def walk(routes, prefix=""):
        for route in routes:
            if isinstance(route, APIRoute):
                yield (prefix + route.path, frozenset(route.methods or ()), route)
                continue
            original = getattr(route, "original_router", None)
            if original is not None:
                context = getattr(route, "include_context", None)
                yield from walk(original.routes, prefix + getattr(context, "prefix", ""))
                continue
            nested = getattr(route, "routes", None)
            if nested:
                yield from walk(nested, prefix + getattr(route, "prefix", ""))

    def _reaches(route, predicate):
        pending = [route.dependant]
        while pending:
            dependant = pending.pop()
            found = predicate(dependant)
            if found is not None:
                return found
            pending.extend(dependant.dependencies)
        return None

    def scope_of(route):
        return _reaches(route, lambda d: getattr(d.call, "prama_scope", None))

    out = []
    for path, methods, route in walk(app.routes):
        if not path.startswith(API_PREFIX):
            continue
        scope = scope_of(route)
        if scope:
            out.append((path.removeprefix(API_PREFIX), sorted(methods - {"HEAD", "OPTIONS"}), scope))
    return out


PLACEHOLDER_ID = "01M2D0000000000000000000A"


def concretise(path):
    import re

    return re.sub(r"\{[^}]+\}", PLACEHOLDER_ID, path)


async def main():
    env = a.Env(str(DB))
    await env.start()
    endpoints = build_endpoint_index(env.app)
    from prama.security.scopes import SCOPES

    all_scopes = sorted(SCOPES)
    keys_by_scope = {}
    for sc in all_scopes:
        keys_by_scope[sc] = await a._issue_key(env.database, env.tenant_id, principal=f"scope-{sc.replace(':', '-')}", scopes=[sc])
    all_other_key = await a._issue_key(env.database, env.tenant_id, principal="allbutone", scopes=["*"])

    wrong_scope_failures = {}
    right_scope_failures = {}
    checked = 0
    for path, methods, scope in endpoints:
        concrete = concretise(path)
        for method in methods:
            checked += 1
            key_for_scope = "declaration:read" if scope != "declaration:read" else "evidence:read"
            wrong_key = keys_by_scope.get(key_for_scope) or all_other_key
            async with env.client(wrong_key) as http:
                body = {} if method in ("POST", "PUT", "PATCH") else None
                r = await http.request(method, concrete, json=body)
                if r.status_code != 403:
                    wrong_scope_failures[f"{method} {path} (needs {scope})"] = f"wrong-scope key got {r.status_code}, not 403: {r.text[:150]}"

            right_key = keys_by_scope.get(scope)
            if right_key:
                async with env.client(right_key) as http:
                    body = {} if method in ("POST", "PUT", "PATCH") else None
                    r = await http.request(method, concrete, json=body)
                    if r.status_code == 403:
                        right_scope_failures[f"{method} {path} (has {scope})"] = f"correct-scope key still got 403: {r.text[:200]}"

    record(
        "API-033",
        "PASS" if not wrong_scope_failures else "FAIL",
        f"n_operations_checked={checked} n_scoped_endpoints={len(endpoints)} failures={wrong_scope_failures}",
    )
    record(
        "API-034",
        "PASS" if not right_scope_failures else "FAIL",
        f"n_operations_checked={checked} failures={right_scope_failures}",
    )

    # API-035: every mutating route declares a scope (walk once more, unscoped this time)
    from fastapi.routing import APIRoute
    from prama.api import API_PREFIX
    from prama.api.deps import get_caller

    def walk(routes, prefix=""):
        for route in routes:
            if isinstance(route, APIRoute):
                yield (prefix + route.path, frozenset(route.methods or ()), route)
                continue
            original = getattr(route, "original_router", None)
            if original is not None:
                context = getattr(route, "include_context", None)
                yield from walk(original.routes, prefix + getattr(context, "prefix", ""))
                continue
            nested = getattr(route, "routes", None)
            if nested:
                yield from walk(nested, prefix + getattr(route, "prefix", ""))

    def _reaches(route, predicate):
        pending = [route.dependant]
        while pending:
            dependant = pending.pop()
            found = predicate(dependant)
            if found is not None:
                return found
            pending.extend(dependant.dependencies)
        return None

    def scope_of(route):
        return _reaches(route, lambda d: getattr(d.call, "prama_scope", None))

    bare_mutating = []
    for path, methods, route in walk(env.app.routes):
        if not path.startswith(API_PREFIX):
            continue
        mutating_methods = methods & {"POST", "PUT", "PATCH", "DELETE"}
        if mutating_methods and scope_of(route) is None:
            bare_mutating.append(f"{sorted(mutating_methods)} {path}")
    record("API-035", "PASS" if not bare_mutating else "FAIL", f"bare_mutating_routes={bare_mutating}")

    # API-036: authorisation decided before body is parsed (Q-46)
    readonly_key = await a._issue_key(env.database, env.tenant_id, principal="ro36", scopes=["declaration:read"])
    async with env.client(readonly_key) as http:
        bad_bodies = [
            {"name": 12345},                  # wrong type
            {"criticality": "not-a-number"},  # wrong type, missing required
            {},                                # missing everything
        ]
        results36 = []
        for b in bad_bodies:
            r = await http.post("/datasets", json=b)
            results36.append((r.status_code, r.text[:150]))
    ok36 = all(code == 403 for code, _ in results36)
    record("API-036", "PASS" if ok36 else "FAIL", f"results={results36}")

    await env.stop()


asyncio.run(main())
print("done api batch 2c")
