import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.semantic.services.base import slugify
from prama.core.errors import ValidationError

def show(label, fn):
    try:
        r = fn()
        print(f"{label}: OK -> {r!r}")
    except Exception as e:
        print(f"{label}: EXC {type(e).__name__}: {e}")

print("=== SEM-147 ===")
show("End-of-day Positions", lambda: slugify("End-of-day Positions"))
show("RISK.POSITIONS_EOD", lambda: slugify("RISK.POSITIONS_EOD"))
show("  spaced  ", lambda: slugify("  spaced  "))

print("=== SEM-148 ===")
show("Société Générale Positions", lambda: slugify("Société Générale Positions"))

print("=== SEM-149 ===")
show("---", lambda: slugify("---"))
show("住所", lambda: slugify("住所"))
show("  (two spaces)", lambda: slugify("  "))

print("=== SEM-150 ===")
name300 = "A" * 300
r = slugify(name300)
print(f"300-char name -> len={len(r)} value_prefix={r[:20]!r} value_suffix={r[-20:]!r}")

# two names differing only after character 128
base = "B" * 128
name_a = base + "XXXX"
name_b = base + "YYYY"
ra = slugify(name_a)
rb = slugify(name_b)
print(f"name_a slug len={len(ra)} == name_b slug len={len(rb)}: {ra == rb}")
print(f"ra={ra[:20]}...{ra[-10:]}  rb={rb[:20]}...{rb[-10:]}")
