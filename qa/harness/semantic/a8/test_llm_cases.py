"""IND-017..026 -- induce/llm.py"""
from __future__ import annotations

from prama.core.provenance import Origin
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.induce.llm import DEFAULT_ATTEMPTS, Inducer, Induced, retrieve
from prama.induce.validate import Gate, Rejection, Validator
from prama.llm.providers import ScriptedProvider
from prama.llm.spi import Request
from prama.pql.types import Catalogue
from prama.semantic.values import Grain, Optionality

CATALOGUE = Catalogue.of(positions={"side": "text", "qty": "number", "lei": "text"})
ROWS = [{"side": "BUY", "qty": 10, "lei": "5493001KJTIIGC8Y1R12"}] * 60


def declaration() -> DatasetDeclaration:
    return DatasetDeclaration(
        name="positions",
        purpose="the firm's end-of-day book, used for FRTB",
        grain=Grain(attributes=("lei",), statement="one row per counterparty"),
        attributes=(
            AttributeDeclaration(
                name="side",
                definition="whether the firm bought or sold",
                interpretation="always from the firm's perspective, never the client's",
                optionality=Optionality.MANDATORY,
            ),
            AttributeDeclaration(name="qty"),
            AttributeDeclaration(name="lei", semantic_type="lei"),
        ),
    )


def inducer(answers, **kwargs):
    provider = ScriptedProvider(answers, **kwargs)
    return Inducer(provider, Validator(catalogue=CATALOGUE)), provider


def sep(cid):
    print(f"\n=== {cid} ===")


# IND-017
sep("IND-017")
engine, provider = inducer(["CHECK positions.nope IS NOT NULL", "CHECK positions.qty > 0"])
outcome = engine.induce(retrieve(declaration()), "check the quantity", ROWS)
assert isinstance(outcome, Induced)
second_prompt = provider.calls[1].prompt
print("gate name present:", "type_check" in second_prompt)
print("parser message present ('nope' + not there):", "nope" in second_prompt and "not there" in second_prompt)
print("plain meaning present:", Gate.TYPE_CHECK.explains in second_prompt)
print(repr(second_prompt[-400:]))

# IND-018
sep("IND-018")
always_fail = ScriptedProvider(["nonsense"] * 10)
default_inducer = Inducer(always_fail, Validator(catalogue=CATALOGUE))
result = default_inducer.induce(retrieve(declaration()), "x", ROWS)
print("default attempts calls:", len(always_fail.calls), "(expect 3)")

zero_provider = ScriptedProvider(["nonsense"] * 10)
zero_inducer = Inducer(zero_provider, Validator(catalogue=CATALOGUE), attempts=0)
result2 = zero_inducer.induce(retrieve(declaration()), "x", ROWS)
print("attempts=0 calls:", len(zero_provider.calls), "(expect 1)")

# IND-019
sep("IND-019")
engine, provider = inducer(["NONE"])
r1 = engine.induce(retrieve(declaration()), "impossible", ROWS)
print("NONE ->", r1, "calls:", len(provider.calls), "(expect None, 1 call)")

engine2, provider2 = inducer([Request])  # placeholder, will override below
class FalseResponseProvider(ScriptedProvider):
    def complete(self, request):
        from prama.llm.spi import Response
        self.calls.append(request)
        return Response(text="", model="scripted", provider=self.name, request_fingerprint=request.fingerprint, incomplete="declined")
fp = FalseResponseProvider([])
engine3 = Inducer(fp, Validator(catalogue=CATALOGUE))
r2 = engine3.induce(retrieve(declaration()), "impossible", ROWS)
print("ok=False ->", r2, "calls:", len(fp.calls), "(expect None, 1 call)")

# IND-020
sep("IND-020")
provider020 = ScriptedProvider(["nope1", "nope2", "nope3", "nope4", "nope5", "nope6", "nope7", "nope8", "nope9"])
engine020 = Inducer(provider020, Validator(catalogue=CATALOGUE))
report = engine020.induce_all(
    [
        (retrieve(declaration()), "a"),
        (retrieve(declaration()), "b"),
        (retrieve(declaration()), "c"),
    ],
    ROWS,
)
print("rejections count:", len(report.rejections), "(expect 9)")
print("failures_by_gate:", report.failures_by_gate())

