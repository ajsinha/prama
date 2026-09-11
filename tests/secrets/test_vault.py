"""The Vault provider, and the four ways a KV v2 read looks fine and is not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.secrets.reference import SecretRef
from prama.secrets.spi import SecretProviderUnavailableError, SecretResolutionError
from prama.secrets.vault import ReadResult, VaultSecretProvider
from prama.security.egress import Gate, ResidencyRefused

REF = SecretRef.parse("vault://secret/data/prama/db#password")


def body(fields: dict | None = None, **metadata) -> dict:
    meta = {"version": 3, "destroyed": False, "deletion_time": ""}
    meta.update(metadata)
    return {"data": {"data": fields, "metadata": meta}}


def provider(response: dict, **kwargs) -> VaultSecretProvider:
    return VaultSecretProvider(transport=lambda _path, _token: response, token="s.abc", **kwargs)


class TestTheEnvelope:
    def test_it_reads_the_inner_data_not_the_outer(self) -> None:
        """The outer `data` is version numbers and timestamps. It is not the
        secret and does not look like an error either."""
        value = provider(body({"password": "hunter2"})).resolve(REF)
        assert value.reveal() == "hunter2"

    def test_the_metadata_is_not_mistaken_for_fields(self) -> None:
        result = ReadResult.from_body(body({"password": "x"}))
        assert dict(result.fields) == {"password": "x"}
        assert result.version == 3

    def test_a_body_of_the_wrong_shape_is_not_readable(self) -> None:
        assert not ReadResult.from_body({"data": "nonsense"}).is_readable
        assert not ReadResult.from_body({}).is_readable


class TestEmptyIsNeverAValue:
    def test_a_soft_deleted_version_is_refused(self) -> None:
        """Vault returns it with empty data and no HTTP error. Reading the
        empty data hands back an empty string, which reaches the driver as an
        authentication failure and sends somebody to check a password that was
        never read."""
        with pytest.raises(SecretResolutionError, match="was deleted at"):
            provider(body({}, deletion_time="2026-09-01T00:00:00Z")).resolve(REF)

    def test_a_destroyed_version_is_refused(self) -> None:
        with pytest.raises(SecretResolutionError, match="has been destroyed"):
            provider(body({}, destroyed=True)).resolve(REF)

    def test_a_path_holding_nothing_is_refused(self) -> None:
        with pytest.raises(SecretResolutionError, match="holds no data"):
            provider(body({})).resolve(REF)

    def test_an_empty_field_is_refused(self) -> None:
        """Almost always a half-finished write."""
        with pytest.raises(SecretResolutionError, match="is empty"):
            provider(body({"password": ""})).resolve(REF)

    def test_a_null_field_is_refused(self) -> None:
        with pytest.raises(SecretResolutionError, match="is empty"):
            provider(body({"password": None})).resolve(REF)


class TestNamingTheField:
    def test_a_reference_with_no_field_is_refused(self) -> None:
        """A KV v2 secret is a document, and guessing which field is the
        credential is how a username gets used as a password."""
        ref = SecretRef.parse("vault://secret/data/prama/db")
        with pytest.raises(SecretResolutionError, match="names none"):
            provider(body({"username": "prama", "password": "hunter2"})).resolve(ref)

    def test_an_absent_field_lists_the_names_that_are_there(self) -> None:
        """The names are not the values, and they are what makes this fixable
        in one step."""
        ref = SecretRef.parse("vault://secret/data/prama/db#secret")
        with pytest.raises(SecretResolutionError) as caught:
            provider(body({"username": "prama", "password": "hunter2"})).resolve(ref)
        assert "password, username" in caught.value.remedy

    def test_the_error_never_carries_the_value(self) -> None:
        ref = SecretRef.parse("vault://secret/data/prama/db#nope")
        with pytest.raises(SecretResolutionError) as caught:
            provider(body({"password": "hunter2"})).resolve(ref)
        rendered = f"{caught.value.message} {caught.value.remedy} {caught.value.context}"
        assert "hunter2" not in rendered


class TestConfiguration:
    def test_a_provider_with_no_transport_is_unavailable(self) -> None:
        assert not VaultSecretProvider(token="s.abc").available()

    def test_a_provider_with_no_token_is_unavailable(self) -> None:
        """The token is itself a credential, given as a reference and not a
        literal — so an unconfigured one is the normal state, not a bug."""
        assert not VaultSecretProvider(transport=lambda _p, _t: {}).available()

    def test_resolving_without_configuration_says_what_to_set(self) -> None:
        with pytest.raises(SecretProviderUnavailableError) as caught:
            VaultSecretProvider().resolve(REF)
        assert "env://VAULT_TOKEN" in caught.value.remedy

    def test_the_resolver_relays_the_providers_own_reason(self) -> None:
        """The resolver knows a provider said no; only the provider knows which
        setting is missing. "Check its configuration" sends somebody looking
        for a plugin that is already installed."""
        from prama.secrets import default_resolver

        with pytest.raises(SecretResolutionError) as caught:
            default_resolver().resolve("vault://secret/data/x#password")
        assert "env://VAULT_TOKEN" in caught.value.remedy

    def test_the_reason_names_only_what_is_actually_missing(self) -> None:
        partial = VaultSecretProvider(transport=lambda _p, _t: {})
        assert "no token reference" in partial.unavailable_remedy()
        assert "no transport" not in partial.unavailable_remedy()

    def test_a_transport_failure_is_translated(self) -> None:
        """An expired Vault token fails exactly like a wrong path, and the
        message says so."""

        def boom(path: str, token: str) -> dict:
            raise ConnectionError("refused")

        bad = VaultSecretProvider(transport=boom, token="s.abc")
        with pytest.raises(SecretResolutionError, match="did not answer"):
            bad.resolve(REF)

    def test_the_path_is_passed_through_as_written(self) -> None:
        """Inserting `data/` silently would be convenient and would break every
        deployment whose mount is not called `secret`."""
        seen = {}

        def record(path: str, token: str) -> dict:
            seen["path"] = path
            return body({"password": "x"})

        VaultSecretProvider(transport=record, token="s.abc").resolve(REF)
        assert seen["path"] == "secret/data/prama/db"


class TestItIsAnEgress:
    def test_a_vault_outside_the_residency_is_refused(self) -> None:
        """A secret store in the wrong region is a data movement like any
        other."""
        gate = Gate.for_tenant("EU", tenant_id="t1")
        with pytest.raises(ResidencyRefused):
            provider(body({"password": "x"}), region="US", gate=gate).resolve(REF)

    def test_an_in_region_vault_is_read(self) -> None:
        gate = Gate.for_tenant("EU", tenant_id="t1")
        value = provider(body({"password": "x"}), region="EU", gate=gate).resolve(REF)
        assert value.reveal() == "x"

    def test_without_a_gate_nothing_changes(self) -> None:
        assert provider(body({"password": "x"})).resolve(REF).reveal() == "x"


class TestTheSpiContract:
    def test_it_declares_its_scheme_and_describes_itself(self) -> None:
        entry = VaultSecretProvider().describe()
        assert entry["scheme"] == "vault"
        assert entry["description"]
        assert entry["available"] == "no"

    def test_the_value_records_where_it_came_from_not_what_it_is(self) -> None:
        value = provider(body({"password": "hunter2"})).resolve(REF)
        assert "hunter2" not in value.origin
        assert "vault://" in value.origin
