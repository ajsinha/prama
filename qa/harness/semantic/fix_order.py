import re

BASE = "."
order = {"SEM":0, "DER":1, "PRP":2, "IND":3, "MIN":4, "ER":5}

def sort_key(fid):
    prefix, num = fid.split("-")
    return (order[prefix], int(num))

blocks = []
with open(f"{BASE}/assembled_fails.md") as f:
    text = f.read()
parts = re.split(r"\n(?=### )", text.strip("\n"))
for p in parts:
    p = p.strip("\n")
    if not p:
        continue
    m = re.match(r"### ([A-Z]+-\d+)", p)
    blocks.append((sort_key(m.group(1)), m.group(1), p))

blocks.sort(key=lambda x: x[0])
with open(f"{BASE}/assembled_fails_ordered.md", "w") as f:
    for _, fid, p in blocks:
        f.write(p + "\n\n")
print([fid for _,fid,_ in blocks])
