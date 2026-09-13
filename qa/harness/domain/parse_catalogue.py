import re, pickle

CAT = "/home/ashutosh/PycharmProjects/prama/docs/qa/catalogue/domain.md"
D = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/dom"

text = open(CAT).read()
# Split on "### ID ·" headers
blocks = re.split(r'\n### ', text)
info = {}
for block in blocks[1:]:
    m = re.match(r'([A-Z]+-\d+)\s*·\s*(.*)', block)
    if not m:
        continue
    cid, title = m.groups()
    title = title.split('\n')[0].strip()
    pm = re.search(r'\*\*Priority:\*\*\s*(P\d)', block)
    priority = pm.group(1) if pm else "?"
    em = re.search(r'\*\*Expected:\*\*\s*(.*?)(?=\n- \*\*Why|\n###|\Z)', block, re.DOTALL)
    expected = em.group(1).strip() if em else ""
    expected = re.sub(r'\s+', ' ', expected)
    area_m = re.search(r'\*\*Area:\*\*\s*(.*)', block)
    area = area_m.group(1).strip() if area_m else ""
    info[cid] = {"title": title, "priority": priority, "expected": expected, "area": area}

print(f"Parsed {len(info)} catalogue entries")
pickle.dump(info, open(f"{D}/catinfo.pkl", "wb"))

# sanity check a few
for cid in ("PCK-001","CLS-062","LIN-063","INT-043","CTR-062","IMP-055","RCN-110"):
    print(cid, info.get(cid))
