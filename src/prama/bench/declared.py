"""Prama itself, on the benchmark: controls derived from a declaration, run per window.

Until this existed the benchmark scored bounds and single-technique ablations
and not the system it was built to measure. This is the system's declared path:
an owner's declaration of the ``payments`` dataset, the controls the generator
derives from it, and the reference interpreter running each on every window. A
control that fails is an alert on its column in that window, scored under the
same exact-locus rule as every baseline.

**How the declaration was written, which is what makes the number worth
anything.** From the base-row schema in `prama.bench.corpus._base_row` (what
each column holds and its legitimate values), as an owner would state it, and
not from the list of defect classes. It is not revised to catch a defect it
misses: a miss is a finding, and the per-family blind spots are reported beside
the score. What it does not use is also stated: no relationships (the corpus
has one dataset), no history, and no monitors, so this is the declared path
alone, not every detector Prama has.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.bench.corpus import Corpus
from prama.bench.scoring import Alert

#: What the owner of ``payments`` declares, from the schema's documented domain.
DECLARED: dict[str, Any] = {
    "grain": ("account_id", "window"),
    "grain_statement": "one payment per account per window",
    "mandatory": ("account_id", "counterparty_id", "party_name", "iban", "currency", "amount"),
    "codelists": {
        "currency": ("GBP", "EUR", "USD"),
        "product": ("CURRENT", "SAVINGS", "LOAN"),
    },
    "semantic_types": {
        "iban": "iban",
        "country": "iso3166",
        "value_date": "iso_date",
        "booking_date": "iso_date",
    },
    "minimum": {"amount": 0.0, "rate": 0.0},
}


def declaration(dataset: str) -> Any:
    """The declaration above, as the generator reads it."""
    from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
    from prama.semantic.values import Grain, Optionality, ValueDomain, ValueDomainKind

    columns = (
        "window", "account_id", "counterparty_id", "party_name", "iban", "country", "currency",
        "product", "amount", "control_total", "rate", "value_date", "booking_date",
    )  # fmt: skip
    attributes = []
    for name in columns:
        domain = ValueDomain()
        if name in DECLARED["codelists"]:
            domain = ValueDomain(
                kind=ValueDomainKind.CODELIST, allowed_values=DECLARED["codelists"][name]
            )
        elif name in DECLARED["minimum"]:
            domain = ValueDomain(kind=ValueDomainKind.RANGE, minimum=DECLARED["minimum"][name])
        attributes.append(
            AttributeDeclaration(
                name=name,
                semantic_type=DECLARED["semantic_types"].get(name, ""),
                value_domain=domain,
                optionality=(
                    Optionality.MANDATORY if name in DECLARED["mandatory"] else Optionality.OPTIONAL
                ),
            )
        )
    return DatasetDeclaration(
        name=dataset,
        grain=Grain(attributes=DECLARED["grain"], statement=DECLARED["grain_statement"]),
        attributes=tuple(attributes),
    )


def _columns(control: Any) -> tuple[str, ...]:
    """The columns a control is about, which is where its alert points."""
    assertion: Any = control.assertion
    subject: Any = getattr(assertion, "subject", None) or getattr(assertion, "column", None)
    name = str(getattr(subject, "name", "") or "")
    if name:
        return (name,)
    columns: Any = getattr(assertion, "columns", ())
    return tuple(str(getattr(c, "name", c)) for c in columns) or ("*",)


def controls(dataset: str) -> list[tuple[Any, Any]]:
    """The derived controls, each with its plan, for the declared dataset."""
    from prama.classify.codelists import REGISTRY as CODELISTS
    from prama.derive.generator import ControlGenerator
    from prama.ir.lower import Lowerer

    generated = ControlGenerator().generate(declaration(dataset))
    lowerer = Lowerer(codelists=CODELISTS.resolve())
    return [(d.control, lowerer.control(d.control)) for d in generated.controls]


def failing(plans: list[tuple[Any, Any]], rows: list[dict[str, Any]]) -> list[Any]:
    """The controls that fail on *rows*."""
    from prama.backend.reference import ReferenceEvaluator
    from prama.ir.model import Verdict

    return [
        control
        for control, plan in plans
        if ReferenceEvaluator().run(plan, rows).verdict is Verdict.FAIL
    ]


def detect(corpus: Corpus) -> tuple[Alert, ...]:
    """Run the derived controls on every window; a failure is an alert."""
    plans = controls(corpus.dataset)
    alerts: list[Alert] = []
    for scenario in corpus.scenarios:
        for control in failing(plans, [dict(r) for r in scenario.rows]):
            for column in _columns(control):
                alerts.append(
                    Alert(
                        dataset=corpus.dataset,
                        column=column,
                        window=scenario.window,
                        detail=control.render().splitlines()[0],
                    )
                )
    return tuple(alerts)
