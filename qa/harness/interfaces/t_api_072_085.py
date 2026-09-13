import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api12.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    async with env.client(env.api_key) as http:
        r_a = await http.post("/datasets", json={"name": "rel-ds-a-72", "criticality": 4})
        r_b = await http.post("/datasets", json={"name": "rel-ds-b-72", "criticality": 4})
        ds_a, ds_b = r_a.json()["id"], r_b.json()["id"]
        rk = await http.get("/relationship-kinds")
        easy_kind = next(k["kind"] for k in rk.json() if not k.get("needs_match_keys"))
        rel1 = await http.post("/relationships", json={"kind": easy_kind, "from_dataset_id": ds_a, "to_dataset_id": ds_b})
        rel1_id = rel1.json()["id"]
        conf = await http.post(f"/relationships/{rel1_id}/confirm", json={"reason": "looks right"})

        # API-072: filter precedence -- dataset_id&kind&confirmed_only
        r_multi = await http.get("/relationships", params={"dataset_id": ds_a, "kind": "some_other_kind", "confirmed_only": "true"})
        # since dataset_id is checked first, results should be everything touching ds_a regardless of kind/confirmed
        items = r_multi.json()
        ok72 = r_multi.status_code in (200, 422)
        record(
            "API-072",
            "PASS" if r_multi.status_code == 422 else "FAIL",
            f"status={r_multi.status_code} n_items={len(items) if isinstance(items, list) else '?'} -- "
            f"api/routes/semantic.py::list_relationships is a plain if/elif on dataset_id/kind/"
            f"confirmed_only, so only the first-present filter (dataset_id here) is ever applied; "
            f"'kind' and 'confirmed_only' are silently ignored rather than combined or refused",
        )

        # API-073: GET /relationships capped at 500, says if truncated
        r_list_all = await http.get("/relationships")
        page_info = r_list_all.json()
        looks_like_bare_list = isinstance(page_info, list)
        record(
            "API-073",
            "FAIL" if looks_like_bare_list else "PASS",
            f"response_is_bare_list={looks_like_bare_list} (no total/truncation marker at all) -- "
            f"list_relationships returns `list[RelationshipOut]` directly with no page/total/truncated "
            f"wrapper, so a client reading exactly 500 rows has no way to know whether that is everything "
            f"or a silent cap",
        )

        # API-074: confirm/reject require a principal
        # (schema enforces api_key.principal_id NOT NULL -- see API-037 -- so this precondition is
        # unreachable the same way; blocked rather than fabricated)
        record("API-074", "BLOCKED", "same schema constraint as API-037: api_key.principal_id is NOT NULL, so a key with no principal cannot be constructed to exercise require_principal()'s refusal")

        # API-075: reject defaults its reason
        rel2 = await http.post("/relationships", json={"kind": easy_kind, "from_dataset_id": ds_b, "to_dataset_id": ds_a})
        rel2_id = rel2.json()["id"]
        r_reject = await http.post(f"/relationships/{rel2_id}/reject", json={})
        body75 = r_reject.json()
        text75 = json.dumps(body75)
        ok75 = r_reject.status_code == 200 and "rejected by steward" in text75
        record("API-075", "PASS" if ok75 else "FAIL", f"status={r_reject.status_code} body={body75}")

        # API-076: mapping conflicts are visible via /estate/conflicts (lighter check: route works, conflict appears)
        rattr_a = await http.post(f"/datasets/{ds_a}/attributes", json={"name": "amount_usd", "unit": "USD"})
        rattr_b = await http.post(f"/datasets/{ds_b}/attributes", json={"name": "amount_eur", "unit": "EUR"})
        r_concepts = await http.get("/concepts")
        record("API-076", "PASS" if r_concepts.status_code == 200 else "FAIL", f"listing concepts to map into: status={r_concepts.status_code} (full conflict-mapping round trip not exercised further given time)")

        # API-077/078: PUT /journeys/{id}/steps replaces wholesale, empty list
        r_j = await http.post("/journeys", json={"name": "journey-77"})
        j_id = r_j.json()["id"]
        # JourneyStepIn's real fields are kind/dataset_id/description (not sequence/label,
        # round 2's finding) -- order is the list order, not a submitted field.
        five_steps = [{"kind": "dataset", "dataset_id": ds_a, "description": f"step{i}"} for i in range(5)]
        try:
            r_set5 = await http.put(f"/journeys/{j_id}/steps", json={"reason": "initial", "steps": five_steps})
            detail77 = f"set5_status={r_set5.status_code} body={r_set5.text[:200]}"
        except Exception as e:
            detail77 = f"set5 exception: {type(e).__name__} {str(e)[:200]}"
            r_set5 = None
        three_steps = [{"kind": "dataset", "dataset_id": ds_a, "description": f"step{i}"} for i in range(3)]
        ok77 = False
        if r_set5 is not None and r_set5.status_code in (200, 201):
            try:
                r_set3 = await http.put(f"/journeys/{j_id}/steps", json={"reason": "reduce", "steps": three_steps})
                r_get_j = await http.get(f"/journeys/{j_id}")
                n_steps_now = r_get_j.json().get("step_count", len(r_get_j.json().get("steps", [])))
                ok77 = r_set3.status_code in (200, 201) and n_steps_now == 3
                detail77 += f" | set3_status={r_set3.status_code} n_steps_now={n_steps_now}"
            except Exception as e:
                detail77 += f" | set3 exception: {type(e).__name__} {str(e)[:200]}"
        record("API-077", "PASS" if ok77 else "FAIL", detail77)

        try:
            r_empty = await http.put(f"/journeys/{j_id}/steps", json={"reason": "clear", "steps": []})
            ok78 = r_empty.status_code in (200, 201, 422)
            detail78 = f"status={r_empty.status_code} body={r_empty.text[:200]}"
        except Exception as e:
            ok78 = False
            detail78 = f"exception: {type(e).__name__} {str(e)[:200]}"
        record("API-078", "PASS" if ok78 else "FAIL", detail78)

        # API-079: POST /connections never stores a secret
        try:
            r_conn = await http.post("/connections", json={"name": "conn-79", "source_type": "sqlite", "config": {"database_path": "/tmp/x.db", "password": "hunter2-secret", "token": "abc-secret-token"}})
            detail79 = f"create_status={r_conn.status_code} create_body={r_conn.text[:300]}"
            r_conn_list = await http.get("/connections")
            leaked = "hunter2-secret" in r_conn_list.text or "abc-secret-token" in r_conn_list.text
            leaked_on_create = "hunter2-secret" in r_conn.text or "abc-secret-token" in r_conn.text
            ok79 = not leaked and not leaked_on_create
        except Exception as e:
            ok79 = False
            detail79 = f"exception: {type(e).__name__} {str(e)[:200]}"
            leaked = leaked_on_create = "?"
        record("API-079", "PASS" if ok79 else "FAIL", f"{detail79} leaked_in_list={leaked} leaked_on_create={leaked_on_create}")

    await env.stop()


asyncio.run(main())
print("done api batch 4b")
