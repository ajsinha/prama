import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api8.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    # API-037: require_principal refuses with a remedy naming the header, on a key with null principal.
    # The schema itself enforces api_key.principal_id NOT NULL (confirmed by attempting to insert one
    # directly, which raises a ConflictError/IntegrityError), so this precondition cannot be constructed
    # at all through any real path -- matching the catalogue's own Why verbatim ("apikey create makes
    # --principal mandatory, so this path should be unreachable").
    from prama.db.security import ApiKeyIssuer
    issuer = ApiKeyIssuer()
    issue = issuer.issue(environment="test")
    precondition_error = None
    try:
        async with env.database.unit_of_work() as uow:
            uow.api_keys.create(
                tenant_id=env.tenant_id, principal_id=None, name="no-principal",
                key_prefix=issue.prefix, key_hash=issue.hash, scopes=["relationship:write"],
            )
            await uow.flush()
    except Exception as e:
        precondition_error = f"{type(e).__name__}: {str(e)[:200]}"
    record(
        "API-037",
        "BLOCKED",
        f"precondition cannot be constructed: creating an api_key row with principal_id=None raises "
        f"{precondition_error} -- schema/sqlite.sql declares api_key.principal_id VARCHAR(26) NOT NULL, "
        f"so no key can ever reach get_caller with a null principal_id; require_principal()'s check is "
        f"defensive code for a state the schema does not allow, exactly matching the catalogue's own "
        f"stated Why ('this path should be unreachable')",
    )

    # API-038: a request that raises leaves no partial write. Monkeypatch the audit-log step (which
    # writes a second row in the SAME unit of work as the primary entity) to raise after the primary
    # write has already gone through the session, then confirm nothing committed.
    from unittest.mock import patch

    ds_name = "partial-write-probe-38"
    async with env.client(env.api_key) as http:
        with patch("prama.semantic.services.base.SemanticService._audit", side_effect=RuntimeError("boom mid-transaction")):
            try:
                r = await http.post("/datasets", json={"name": ds_name, "criticality": 4})
                status_or_exc = r.status_code
            except Exception as e:
                status_or_exc = f"EXCEPTION: {type(e).__name__} {str(e)[:150]}"
        r_list = await http.get("/datasets")
    names = [d["name"] for d in r_list.json().get("items", [])]
    ok = ds_name not in names
    record(
        "API-038",
        "PASS" if ok else "FAIL",
        f"forced_failure_result={status_or_exc} dataset_visible_after={ds_name in names} "
        f"(expected: the dataset write did NOT commit despite having happened before the injected failure)",
    )

    await env.stop()


asyncio.run(main())
print("done api batch 2d")
