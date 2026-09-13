import sys, os, json, asyncio, logging
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api4.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    # API-015: a 4xx is not logged at ERROR
    records = []

    class Capture(logging.Handler):
        def emit(self, rec):
            records.append(rec)

    handler = Capture()
    handler.setLevel(logging.ERROR)
    logging.getLogger("prama.api.errors").addHandler(handler)
    async with env.client() as anon:
        for _ in range(10):
            await anon.get("/datasets")
    logging.getLogger("prama.api.errors").removeHandler(handler)
    ok = len(records) == 0
    record("API-015", "PASS" if ok else "FAIL", f"n_error_logs_for_10x_401={len(records)} sample={[r.getMessage() for r in records[:2]]}")

    # API-002: every operation in openapi.json is callable with a minimal well-formed call.
    # Round 2 found that a fake placeholder id makes 5 by-id operations (GET/DELETE
    # /datasets/{id}, POST /relationships/{id}/confirm|reject, GET /journeys/{id}) look like
    # 404 "route does not exist" when they are really "the id looked up cleanly and correctly
    # was not found" -- both produce a 404, but only the first is the defect this case is about.
    # Seed real entities and route their ids to the right path parameter names instead.
    async with env.client(env.api_key) as http:
        r_ds = await http.post("/datasets", json={"name": "api002-ds", "criticality": 4})
        real_dataset_id = r_ds.json()["id"]
        r_ds2 = await http.post("/datasets", json={"name": "api002-ds2", "criticality": 4})
        real_dataset_id2 = r_ds2.json()["id"]
        # a THIRD, disposable dataset just for the DELETE operation -- so deleting it does not
        # remove the one GET /datasets/{id} (and the relationship built from it) still needs
        r_ds3 = await http.post("/datasets", json={"name": "api002-ds-to-delete", "criticality": 4})
        delete_dataset_id = r_ds3.json()["id"]
        r_rel = await http.post("/relationships", json={
            "kind": "references", "from_dataset_id": real_dataset_id, "to_dataset_id": real_dataset_id2,
            "match_keys": [{"left": "id"}],
        })
        real_relationship_id = r_rel.json().get("id")
        r_j = await http.post("/journeys", json={"name": "api002-journey"})
        real_journey_id = r_j.json().get("id")
        ID_BY_PARAM = {
            "dataset_id": real_dataset_id,
            "relationship_id": real_relationship_id,
            "journey_id": real_journey_id,
        }

        doc = (await http.get("/openapi.json")).json()
        bad = {}
        checked = 0
        # DELETE operations run last, so removing an entity cannot make an earlier GET/POST
        # against the SAME id see a legitimate post-delete 404 and misread it as a missing route.
        operations = [
            (path, method, spec)
            for path, methods in doc.get("paths", {}).items()
            for method, spec in methods.items()
            if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE")
        ]
        operations.sort(key=lambda item: item[1].upper() == "DELETE")
        for path, method, spec in operations:
                # substitute path params with a real id when one is available for that param
                # name, and a plausible-looking (but nonexistent) ULID otherwise; strip the
                # /api/v1 prefix since the client's base_url already carries it
                concrete_path = path.removeprefix("/api/v1")
                for param in spec.get("parameters", []):
                    if param.get("in") == "path":
                        pname = param["name"]
                        if method.upper() == "DELETE" and pname == "dataset_id":
                            value = delete_dataset_id
                        else:
                            value = ID_BY_PARAM.get(pname) or "01M2D0000000000000000000A"
                        concrete_path = concrete_path.replace("{" + pname + "}", value)
                checked += 1
                try:
                    if method.upper() == "GET":
                        r = await http.get(concrete_path)
                    elif method.upper() == "DELETE":
                        r = await http.delete(concrete_path)
                    else:
                        # send an empty-ish body; a 422 (unprocessable) counts as "callable" (route exists,
                        # handler ran, validation happened) -- only 404/405 indicate the operation itself
                        # is not reachable
                        r = await http.request(method.upper(), concrete_path, json={})
                except Exception as e:
                    bad[f"{method.upper()} {path}"] = f"client exception: {type(e).__name__} {str(e)[:150]}"
                    continue
                if r.status_code in (404, 405):
                    bad[f"{method.upper()} {path}"] = f"status={r.status_code}"
        ok = not bad
        record("API-002", "PASS" if ok else "FAIL", f"n_operations_checked={checked} bad={bad}")

    await env.stop()


asyncio.run(main())
print("done api batch 1d")
