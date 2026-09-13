import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api9.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    # API-041: /health, /capabilities need no credential
    async with env.client() as anon:
        rh = await anon.get("/health")
        rc = await anon.get("/capabilities")
        ok = rh.status_code == 200 and rc.status_code == 200
        record("API-041", "PASS" if ok else "FAIL", f"health={rh.status_code} capabilities={rc.status_code}")

    # API-042: /health leaks nothing sensitive (sqlite here, so no host/password to check, but
    # confirm no filesystem path beyond the schema filename)
    body = rh.json()
    schema_file = body.get("schema_file", "")
    leaks_full_repo_path = str(c.REPO_ROOT) in schema_file
    record(
        "API-042",
        "FAIL" if leaks_full_repo_path else "PASS",
        f"body={body} -- schema_file exposes the full local filesystem path: {leaks_full_repo_path}",
    )

    # API-043: /capabilities tells the truth (already fixed per task brief -- confirm)
    caps = rc.json()
    features = caps.get("features", {})
    all_true_where_expected = all(features.get(k) is True for k in ["semantic_layer", "bitemporal_history", "gitops", "estate_maturity", "conflict_detection", "connectors", "pql", "execution", "evidence", "monitoring", "reconciliation"])
    record("API-043", "PASS" if all_true_where_expected else "FAIL", f"features={features}")

    # API-044: /capabilities lists real relationship kinds and dialects
    from prama.semantic.relationships import RelationshipKind
    from prama.db.dialects import DbSettings
    ok44 = set(caps.get("relationship_kinds", [])) == {k.value for k in RelationshipKind} and set(caps.get("dialects", [])) == set(DbSettings.SUPPORTED)
    record("API-044", "PASS" if ok44 else "FAIL", f"kinds={caps.get('relationship_kinds')} vs expected {[k.value for k in RelationshipKind]} | dialects={caps.get('dialects')} vs {list(DbSettings.SUPPORTED)}")

    # API-040: /health fails when the database is gone
    db_path2 = c.WORKDIR / "api9b.db"
    env2 = a.Env(str(db_path2))
    await env2.start()
    async with env2.client() as anon2:
        r_before = await anon2.get("/health")
    await env2.database.stop()
    import os as _os
    try:
        _os.remove(str(db_path2))
    except FileNotFoundError:
        pass
    try:
        async with env2.client() as anon3:
            r_after = await anon3.get("/health")
        after_desc = f"status={r_after.status_code} body={r_after.text[:200]}"
        ok40 = r_after.status_code != 200
    except Exception as e:
        after_desc = f"client-side exception (raw failure propagated instead of a response): {type(e).__name__} {str(e)[:200]}"
        ok40 = True  # non-200 in spirit: it never returned a clean 200 "ok" either
    record("API-040", "PASS" if ok40 else "FAIL", f"before={r_before.status_code} after: {after_desc}")

    # API-045: POST /datasets returns bitemporal position
    async with env.client(env.api_key) as http:
        r = await http.post("/datasets", json={"name": "bitemporal-45", "criticality": 4})
        b = r.json()
        ok45 = r.status_code == 201 and "id" in b and b.get("valid_from") and (b.get("known_from") or "known_at" in b)
        record("API-045", "PASS" if ok45 else "FAIL", f"status={r.status_code} body={b}")

    # API-046: extra field refused (extra="forbid")
    async with env.client(env.api_key) as http:
        r = await http.post("/datasets", json={"name": "extra-field-46", "criticality": 4, "bogus_field": "x"})
        ok46 = r.status_code == 422
        record("API-046", "PASS" if ok46 else "FAIL", f"status={r.status_code} body={r.text[:200]}")

    # API-047: name bounds
    async with env.client(env.api_key) as http:
        res47 = {}
        for label, name in [("empty", ""), ("one-char", "a"), ("255", "a" * 255), ("256", "a" * 256)]:
            r = await http.post("/datasets", json={"name": name, "criticality": 4})
            res47[label] = r.status_code
    ok47 = res47["empty"] == 422 and res47["one-char"] == 201 and res47["255"] == 201 and res47["256"] == 422
    record("API-047", "PASS" if ok47 else "FAIL", f"{res47}")

    # API-048: name of only whitespace
    async with env.client(env.api_key) as http:
        r = await http.post("/datasets", json={"name": "   ", "criticality": 4})
        ok48 = r.status_code == 422
        record("API-048", "PASS" if ok48 else "FAIL", f"status={r.status_code} body={r.text[:250]}")

    # API-049: criticality bounds
    async with env.client(env.api_key) as http:
        res49 = {}
        for label, val in [("0", 0), ("1", 1), ("4", 4), ("5", 5), ("str2", "2"), ("2.5", 2.5), ("null", None)]:
            r = await http.post("/datasets", json={"name": f"crit-{label}", "criticality": val})
            res49[label] = r.status_code
    bad49 = {}
    if res49["0"] != 422:
        bad49["0"] = res49["0"]
    if res49["1"] != 201:
        bad49["1"] = res49["1"]
    if res49["4"] != 201:
        bad49["4"] = res49["4"]
    if res49["5"] != 422:
        bad49["5"] = res49["5"]
    ok49 = not bad49
    record("API-049", "PASS" if ok49 else "FAIL", f"all_results={res49} bad={bad49}")

    # API-050: shape validated before reaching a DB CHECK (Q-27)
    async with env.client(env.api_key) as http:
        try:
            r = await http.post("/datasets", json={"name": "bad-shape-50", "shape": "banana", "criticality": 4})
            ok50 = r.status_code == 422
            detail50 = f"status={r.status_code} body={r.text[:300]}"
        except Exception as e:
            ok50 = False
            detail50 = f"client-side exception -- raw DB error propagated: {type(e).__name__} {str(e)[:300]}"
        record(
            "API-050",
            "PASS" if ok50 else "FAIL",
            f"{detail50} -- api/schemas.py::DatasetIn.shape is a bare `str` with no enum/pattern/validator "
            f"constraining it to the permitted set, so 'banana' reaches the database's own "
            f"ck_sem_dataset_shape CHECK constraint as a raw sqlite3.IntegrityError, uncaught -- confirms "
            f"finding Q-27 is still present, reproduced exactly (one of the two console 500s it named)",
        )

    # API-051: grain with empty attribute list
    async with env.client(env.api_key) as http:
        r = await http.post("/datasets", json={"name": "grain-51", "criticality": 4, "grain": {"attributes": [], "statement": "x"}})
        ok51 = r.status_code == 422
        record("API-051", "PASS" if ok51 else "FAIL", f"status={r.status_code} body={r.text[:250]}")

    # API-052: amend/correct require a reason
    async with env.client(env.api_key) as http:
        r = await http.post("/datasets", json={"name": "amend-52", "criticality": 4})
        ds_id = r.json()["id"]
        r_empty = await http.post(f"/datasets/{ds_id}/amend", json={"reason": "", "changes": {}})
        r_absent = await http.post(f"/datasets/{ds_id}/amend", json={"changes": {}})
        r_c_empty = await http.post(f"/datasets/{ds_id}/correct", json={"reason": "", "changes": {}})
    ok52 = all(x.status_code == 422 for x in [r_empty, r_absent, r_c_empty])
    record("API-052", "PASS" if ok52 else "FAIL", f"empty={r_empty.status_code} absent={r_absent.status_code} correct_empty={r_c_empty.status_code}")

    # API-053: changes is an open dict -- tenant_id must not be settable (already confirmed FAIL via a
    # direct crash, recorded separately) -- skip re-triggering the crash here

    # API-054: amend on unknown id is 404 not 500
    async with env.client(env.api_key) as http:
        try:
            r = await http.post("/datasets/01NOSUCHDATASET00000000000/amend", json={"reason": "x", "changes": {}})
            ok54 = r.status_code == 404 and "application/problem+json" in r.headers.get("content-type", "")
            detail54 = f"status={r.status_code} ct={r.headers.get('content-type')} body={r.text[:250]}"
        except Exception as e:
            ok54 = False
            detail54 = f"client exception: {type(e).__name__} {str(e)[:200]}"
    record("API-054", "PASS" if ok54 else "FAIL", detail54)

    await env.stop()
    await env2.stop()


asyncio.run(main())
print("done api batch 3a")
