"""Reconciling a PramaEstate.

An operator is two things wearing one name: a control loop that needs a cluster,
and a decision that does not. This is the decision, and it is where an operator
is dangerous — every rule below exists because the obvious reconciler does
something a bank would not accept.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prama.integrate.operator import MANAGED_BY, Verb, plan

yaml = pytest.importorskip("yaml")

CRD = Path(__file__).resolve().parents[2] / "deploy" / "operator" / "crds" / "pramaestate.yaml"


def spec(**kw):
    return {
        "tenant": kw.pop("tenant", "01TENANT"),
        "datasets": kw.pop(
            "datasets",
            [{"name": "positions_eod", "description": "EOD positions", "criticality": 1}],
        ),
    }


class TestDriftIsReportedNeverResolved:
    def test_a_person_s_declaration_is_a_conflict_not_an_overwrite(self) -> None:
        """The Kubernetes instinct is that desired state wins. Applied here it
        silently overwrites a declaration a business owner made in the console —
        the one place this product insists a human states meaning."""
        result = plan(spec(), [{"name": "positions_eod", "description": "something else"}])
        [step] = result.steps
        assert step.verb is Verb.CONFLICT
        assert "erase a statement somebody made" in step.why

    def test_the_conflicting_fields_are_named(self) -> None:
        """ "This dataset conflicts" is not something anybody can settle."""
        result = plan(
            spec(datasets=[{"name": "d", "description": "a", "criticality": 1}]),
            [{"name": "d", "description": "b", "criticality": 3}],
        )
        assert set(result.steps[0].differing) == {"description", "criticality"}

    def test_the_operator_may_amend_what_it_declared_itself(self) -> None:
        """Its own earlier output is not a person's statement."""
        result = plan(
            spec(),
            [{"name": "positions_eod", "description": "old", "managedBy": MANAGED_BY}],
        )
        assert result.steps[0].verb is Verb.AMEND

    def test_a_conflict_stops_the_resource_being_ready(self) -> None:
        """Ready over an unsettled conflict is a lie the cluster repeats every
        thirty seconds."""
        result = plan(spec(), [{"name": "positions_eod", "description": "other"}])
        assert not result.is_settled
        [condition] = result.conditions(generation=1, applied=0)
        assert condition["status"] == "False"
        assert condition["reason"] == "NeedsDecision"


class TestNothingIsEverDeleted:
    def test_a_dataset_dropped_from_the_manifest_is_orphaned_not_removed(self) -> None:
        """A manifest that stopped mentioning something is not the business
        retiring it, and deleting would take its controls and evidence with
        it."""
        result = plan(spec(datasets=[{"name": "kept"}]), [{"name": "kept"}, {"name": "gone"}])
        orphan = next(step for step in result.steps if step.dataset == "gone")
        assert orphan.verb is Verb.ORPHANED
        assert "controls and its evidence" in orphan.why

    def test_no_verb_in_the_vocabulary_deletes(self) -> None:
        """A structural guard: there is no delete to reach for."""
        assert "delete" not in {verb.value for verb in Verb}

    def test_an_orphan_also_stops_the_resource_being_ready(self) -> None:
        result = plan(spec(datasets=[{"name": "kept"}]), [{"name": "kept"}, {"name": "gone"}])
        assert not result.is_settled


class TestADeclarationIsNotAnApproval:
    def test_the_crd_carries_no_field_that_could_approve_or_suppress(self) -> None:
        """A cluster admin with kubectl must not be able to make a control
        pass — that is what an estate's approval workflow exists to prevent, and
        a CRD field would route around it entirely."""
        document = yaml.safe_load(CRD.read_text())
        rendered = repr(document)
        for forbidden in ("suppress", "approve", "verdict", "activate", "override"):
            assert forbidden not in rendered.lower(), forbidden

    def test_no_verb_activates_anything(self) -> None:
        assert {verb.value for verb in Verb} == {
            "create",
            "amend",
            "unchanged",
            "conflict",
            "orphaned",
        }


