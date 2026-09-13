import re, os, pickle, glob

D = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/dom"

scripts = sorted(glob.glob(f"{D}/*.py"))
scripts = [s for s in scripts if os.path.basename(s) not in ("compile.py","parse_catalogue.py","extract_repro.py")]

repro = {}  # id -> (script_basename, code_snippet)

block_re = re.compile(r'@block\("([A-Z]+-\d+)"\)\ndef _\(\):\n((?:    .*\n|\n)*)')

for path in scripts:
    src = open(path).read()
    for m in block_re.finditer(src):
        cid = m.group(1)
        body = m.group(2)
        # dedent
        lines = [l[4:] if l.startswith('    ') else l for l in body.splitlines()]
        code = "\n".join(lines).rstrip()
        repro[cid] = (os.path.basename(path), code)

print(f"Extracted repro snippets for {len(repro)} case ids")
pickle.dump(repro, open(f"{D}/repro.pkl","wb"))

# spot check
for cid in ("PCK-043","CLS-062","LIN-009","INT-041"):
    if cid in repro:
        print("===", cid, repro[cid][0], "===")
        print(repro[cid][1][:300])
    else:
        print(cid, "NOT FOUND")