# IND-021
sep("IND-021")
answers = (
    ["CHECK positions.qty > 0"] * 2
    + ["CHECK positions.side IN ('BUY', 'SELL')"] * 4
    + ["NONE"] * 2
    + ["not pql"] * 3 * 2
)
# 10 requests: 6 induced, 2 declined, 2 rejected (need 3 attempts each for the rejected ones -> 6 calls)
requests = [(retrieve(declaration()), f"req{i}") for i in range(10)]
provider021 = ScriptedProvider(
    ["CHECK positions.qty > 0"] * 6 + ["NONE"] * 2 + ["not pql"] * 6
)
engine021 = Inducer(provider021, Validator(catalogue=CATALOGUE))
report021 = engine021.induce_all(requests, ROWS)
print("induced:", len(report021.induced), "declined:", report021.declined, "rejections:", len(report021.rejections))
print("rate:", report021.generation_failure_rate, "(expect 0.4)")
desc = report021.describe()
print("describe:", desc)
print("mentions declined separately:", "declined" in desc)

empty_report = engine021.induce_all([], ROWS)
print("zero requests rate:", empty_report.generation_failure_rate, "(expect 0.0)")

# IND-022
sep("IND-022")
constrained, _ = inducer(["CHECK positions.qty > 0"], supports_grammar=True)
loose, _ = inducer(["CHECK positions.qty > 0"], supports_grammar=False)
first = constrained.induce(retrieve(declaration()), "x", ROWS)
second = loose.induce(retrieve(declaration()), "x", ROWS)
print("constrained obs:", first.provenance.observations[0])
print("loose obs:", second.provenance.observations[0])

# IND-023
sep("IND-023")
declared = declaration()
prompt = retrieve(declared, declared.attribute("side")).render()
print("purpose present:", "the firm's end-of-day book" in prompt)
print("grain present:", "one row per counterparty" in prompt)
print("attribute definition present:", "whether the firm bought or sold" in prompt)
print("How to read it present:", "How to read it: always from the firm's perspective, never the client's" in prompt)
print(prompt)

# IND-024
sep("IND-024")
declared_pii = DatasetDeclaration(
    name="customers",
    attributes=(AttributeDeclaration(name="ssn", semantic_type="ssn"),),
)
retrieved = retrieve(declared_pii, declared_pii.attribute("ssn"))
rendered = retrieved.render()
print("no examples in retrieved:", retrieved.examples == ())
print("rendered has no 'Example values':", "Example values" not in rendered)

# IND-025
sep("IND-025")
prompt2 = retrieve(
    declaration(),
    existing=[
        "CHECK positions.side IS NOT NULL",
        "CHECK positions.qty > 0",
        "CHECK positions.lei IS VALID 'lei'",
    ],
).render()
print("has do-not-repeat block:", "do not repeat these" in prompt2)
for rule in [
    "CHECK positions.side IS NOT NULL",
    "CHECK positions.qty > 0",
    "CHECK positions.lei IS VALID 'lei'",
]:
    print(f"  contains {rule!r}:", rule in prompt2)

# IND-026
sep("IND-026")
engine026, provider026 = inducer(["CHECK positions.side IN ('BUY', 'SELL')"])
outcome026 = engine026.induce(retrieve(declaration()), "check the side is valid", ROWS)
prov = outcome026.provenance
print("origin:", prov.origin)
print("source_ref:", prov.source_ref)
print("observations:", prov.observations)
print("names provider:", "scripted" in prov.observations[0])
print("names gates passed:", "5 gates" in prov.observations[1] or "gates" in prov.observations[1])
print("names probes caught:", "value_probes" not in prov.observations[1] and "caught" in prov.observations[1])

print("\nDONE")
