import sys, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line

r = subprocess.run(["python3", "-m", "pytest", "tests/secrets/", "-v"],
                    capture_output=True, text=True, cwd="/home/ashutosh/PycharmProjects/prama")
out = r.stdout
def pyresult(name):
    for l in out.splitlines():
        if name in l:
            return "PASSED" in l
    return None

mapping = {
    "SEC-168": "test_a_reference_names_a_scheme_and_a_location",
    "SEC-169": "test_the_error_for_a_bad_reference_does_not_echo_it_back",  # partial, refined below too
    "SEC-170": "test_a_pasted_password_is_refused_with_advice_not_stored",
    "SEC-171": "test_a_scheme_with_no_location_is_refused",
    "SEC-172": "test_try_parse_returns_none_rather_than_raising",
    "SEC-174": "test_it_reads_the_variable",  # + test_an_unset_variable_says_where_to_set_it
    "SEC-175": "test_a_trailing_newline_is_not_part_of_the_password",
    "SEC-176": "test_a_reference_cannot_escape_the_secrets_directory",
    "SEC-178": "test_a_world_readable_secret_is_reported_but_still_works",
    "SEC-179": "test_a_field_can_be_taken_from_a_json_variable",
    "SEC-181": "test_a_missing_field_lists_the_ones_present",
    "SEC-183": "test_the_memory_provider_is_not_a_default",
    "SEC-184": "test_vault_is_registered_but_unavailable_by_default",
    "SEC-186": "test_it_reads_the_inner_data_not_the_outer",
    "SEC-187": "test_a_soft_deleted_version_is_refused",  # + destroyed + empty
    "SEC-188": "test_a_reference_with_no_field_is_refused",
    "SEC-189": "test_an_empty_field_is_refused",  # + null field
    "SEC-190": "test_a_transport_failure_is_translated",
    "SEC-191": "test_the_path_is_passed_through_as_written",
    "SEC-193": "test_an_unknown_scheme_says_what_is_installed",
    "SEC-194": "test_the_resolver_relays_the_providers_own_reason",
    "SEC-195": "test_an_empty_secret_fails_where_the_truth_is",
    "SEC-196": "test_a_second_resolution_does_not_call_the_provider_again",
    "SEC-197": "test_caching_can_be_switched_off_entirely",
    "SEC-198": "test_a_rotated_credential_is_picked_up_without_a_restart",
    "SEC-200": "test_every_resolution_is_recorded",
    "SEC-201": "test_a_rotation_is_visible_without_the_trail_holding_a_credential",
    "SEC-202": "test_a_failure_is_recorded_as_carefully_as_a_success",
    "SEC-203": "test_str_is_redacted",  # + repr, f-string, etc
    "SEC-204": "test_it_refuses_to_pickle",
    "SEC-205": "test_its_length_is_not_a_side_channel",
    "SEC-206": "test_comparison_does_not_require_revealing",  # + a_secret_never_equals_a_bare_string
    "SEC-207": "test_hashing_uses_the_fingerprint_not_the_value",
}
for cid, testname in mapping.items():
    ok = pyresult(testname)
    matching = [l.strip() for l in out.splitlines() if testname in l]
    line(cid, "PASS" if ok else "FAIL", f"pytest tests/secrets/ ::{testname} -> {matching}")

print("SECTION Secrets-mapped-from-pytest DONE")
