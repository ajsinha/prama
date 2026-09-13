import json, os

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.jsonl")


def record(cid, result, observed):
    assert result in ("PASS", "FAIL", "BLOCKED"), (cid, result)
    observed = " ".join(str(observed).split())[:500]
    with open(RESULTS_PATH, "a") as f:
        f.write(json.dumps({"id": cid, "result": result, "observed": observed}) + "\n")
    print(f"{cid}: {result} :: {observed}")


def already_done():
    done = set()
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                done.add(json.loads(line)["id"])
    return done
