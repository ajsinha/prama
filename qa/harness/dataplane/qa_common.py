import json, os

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.jsonl")

def log(id_, result, observed):
    with open(RESULTS_PATH, "a") as f:
        f.write(json.dumps({"id": id_, "result": result, "observed": str(observed)}) + "\n")
    print(f"{id_}: {result} :: {observed}")
