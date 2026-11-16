"""Queue ownership and drain on an isolated store with independent processes."""
from contextlib import contextmanager
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from research.store import lock
from services.two_workers import ParallelResearchJobs, executor_lock


LANE_FIXTURE = """
from pathlib import Path
import sys
from time import monotonic, sleep
root = Path(sys.argv[1])
for line in sys.stdin:
    rid = line.strip()
    (root / (rid + '.started')).touch()
    until = monotonic() + 8
    while not (root / (rid + '.release')).exists():
        if monotonic() >= until:
            raise RuntimeError('Fixture ran past its deadline')
        sleep(.02)
    print(rid, flush=True)
"""


@contextmanager
def fixture_lane(root, lease):
    with subprocess.Popen([sys.executable, "-B", "-c", LANE_FIXTURE, str(root)],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, pass_fds=(lease,)) as child:
        try:
            yield child
        finally:
            child.stdin.close()


class ParallelWorkerTests(unittest.TestCase):
    def test_two_distinct_claims_drain_before_next_job(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            jobs = ParallelResearchJobs(root)
            requests = [str(uuid4()) for _ in range(3)]
            scopes = dict(zip(requests, ("EURUSD", "GBPUSD", "NZDUSD")))
            errors = []

            def dispatch():
                try:
                    with executor_lock(root) as lease:
                        jobs._serve_batch(requests, lease)
                except Exception as exc:
                    errors.append(exc)

            with patch.object(jobs, "_instrument", side_effect=scopes.__getitem__), \
                    patch("services.two_workers.lane", fixture_lane):
                thread = threading.Thread(target=dispatch)
                thread.start()
                try:
                    deadline = time.monotonic() + 5
                    while not all((root / (rid + ".started")).exists() for rid in requests[:2]):
                        if time.monotonic() >= deadline:
                            self.fail(f"Both requests did not start: {errors}")
                        time.sleep(.02)
                    self.assertEqual(jobs.activity()["request_ids"], requests[:2])
                    with lock(root, "research-executor", nonblocking=True) as claimed:
                        self.assertFalse(claimed)
                    jobs.drain()
                    self.assertFalse(jobs.stop_event.is_set())
                finally:
                    for rid in requests:
                        (root / (rid + ".release")).touch()
                    thread.join(10)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertTrue(jobs.stop_event.is_set())
                self.assertFalse((root / (requests[2] + ".started")).exists())

    def test_inherited_lock_outlives_its_opening_process(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with executor_lock(root) as lease:
                child = subprocess.Popen([sys.executable, "-B", "-c", "input()"],
                                         stdin=subprocess.PIPE, pass_fds=(lease,))
            with child:
                with lock(root, "research-executor", nonblocking=True) as claimed:
                    self.assertFalse(claimed)
                child.communicate(b"release\n", timeout=5)
            with lock(root, "research-executor", nonblocking=True) as claimed:
                self.assertTrue(claimed)


if __name__ == "__main__":
    unittest.main()
