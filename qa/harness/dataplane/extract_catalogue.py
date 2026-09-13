import re, json

text = open("/home/ashutosh/PycharmProjects/prama/docs/qa/catalogue/dataplane.md").read()
# Split into case blocks by "### ID · Title"
pattern = re.compile(r"^### (?P<id>[A-Z]+-\d+) · (?P<title>.+)$", re.M)
matches = list(pattern.finditer(text))
cases = {}
for i, m in enumerate(matches):
    start = m.end()
    end = matches[i+1].start() if i+1 < len(matches) else len(text)
    body = text[start:end]
    priority = re.search(r"\*\*Priority:\*\*\s*(P\d)", body)
    expected = re.search(r"\*\*Expected:\*\*\s*(.+?)(?=\n- \*\*Why|\Z)", body, re.S)
    cases[m.group("id")] = {
        "title": m.group("title").strip(),
        "priority": priority.group(1) if priority else "P?",
        "expected": (expected.group(1).strip().replace("\n", " ") if expected else ""),
    }

with open("catalogue_meta.json", "w") as f:
    json.dump(cases, f, indent=2)
print(f"extracted {len(cases)} cases")
print(list(cases.items())[:2])
