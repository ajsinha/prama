"""IND-027..035 -- induce/documents.py"""
from __future__ import annotations

from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.induce.documents import Document, DocumentInducer, MINIMUM_PASSAGE, stale_citations
from prama.induce.llm import retrieve
from prama.induce.validate import Validator
from prama.llm.providers import ScriptedProvider
from prama.pql.types import Catalogue

TEXT = """\
Schedule H.1 Corporate Loan Data

This schedule collects loan-level data for the corporate portfolio.

Field 23 Obligor LEI. The reporting entity must report the legal entity
identifier of the obligor. This field shall not be left blank for any
outstanding facility.

Field 24 Obligor Name. The name of the obligor as recorded in the reporting
entity's systems. This is provided for reconciliation purposes.
"""

CATALOGUE = Catalogue.of(loans={"obligor_lei": "text", "obligor_name": "text"})
ROWS = [{"obligor_lei": "5493001KJTIIGC8Y1R12", "obligor_name": "X"}] * 60


def declaration():
    return DatasetDeclaration(
        name="loans",
        attributes=(
            AttributeDeclaration(name="obligor_lei", semantic_type="lei"),
            AttributeDeclaration(name="obligor_name"),
        ),
    )


def document():
    return Document(name="FR Y-14Q instructions", text=TEXT, reference="fry14q-2026")


def inducer(answers):
    return DocumentInducer(ScriptedProvider(answers), Validator(catalogue=CATALOGUE))


def sep(cid):
    print(f"\n=== {cid} ===")


# IND-027
sep("IND-027")
paraphrase_answer = (
    "QUOTE: Obligors must report a valid legal entity identifier at all times.\n"
    "CONTROL: CHECK loans.obligor_lei IS NOT NULL"
)
report = inducer([paraphrase_answer]).extract(document(), retrieve(declaration()), ROWS)
print("extracted:", len(report.extracted), "(expect 0)")
print("fabricated_quotes:", report.fabricated_quotes, "(expect 1)")

# IND-028
sep("IND-028")
reflowed = (
    "QUOTE: This field shall   not be left\n  blank for any outstanding facility.\n"
    "CONTROL: CHECK loans.obligor_lei IS NOT NULL"
)
report_r = inducer([reflowed]).extract(document(), retrieve(declaration()), ROWS)
print("reflowed extracted:", len(report_r.extracted), "(expect 1, matched)")

changed_word = (
    "QUOTE: This field shall not be left blank for any outstanding transaction.\n"
    "CONTROL: CHECK loans.obligor_lei IS NOT NULL"
)
report_c = inducer([changed_word]).extract(document(), retrieve(declaration()), ROWS)
print("changed-word extracted:", len(report_c.extracted), "(expect 0, not matched)")
print("changed-word fabricated:", report_c.fabricated_quotes, "(expect 1)")

# IND-029
sep("IND-029")
mixed_answers = [
    "QUOTE: This field shall not be left blank for any outstanding facility.\n"
    "CONTROL: CHECK loans.obligor_lei IS NOT NULL",
    "QUOTE: invented passage that is not real.\nCONTROL: CHECK loans.obligor_name IS NOT NULL",
]
# document has only 1 normative passage, so to get "ten normative, two fabricated"
# we build a synthetic document with ten normative passages.
passages_text = "\n\n".join(
    f"Field {i} X. The reporting entity must report field {i}." for i in range(1, 11)
)
big_doc = Document(name="synthetic", text=passages_text, reference="synthetic-1")
answers = []
for i in range(1, 11):
    if i <= 2:
        answers.append(f"QUOTE: a fabricated sentence about field {i}.\nCONTROL: CHECK loans.obligor_lei IS NOT NULL")
    else:
        answers.append(
            f"QUOTE: The reporting entity must report field {i}.\nCONTROL: CHECK loans.obligor_lei IS NOT NULL"
        )
report_big = inducer(answers).extract(big_doc, retrieve(declaration()), ROWS)
print("considered:", report_big.considered, "(expect 10)")
print("fabricated_quotes:", report_big.fabricated_quotes, "(expect 2)")
print("fabrication_rate:", report_big.fabrication_rate, "(expect 0.2)")
print("describe:", report_big.describe())

