"""Data contracts over HTTP: import, export, diff, and the gate a build calls.

``prama contract check`` exits 3 on a breach. Over HTTP the same check answers
200 with ``breached: true`` — a breach is a finding, not a failed request — and
a build gates on that field. A request the check cannot make (no schema in the
contract, rows that do not parse) is refused as an error, which keeps "your
change broke the contract" apart from "the checker fell over", as the exit
codes do.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile

from prama.api.deps import ContractChecker, Reader, Uow
from prama.api.uploaded_text import text_of
from prama.contract import gate

router = APIRouter(tags=["contracts"])


def _columns(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


@router.post("/contracts/import")
async def import_contract(
    caller: ContractChecker, contract: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    """An ODCS contract read as a declaration, and what did not come across. Stores nothing."""
    name, text = await text_of(contract, "contract.json")
    return gate.imported(gate.document_from_text(text, name=name))


@router.get("/contracts/export/{dataset}")
async def export_contract(dataset: str, caller: Reader, uow: Uow) -> dict[str, Any]:
    """A declared dataset, by slug, as an ODCS contract."""
    return await gate.exported(uow, caller.tenant_id, dataset)


@router.post("/contracts/check")
async def check_contract(
    caller: ContractChecker,
    contract: Annotated[UploadFile, File()],
    data: Annotated[UploadFile, File()],
    allow_additions: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    """Whether the rows keep the contract's promises; ``breached`` is the gate."""
    contract_name, contract_text = await text_of(contract, "contract.json")
    data_name, data_text = await text_of(data, "rows.json")
    return gate.check(
        gate.document_from_text(contract_text, name=contract_name),
        gate.rows_from_text(data_text, name=data_name),
        allow_additions=allow_additions,
        contract=contract_name,
    )


@router.post("/contracts/diff")
async def diff(
    caller: ContractChecker,
    before: Annotated[UploadFile, File()],
    after: Annotated[UploadFile, File()],
    key: Annotated[str, Form()] = "",
    ignore: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    """What changed between two versions of a dataset, matched by key."""
    before_name, before_text = await text_of(before, "before.json")
    after_name, after_text = await text_of(after, "after.json")
    return gate.difference(
        gate.rows_from_text(before_text, name=before_name),
        gate.rows_from_text(after_text, name=after_name),
        key=_columns(key),
        ignore=_columns(ignore),
    )
