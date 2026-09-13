import asyncio, sys, tempfile
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
import httpx
from httpx import ASGITransport
from prama.api import API_PREFIX, create_app
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.db.security import ApiKeyIssuer
from pathlib import Path

REPO = Path("/home/ashutosh/PycharmProjects/prama")

async def main():
    tmp = tempfile.mkdtemp()
    config = (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping({
            "database": {"dialect": "sqlite", "sqlite": {"path": f"{tmp}/prama-test.db"},
                         "schema_dir": str(REPO / "schema"), "verify_on_start": True},
            "security": {"session_secret": "test-only-not-a-secret", "cookies_https_only": False},
        }, name="test")
        .build()
    )
    database = Database.from_config(config)
    database.initialise(applied_by="qa-harness")
    await database.start()

    async with database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug="acme-bank", display_name="Acme Bank")
        await uow.flush()
        tenant_id = str(tenant.id)

    # ---- API-level: SEC-012, SEC-013 ----
    issued = ApiKeyIssuer().issue(environment="test")
    async with database.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=tenant_id, username="readonly", display_name="Read Only")
        await uow.flush()
        uow.api_keys.create(tenant_id=tenant_id, principal_id=str(person.id), name="ro",
                             key_prefix=issued.prefix, key_hash=issued.hash, scopes=["declaration:read"])
    app = create_app(config, database=database)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver" + API_PREFIX,
                                  headers={"Authorization": f"Bearer {issued.plaintext}"}) as http, \
               app.router.lifespan_context(app):
        # enumerate every route with the walk() logic from test_scopes.py
        from fastapi.routing import APIRoute
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
                d = pending.pop()
                found = predicate(d)
                if found is not None:
                    return found
                pending.extend(d.dependencies)
            return None

        def scope_of(route):
            return _reaches(route, lambda d: getattr(d.call, "prama_scope", None))

        endpoints = [(p, m, r) for p, m, r in walk(app.routes) if p.startswith(API_PREFIX)]
        mutating = [(p, m, r) for p, m, r in endpoints if m & {"POST", "PUT", "PATCH", "DELETE"} and scope_of(r) is not None]

        # SEC-012: read-only key attempts every write route -> 403
        results = []
        for path, methods, route in mutating:
            method = sorted(methods & {"POST", "PUT", "PATCH", "DELETE"})[0]
            url = path[len(API_PREFIX):] if path.startswith(API_PREFIX) else path
            # substitute any {param} with a dummy ULID-ish value
            import re
            url_filled = re.sub(r"\{[^}]+\}", "01TESTTESTTESTTESTTESTTESTT", url)
            resp = await http.request(method, url_filled, json={})
            results.append((method, path, resp.status_code))
        non_403 = [r for r in results if r[2] != 403]
        line("SEC-012", "PASS" if not non_403 else "FAIL",
             f"tested {len(results)} mutating routes with a declaration:read-only key -- non-403 results: {non_403}")

        # SEC-013: authorisation decided before body parsed -- POST invalid body to a write route -> 403 not 422
        if mutating:
            path, methods, route = mutating[0]
            method = sorted(methods & {"POST", "PUT", "PATCH", "DELETE"})[0]
            url = path[len(API_PREFIX):]
            import re
            url_filled = re.sub(r"\{[^}]+\}", "01TESTTESTTESTTESTTESTTESTT", url)
            resp = await http.request(method, url_filled, content=b"not-json-at-all-{{{", headers={"content-type": "application/json"})
            line("SEC-013", "PASS" if resp.status_code == 403 else "FAIL",
                 f"POST invalid body to {method} {path} with read-only key -> {resp.status_code} (expected 403, not 422)")
        else:
            line("SEC-013", "BLOCKED", "no mutating route found to test")

    # ---- Console-level: SEC-014 ----
    from prama.cli.principal import BUILTIN_ROLES
    PASSWORD = "correct-horse-battery-staple"
    async with database.unit_of_work() as uow:
        role_perm = BUILTIN_ROLES["steward"][1]
        person = uow.principals.create(tenant_id=tenant_id, username="steward1", display_name="Steward One")
        uow.principals.set_password(person, PASSWORD)
        role = uow.roles.create(tenant_id=tenant_id, name="steward", permissions=role_perm)
        await uow.flush()
        await uow.roles.grant(str(person.id), str(role.id))
        await uow.flush()

    app2 = create_app(config, database=database)
    transport2 = ASGITransport(app=app2)
    async with httpx.AsyncClient(transport=transport2, base_url="http://testserver") as http2, \
               app2.router.lifespan_context(app2):
        signin = await http2.post("/sign-in", data={"username": "steward1", "password": PASSWORD})
        signed_in_ok = signin.status_code == 303

        # A break workbench write action the console offers a steward (break:* granted)
        resp_assign = await http2.post("/reconciliation/breaks/01TESTTESTTESTTESTTESTTESTT/assign",
                                        data={"assignee": "steward1"}, follow_redirects=False)
        resp_explain = await http2.post("/reconciliation/breaks/01TESTTESTTESTTESTTESTTESTT/explain",
                                         data={"explanation": "x"}, follow_redirects=False)
        line("SEC-014", "PASS" if (resp_assign.status_code != 403 and resp_explain.status_code != 403) else "FAIL",
             f"signed_in={signed_in_ok} POST /reconciliation/breaks/.../assign -> {resp_assign.status_code}; "
             f".../explain -> {resp_explain.status_code} (steward holds break:* per BUILTIN_ROLES; "
             f"route registered via self.page() with no explicit scope=, so it defaults to auto->declaration:write "
             f"for a POST, which steward does NOT hold -- steward's grants: {role_perm})")

    await database.stop()

asyncio.run(main())
