"""SCIM provisioning decisions.

The protocol is tedious and the decisions are not. Every test here is about a
decision where being wrong is expensive: a leaver still signed in, somebody
locked out of their own tenant, or an attestation signed by a principal that no
longer exists.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.security.oidc import ClaimMapping
from prama.security.scim import Account, Change, ScimUser, reconcile, reconcile_all

MAPPING = ClaimMapping(roles={"prama-owners": "owner", "prama-admins": "admin"})


def user(**changes) -> ScimUser:
    base = {
        "external_id": "ext-1",
        "user_name": "jsmith",
        "active": True,
        "email": "jsmith@example.com",
        "display_name": "J Smith",
        "groups": ("prama-owners",),
    }
    base.update(changes)
    return ScimUser(**base)


def account(**changes) -> Account:
    base = {
        "external_id": "ext-1",
        "user_name": "jsmith",
        "active": True,
        "email": "jsmith@example.com",
        "display_name": "J Smith",
        "roles": ("owner",),
    }
    base.update(changes)
    return Account(**base)


def decide(u: ScimUser, a: Account | None, **kwargs):
    return reconcile(u, a, mapping=MAPPING, **kwargs)


class TestNobodyIsEverDeleted:
    def test_an_inactive_user_deactivates_rather_than_deletes(self) -> None:
        """They signed things. Deleting the account leaves an attestation
        signed by a principal that does not exist, which is a hole in the audit
        trail rather than a tidy-up."""
        result = decide(user(active=False), account(), other_active_admins=1)
        assert result.change is Change.DEACTIVATE
        assert "deleting them leaves an attestation" in result.reason

    def test_there_is_no_delete_outcome_at_all(self) -> None:
        assert "DELETE" not in {member.name for member in Change}

    def test_a_deactivated_person_can_come_back(self) -> None:
        result = decide(user(), account(active=False))
        assert result.change is Change.REACTIVATE


class TestDemotionIsNotDeprovisioning:
    def test_leaving_a_group_drops_the_role_and_keeps_the_account(self) -> None:
        """A person who moved desk must not be locked out."""
        result = decide(user(groups=()), account(roles=("owner",)))
        assert result.change is Change.UPDATE
        assert result.roles == ()

    def test_leaving_the_company_deactivates(self) -> None:
        result = decide(user(active=False, groups=()), account(), other_active_admins=1)
        assert result.change is Change.DEACTIVATE

    def test_roles_are_replaced_not_merged(self) -> None:
        """A union means a role granted once is granted forever, and the group
        somebody was removed from six months ago still confers it."""
        result = decide(user(groups=("prama-admins",)), account(roles=("owner",)))
        assert result.roles == ("admin",)
        assert "owner" not in result.roles


class TestTheLastAdministrator:
    def test_deactivating_them_is_refused(self) -> None:
        """A directory misconfiguration that deactivates every admin locks
        everybody out of the tenant with no way back that does not involve the
        database."""
        result = decide(
            user(active=False, groups=("prama-admins",)),
            account(roles=("admin",)),
            other_active_admins=0,
        )
        assert result.change is Change.REFUSED
        assert "locks everybody out" in result.reason

    def test_deactivating_one_of_several_is_allowed(self) -> None:
        result = decide(
            user(active=False, groups=("prama-admins",)),
            account(roles=("admin",)),
            other_active_admins=2,
        )
        assert result.change is Change.DEACTIVATE

    def test_a_refusal_is_not_a_no_op(self) -> None:
        """Nothing changed, and something should have — the two are different
        findings."""
        result = decide(
            user(active=False, groups=("prama-admins",)),
            account(roles=("admin",)),
            other_active_admins=0,
        )
        assert not result.applies
        assert result.change is not Change.NONE

    def test_a_batch_counts_admins_once_across_the_whole_sync(self) -> None:
        """A sync deactivating three of four admins must refuse on the one that
        would leave none, not on the first one it happens to reach."""
        accounts = {
            f"ext-{n}": Account(f"ext-{n}", f"admin{n}", roles=("admin",)) for n in range(1, 5)
        }
        leavers = [
            ScimUser(external_id=f"ext-{n}", user_name=f"admin{n}", active=False)
            for n in range(1, 5)
        ]
        decisions = reconcile_all(leavers, accounts, mapping=MAPPING)
        changes = [d.change for d in decisions]
        assert changes.count(Change.DEACTIVATE) == 3
        assert changes[-1] is Change.REFUSED


class TestUnmappedGroups:
    def test_a_group_prama_does_not_map_grants_nothing(self) -> None:
        """Silently defaulting is how everybody in the directory becomes an
        owner."""
        result = decide(user(groups=("everyone",)), account(roles=()))
        assert result.roles == ()

    def test_the_unmapped_groups_are_reported(self) -> None:
        """Silently ignoring is how somebody signs in successfully and can see
        nothing, which looks exactly like a permissions bug."""
        result = decide(user(groups=("prama-owners", "everyone")), account())
        assert result.unmapped_groups == ("everyone",)


class TestPartialUpdates:
    def test_an_absent_field_does_not_blank_an_existing_one(self) -> None:
        """SCIM PATCH omits what it is not changing, and treating omission as
        deletion wipes an email address on every sync."""
        result = decide(user(email=""), account())
        assert result.change is Change.NONE

    def test_a_changed_field_is_named_with_its_old_value(self) -> None:
        """An audit record saying "3 fields changed" answers nothing."""
        result = decide(user(email="new@example.com"), account())
        assert ("email", "jsmith@example.com", "new@example.com") in result.fields

    def test_agreement_produces_no_change(self) -> None:
        assert decide(user(), account()).change is Change.NONE


class TestCreation:
    def test_somebody_the_directory_has_and_prama_does_not(self) -> None:
        result = decide(user(), None)
        assert result.change is Change.CREATE
        assert result.roles == ("owner",)

    def test_an_inactive_new_user_is_not_created(self) -> None:
        """Creating a deactivated account would put somebody in the estate who
        was never in it."""
        result = decide(user(active=False), None)
        assert result.change is Change.NONE

    def test_a_user_with_no_external_id_is_refused(self) -> None:
        """Without one this cannot be matched, and a create would make a
        duplicate on every sync."""
        result = decide(user(external_id=""), None)
        assert result.change is Change.REFUSED
        assert "duplicate on every sync" in result.reason


class TestParsingAResource:
    def test_a_scim_user_resource_is_read(self) -> None:
        parsed = ScimUser.from_resource(
            {
                "id": "ext-9",
                "userName": "arow",
                "active": True,
                "name": {"formatted": "A Roy"},
                "emails": [
                    {"value": "old@example.com"},
                    {"value": "arow@example.com", "primary": True},
                ],
                "groups": [{"display": "prama-owners", "value": "g-1"}],
            }
        )
        assert parsed.external_id == "ext-9"
        assert parsed.display_name == "A Roy"
        assert parsed.groups == ("prama-owners",)

    def test_the_primary_email_wins(self) -> None:
        """A directory sends several and only one is the one to use."""
        parsed = ScimUser.from_resource(
            {
                "id": "x",
                "userName": "u",
                "emails": [
                    {"value": "personal@example.com"},
                    {"value": "work@example.com", "primary": True},
                ],
            }
        )
        assert parsed.email == "work@example.com"

    def test_external_id_is_preferred_over_id(self) -> None:
        parsed = ScimUser.from_resource({"externalId": "ext", "id": "internal", "userName": "u"})
        assert parsed.external_id == "ext"

    def test_active_defaults_to_true_as_the_specification_says(self) -> None:
        assert ScimUser.from_resource({"id": "x", "userName": "u"}).active

    def test_a_group_given_as_a_bare_string_is_read(self) -> None:
        parsed = ScimUser.from_resource({"id": "x", "userName": "u", "groups": ["prama-owners"]})
        assert parsed.groups == ("prama-owners",)


class TestTheDecisionIsReadable:
    def test_it_describes_itself_in_a_sentence(self) -> None:
        described = decide(user(email="new@example.com"), account()).describe()
        assert "update jsmith" in described
        assert "email" in described

    def test_a_refusal_says_so_first(self) -> None:
        result = decide(user(external_id=""), None)
        assert result.describe().startswith("refused:")

    def test_the_dict_form_carries_the_reason(self) -> None:
        payload = decide(user(active=False), account(), other_active_admins=1).to_dict()
        assert payload["change"] == "deactivate"
        assert payload["reason"]


@pytest.mark.parametrize(
    "change,alters",
    [
        (Change.CREATE, True),
        (Change.UPDATE, True),
        (Change.DEACTIVATE, True),
        (Change.REACTIVATE, True),
        (Change.NONE, False),
        (Change.REFUSED, False),
    ],
)
def test_only_real_changes_alter_anything(change: Change, alters: bool) -> None:
    assert change.alters_anything is alters
