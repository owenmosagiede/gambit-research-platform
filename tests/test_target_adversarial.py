"""Storage/adapter integrity acceptance over the production Target service."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from data.alfred_onboarding import strict_json
from data.targets.contracts import create_policy
from data.targets.service import (
    create_target, get_definition, list_targets, materialize, preflight_request,
    read_materialization, retrieve_target,
)
from data.targets.store import TargetStore, materialization_path
from data.transformations.contracts import ContractError
from data.transformations.identity import canonical_bytes, digest, reference
from target_persistence_fixture import persistence_fixture, refresh_fixture


class TargetAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = tempfile.TemporaryDirectory(prefix="target_adversarial_template_")
        cls.addClassCleanup(cls.template.cleanup)
        cls.template_root = Path(cls.template.name)
        cls.setup = persistence_fixture(cls.template_root)
        cls.publication = materialize(cls.template_root, cls.setup["request"])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="target_adversarial_case_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "research_platform"
        shutil.copytree(self.template_root, self.root)
        self.request = deepcopy(self.setup["request"])
        self.target_id = self.publication["target_id"]
        self.materialization_id = self.publication["materialization"]["id"]

    def result(self):
        return read_materialization(self.root, self.materialization_id)

    def payload_path(self, member):
        checksum = member["blob_sha256"]
        return self.root / "storage/payloads/sha256" / checksum[:2] / (checksum + "." + member["format"])

    def manifest_path(self):
        return self.root / materialization_path(self.materialization_id)

    def replace_manifest(self, manifest):
        self.manifest_path().write_bytes(canonical_bytes(manifest) + b"\n")

    def new_definition_request(self, *, horizon_amount=1):
        body = deepcopy(get_definition(self.root, self.target_id)["body"])
        body["horizon"]["amount"] = horizon_amount
        definition = create_target(self.root, body, "Second independently materialized Target")
        request = deepcopy(self.request)
        request["definition"] = reference(definition)
        return definition, request

    def test_persisted_full_metadata_and_exact_contributing_record_locators(self):
        result = self.result()
        store = TargetStore(self.root)
        row = result["observations"][0]
        selected = row["selected_sources"][0]
        metadata = result["source_metadata"]["instrument"]
        self.assertEqual(selected["source_view"], reference(metadata["source_view"]))
        self.assertEqual(selected["source_snapshots"], [reference(metadata["snapshot"])])
        self.assertEqual(selected["economic_policy"], reference(metadata["economic_policy"]))
        self.assertEqual(metadata["source_view"]["body"]["dataset"], reference(metadata["dataset"]))
        self.assertEqual(metadata["dataset"]["body"]["source_contract"], reference(metadata["provider"]))
        self.assertEqual(selected["provenance"]["dataset_name"], metadata["dataset"]["display_name"])
        self.assertEqual(selected["provenance"]["provider"], metadata["provider"]["display_name"])
        operands = result["operand_lineage"][0]["operands"]
        self.assertEqual([item["operand_role"] for item in operands], ["entry", "exit"])
        self.assertEqual([item["row_index"] for item in operands], [0, 2])
        self.assertEqual(result["operand_lineage"][0]["observation_id"], row["id"])
        for operand in operands:
            self.assertEqual(operand["dataset"], reference(metadata["dataset"]))
            self.assertEqual(operand["source_view"], reference(metadata["source_view"]))
            self.assertEqual(operand["snapshot"], self.request["sources"]["instrument"])
            member = next(item for item in metadata["snapshot"]["members"]
                          if item["blob_sha256"] == operand["payload_sha256"])
            record = strict_json(store.payload(member).splitlines()[operand["row_index"]])
            self.assertEqual(digest(record), operand["row_sha256"])
            for key in ("lineage", "reference_time", "available_at", "vintage_id"):
                self.assertEqual(record[key], operand[key])
            lineage = store.resolve(record["lineage"])
            self.assertEqual({item["role"] for item in lineage["inputs"]}, {"raw", "record_locator"})
            locator = store.resolve(next(item["artifact"] for item in lineage["inputs"] if item["role"] == "record_locator"))
            self.assertEqual(locator["body"]["kind"], "canonical_record_locator")

    def test_calendar_evidence_rejects_changed_marks_with_same_certificate(self):
        self.request["schedule"]["marks"][1]["time"] = "2024-01-03"  # Original unchanged.
        self.request["schedule"]["coverage_end"] = "2024-01-10"  # Plausible but uncertified extension.
        with self.assertRaises((ContractError, RuntimeError, ValueError)):
            preflight_request(self.root, self.request)

    def test_arbitrary_existing_reference_is_not_calendar_certification(self):
        self.request["schedule"]["evidence"] = self.setup["fixture"]["sources"]["instrument"]["economics"]["body"]["evidence"][0]
        with self.assertRaises((ContractError, RuntimeError, ValueError)):
            preflight_request(self.root, self.request)

    def test_corrupt_observation_payload_rejected_without_a_new_materialization(self):
        result = self.result()
        payload = self.payload_path(result["manifest"]["observations"])
        original = payload.read_bytes()
        rows = [strict_json(line) for line in original.splitlines()]
        rows[0]["value"] = "999"
        payload.write_bytes(b"".join(canonical_bytes(row) + b"\n" for row in rows))
        with self.assertRaises((ContractError, RuntimeError, ValueError)):
            self.result()
        self.assertEqual(len(list((self.root / "storage/catalog/target_store").glob("*/manifest.json"))), 1)

    def test_missing_schedule_payload_cannot_appear_ready(self):
        result = self.result()
        self.payload_path(result["manifest"]["schedule"]).unlink()
        with self.assertRaises((ContractError, RuntimeError, ValueError, FileNotFoundError)):
            retrieve_target(self.root, self.target_id, self.materialization_id)
        self.assertEqual(list_targets(self.root)["target_count"], 0)

    def test_manifest_status_summary_must_match_authoritative_rows(self):
        manifest = self.result()["manifest"]
        manifest["status_counts"] = {"missing": manifest["row_count"]}
        self.replace_manifest(manifest)
        with self.assertRaises((ContractError, RuntimeError, ValueError)):
            self.result()

    def test_manifest_availability_summary_must_match_authoritative_rows(self):
        manifest = self.result()["manifest"]
        manifest["availability_coverage"] = {"start": "1900-01-01", "end": "1900-01-01"}
        self.replace_manifest(manifest)
        with self.assertRaises((ContractError, RuntimeError, ValueError)):
            self.result()

    def test_manifest_cannot_change_knowledge_cutoff_without_identity_change(self):
        manifest = self.result()["manifest"]
        manifest["input_key"]["knowledge_cutoff"] = "1900-01-01"
        self.replace_manifest(manifest)
        with self.assertRaises((ContractError, RuntimeError, ValueError)):
            self.result()

    def test_corrupt_unrelated_target_does_not_hide_healthy_target(self):
        definition, request = self.new_definition_request()
        second = materialize(self.root, request)
        manifest = self.result()["manifest"]
        manifest["input_key"]["knowledge_cutoff"] = "1900-01-01"
        self.replace_manifest(manifest)
        catalog = list_targets(self.root)
        self.assertEqual([item["target_id"] for item in catalog["targets"]], [definition["id"]])
        self.assertTrue(catalog["issues"])
        self.assertEqual(read_materialization(self.root, second["materialization"]["id"])["definition"]["id"], definition["id"])

    def test_unassignable_wrong_json_types_cannot_hide_healthy_target(self):
        definition, request = self.new_definition_request()
        materialize(self.root, request)
        for malformed in ([], {"definition": []}, {"definition": "not an object"}, None):
            with self.subTest(malformed=malformed):
                self.manifest_path().write_bytes(canonical_bytes(malformed) + b"\n")
                catalog = list_targets(self.root)
                self.assertIn(definition["id"], [item["target_id"] for item in catalog["targets"]])
                self.assertTrue(catalog["issues"])

    def test_implementation_pins_timezone_database_and_actual_source_dependencies(self):
        result = self.result()
        store = TargetStore(self.root)
        implementation = store.resolve(result["manifest"]["input_key"]["implementation"])
        artifacts = {item["role"]: item for item in implementation["code_artifacts"]}
        self.assertIn("src_data_targets_scheduling.py", artifacts)
        self.assertIn("src_data_pit_selection.py", artifacts)
        self.assertIn("iana_timezone_America_New_York", artifacts)
        zone = store.payload(artifacts["iana_timezone_America_New_York"])
        self.assertTrue(zone.startswith(b"TZif"))
        runtime = strict_json(store.payload(implementation["environment_artifacts"][0]))
        self.assertEqual(runtime["decimal_precision"], 50)

    def test_dataset_unit_conflict_rejects_rebound_economic_policy(self):
        store = TargetStore(self.root)
        body = deepcopy(get_definition(self.root, self.target_id)["body"])
        economic = deepcopy(store.resolve(body["sources"][0]["economic_policy"])["body"])
        economic["unit"] = "unapproved_other_units"
        policy = create_policy(economic)
        store.install_record(policy)
        body["sources"][0]["economic_policy"] = reference(policy)
        definition = create_target(self.root, body)
        self.request["definition"] = reference(definition)
        with self.assertRaisesRegex((ContractError, RuntimeError, ValueError), "unit"):
            preflight_request(self.root, self.request)

    def test_source_calendar_conflict_is_rejected_before_arithmetic(self):
        store = TargetStore(self.root)
        body = deepcopy(get_definition(self.root, self.target_id)["body"])
        economic = deepcopy(store.resolve(body["sources"][0]["economic_policy"])["body"])
        economic["calendar_id"] = "UNRELATED_CALENDAR"
        policy = create_policy(economic)
        store.install_record(policy)
        body["sources"][0]["economic_policy"] = reference(policy)
        definition = create_target(self.root, body)
        self.request["definition"] = reference(definition)
        with self.assertRaisesRegex((ContractError, RuntimeError, ValueError), "calendar"):
            preflight_request(self.root, self.request)

    def test_raw_snapshot_cannot_substitute_for_canonical_pit(self):
        store = TargetStore(self.root)
        snapshot = store.resolve(self.request["sources"]["instrument"])
        self.request["sources"]["instrument"] = snapshot["upstream_snapshots"][0]
        with self.assertRaisesRegex((ContractError, RuntimeError, ValueError), "PIT"):
            preflight_request(self.root, self.request)

    def test_forged_source_content_reference_fails(self):
        self.request["sources"]["instrument"]["content_sha256"] = "0" * 64
        with self.assertRaises((ContractError, RuntimeError, ValueError)):
            preflight_request(self.root, self.request)

    def test_display_rename_never_changes_logical_identity_or_existing_definition(self):
        before = get_definition(self.root, self.target_id)
        renamed = create_target(self.root, deepcopy(before["body"]), "Renamed for presentation")
        self.assertEqual(reference(renamed), reference(before))
        self.assertEqual(renamed["display_name"], before["display_name"])
        self.assertEqual(list_targets(self.root)["target_count"], 1)

    def test_unrelated_source_observation_cannot_change_finalized_return(self):
        before = self.result()["observations"][0]
        setup = deepcopy(self.setup)
        setup["fixture"]["sources"]["instrument"]["series"]["observations"][-1]["value"] = "987654321"
        changed = refresh_fixture(self.root, setup)
        refreshed = materialize(self.root, changed["request"])
        after = read_materialization(self.root, refreshed["materialization"]["id"])["observations"][0]
        for field in ("target", "value", "prediction_anchor", "entry_time", "exit_time", "label_available_at", "status"):
            self.assertEqual(before[field], after[field])
        self.assertNotEqual(refreshed["materialization"]["id"], self.materialization_id)
        self.assertEqual(self.result()["observations"][0], before)


if __name__ == "__main__":
    unittest.main()
