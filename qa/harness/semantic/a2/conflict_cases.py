"""SEM-110..SEM-127: ConflictDetector cases."""
import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.semantic.conflict import ConflictDetector, ConflictKind, SemanticConflict


class Attr:
    def __init__(self, attribute_id, name, **kw):
        self.attribute_id = attribute_id
        self.name = name
        self.semantic_type = kw.get("semantic_type")
        self.unit = kw.get("unit")
        self.optionality = kw.get("optionality", "optional")
        self.sensitivity = kw.get("sensitivity", "internal")
        self.value_domain_json = kw.get("value_domain_json")
        self.definition = kw.get("definition", "defined")
        self.criticality = kw.get("criticality")


det = ConflictDetector()

# SEM-110: one claimant
attrs = [Attr("a1", "lei", semantic_type="lei")]
r = det.detect("p1", "Party.LEI", attrs)
print("SEM-110:", r)

# SEM-111: zero claimants
r = det.detect("p1", "Party.LEI", [])
print("SEM-111:", r)

# SEM-112: two attrs agreeing on everything
attrs = [
    Attr("a1", "x1", semantic_type="lei", unit="EUR", optionality="mandatory",
         sensitivity="pii", value_domain_json={"kind": "codelist", "codelist_ref": "iso4217"}, definition="d"),
    Attr("a2", "x2", semantic_type="lei", unit="EUR", optionality="mandatory",
         sensitivity="pii", value_domain_json={"kind": "codelist", "codelist_ref": "iso4217"}, definition="d2"),
]
r = det.detect("p1", "P", attrs)
print("SEM-112:", r)

# SEM-113: unit mismatch EUR vs EUR_THOUSANDS
attrs = [Attr("a1", "n1", unit="EUR"), Attr("a2", "n2", unit="EUR_THOUSANDS")]
r = det.detect("p1", "Exposure.Notional", attrs)
print("SEM-113:", [(c.kind, c.severity) for c in r])

# SEM-114: semantic type mismatch lei vs bic
attrs = [Attr("a1", "n1", semantic_type="lei"), Attr("a2", "n2", semantic_type="bic")]
r = det.detect("p1", "P", attrs)
print("SEM-114:", [(c.kind, c.severity) for c in r])

# SEM-115: optionality mismatch mandatory vs optional
attrs = [Attr("a1", "n1", optionality="mandatory"), Attr("a2", "n2", optionality="optional")]
r = det.detect("p1", "P", attrs)
print("SEM-115:", [(c.kind, c.severity) for c in r])

# SEM-116: sensitivity mismatch pii vs internal
attrs = [Attr("a1", "n1", sensitivity="pii"), Attr("a2", "n2", sensitivity="internal")]
r = det.detect("p1", "P", attrs)
print("SEM-116:", [(c.kind, c.severity) for c in r])

# SEM-117: one unit=EUR, one unit=None -> no UNIT conflict
attrs = [Attr("a1", "n1", unit="EUR"), Attr("a2", "n2", unit=None)]
r = det.detect("p1", "P", attrs)
print("SEM-117:", [(c.kind, c.severity) for c in r])

# SEM-118: two attrs, tier1 & tier4 dataset criticality -- no CRITICALITY conflict, verify COMPARED dict
attrs = [Attr("a1", "n1", criticality=1), Attr("a2", "n2", criticality=4)]
r = det.detect("p1", "P", attrs)
print("SEM-118 conflicts:", [(c.kind, c.severity) for c in r])
print("SEM-118 COMPARED keys:", list(ConflictDetector.COMPARED.keys()))
print("SEM-118 COMPARED values contain CRITICALITY:", ConflictKind.CRITICALITY in ConflictDetector.COMPARED.values())
print("SEM-118 CRITICALITY severity exists:", ConflictKind.CRITICALITY.severity)

# SEM-119: two codelist domains same ref, different allowed_values spelling
attrs = [
    Attr("a1", "ccy1", value_domain_json={"kind": "codelist", "codelist_ref": "iso4217", "allowed_values": ["EUR", "USD"]}),
    Attr("a2", "ccy2", value_domain_json={"kind": "codelist", "codelist_ref": "iso4217", "allowed_values": ["USD", "EUR"]}),
]
r = det.detect("p1", "P", attrs)
print("SEM-119:", [(c.kind, c.severity) for c in r])

