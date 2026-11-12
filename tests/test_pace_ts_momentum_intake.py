from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import json
import unittest


spec = importlib.util.spec_from_file_location(
    'paced_ts_intake', Path(__file__).resolve().parents[1] / 'tools/pace_ts_momentum_intake.py')
pace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pace)


class PacedIntakeTests(unittest.TestCase):
    def test_initial_admission_then_one_for_each_completed_job(self):
        self.assertTrue(pace.may_admit(554, 9, 554, 554, 9))
        self.assertFalse(pace.may_admit(555, 9, 555, 554, 9))
        self.assertTrue(pace.may_admit(555, 10, 555, 554, 9))
        self.assertFalse(pace.may_admit(556, 10, 556, 554, 9))

    def test_empty_queue_can_refill_after_a_blocked_admission(self):
        self.assertFalse(pace.may_admit(10, 7, 8, 9, 7))
        self.assertTrue(pace.may_admit(10, 8, 8, 9, 8))

    def test_only_processed_terminal_jobs_supply_intake_slots(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            jobs = root / 'storage/catalog/operations/jobs'
            jobs.mkdir(parents=True)
            entries = [{'request_id': label} for label in ('done', 'live', 'missing', 'outside')]
            for name, status in (('done', 'succeeded'), ('live', 'p1'), ('outside', 'succeeded')):
                (jobs / (name + '.json')).write_text(json.dumps({'request_id': name, 'status': status}))
            read = lambda path: json.loads(path.read_bytes())
            self.assertEqual(pace.terminal_count(root, entries, 3, read), 1)


if __name__ == '__main__':
    unittest.main()
