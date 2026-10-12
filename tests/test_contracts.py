"""Small synthetic structural checks; these do not certify scientific readiness."""

from copy import deepcopy
import json
from pathlib import Path
import re
import unittest

from contracts import (
    ContractError, canonical_experiment_bytes, canonical_resolved_bytes,
    experiment_id, load_json_strict, normalize_experiment,
    normalize_resolved_experiment, resolved_experiment_id,
    submission_content_fingerprint, validate_submission,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def fixture(name):
    return load_json_strict((FIXTURES / ("synthetic_" + name + ".json")).read_text())


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.experiment = fixture("experiment")
        self.request = fixture("submission")
        self.resolved = fixture("resolved_experiment")

    def test_valid_synthetic_forms_are_structural_only(self):
        self.assertEqual(normalize_experiment(self.experiment), self.experiment)
        self.assertEqual(validate_submission(self.request), self.request)
        self.assertEqual(normalize_resolved_experiment(self.resolved), self.resolved)
        self.assertNotIn("ready", normalize_resolved_experiment(self.resolved))

    def test_every_scientific_input_is_required(self):
        for name in self.experiment:
            with self.subTest(field=name):
                value = deepcopy(self.experiment)
                del value[name]
                with self.assertRaises(ContractError):
                    normalize_experiment(value)

    def test_unknown_and_executable_fields_are_rejected(self):
        for field in ("code", "python", "capital", "mandate", "positions", "metadata", "latest"):
            with self.subTest(field=field):
                value = deepcopy(self.experiment)
                value[field] = "print('not executed')"
                with self.assertRaises(ContractError):
                    normalize_experiment(value)
        for location in ("feature", "target", "scope", "research_spec"):
            value = deepcopy(self.experiment)
            value[location]["expression"] = "__import__('os')"
            with self.assertRaises(ContractError):
                normalize_experiment(value)
        value = deepcopy(self.request)
        value["execution_options"] = {}
        with self.assertRaises(ContractError):
            validate_submission(value)

    def test_direction_is_explicit_and_never_inferred(self):
        for direction in ("positive", "AUTO", "", None, True, 1, [], {}):
            with self.subTest(direction=direction):
                self.experiment["expected_direction"] = direction
                with self.assertRaises(ContractError):
                    normalize_experiment(self.experiment)

    def test_unpinned_and_ambiguous_versions_are_rejected(self):
        for version in ("latest", "dev", "main", "1", "1.0", "v1.0.0", "01.0.0", "1.0.*", "1.0.0-dev", "1.0.0\n", None):
            with self.subTest(version=version):
                self.experiment["feature"]["version"] = version
                with self.assertRaises(ContractError):
                    normalize_experiment(self.experiment)

    def test_no_silent_case_whitespace_unicode_or_type_coercion(self):
        for identifier in (" SYNTHETIC_FEATURE", "SYNTHETIC_FEATURE ", "SYNTHETIC_FEATURE\n", "FÉATURE", "/tmp/feature", "x()", 123, None):
            with self.subTest(identifier=identifier):
                self.experiment["feature"]["id"] = identifier
                with self.assertRaises(ContractError):
                    normalize_experiment(self.experiment)
        self.experiment = fixture("experiment")
        self.experiment["feature"]["id"] = "synthetic_feature"
        self.assertNotEqual(experiment_id(self.experiment), experiment_id(fixture("experiment")))

    def test_wrong_shapes_fail_as_contract_errors(self):
        for value in (None, [], "string", 1, True, {1: "bad key"}):
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    normalize_experiment(value)
        self.resolved["dependencies"]["data_snapshots"] = []
        with self.assertRaises(ContractError):
            normalize_resolved_experiment(self.resolved)

    def test_strict_json_parser_rejects_duplicates_and_nonfinite_values(self):
        for text in ('{"feature":1,"feature":2}', '{"a":{"x":1,"x":2}}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{'):
            with self.subTest(text=text):
                with self.assertRaises(ContractError):
                    load_json_strict(text)
        self.assertEqual(load_json_strict(json.dumps(self.experiment)), self.experiment)

    def test_key_order_and_json_whitespace_do_not_change_identity(self):
        reordered = {key: self.experiment[key] for key in reversed(self.experiment)}
        reordered["feature"] = {"version": "1.0.0", "id": "SYNTHETIC_FEATURE"}
        self.assertEqual(canonical_experiment_bytes(reordered), canonical_experiment_bytes(self.experiment))
        self.assertEqual(experiment_id(load_json_strict(json.dumps(reordered, indent=8))), experiment_id(self.experiment))

    def test_frozen_identity_vectors(self):
        self.assertEqual(experiment_id(self.experiment), "exp_v0_1_sha256_4721c9646060c9307506f749677716071cf3b9b9d5a798c0f469bbed4150c414")
        self.assertEqual(submission_content_fingerprint(self.request), "requestcontent_v0_1_sha256_4721c9646060c9307506f749677716071cf3b9b9d5a798c0f469bbed4150c414")
        self.assertEqual(resolved_experiment_id(self.resolved), "resolved_v0_1_sha256_6c69fe0dac092286801249fbf720ce6652b8c07c4a29c8a465a53c300b8a330f")
        self.assertNotIn(b" ", canonical_experiment_bytes(self.experiment))

    def test_each_scientific_input_changes_identity(self):
        for name in self.experiment:
            with self.subTest(field=name):
                value = deepcopy(self.experiment)
                if name == "expected_direction":
                    value[name] = "NEGATIVE"
                else:
                    value[name]["version"] = "2.0.0"
                self.assertNotEqual(experiment_id(value), experiment_id(self.experiment))

    def test_request_identifier_is_operational_and_content_conflicts_are_detectable(self):
        other = deepcopy(self.request)
        other["request_id"] = "22222222-2222-4222-8222-222222222222"
        self.assertEqual(submission_content_fingerprint(other), submission_content_fingerprint(self.request))
        other["request_id"] = self.request["request_id"]
        other["experiment"]["expected_direction"] = "NEGATIVE"
        self.assertNotEqual(submission_content_fingerprint(other), submission_content_fingerprint(self.request))
        # No persistent request store is exercised or claimed here.

    def test_request_envelope_required_fields_and_version(self):
        for key in self.request:
            value = deepcopy(self.request)
            del value[key]
            with self.assertRaises(ContractError):
                validate_submission(value)
        for key, value in (("contract_version", "latest"), ("request_id", "not-a-uuid"), ("request_id", self.request["request_id"] + "\n")):
            request = deepcopy(self.request)
            request[key] = value
            with self.assertRaises(ContractError):
                validate_submission(request)

    def test_normalized_objects_are_detached_from_caller(self):
        normalized = normalize_resolved_experiment(self.resolved)
        normalized["experiment"]["feature"]["id"] = "CHANGED"
        normalized["dependencies"]["data_snapshots"]["bindings"][0]["artifact"]["id"] = "CHANGED"
        self.assertEqual(self.resolved, fixture("resolved_experiment"))

    def test_resolved_bindings_must_match_requested_refs(self):
        self.resolved["definition_bindings"]["target"]["version"] = "2.0.0"
        with self.assertRaises(ContractError):
            normalize_resolved_experiment(self.resolved)

    def test_claimed_dependency_hash_changes_affect_resolved_identity(self):
        paths = [("dependencies", "data_snapshots"), ("dependencies", "implementation_manifest"), ("definition_bindings", "target")]
        # Changed content for one definition ID/version is a future resolver error.
        # This verifies hash sensitivity of claims, not acceptance by a registry.
        original = resolved_experiment_id(self.resolved)
        for section, name in paths:
            with self.subTest(name=name):
                value = deepcopy(self.resolved)
                if section == "definition_bindings":
                    value[section][name]["content_sha256"] = "f" * 64
                else:
                    value[section][name]["bindings"][0]["artifact"]["content_sha256"] = "f" * 64
                self.assertNotEqual(resolved_experiment_id(value), original)
                self.assertEqual(experiment_id(value["experiment"]), experiment_id(self.experiment))

    def test_operational_metadata_and_paths_cannot_enter_scientific_identity(self):
        for key in ("path", "run_directory", "attempt_id", "started_at", "certificate_issued_at"):
            with self.subTest(key=key):
                value = deepcopy(self.resolved)
                value[key] = "/somewhere/else"
                with self.assertRaises(ContractError):
                    resolved_experiment_id(value)
        self.resolved["dependencies"]["data_snapshots"]["bindings"][0]["artifact"]["path"] = "/tmp/data"
        with self.assertRaises(ContractError):
            normalize_resolved_experiment(self.resolved)

    def test_required_missing_dependencies_are_rejected(self):
        for name in ("data_snapshots", "availability_policy", "implementation_manifest", "readiness_evidence"):
            with self.subTest(dependency=name):
                value = deepcopy(self.resolved)
                value["dependencies"][name] = {"requirement": "required", "bindings": []}
                with self.assertRaises(ContractError):
                    normalize_resolved_experiment(value)
        del self.resolved["dependencies"]["randomness_settings"]
        with self.assertRaises(ContractError):
            normalize_resolved_experiment(self.resolved)

    def test_optional_and_inapplicable_need_explicit_reason(self):
        for requirement in ("optional", "inapplicable"):
            value = deepcopy(self.resolved)
            value["dependencies"]["readiness_evidence"] = {"requirement": requirement, "bindings": [], "reason_code": "SYNTHETIC_POLICY_DECISION"}
            normalize_resolved_experiment(value)
            del value["dependencies"]["readiness_evidence"]["reason_code"]
            with self.assertRaises(ContractError):
                normalize_resolved_experiment(value)
        self.resolved["dependencies"]["data_snapshots"]["requirement"] = "optional"
        with self.assertRaises(ContractError):
            normalize_resolved_experiment(self.resolved)

    def test_dependency_order_normalizes_but_duplicate_roles_fail(self):
        bindings = self.resolved["dependencies"]["data_snapshots"]["bindings"]
        second = deepcopy(bindings[0])
        second["role"] = "other_observations"
        second["artifact"]["id"] = "SYNTHETIC_OTHER_SNAPSHOT"
        bindings.append(second)
        original = canonical_resolved_bytes(self.resolved)
        bindings.reverse()
        self.assertEqual(canonical_resolved_bytes(self.resolved), original)
        bindings[0]["role"] = bindings[1]["role"]
        with self.assertRaises(ContractError):
            normalize_resolved_experiment(self.resolved)

    def test_invalid_digest_and_false_inapplicability_fail(self):
        for digest in ("", "g" * 64, "A" * 64, "a" * 63, "a" * 64 + "\n"):
            with self.subTest(digest=digest):
                value = deepcopy(self.resolved)
                value["definition_bindings"]["target"]["content_sha256"] = digest
                with self.assertRaises(ContractError):
                    normalize_resolved_experiment(value)
        self.resolved["dependencies"]["readiness_evidence"]["requirement"] = "inapplicable"
        with self.assertRaises(ContractError):
            normalize_resolved_experiment(self.resolved)

    def test_schema_is_self_contained_closed_and_has_three_forms(self):
        schema = load_json_strict((ROOT / "specs/schemas/contracts.schema.json").read_text())
        self.assertEqual(len(schema["oneOf"]), 3)
        def inspect(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertTrue(value["$ref"].startswith("#/$defs/"))
                    self.assertIn(value["$ref"].split("/")[-1], schema["$defs"])
                if value.get("type") == "object":
                    self.assertIs(value.get("additionalProperties"), False)
                    self.assertEqual(set(value["required"]), set(value["properties"]))
                if "pattern" in value:
                    re.compile(value["pattern"])
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        inspect(schema)
        self.assertEqual(set(schema["$defs"]["experiment_definition"]["required"]), set(self.experiment))


if __name__ == "__main__":
    unittest.main()
