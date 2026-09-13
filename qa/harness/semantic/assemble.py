import re

BASE = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/sem"
sections = ["a1","a2","a3","a4","a5","a6","a7","a8","a9","a10"]

table_rows = []
fail_sections = []
extra_notes = []

for s in sections:
    with open(f"{BASE}/results/{s}.md") as f:
        content = f.read()
    lines = content.split("\n")
    mode = "table"
    buf = []
    for line in lines:
        if line.strip() == "ENDFAIL":
            mode = "fail"
            continue
        if mode == "table":
            if line.startswith("| "):
                table_rows.append(line)
        else:
            buf.append(line)
    if buf:
        # split buf into ### sections; separate "Additional notes"/"ADDITIONAL FLAGGED DEFECT" blocks from real ### <ID> · sections
        text = "\n".join(buf).strip("\n")
        # find all top-level blocks starting with "### "
        blocks = re.split(r"\n(?=### )", text)
        for b in blocks:
            b = b.strip("\n")
            if not b:
                continue
            m = re.match(r"### ([A-Z]+-\d+)", b)
            if m:
                fail_sections.append((m.group(1), b))
            else:
                extra_notes.append(b)

print(f"table_rows: {len(table_rows)}")
print(f"fail_sections: {len(fail_sections)}")
for fid, _ in fail_sections:
    print("  ", fid)
print(f"extra_notes blocks: {len(extra_notes)}")

# write outputs
with open(f"{BASE}/assembled_table.md", "w") as f:
    f.write("\n".join(table_rows) + "\n")

with open(f"{BASE}/assembled_fails.md", "w") as f:
    for fid, b in sorted(fail_sections, key=lambda x: x[0]):
        f.write(b + "\n\n")

with open(f"{BASE}/assembled_notes.md", "w") as f:
    for b in extra_notes:
        f.write(b + "\n\n")
