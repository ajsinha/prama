"""Curation assistants: a model drafts, a person accepts, and the person is the author.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.core.errors import ValidationError
from prama.curation.suggestions import decide
from prama.db import Database
from prama.semantic.services.datasets import DatasetService
from prama.steward import identity
from prama.steward.runner import run_task

DRAFT = "One row per trade booked. Used to reconcile the day's bookings."


async def _drafted(uow: Any, tenant_id: str, config: Any) -> tuple[str, str, Any]:
    person = uow.principals.create(tenant_id=tenant_id, username="ada", display_name="Ada")
    await uow.flush()
    await uow.llm.add_provider(
        tenant_id,
        name="local",
        kind="scripted",
        hosting="self_hosted",
        settings={"answers": [DRAFT]},
    )
    await uow.llm.set_profile(tenant_id, "curate", [("local", "qwen")])
    service = DatasetService(uow)
    _, bare = await service.declare(tenant_id=tenant_id, name="trades", criticality=4)
    await service.declare(tenant_id=tenant_id, name="books", description="Known.", criticality=4)
    steward, _ = await identity.create(uow, tenant_id, "curator", sponsor_id=str(person.id))
    goal = await uow.stewards.add_goal(
        tenant_id,
        steward.id,
        statement="describe",
        kind="curation.describe",
        inputs={},
        schedule=None,
        by=str(person.id),
    )
    task = await run_task(uow, config, tenant_id, steward, goal, key="k1")
    return str(person.id), bare.dataset_id, task


async def test_only_the_undescribed_dataset_gets_a_draft_and_nothing_is_applied(
    started_database: Database, tenant_id: str, sqlite_config: Any
) -> None:
    async with started_database.unit_of_work() as uow:
        _, dataset_id, task = await _drafted(uow, tenant_id, sqlite_config)
        (suggestion,) = await uow.stewards.suggestions(tenant_id)
        current = await uow.datasets.current(dataset_id, tenant_id=tenant_id)
    assert task.state == "succeeded" and task.output_json["drafted"] == 1
    assert suggestion.object_name == "trades" and suggestion.suggested == DRAFT
    assert current.description == ""  # a draft is not a declaration


async def test_accepting_amends_the_dataset_as_the_person_who_accepted(
    started_database: Database, tenant_id: str, sqlite_config: Any
) -> None:
    async with started_database.unit_of_work() as uow:
        person, dataset_id, _ = await _drafted(uow, tenant_id, sqlite_config)
        (suggestion,) = await uow.stewards.suggestions(tenant_id)
        row = await decide(uow, tenant_id, suggestion.id, accept=True, by=person)
        current = await uow.datasets.current(dataset_id, tenant_id=tenant_id)
    assert row.state == "accepted" and row.decided_by == person
    assert current.description == DRAFT
    assert current.authored_by == person  # the human, never the model or the steward


async def test_a_rejected_draft_changes_nothing_and_a_decision_needs_a_person(
    started_database: Database, tenant_id: str, sqlite_config: Any
) -> None:
    async with started_database.unit_of_work() as uow:
        person, dataset_id, _ = await _drafted(uow, tenant_id, sqlite_config)
        (suggestion,) = await uow.stewards.suggestions(tenant_id)
        with pytest.raises(ValidationError, match="signed-in person"):
            await decide(uow, tenant_id, suggestion.id, accept=True, by=None)
        row = await decide(uow, tenant_id, suggestion.id, accept=False, by=person)
        current = await uow.datasets.current(dataset_id, tenant_id=tenant_id)
    assert row.state == "rejected" and current.description == ""


async def test_a_draft_for_a_gap_since_filled_is_stale_not_applied(
    started_database: Database, tenant_id: str, sqlite_config: Any
) -> None:
    async with started_database.unit_of_work() as uow:
        person, dataset_id, _ = await _drafted(uow, tenant_id, sqlite_config)
        (suggestion,) = await uow.stewards.suggestions(tenant_id)
        await DatasetService(uow).amend(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            reason="owner wrote it",
            authored_by=person,
            description="Written by the owner.",
        )
        row = await decide(uow, tenant_id, suggestion.id, accept=True, by=person)
        current = await uow.datasets.current(dataset_id, tenant_id=tenant_id)
    assert row.state == "stale" and current.description == "Written by the owner."
