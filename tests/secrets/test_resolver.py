"""References in, values out — and a record that it happened.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from prama.core.clock import Clock
from prama.core.errors import ValidationError
from prama.secrets import (
    EnvironmentSecretProvider,
    FileSecretProvider,
    MemorySecretProvider,
    SecretAccess,
    SecretRef,
    SecretResolutionError,
    SecretResolver,
    default_resolver,
)


class MovableClock(Clock):
    def __init__(self) -> None:
        self._now = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return 0.0

    def epoch_millis(self) -> int:
        return int(self._now.timestamp() * 1000)


class TestReferences:
    def test_a_reference_names_a_scheme_and_a_location(self) -> None:
        ref = SecretRef.parse("env://PRAMA_PG_PASSWORD")
        assert (ref.scheme, ref.location, ref.key) == ("env", "PRAMA_PG_PASSWORD", "")

    def test_a_fragment_names_one_field_of_a_document(self) -> None:
        # Most vaults store a JSON document per path, not a bare string.
        ref = SecretRef.parse("hashicorp://secret/data/prod/warehouse#password")
        assert ref.location == "secret/data/prod/warehouse"
        assert ref.key == "password"
        assert ref.render() == "hashicorp://secret/data/prod/warehouse#password"

    def test_a_pasted_password_is_refused_with_advice_not_stored(self) -> None:
        with pytest.raises(ValidationError) as caught:
            SecretRef.parse("hunter2")
        assert "will not keep a credential" in caught.value.remedy

    def test_the_error_for_a_bad_reference_does_not_echo_it_back(self) -> None:
        # The offending text may *be* the password somebody pasted, and this
        # error gets logged.
        pasted = "s3cr3t-pa55w0rd"
        with pytest.raises(ValidationError) as caught:
            SecretRef.parse(pasted)
        assert pasted not in str(caught.value)
        assert pasted not in str(caught.value.context)

    def test_a_scheme_with_no_location_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="names no location"):
            SecretRef.parse("env://")

    def test_try_parse_returns_none_rather_than_raising(self) -> None:
        assert SecretRef.try_parse("not a reference") is None
        assert SecretRef.try_parse(None) is None
        assert SecretRef.try_parse("env://X") is not None


class TestEnvironmentProvider:
    def test_it_reads_the_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PRAMA_TEST_SECRET", "opensesame")
        value = EnvironmentSecretProvider().resolve(SecretRef.parse("env://PRAMA_TEST_SECRET"))
        assert value.reveal() == "opensesame"
        assert value.origin == "env://PRAMA_TEST_SECRET"

    def test_an_unset_variable_says_where_to_set_it(self) -> None:
        with pytest.raises(SecretResolutionError) as caught:
            EnvironmentSecretProvider().resolve(SecretRef.parse("env://PRAMA_NOT_SET_ANYWHERE"))
        assert "deployment manifest" in caught.value.remedy

    def test_a_field_can_be_taken_from_a_json_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRAMA_TEST_DOC", json.dumps({"user": "prama", "password": "pw"}))
        ref = SecretRef.parse("env://PRAMA_TEST_DOC#password")
        assert EnvironmentSecretProvider().resolve(ref).reveal() == "pw"

    def test_a_missing_field_lists_the_ones_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PRAMA_TEST_DOC", json.dumps({"user": "prama"}))
        with pytest.raises(SecretResolutionError) as caught:
            EnvironmentSecretProvider().resolve(SecretRef.parse("env://PRAMA_TEST_DOC#password"))
        assert "user" in caught.value.remedy


class TestFileProvider:
    def test_it_reads_a_mounted_secret(self, tmp_path: Path) -> None:
        (tmp_path / "pg_password").write_text("from-the-mount\n")
        provider = FileSecretProvider(root=str(tmp_path))
        assert provider.resolve(SecretRef.parse("file:///pg_password")).reveal() == (
            "from-the-mount"
        )

    def test_a_trailing_newline_is_not_part_of_the_password(self, tmp_path: Path) -> None:
        # echo, kubectl and every editor add one. Including it produces an
        # authentication failure that looks like a wrong password.
        (tmp_path / "s").write_text("value\n")
        provider = FileSecretProvider(root=str(tmp_path))
        assert provider.resolve(SecretRef.parse("file:///s")).reveal() == "value"

    def test_a_reference_cannot_escape_the_secrets_directory(self, tmp_path: Path) -> None:
        # A reference is a stored value an authenticated user can edit. Without
        # a root it would be a way to read any file the process can read.
        (tmp_path / "secrets").mkdir()
        (tmp_path / "elsewhere").write_text("not a secret")
        provider = FileSecretProvider(root=str(tmp_path / "secrets"))
        with pytest.raises(SecretResolutionError) as caught:
            provider.resolve(SecretRef.parse("file:///../elsewhere"))
        assert "outside the configured secrets directory" in str(caught.value)

    def test_a_missing_file_points_at_the_mount(self, tmp_path: Path) -> None:
        provider = FileSecretProvider(root=str(tmp_path))
        with pytest.raises(SecretResolutionError) as caught:
            provider.resolve(SecretRef.parse("file:///absent"))
        assert "mountPath" in caught.value.remedy

    def test_a_world_readable_secret_is_reported_but_still_works(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Refusing to start would be a worse outcome than a warning somebody
        # can act on; passing silently would be worse than either.
        path = tmp_path / "loose"
        path.write_text("value")
        path.chmod(0o644)
        provider = FileSecretProvider(root=str(tmp_path))
        with caplog.at_level("WARNING"):
            assert provider.resolve(SecretRef.parse("file:///loose")).reveal() == "value"
        assert "readable by group or other" in caplog.text


class TestResolver:
    def test_an_unknown_scheme_says_what_is_installed(self) -> None:
        resolver = SecretResolver([EnvironmentSecretProvider()])
        with pytest.raises(SecretResolutionError) as caught:
            resolver.resolve("hashicorp://secret/prod#password")
        assert "env" in caught.value.remedy
        assert "install the package" in caught.value.remedy.lower()

    def test_an_empty_secret_fails_where_the_truth_is(self) -> None:
        # An empty password reaches the driver and comes back as an
        # authentication failure, sending somebody to check a credential that
        # was never actually read.
        provider = MemorySecretProvider({"blank": ""})
        with pytest.raises(SecretResolutionError) as caught:
            SecretResolver([provider]).resolve("memory://blank")
        assert "blank password" in caught.value.remedy

    def test_a_missing_reference_is_not_an_error(self) -> None:
        # A file on a mounted share, or a database using OS authentication.
        assert SecretResolver([]).resolve_optional(None) is None

    def test_the_memory_provider_is_not_a_default(self) -> None:
        # A provider that manufactures secrets from nowhere would make a
        # misconfigured deployment look like a working one.
        assert "memory" not in default_resolver().schemes
        assert set(default_resolver().schemes) == {"env", "file"}


class TestCaching:
    def test_a_second_resolution_does_not_call_the_provider_again(self) -> None:
        # One vault call per connection test is fine. One per batch of a table
        # read will get Prama rate limited and then switched off.
        provider = CountingProvider({"pg": "value"})
        resolver = SecretResolver([provider], clock=MovableClock())
        resolver.resolve("counting://pg")
        resolver.resolve("counting://pg")
        assert provider.calls == 1

    def test_a_rotated_credential_is_picked_up_without_a_restart(self) -> None:
        clock = MovableClock()
        provider = CountingProvider({"pg": "old"})
        resolver = SecretResolver([provider], clock=clock, cache_ttl_seconds=300)
        assert resolver.resolve("counting://pg").reveal() == "old"
        provider.put("pg", "new")
        clock.advance(301)
        assert resolver.resolve("counting://pg").reveal() == "new"

    def test_a_rotation_can_be_applied_immediately(self) -> None:
        provider = CountingProvider({"pg": "old"})
        resolver = SecretResolver([provider], clock=MovableClock())
        resolver.resolve("counting://pg")
        provider.put("pg", "new")
        resolver.invalidate("counting://pg")
        assert resolver.resolve("counting://pg").reveal() == "new"

    def test_caching_can_be_switched_off_entirely(self) -> None:
        provider = CountingProvider({"pg": "value"})
        resolver = SecretResolver([provider], clock=MovableClock(), cache_ttl_seconds=0)
        resolver.resolve("counting://pg")
        resolver.resolve("counting://pg")
        assert provider.calls == 2


class TestAudit:
    def test_every_resolution_is_recorded(self) -> None:
        seen: list[SecretAccess] = []
        resolver = SecretResolver(
            [MemorySecretProvider({"pg": "value"})],
            clock=MovableClock(),
            audit_sink=seen.append,
        )
        resolver.resolve("memory://pg", purpose="connection:c1", principal="alice")
        assert len(seen) == 1
        assert seen[0].outcome == "resolved"
        assert seen[0].purpose == "connection:c1"
        assert seen[0].principal == "alice"

    def test_the_record_never_holds_the_value(self) -> None:
        seen: list[SecretAccess] = []
        resolver = SecretResolver(
            [MemorySecretProvider({"pg": "hunter2"})],
            clock=MovableClock(),
            audit_sink=seen.append,
        )
        resolver.resolve("memory://pg")
        assert "hunter2" not in json.dumps(seen[0].to_dict())

    def test_a_rotation_is_visible_without_the_trail_holding_a_credential(self) -> None:
        seen: list[SecretAccess] = []
        provider = MemorySecretProvider({"pg": "old"})
        resolver = SecretResolver([provider], clock=MovableClock(), audit_sink=seen.append)
        resolver.resolve("memory://pg")
        provider.put("pg", "new")
        resolver.invalidate("memory://pg")
        resolver.resolve("memory://pg")
        assert seen[0].fingerprint != seen[1].fingerprint

    def test_a_failure_is_recorded_as_carefully_as_a_success(self) -> None:
        # "Which credential could not be read, and when" is the question after
        # an outage; it should not require reading application logs.
        seen: list[SecretAccess] = []
        resolver = SecretResolver(
            [MemorySecretProvider({})], clock=MovableClock(), audit_sink=seen.append
        )
        with pytest.raises(SecretResolutionError):
            resolver.resolve("memory://absent", purpose="connection:c1")
        assert seen[0].outcome == "failed"
        assert seen[0].reference == "memory://absent"

    def test_an_unknown_scheme_is_recorded_too(self) -> None:
        seen: list[SecretAccess] = []
        resolver = SecretResolver([], clock=MovableClock(), audit_sink=seen.append)
        with pytest.raises(SecretResolutionError):
            resolver.resolve("hashicorp://x#y")
        assert seen[0].outcome == "unknown-scheme"


class CountingProvider(MemorySecretProvider):
    scheme = "counting"

    def __init__(self, secrets: dict[str, str]) -> None:
        super().__init__(secrets)
        self.calls = 0

    def resolve(self, reference: SecretRef):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().resolve(reference)
