"""SEM-146: compare CONTROLS_PER_GRAIN=3 against what the Gamma generator actually
emits for grain arities 1, 2, 4 (uniqueness + one completeness per grain column)."""
import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.derive.generator import ControlGenerator
from prama.semantic.maturity import MaturityAssessor
from prama.semantic.values import Criticality, Grain


def make(grain_attrs):
    return DatasetDeclaration(
        name="t",
        slug="t",
        criticality=Criticality.TIER_1,
        declared_by="a.sinha",
        declared_at="2026-03-04T09:12:00Z",
        reference="DS01",
        grain=Grain(attributes=tuple(grain_attrs), statement="grain"),
        attributes=tuple(AttributeDeclaration(name=a) for a in grain_attrs),
    )


for arity, attrs in [(1, ["a"]), (2, ["a", "b"]), (4, ["a", "b", "c", "d"])]:
    generated = ControlGenerator().generate(make(attrs))
    grain_related = [c for c in generated.controls if c.rule.startswith("grain.")]
    print(f"arity={arity}: rules={[c.rule for c in grain_related]} count={len(grain_related)}")

print("CONTROLS_PER_GRAIN constant:", MaturityAssessor.CONTROLS_PER_GRAIN)
