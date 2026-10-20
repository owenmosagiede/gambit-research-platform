"""Synthetic-only recovery, authority-link and no-leakage integration checks."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from research.contracts import canonical, digest, ref, ResearchError, ResearchConflict
from research.store import ResearchStore, read_json
from runtime.research_jobs import ResearchJobs
from test_research_runtime import Adapter, KernelSpy, intent, profile, reference


class SimulatedProcessLoss(BaseException):
    pass


class ResearchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "config/research_execution.json").write_bytes(canonical(profile()))
        self.adapter = Adapter()

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, *, spy=None, request=None):
        jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=spy)
        request = request or intent()
        jobs.submit(request)
        jobs.run_pending_once()
        self.assertEqual(jobs.get(request["request_id"])["status"], "succeeded")
        return jobs, request

    def test_abrupt_loss_after_trial_publication_reuses_exact_science(self):
        spy = KernelSpy()
        jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=spy)
        request = intent()
        jobs.submit(request)
        real_put = jobs.store.put
        failed = False

        def publication_loss(kind, key, body):
            nonlocal failed
            record = real_put(kind, key, body)
            if kind == "trial" and body["stage"] == "P1" and not failed:
                failed = True
                raise SimulatedProcessLoss()
            return record

        jobs.store.put = publication_loss
        with self.assertRaises(SimulatedProcessLoss):
            jobs.run_pending_once()
        trial_paths = sorted((self.root / "storage/catalog/trial_ledger/records").glob("*.json"))
        self.assertEqual(len(trial_paths), 1)
        committed = trial_paths[0].read_bytes()
        self.assertEqual(spy.calls, [("P1", 1)])
        recovered = ResearchJobs(self.root, adapter=self.adapter, kernels=spy)
        recovered.run_pending_once()
        self.assertEqual(recovered.get(request["request_id"])["status"], "succeeded")
        self.assertEqual(spy.calls.count(("P1", 1)), 1)
        self.assertEqual(trial_paths[0].read_bytes(), committed)
        self.assertEqual(len(list((self.root / "storage/catalog/trial_ledger/records").glob("*.json"))), 10)
        self.assertEqual(len(recovered.store.results_for_recipe(request["feature"]["id"])), 5)

    def test_competing_workers_do_not_duplicate_scientific_execution(self):
        spy = KernelSpy()
        jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=spy)
        other = ResearchJobs(self.root, adapter=self.adapter, kernels=spy)
        request = intent()
        jobs.submit(request)
        entered, release = threading.Event(), threading.Event()
        errors = []

        def hold_preparation():
            entered.set()
            if not release.wait(timeout=10):
                raise AssertionError("test worker release timed out")

        def run():
            try:
                jobs.run_pending_once()
            except BaseException as error:
                errors.append(error)

        self.adapter.on_prepare = hold_preparation
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(entered.wait(timeout=5))
            other.run_pending_once()
            self.assertEqual(spy.calls, [])
        finally:
            release.set()
            worker.join(timeout=15)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)
        self.assertEqual(len(spy.calls), 10)
        self.assertEqual(len(set(spy.calls)), 10)
        self.assertEqual(jobs.get(request["request_id"])["status"], "succeeded")

    def test_real_cs_runtime_uses_five_date_level_evaluations(self):
        jobs, request = self.execute()
        records = jobs.store.results_for_recipe(request["feature"]["id"])
        self.assertEqual(len(records), 5)
        self.assertEqual({record["horizon"] for record in records}, {1, 7, 21, 63, 252})
        self.assertEqual(len([item for item in self.adapter.loads if item[0] == "P1"]), 5)
        for record in records:
            p1 = next(item for item in record["results"] if item["stage"] == "P1")
            self.assertEqual(record["mode"], "CS")
            self.assertEqual(p1["sample"]["required_members"], ["AAA", "BBB", "CCC", "DDD", "EEE"])
            self.assertEqual(p1["sample"]["inference_observation_count"], 400)
            self.assertEqual(p1["sample"]["usable_pair_count"], 2000)
            self.assertEqual(p1["sample"]["inference_observation_unit"], "dates")
            self.assertIsNotNone(p1["metrics"]["primary_effect"])

    def test_validation_trial_identity_pins_discovery_record_and_effect(self):
        spy = KernelSpy()
        jobs, request = self.execute(spy=spy)
        p2_paths = [path for path in (self.root / "storage/catalog/trial_ledger/records").glob("*.json")
                    if read_json(path)["body"]["stage"] == "P2"]
        self.assertEqual(len(p2_paths), 5)
        for path in p2_paths:
            record = read_json(path)
            source = jobs.store.resolve("trial", record["scientific_key"]["discovery_trial"])
            self.assertEqual(source["body"]["stage"], "P1")
            self.assertEqual(record["scientific_key"]["discovery_effect"], source["body"]["metrics"]["primary_effect"])
            self.assertEqual(source["scientific_key"]["relationship"], record["scientific_key"]["relationship"])
            changed = deepcopy(record["scientific_key"])
            changed["discovery_trial"]["content_sha256"] = "0" * 64
            self.assertIsNone(jobs.store.find("trial", changed))

    def test_reuse_verifies_artifact_bytes_before_skipping_kernel(self):
        spy = KernelSpy()
        jobs, first = self.execute(spy=spy)
        before = list(spy.calls)
        trial = next(record for record in (read_json(path) for path in (self.root / "storage/catalog/trial_ledger/records").glob("*.json"))
                     if record["body"]["stage"] == "P1" and record["scientific_key"]["horizon"] == 1)
        artifact = jobs.store.verify_artifact(trial["body"]["artifact_manifests"][0])
        member = artifact["members"][0]
        sha = member["blob_sha256"]
        payload = self.root / f"storage/payloads/sha256/{sha[:2]}/{sha}.json"
        payload.write_bytes(payload.read_bytes() + b" ")
        second = intent()
        with self.assertRaisesRegex(ResearchConflict, "reconciliation"):
            jobs.submit(second)
        self.assertFalse(jobs._submission_path(second["request_id"]).exists())
        self.assertEqual(spy.calls, before)
        with self.assertRaisesRegex(ResearchError, "corruption"):
            jobs.store.results_for_recipe(first["feature"]["id"])

    def test_exact_reference_checksum_is_checked(self):
        store = ResearchStore(self.root)
        record = store.put("trial", {"synthetic": True}, {"metrics": {"value": 1}})
        altered = dict(ref(record), content_sha256="0" * 64)
        with self.assertRaisesRegex(ResearchError, "reference checksum"):
            store.resolve("trial", altered)

    def test_partial_and_complete_links_render_only_maximal_evidence(self):
        jobs, request = self.execute(spy=KernelSpy())
        link_paths = list((self.root / "storage/catalog/signal_library/research_links").glob("*.json"))
        self.assertEqual(len(link_paths), 10)  # immutable P1-only and P1/P2 links
        entries = jobs.store.results_for_recipe(request["feature"]["id"])
        self.assertEqual(len(entries), 5)
        self.assertTrue(all(len(entry["trial_results"]) == 2 for entry in entries))
        self.assertTrue(all(entry["p2_status"] == "VALIDATED" for entry in entries))

    def test_independent_research_spec_branches_remain_visible(self):
        spy = KernelSpy()
        jobs, first = self.execute(spy=spy)
        revised = profile()
        revised["version"] = "1.0.1"
        (self.root / "config/research_execution.json").write_bytes(canonical(revised))
        second = intent()
        jobs.submit(second)
        jobs.run_pending_once()
        self.assertEqual(jobs.get(second["request_id"])["status"], "succeeded")
        entries = jobs.store.results_for_recipe(first["feature"]["id"])
        self.assertEqual(len(entries), 10)
        for horizon in (1, 7, 21, 63, 252):
            versions = {row["results"][0]["research_spec"]["version"] for row in entries if row["horizon"] == horizon}
            self.assertEqual(versions, {"1.0.0", "1.0.1"})

    def test_rejected_horizons_never_load_validation_data(self):
        class SelectiveAdmission(KernelSpy):
            def run_p1(self, rows, **kw):
                value = super().run_p1(rows, **kw)
                if kw["horizon"] in (7, 252):
                    value["admission"] = "rejected"
                return value

        jobs, request = self.execute(spy=SelectiveAdmission())
        job = jobs.get(request["request_id"])
        self.assertEqual(len(job["horizons"]), 5)
        self.assertEqual([h for phase, h in self.adapter.loads if phase == "P2"], [1, 21, 63])
        for row in job["horizons"]:
            if row["horizon"] in (7, 252):
                self.assertEqual(row["p1_status"], "rejected")
                self.assertEqual(row["p2_status"], "not_admitted")

    def test_link_reader_rejects_cross_relationship_trial_references(self):
        jobs, request = self.execute(spy=KernelSpy())
        entries = jobs.store.results_for_recipe(request["feature"]["id"])
        first, other = entries[:2]
        original = jobs.store.resolve("link", first["projection"])
        wrong = deepcopy(original["body"])
        wrong["trial_results"] = other["trial_results"]
        jobs.store.put("link", wrong, wrong)
        with self.assertRaises(ResearchError):
            jobs.store.results_for_recipe(request["feature"]["id"])

    def test_link_reader_rejects_cross_relationship_validation_references(self):
        jobs, request = self.execute(spy=KernelSpy())
        entries = jobs.store.results_for_recipe(request["feature"]["id"])
        first, other = entries[:2]
        original = jobs.store.resolve("link", first["projection"])
        wrong = deepcopy(original["body"])
        wrong["validation_results"] = other["validation_results"]
        jobs.store.put("link", wrong, wrong)
        with self.assertRaises(ResearchError):
            jobs.store.results_for_recipe(request["feature"]["id"])

    def test_unreadable_event_is_quarantined_without_crashing_worker(self):
        jobs = ResearchJobs(self.root, adapter=self.adapter)
        request = intent()
        jobs.submit(request)
        event_path = next((self.root / "storage/catalog/attempts").glob("*/events/RESEVENT_*.json"))
        event_path.write_text('{broken')
        jobs.run_pending_once()
        failure = jobs.get(request["request_id"])
        self.assertTrue(failure["operational_failure"])
        self.assertIn("Unreadable execution event", failure["incident"]["diagnostic"])
        self.assertEqual(self.adapter.resolve_calls, 1)

    def test_tampered_event_cannot_be_ignored_in_favor_of_mutable_job(self):
        jobs = ResearchJobs(self.root, adapter=self.adapter)
        request = intent()
        jobs.submit(request)
        event_path = next((self.root / "storage/catalog/attempts").glob("*/events/RESEVENT_*.json"))
        event = read_json(event_path)
        event["job"]["status"] = "succeeded"
        event_path.write_bytes(canonical(event))
        failure = jobs.get(request["request_id"])
        self.assertTrue(failure["operational_failure"])
        self.assertIn("event checksum", failure["incident"]["diagnostic"])
        self.assertEqual(failure["results"], [])
        jobs.run_pending_once()
        self.assertEqual(self.adapter.resolve_calls, 1)


if __name__ == "__main__":
    unittest.main()