class TestThePlanIsHonestAboutWhatLanded:
    def test_planned_but_not_applied_is_not_ready(self) -> None:
        """Different from applying it and having everything succeed — and a
        condition conflating them reports Ready on a reconcile that never ran."""
        result = plan(spec(), [])
        [condition] = result.conditions(generation=1)
        assert condition["status"] == "False"
        assert condition["reason"] == "NotApplied"

    def test_a_partial_apply_is_not_ready(self) -> None:
        """Twelve of forty applied leaves twenty-eight in a state nobody
        knows."""
        result = plan(spec(datasets=[{"name": "a"}, {"name": "b"}, {"name": "c"}]), [])
        [condition] = result.conditions(generation=1, applied=1)
        assert condition["status"] == "False"
        assert condition["reason"] == "PartiallyApplied"
        assert "state nobody knows" in condition["message"]

    def test_a_full_apply_of_a_settled_plan_is_ready(self) -> None:
        result = plan(spec(), [])
        [condition] = result.conditions(generation=3, applied=len(result.writes))
        assert condition["status"] == "True"
        assert condition["observedGeneration"] == 3


class TestComparison:
    def test_an_identical_dataset_is_unchanged(self) -> None:
        result = plan(
            spec(datasets=[{"name": "d", "description": "x"}]),
            [{"name": "d", "description": "x"}],
        )
        assert result.steps[0].verb is Verb.UNCHANGED
        assert result.is_settled

    def test_a_field_the_manifest_does_not_state_is_not_a_difference(self) -> None:
        """The console holds facts a manifest never carries — an owner, a
        rhythm — and treating their absence as a difference would make every
        dataset conflict forever."""
        result = plan(
            spec(datasets=[{"name": "d", "description": "x"}]),
            [{"name": "d", "description": "x", "criticality": 2, "owner": "alice"}],
        )
        assert result.steps[0].verb is Verb.UNCHANGED

    def test_a_grain_compares_by_value_not_by_container(self) -> None:
        """A list from YAML and a tuple from the store are the same grain, and
        comparing types would conflict on every reconcile."""
        result = plan(
            spec(datasets=[{"name": "d", "grain": ["a", "b"]}]),
            [{"name": "d", "grain": ("a", "b")}],
        )
        assert result.steps[0].verb is Verb.UNCHANGED


class TestTheSummary:
    def test_conflicts_come_before_the_counts(self) -> None:
        """A summary leading with "18 unchanged" buries the only part a human
        has to act on."""
        datasets = [{"name": f"d{n}", "description": "new"} for n in range(3)]
        stored = [{"name": "d0", "description": "old"}] + [
            {"name": f"d{n}", "description": "new"} for n in (1, 2)
        ]
        described = plan(spec(datasets=datasets), stored).describe()
        assert described.index("conflict(s) needing a decision") < described.index("unchanged")

    def test_an_empty_manifest_says_so(self) -> None:
        assert "nothing to do" in plan({"tenant": "t", "datasets": []}, []).describe()

    def test_the_dictionary_form_counts_each_verb(self) -> None:
        payload = plan(spec(), []).to_dict()
        assert payload["creates"] == 1
        assert payload["conflicts"] == 0
        assert payload["settled"] is True


class TestTheCrdItself:
    def test_it_is_a_valid_custom_resource_definition(self) -> None:
        document = yaml.safe_load(CRD.read_text())
        assert document["kind"] == "CustomResourceDefinition"
        assert document["spec"]["group"] == "prama.io"
        assert document["spec"]["names"]["kind"] == "PramaEstate"

    def test_a_tenant_and_at_least_one_dataset_are_required(self) -> None:
        """A declaration with no owner is one nobody can be asked about."""
        document = yaml.safe_load(CRD.read_text())
        schema = document["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
        assert schema["properties"]["spec"]["required"] == ["tenant", "datasets"]
        assert schema["properties"]["spec"]["properties"]["datasets"]["minItems"] == 1

    def test_drift_is_a_status_field_rather_than_a_spec_one(self) -> None:
        """Reported, not configured."""
        document = yaml.safe_load(CRD.read_text())
        status = document["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"][
            "status"
        ]["properties"]
        assert "datasetsDrifted" in status
