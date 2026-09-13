import os
RESULTS_PATH = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust/results.tsv"

def line(id_, result, obs):
    obs = str(obs).replace("\t", " ").replace("\n", " \\n ")
    row = f"{id_}\t{result}\t{obs}"
    print(row)
    with open(RESULTS_PATH, "a") as f:
        f.write(row + "\n")
