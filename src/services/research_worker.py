"""Independent local worker and read-only health bridge for the web process."""
import os
import signal
import threading
import time
from pathlib import Path

from api.preparation_progress import ObservedResearchJobs
from research.contracts import canonical
from research.store import install_bytes, lock, read_json

HEARTBEAT = 'storage/catalog/operations/worker_service.json'
STALE_SECONDS = 15


def external_health(root):
    unavailable = {'healthy': False, 'state': 'unavailable', 'worker_alive': False,
                   'supervisor_alive': False, 'execution_process': 'separate'}
    try:
        value = read_json(Path(root) / HEARTBEAT)
        age = (time.monotonic_ns() - value['monotonic_ns']) / 1_000_000_000
        if value['workspace'] != str(Path(root).resolve()) or not 0 <= age <= STALE_SECONDS:
            return dict(unavailable, state='stale')
        os.kill(value['pid'], 0)
        # A live unrelated/reused PID is insufficient: the service must hold its lock.
        with lock(root, 'research-worker-service', nonblocking=True) as free:
            if free:
                return unavailable
        return dict(value['health'], execution_process='separate', pid=value['pid'],
                    session_id=value['session_id'], heartbeat_age_seconds=age)
    except (OSError, ValueError, KeyError, TypeError):
        return unavailable


class WebResearchJobs(ObservedResearchJobs):
    """Durable commands and projections only. Web lifetime cannot stop execution."""
    def __init__(self, root, **kwargs):
        if kwargs.pop('start_worker', False):
            raise ValueError('Start the independent research worker instead')
        super().__init__(root, start_worker=False, **kwargs)

    def start(self):
        raise RuntimeError('The web process cannot execute research')

    def health(self):
        return external_health(self.root)


class ServiceResearchJobs(ObservedResearchJobs):
    """SIGTERM drains the current submission before stopping; cancellation stays explicit."""
    def __init__(self, root, **kwargs):
        self._drain_lock = threading.Lock()
        self._draining = False
        self._executing = False
        super().__init__(root, **kwargs)

    def drain(self):
        with self._drain_lock:
            self._draining = True
            if not self._executing:
                self.stop_event.set()
                self.wake.set()

    def _run(self, rid):
        with self._drain_lock:
            if self._draining:
                return
            self._executing = True
        try:
            return super()._run(rid)
        finally:
            with self._drain_lock:
                self._executing = False
                if self._draining:
                    self.stop_event.set()
                    self.wake.set()

    def health(self):
        value = super().health()
        if self._draining:
            value.update(healthy=False, state='draining')
        return value


def run_service(root, *, jobs_factory=ServiceResearchJobs, heartbeat_interval=1):
    """One service per store. Existing executor locking remains authoritative."""
    root = Path(root).resolve()
    with lock(root, 'research-worker-service', nonblocking=True) as claimed:
        if not claimed:
            raise RuntimeError('A separate research worker already owns this workspace')
        # Do not compete with an active older combined server during deployment.
        with lock(root, 'research-executor', nonblocking=True) as available:
            if not available:
                raise RuntimeError('An existing executor is active. Leave it running; start this service after safe cutover.')
        jobs = jobs_factory(root)
        previous = {}
        def drain(signum, frame):
            jobs.drain()
        def publish():
            install_bytes(root / HEARTBEAT, canonical({
                'workspace': str(root), 'pid': os.getpid(), 'session_id': jobs.session_id,
                'monotonic_ns': time.monotonic_ns(), 'health': jobs.health(),
            }) + b'\n', mutable=True)
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, drain)
            jobs.start()
            while not jobs.stop_event.is_set():
                publish()
                if jobs.health()['state'] == 'failed':
                    return 1
                jobs.stop_event.wait(heartbeat_interval)
            return 0
        finally:
            jobs.close()
            publish()
            for sig, handler in previous.items():
                signal.signal(sig, handler)
