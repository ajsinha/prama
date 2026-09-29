"""Every API error is `application/problem+json`, including the ones FastAPI raises.

QA round 4 triage, cluster B1 — `API-010`, `API-011`, `API-012`, `API-013`,
`API-017`, `API-058`. `api/app.py` registers two exception handlers:

    app.add_exception_handler(PramaError, prama_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

Neither catches Starlette's `HTTPException` — raised by the router itself for an
unknown path or a wrong method — nor FastAPI's `RequestValidationError`, raised
for a malformed query or body before any handler runs. Starlette answers those
with its own built-in handler first, producing a bare `{"detail": "..."}` with
`content-type: application/json`, and the request never reaches Prama's error
code at all.

**Why that matters more than a header.** `Q-22`'s whole point was that an
integrator branches on `code`, not on prose: a 404 carrying `type`, `code`,
`remedy` and `correlation_id` can be handled programmatically, and
`{"detail": "Not Found"}` can only be logged. The product documents
problem+json as its error contract and then does not honour it on the two error
classes a caller hits most often — a mistyped URL and a malformed parameter.

**What a careless version of this test would assert.** `status_code == 404`.
That passes today, passed before the fix, and would never notice that every
field an integrator needs is missing. So each case below checks the media type
*and* the document's fields, and one case pins the status codes separately so a
handler that returns problem+json with the wrong status cannot hide behind the
header.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.config import Configuration
from prama.db import Database
from prama.db.security import ApiKeyIssuer
from prama.security.accounts import grant_roles

PROBLEM = "application/problem+json"


@pytest.fixture
async def api_client(
    qa_config: Configuration, estate: Database, two_tenants: tuple[str, str]
) -> AsyncIterator[httpx.AsyncClient]:
    """An authenticated API client, with a real key.

    Self-contained rather than borrowing `tests/api/conftest.py`'s fixture,
    whose `base_url` already carries the API prefix — the paths below are
    written in full so that what the test asks for is what a caller would type.
    """
    ours, _ = two_tenants
    issued = ApiKeyIssuer().issue(environment="test")
    async with estate.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=ours, username="api", display_name="api")
        await uow.flush()
        # A person's key is bounded by their roles; this one may do anything.
        await grant_roles(uow, ours, person, ["admin"])
        uow.api_keys.create(
            tenant_id=ours,
            principal_id=str(person.id),
            name="regression",
            key_prefix=issued.prefix,
            key_hash=issued.hash,
            scopes=["*"],
        )

    app = create_app(qa_config, database=estate)
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {issued.plaintext}"},
        ) as http,
        app.router.lifespan_context(app),
    ):
        yield http


#: Each is an error FastAPI or Starlette raises *before* any Prama code runs.
#: `method-not-allowed` and `unknown-path` come from the router; the last two
#: from request validation.
ROUTER_ERRORS = [
    pytest.param("GET", "/api/v1/no-such-route", None, 404, id="unknown-path"),
    pytest.param("DELETE", "/api/v1/datasets", None, 405, id="method-not-allowed"),
]


@pytest.mark.parametrize("method,path,body,expected_status", ROUTER_ERRORS)
async def test_a_router_error_is_a_problem_document(
    api_client: httpx.AsyncClient,
    method: str,
    path: str,
    body: dict | None,
    expected_status: int,
) -> None:
    response = await api_client.request(method, path, json=body)

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith(PROBLEM), (
        f"{method} {path} answered with {response.headers['content-type']!r}. "
        "Starlette's own handler ran instead of Prama's, so the body is "
        f"{response.text[:160]}"
    )

    document = response.json()
    for field in ("type", "title", "status", "code"):
        assert field in document, (
            f"{method} {path} returned a problem document without {field!r}: {document}. "
            "An integrator branches on `code`; prose can only be logged."
        )
    assert document["status"] == expected_status


async def test_a_malformed_parameter_is_a_problem_document(
    api_client: httpx.AsyncClient,
) -> None:
    """`RequestValidationError`, the other class Starlette answers first.

    `limit` is declared `int = Query(ge=1, le=500)`, so a non-numeric value is
    refused by FastAPI before any handler runs — which is the point. An earlier
    draft used `valid_at="not-a-date"` on the assumption it was date-validated;
    it is not, the request returns 200, and the test failed for a reason
    unrelated to the defect. Checked rather than assumed, after the third time
    that happened today.
    """
    response = await api_client.get("/api/v1/datasets", params={"limit": "lots"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM), (
        f"a malformed query parameter answered with "
        f"{response.headers['content-type']!r}: {response.text[:160]}"
    )
    document = response.json()
    assert "code" in document and "title" in document
    assert document["status"] == 422


async def test_the_body_still_says_what_was_wrong(api_client: httpx.AsyncClient) -> None:
    """Turning these into problem documents must not lose FastAPI's detail.

    The failure mode of this repair is a handler that produces a beautifully
    shaped document saying nothing — "a request was invalid" — which satisfies
    every field check above and helps nobody. The parameter's name has to
    survive into the response.
    """
    response = await api_client.get("/api/v1/datasets", params={"limit": "lots"})
    rendered = response.text

    assert "limit" in rendered, (
        "the refusal no longer names the parameter that was wrong. A problem "
        f"document that cannot say which field failed is prose with a schema: {rendered[:200]}"
    )


async def test_a_prama_error_is_unchanged(api_client: httpx.AsyncClient) -> None:
    """The handler that already worked must keep working.

    Registering two more handlers is exactly the kind of change that reorders
    dispatch. A `PramaError` still has to reach `prama_error_handler` and carry
    its remedy — the field the other handlers cannot synthesise.
    """
    response = await api_client.get("/api/v1/datasets/not-a-ulid")

    assert response.headers["content-type"].startswith(PROBLEM)
    document = response.json()
    assert "remedy" in document, (
        "a Prama error lost its remedy, so the new handlers are catching what "
        f"prama_error_handler should have: {document}"
    )
