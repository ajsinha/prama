"""The shipped obligations: BCBS 239, and the payment-message regimes.

Deliberately small and deliberately cited. A catalogue of four hundred
obligations nobody has read is worth less than a dozen whose provenance survives
being asked about — and "show me where this comes from" is the follow-up to
every finding an examiner makes.

The anchor is BCBS 239 principles 3, 4 and 5. Those three are the ones a data
quality control can actually discharge: accuracy, completeness and timeliness
are testable properties of data. Principles 1, 2 and 7 to 14 are about
governance, architecture and reporting — Prama supports them with its ownership
model, its estate map and its attestation pack, and *claiming them as controls
would be a lie*, so they are absent here rather than represented by a template
that checks nothing.

Every template carries placeholders rather than column names, so one entry
serves four banks whose warehouses agree about nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.packs.banking.regulatory import Catalogue, Citation, Obligation, Template

BCBS_239 = "BCBS 239"
ISO_20022 = "ISO 20022 payments"

_BCBS = "Principles for effective risk data aggregation and risk reporting"


def _cite(clause: str, document: str = _BCBS, authority: str = "BCBS") -> Citation:
    return Citation(document=document, clause=clause, authority=authority)


OBLIGATIONS: tuple[Obligation, ...] = (
    # -- P3 Accuracy and integrity -----------------------------------------
    Obligation(
        identity="BCBS239-P3-CDE-COMPLETE",
        regime=BCBS_239,
        principle="P3",
        citation=_cite("Principle 3, paragraph 36"),
        objective=(
            "Every critical data element used in risk reporting has a value. A "
            "figure aggregated over rows with missing drivers is wrong by an "
            "amount nobody can state."
        ),
        templates=(
            Template(
                identity="cde-not-null",
                pql=(
                    "CHECK {dataset}.{attribute} IS NOT NULL "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'a critical data element used in risk aggregation'"
                ),
                requires=("dataset", "attribute"),
                dimension="completeness",
            ),
        ),
    ),
    Obligation(
        identity="BCBS239-P3-GRAIN-UNIQUE",
        regime=BCBS_239,
        principle="P3",
        citation=_cite("Principle 3, paragraph 37"),
        objective=(
            "One row per thing. A duplicated position is counted twice in every "
            "aggregate built on it, and no downstream total reveals it."
        ),
        templates=(
            Template(
                identity="grain-unique",
                pql=(
                    "CHECK {dataset} HAS UNIQUE KEY ({grain}) "
                    "SEVERITY critical DIMENSION uniqueness "
                    "BECAUSE 'the declared grain of the dataset'"
                ),
                requires=("dataset", "grain"),
                dimension="uniqueness",
            ),
        ),
    ),
    Obligation(
        identity="BCBS239-P3-RECONCILED",
        regime=BCBS_239,
        principle="P3",
        citation=_cite("Principle 3, paragraph 38"),
        objective=(
            "Risk data reconciles to the accounting records. Two systems that "
            "have never been compared agree only by assumption."
        ),
        templates=(
            Template(
                identity="reconciles-with",
                pql=(
                    "CHECK {dataset} SATISFIES {measure} = {counterpart_measure} "
                    "SEVERITY critical DIMENSION consistency "
                    "BECAUSE 'risk data must reconcile to the accounting record'"
                ),
                requires=("dataset", "measure", "counterpart_measure"),
                dimension="consistency",
            ),
        ),
    ),
    # -- P4 Completeness ----------------------------------------------------
    Obligation(
        identity="BCBS239-P4-POPULATION",
        regime=BCBS_239,
        principle="P4",
        citation=_cite("Principle 4, paragraph 42"),
        objective=(
            "All material risk is captured. A population short by one book is a "
            "report that is confidently wrong rather than visibly incomplete."
        ),
        templates=(
            Template(
                identity="row-count-plausible",
                pql=(
                    "CHECK {dataset} HAS ROW COUNT BETWEEN {minimum} AND {maximum} "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'the population must cover all material risk'"
                ),
                requires=("dataset", "minimum", "maximum"),
                dimension="completeness",
                note=(
                    "A range, not a floor. A population that doubled overnight is "
                    "as much a defect as one that halved, and only one of those "
                    "is caught by a minimum."
                ),
            ),
        ),
    ),
    Obligation(
        identity="BCBS239-P4-REFERENTIAL",
        regime=BCBS_239,
        principle="P4",
        citation=_cite("Principle 4, paragraph 43"),
        objective=(
            "Every exposure names a counterparty that exists. An orphan is "
            "excluded from every aggregation that joins, silently."
        ),
        templates=(
            Template(
                identity="references",
                pql=(
                    "CHECK {dataset}.{attribute} REFERENCES {target_dataset}.{target_attribute} "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'an exposure whose counterparty is absent is dropped by every join'"
                ),
                requires=("dataset", "attribute", "target_dataset", "target_attribute"),
                dimension="completeness",
            ),
        ),
    ),
    # -- P5 Timeliness ------------------------------------------------------
    Obligation(
        identity="BCBS239-P5-FRESH",
        regime=BCBS_239,
        principle="P5",
        citation=_cite("Principle 5, paragraph 47"),
        objective=(
            "Risk data is available when the report is produced, including "
            "during a stress period — which is when it is late."
        ),
        templates=(
            Template(
                identity="freshness",
                pql=(
                    "CHECK {dataset} IS FRESH WITHIN {window} "
                    "SEVERITY critical DIMENSION timeliness "
                    "BECAUSE 'a stale figure is indistinguishable from a current one'"
                ),
                requires=("dataset", "window"),
                dimension="timeliness",
                cadence="hourly",
            ),
        ),
    ),
    # -- ISO 20022 payments -------------------------------------------------
    Obligation(
        identity="ISO20022-IBAN-BIC",
        regime=ISO_20022,
        principle="",
        citation=Citation(
            document="CBPR+ Usage Guidelines",
            clause="pacs.008 creditor agent",
            authority="Swift",
        ),
        objective=(
            "A payment's account and its agent name the same country. Both "
            "identifiers are individually valid when they disagree, and the "
            "money goes to a bank that does not hold the account."
        ),
        templates=(
            Template(
                identity="iban-bic-consistent",
                pql=(
                    "CHECK {dataset} SATISFIES IBAN_BIC_CONSISTENT({iban}, {bic}) "
                    "SEVERITY critical DIMENSION consistency "
                    "BECAUSE 'the account country and the agent country must agree'"
                ),
                requires=("dataset", "iban", "bic"),
                dimension="consistency",
            ),
        ),
    ),
    Obligation(
        identity="ISO20022-CONTROL-SUM",
        regime=ISO_20022,
        principle="",
        citation=Citation(
            document="ISO 20022 pacs.008",
            clause="GrpHdr/CtrlSum",
            authority="ISO",
        ),
        objective=(
            "What the file claims it contains is what it contains. A truncated "
            "batch whose every remaining transaction is valid is invisible to "
            "any per-transaction check."
        ),
        templates=(
            Template(
                identity="control-sum-agrees",
                pql=(
                    "CHECK {dataset} SATISFIES {control_sum} = {transaction_total} "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'the stated control total must equal what arrived'"
                ),
                requires=("dataset", "control_sum", "transaction_total"),
                dimension="completeness",
            ),
        ),
    ),
    Obligation(
        identity="ISO20022-MINOR-UNITS",
        regime=ISO_20022,
        principle="",
        citation=Citation(document="ISO 4217", clause="list one, minor unit", authority="ISO"),
        objective=(
            "An amount's scale suits its currency. A yen amount with two "
            "decimal places is a number no yen amount can take, and every sum "
            "built on it inherits the error."
        ),
        templates=(
            Template(
                identity="minor-units-ok",
                pql=(
                    "CHECK {dataset} SATISFIES MINOR_UNITS_OK({amount}, {currency}) "
                    "SEVERITY major DIMENSION accuracy "
                    "BECAUSE 'the amount scale must suit the currency'"
                ),
                requires=("dataset", "amount", "currency"),
                dimension="accuracy",
            ),
        ),
    ),
)

#: BCBS 239 principles this pack claims to *discharge with controls*.
#:
#: Three of fourteen, and stating the number is the point. Principles 1, 2 and
#: 7 to 14 are governance, architecture and reporting obligations; Prama
#: supports them with its ownership model, estate map and attestation pack, and
#: representing them here as templates that check nothing would be a claim the
#: product cannot defend at an examination.
DISCHARGEABLE_PRINCIPLES = ("P3", "P4", "P5")

#: What the pack supports without a control discharging it, so a coverage report
#: can say so rather than leave a reader to infer it from an absence.
SUPPORTED_NOT_DISCHARGED = {
    "P1": "governance — ownership, approval, segregation of duties, attestation, audit trail",
    "P2": "architecture — estate map, semantic layer, lineage, connector inventory",
    "P6": "adaptability — ad-hoc authoring and on-demand re-examination",
    "P7": "reporting accuracy — scorecards built from evidence",
    "P12": "supervisory review — auditor role, evidence export, deterministic replay",
}


def catalogue() -> Catalogue:
    return Catalogue(OBLIGATIONS)


__all__ = [
    "BCBS_239",
    "DISCHARGEABLE_PRINCIPLES",
    "ISO_20022",
    "OBLIGATIONS",
    "SUPPORTED_NOT_DISCHARGED",
    "catalogue",
]
