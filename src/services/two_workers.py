"""One queue owner and up to two compute subprocesses on a single store."""
from collections import deque
from contextlib import ExitStack, contextmanager
import fcntl
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys

from api.preparation_progress import ObservedResearchJobs
from research.contracts import ResearchError, request_id
from research.store import inside
from runtime.research_jobs import implementation
from services.research_worker import ServiceResearchJobs
from services.worker_inputs import coordinated_inputs


@contextmanager
def executor_lock(root):
    """Inherit the same flock across processes, including on coordinator death."""
    path = inside(root, "storage/catalog/operations/research-executor.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
        else:
            # Do not explicitly unlock a file description inherited by children.
            yield lease.fileno()


def lane_main(root, lease):
    path = inside(root, "storage/catalog/operations/research-executor.lock")
    inherited = os.fstat(lease)
    current = path.stat()
    if (current.st_dev, current.st_ino) != (inherited.st_dev, inherited.st_ino):
        raise RuntimeError("The worker lane must inherit its workspace executor lock")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # systemd signals the whole group. The queue owner drains by closing stdin
    # after the running submissions complete. Explicit request cancellation
    # still travels through the verified job state in the ordinary worker.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    jobs = ObservedResearchJobs(root)
    with coordinated_inputs(root, implementation()):
        for line in sys.stdin:
            rid = request_id(line.rstrip("\n"))
            jobs._run(rid)
            print(rid, flush=True)


@contextmanager
def lane(root, lease):
    src = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(src))
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "services.two_workers", str(root), str(lease)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, pass_fds=(lease,), env=env,
    )
    try:
        yield process
    finally:
        try:
            process.stdin.close()
        finally:
            process.wait()
            process.stdout.close()


class ParallelResearchJobs(ServiceResearchJobs):
    """Parallelize distinct frozen individual FX jobs in existing queue order."""

    def __init__(self, root):
        super().__init__(root)
        self._active = {}

    def activity(self):
        with self._drain_lock:
            requests = [rid for rid, scope in self._active.values()]
        return {"request_id": next(iter(requests), None), "request_ids": requests}

    def _instrument(self, rid):
        try:
            submission = self._submission(rid)
            plan = submission["frozen_plan"]
            scope = plan["scope"]
            if (plan["mode"] == "TS" and scope["kind"] == "instrument"
                    and plan["intent"]["target_family"] == "price_return"
                    and plan.get("application_class") is None and not submission.get("p2_followup")
                    and len(plan["members"]) == 1 and plan["members"][0]["instrument_id"] == scope["id"]):
                return scope["id"]
        except (KeyError, OSError, TypeError, ValueError, ResearchError):
            # The ordinary executor reports invalid frozen inputs through the
            # existing per-request recovery path. They run exclusively.
            pass
        return None

    def _claim(self, process, rid, scope):
        with self._drain_lock:
            if self._draining:
                return False
            self._active[process] = (rid, scope)
            self._executing = True
            process.stdin.write((rid + "\n").encode("ascii"))
            process.stdin.flush()
            return True

    def _finish(self, process):
        received = process.stdout.readline(38)
        with self._drain_lock:
            active = self._active.get(process)
            if active is None or received != (active[0] + "\n").encode("ascii"):
                raise RuntimeError("A research subprocess lost its assigned request")
            del self._active[process]
            self._executing = bool(self._active)
            if self._draining and not self._executing:
                self.stop_event.set()

    def _serve_batch(self, pending, lease):
        pending = deque((rid, self._instrument(rid)) for rid in pending)
        try:
            with ExitStack() as resources, selectors.DefaultSelector() as selector:
                processes = [resources.enter_context(lane(self.root, lease)) for _ in range(min(2, len(pending)))]
                for process in processes:
                    selector.register(process.stdout, selectors.EVENT_READ, process)
                while pending or self._active:
                    for process in processes:
                        if not pending or self._draining:
                            pending.clear()
                            break
                        if process in self._active:
                            continue
                        rid, scope = pending[0]
                        active_scopes = {instrument for _, instrument in self._active.values()}
                        if active_scopes and (scope is None or None in active_scopes or scope in active_scopes):
                            break
                        if self._claim(process, rid, scope):
                            pending.popleft()
                    if self._active:
                        for ready, _ in selector.select(timeout=0.25):
                            self._finish(ready.data)
        finally:
            # Lane pipe closure waits for surviving work before releasing the
            # maintenance lock or letting the supervisor reconcile attempts.
            with self._drain_lock:
                self._active.clear()
                self._executing = False
                if self._draining:
                    self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            with executor_lock(self.root) as lease:
                if lease is None:
                    self._worker_ready("waiting_for_executor")
                else:
                    pending = self._pending()
                    self._worker_ready("running" if pending else "idle")
                    if pending:
                        self._serve_batch(pending, lease)
                        self._worker_ready("idle")
            self.wake.wait(1)
            self.wake.clear()


if __name__ == "__main__":
    lane_main(Path(sys.argv[1]).resolve(), int(sys.argv[2]))
