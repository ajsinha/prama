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

    # API-002: every operation in openapi.json is callable with a minimal well-formed call
    async with env.client(env.api_key) as http:
        doc = (await http.get("/openapi.json")).json()
        bad = {}
        checked = 0
        for path, methods in doc.get("paths", {}).items():
            for method, spec in methods.items():
                if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    continue
                # substitute path params with a plausible-looking ULID; strip the /api/v1 prefix since
                # the client's base_url already carries it
                concrete_path = path.removeprefix("/api/v1")
                for param in spec.get("parameters", []):
                    if param.get("in") == "path":
                        concrete_path = concrete_path.replace("{" + param["name"] + "}", "01M2D0000000000000000000A")
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