# SEM-120: two code lists w/ different explicit values, same/no ref
attrs = [
    Attr("a1", "s1", value_domain_json={"kind": "codelist", "allowed_values": ["BUY", "SELL"]}),
    Attr("a2", "s2", value_domain_json={"kind": "codelist", "allowed_values": ["BUY", "SELL", "CANCEL"]}),
]
r = det.detect("p1", "P", attrs)
print("SEM-120:", [(c.kind, c.severity) for c in r])

# SEM-121: ranges 0..100 vs 0..1000; patterns ^A vs ^B
attrs_range = [
    Attr("a1", "r1", value_domain_json={"kind": "range", "minimum": 0, "maximum": 100}),
    Attr("a2", "r2", value_domain_json={"kind": "range", "minimum": 0, "maximum": 1000}),
]
r_range = det.detect("p1", "P", attrs_range)
print("SEM-121 range:", [(c.kind, c.severity) for c in r_range])

attrs_pattern = [
    Attr("a1", "p1", value_domain_json={"kind": "pattern", "pattern": "^A"}),
    Attr("a2", "p2", value_domain_json={"kind": "pattern", "pattern": "^B"}),
]
r_pattern = det.detect("p1", "P", attrs_pattern)
print("SEM-121 pattern:", [(c.kind, c.severity) for c in r_pattern])

# free_text fall-through: two free_text domains must NOT conflict
attrs_free = [
    Attr("a1", "f1", value_domain_json={"kind": "free_text"}),
    Attr("a2", "f2", value_domain_json={"kind": "free_text"}),
]
r_free = det.detect("p1", "P", attrs_free)
print("SEM-121 free_text (should be no VALUE_DOMAIN conflict):", [(c.kind, c.severity) for c in r_free])

# SEM-122: three attributes on one property, one with empty definition
attrs = [
    Attr("a1", "n1", definition="real def one"),
    Attr("a2", "n2", definition="real def two"),
    Attr("a3", "n3", definition=""),
]
r = det.detect("p1", "P", attrs)
print("SEM-122:", [(c.kind, c.severity, c.values) for c in r])

# SEM-123: two attributes, both empty definitions -> no DEFINITION_ABSENT
attrs = [Attr("a1", "n1", definition=""), Attr("a2", "n2", definition="")]
r = det.detect("p1", "P", attrs)
print("SEM-123:", [(c.kind, c.severity) for c in r])

# SEM-124: one definition whitespace-only, one real
attrs = [Attr("a1", "n1", definition="   "), Attr("a2", "n2", definition="A real definition.")]
r = det.detect("p1", "P", attrs)
print("SEM-124:", [(c.kind, c.severity) for c in r])

# SEM-125: worst_severity ordering
one_of_each = [
    SemanticConflict(ConflictKind.DEFINITION_ABSENT, "p", "P", {}, {}),
    SemanticConflict(ConflictKind.OPTIONALITY, "p", "P", {}, {}),
    SemanticConflict(ConflictKind.VALUE_DOMAIN, "p", "P", {}, {}),
    SemanticConflict(ConflictKind.UNIT, "p", "P", {}, {}),
]
print("SEM-125 non-empty:", det.worst_severity(one_of_each))
print("SEM-125 empty:", det.worst_severity([]))

# SEM-126: render() - unit conflict across three attributes, two agreeing
attrs = [Attr("a3", "third", unit="EUR"), Attr("a1", "first", unit="EUR"), Attr("a2", "second", unit="USD")]
r = det.detect("p1", "Exposure.Notional", attrs)
unit_conflicts = [c for c in r if c.kind == ConflictKind.UNIT]
print("SEM-126 rendered:", unit_conflicts[0].render() if unit_conflicts else None)

# SEM-127: detect never mutates - re-read attribute objects after detect
attrs = [Attr("a1", "n1", unit="EUR"), Attr("a2", "n2", unit="USD")]
before = [(a.unit, a.definition) for a in attrs]
det.detect("p1", "P", attrs)
after = [(a.unit, a.definition) for a in attrs]
print("SEM-127 unchanged:", before == after, "no winner attr on conflict object:", not hasattr(SemanticConflict, "winner"))
