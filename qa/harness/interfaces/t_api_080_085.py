import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api13.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    async with env.client(env.api_key) as http:
        # API-080: credential_ref is a reference, not a credential
        r_conn = await http.post("/connections", json={"name": "conn-80", "source_type": "sqlite", "config": {"database_path": "/tmp/x.db"}, "credential_ref": "hunter2-looks-like-a-password"})
        create_body = r_conn.text
        r_list = await http.get("/connections")
        list_body = r_list.text
        ok80 = r_conn.status_code == 201 and "hunter2-looks-like-a-password" in create_body
        record(
            "API-080",
            "PASS" if ok80 else "FAIL",
            f"create_status={r_conn.status_code} create_body={create_body[:250]} -- "
            f"credential_ref is stored and echoed back as an opaque string (not dereferenced) and no "
            f"further processing of it was observed",
        )

        # API-081: bind branches on attribute_id
        r_ds = await http.post("/datasets", json={"name": "bind-ds-81", "criticality": 4})
        ds_id = r_ds.json()["id"]
        r_ds2 = await http.post("/datasets", json={"name": "bind-ds-81-other", "criticality": 4})
        ds2_id = r_ds2.json()["id"]
        r_attr = await http.post(f"/datasets/{ds_id}/attributes", json={"name": "field81"})
        attr_id = r_attr.json()["id"]
        r_conn2 = await http.post("/connections", json={"name": "conn-81", "source_type": "sqlite", "config": {"database_path": "/tmp/y.db"}})
        conn_id = r_conn2.json().get("id")
        res81 = {}
        if conn_id:
            r_bind_ds = await http.post(f"/datasets/{ds_id}/bindings", json={"connection_id": conn_id, "physical_ref": {"table": "t"}})
            res81["dataset-binding"] = (r_bind_ds.status_code, r_bind_ds.text[:150])
            r_bind_attr = await http.post(f"/datasets/{ds_id}/bindings", json={"connection_id": conn_id, "attribute_id": attr_id, "physical_ref": {"column": "c"}})
            res81["attribute-binding"] = (r_bind_attr.status_code, r_bind_attr.text[:150])
            # mismatched: attribute belongs to ds_id, but we bind against ds2_id's endpoint
            r_bind_mismatch = await http.post(f"/datasets/{ds2_id}/bindings", json={"connection_id": conn_id, "attribute_id": attr_id, "physical_ref": {"column": "c"}})
            res81["mismatched-attribute"] = (r_bind_mismatch.status_code, r_bind_mismatch.text[:200])
        ok81 = conn_id is not None and res81.get("mismatched-attribute", (0,))[0] in (400, 404, 422)
        record("API-081", "PASS" if ok81 else "FAIL", f"conn_created={conn_id is not None} {res81}")

        # API-082: GET /bindings/drifted
        r_drift = await http.get("/bindings/drifted")
        ok82 = r_drift.status_code == 200 and isinstance(r_drift.json(), list)
        record("API-082", "PASS" if ok82 else "FAIL", f"status={r_drift.status_code} body={r_drift.text[:200]}")

        # API-083: /estate/maturity decomposes
        r_mat = await http.get("/estate/maturity")
        body83 = r_mat.json()
        ok83 = r_mat.status_code == 200 and isinstance(body83, dict) and len(body83) > 1
        record("API-083", "PASS" if ok83 else "FAIL", f"status={r_mat.status_code} keys={list(body83.keys()) if isinstance(body83, dict) else body83}")

        # API-084: /estate/maturity with unexpected scope/domain_id
        try:
            r_bad_scope = await http.get("/estate/maturity", params={"scope": "banana"})
            detail_scope = f"status={r_bad_scope.status_code} body={r_bad_scope.text[:250]}"
            ok_scope = r_bad_scope.status_code in (400, 422)
        except Exception as e:
            ok_scope = False
            detail_scope = f"exception: {type(e).__name__} {str(e)[:200]}"
        try:
            r_bad_domain = await http.get("/estate/maturity", params={"domain_id": "01NOSUCH00000000000000000"})
            detail_domain = f"status={r_bad_domain.status_code} body={r_bad_domain.text[:250]}"
            ok_domain = r_bad_domain.status_code in (400, 404, 422)
        except Exception as e:
            ok_domain = False
            detail_domain = f"exception: {type(e).__name__} {str(e)[:200]}"
        ok84 = ok_scope and ok_domain
        record("API-084", "PASS" if ok84 else "FAIL", f"bad_scope: {detail_scope} | bad_domain: {detail_domain}")

        # API-085: /estate/coverage-gaps returns the honest list
        r_gaps = await http.get("/estate/coverage-gaps")
        body85 = r_gaps.json()
        ok85 = r_gaps.status_code == 200 and isinstance(body85, dict)
        record("API-085", "PASS" if ok85 else "FAIL", f"status={r_gaps.status_code} keys={list(body85.keys()) if isinstance(body85, dict) else body85}")

    await env.stop()


asyncio.run(main())
print("done api batch 4c")