zero_doc = Document(name="empty", text="Just a description with no obligation words at all here, at all.", reference="e")
zero_report = inducer([]).extract(zero_doc, retrieve(declaration()), ROWS)
print("zero considered rate:", zero_report.fabrication_rate, "(expect 0.0)")

# IND-030
sep("IND-030")
provider30 = ScriptedProvider(
    ["QUOTE: This field shall not be left blank for any outstanding facility.\nCONTROL: CHECK loans.obligor_lei IS NOT NULL"]
)
di = DocumentInducer(provider30, Validator(catalogue=CATALOGUE))
report30 = di.extract(document(), retrieve(declaration()), ROWS)
print("provider calls:", len(provider30.calls), "(expect 1, one call per normative passage)")
print("considered:", report30.considered, "(expect 1)")

# IND-031
sep("IND-031")
short_heading = "X" * 34 + " must"  # 39 chars total
assert len(short_heading) == 39, len(short_heading)
long_enough = "Y" * 35 + " must"  # 40 chars total
assert len(long_enough) == 40, len(long_enough)
third_block = "Another paragraph without a recognised heading that must be reported."
doc31 = Document(name="d31", text=f"{short_heading}\n\n{long_enough}\n\n{third_block}", reference="r")
passages = list(doc31.passages())
print("num passages:", len(passages), "(expect 2: the 39-char one is skipped)")
for p in passages:
    print("  ", repr(p.text[:50]), "locator:", p.locator)
print("short (39-char) one skipped:", not any(p.text.startswith("X" * 10) for p in passages))
print("second block (index 2) locator == 'paragraph 2':", passages[0].locator == "paragraph 2")
print("third block (index 3) locator == 'paragraph 3' (index advanced past the skip):", passages[1].locator == "paragraph 3")
print("MINIMUM_PASSAGE:", MINIMUM_PASSAGE)

# IND-032
sep("IND-032")
doc32_text = (
    "Schedule H.1 something here that is over forty characters long for sure.\n\n"
    "Field 23 something here that is over forty characters long for the check.\n\n"
    "3.2.1 something here that is over forty characters long as well indeed.\n\n"
    "No heading at all just a plain paragraph that runs long enough to count here."
)
doc32 = Document(name="d32", text=doc32_text, reference="r")
locators = [p.locator for p in doc32.passages()]
print("locators:", locators)

# IND-033
sep("IND-033")
no_quote_answer = "CHECK loans.obligor_lei IS NOT NULL"
report33 = inducer([no_quote_answer]).extract(document(), retrieve(declaration()), ROWS)
print("extracted:", len(report33.extracted), "(expect 0)")
print("rejections:", len(report33.rejections))
if report33.rejections:
    print("gate:", report33.rejections[0].gate)
    print("detail:", report33.rejections[0].detail)

# IND-034
sep("IND-034")
curly_answer = (
    "QUOTE: “This field shall not be left blank for any outstanding facility.”\n"
    "CONTROL: CHECK loans.obligor_lei IS NOT NULL"
)
report34 = inducer([curly_answer]).extract(document(), retrieve(declaration()), ROWS)
print("extracted with curly quotes:", len(report34.extracted), "(expect 1)")

# IND-035
sep("IND-035")
answer35 = (
    "QUOTE: This field shall not be left blank for any outstanding facility.\n"
    "CONTROL: CHECK loans.obligor_lei IS NOT NULL"
)
report35 = inducer([answer35]).extract(document(), retrieve(declaration()), ROWS)
edited_doc = Document(
    name="FR Y-14Q instructions",
    text=TEXT + "\n\nField 25 has been added and is new.",
    reference="fry14q-2026",
)
stale = stale_citations(report35.extracted, edited_doc)
print("stale (edited doc) count:", len(stale), "(expect 1, all rules from that doc)")
different_doc = Document(name="A different document", text=TEXT, reference="different")
stale_diff = stale_citations(report35.extracted, different_doc)
print("stale (different doc name) count:", len(stale_diff), "(expect 0)")
unchanged = stale_citations(report35.extracted, document())
print("stale (same doc unchanged) count:", len(unchanged), "(expect 0)")

print("\nDONE")
