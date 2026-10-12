"""Separate OS processes, real HTTP and statistical kernels, isolated synthetic stores."""
import http.client
import json
import multiprocessing
import os
from pathlib import Path
import signal
from tempfile import TemporaryDirectory
import time
import unittest

from services.research_worker import (ServiceResearchJobs, WebResearchJobs, external_health,
                                     run_service, HEARTBEAT)
from test_research_runtime import Adapter, intent, profile


class PausedAdapter(Adapter):
    def prepare_phase(self, root, plan, phase, **kwargs):
        root = Path(root)
        (root / 'entered').touch()
        deadline = time.monotonic() + 20
        while not (root / 'release').exists():
            if kwargs.get('cancelled') and kwargs['cancelled']():
                return super().prepare_phase(root, plan, phase, **kwargs)
            if time.monotonic() > deadline:
                raise RuntimeError('Isolated fixture timeout')
            time.sleep(.03)
        if (root / 'fail_once').exists():
            (root / 'fail_once').unlink()
            raise RuntimeError('Isolated ordinary preparation failure')
        return super().prepare_phase(root, plan, phase, **kwargs)


def worker_main(root):
    try:
        code = run_service(root, jobs_factory=lambda r: ServiceResearchJobs(r, adapter=PausedAdapter()),
                           heartbeat_interval=.05)
    except RuntimeError as exc:
        print(str(exc), flush=True)
        code = 1
    raise SystemExit(code)


def web_main(root, pipe):
    from api.server import make_server
    server = make_server(root, research_jobs=WebResearchJobs(root, adapter=Adapter()))
    pipe.send(server.server_port)
    pipe.close()
    try:
        server.serve_forever()
    finally:
        server.server_close()


class SeparateServicesTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        self.processes = []; self.ctx = multiprocessing.get_context('spawn')
        (self.root / 'config').mkdir()
        (self.root / 'config/research_execution.json').write_text(json.dumps(profile()))
        self.addCleanup(self.cleanup)

    def cleanup(self):
        (self.root / 'release').touch()
        for p in self.processes:
            if p.is_alive(): p.terminate()
        for p in self.processes:
            p.join(3)
            if p.is_alive(): p.kill(); p.join(2)
        self.temp.cleanup()

    def start(self, target, *args):
        p = self.ctx.Process(target=target, args=args); p.start(); self.processes.append(p); return p

    def web(self):
        parent, child = self.ctx.Pipe(False)
        p = self.start(web_main, self.root, child); child.close()
        self.assertTrue(parent.poll(10)); self.port = parent.recv(); parent.close(); return p

    def request(self, method, path, body=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            c.request(method, path, json.dumps(body) if body is not None else None,
                      {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{self.port}'})
            r = c.getresponse(); return r.status, json.loads(r.read())
        finally: c.close()

    def wait(self, predicate, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = predicate()
            if value: return value
            time.sleep(.05)
        self.fail('Timed out waiting for isolated service evidence')

    def status(self, rid):
        return self.request('GET', '/api/experiments/' + rid)[1]['job']['status']

    def test_web_restart_does_not_stop_worker_and_results_are_retrievable(self):
        worker = self.start(worker_main, self.root); web = self.web()
        self.wait(lambda: external_health(self.root)['healthy'])
        r = intent(mode='TS')
        self.assertEqual(self.request('POST', '/api/experiments', r)[0], 202)
        self.wait(lambda: (self.root / 'entered').exists())
        self.assertNotEqual(worker.pid, web.pid)
        web.terminate(); web.join(3)
        self.assertTrue(worker.is_alive())
        (self.root / 'release').touch()
        jobs = WebResearchJobs(self.root, adapter=Adapter())
        self.wait(lambda: jobs.get(r['request_id'])['status'] == 'succeeded')
        self.web()
        self.assertEqual(self.status(r['request_id']), 'succeeded')
        code, results = self.request('GET', '/api/research-results/' + r['feature']['id'])
        self.assertEqual(code, 200); self.assertEqual(len(results['relationships']), 5)
        self.assertTrue(any(len(row['results']) == 2 for row in results['relationships']))
        self.assertEqual(self.request('POST', '/api/experiments', r)[0], 200)
        self.assertEqual(len(list((self.root / 'storage/catalog/submissions').glob('*.json'))), 1)
        self.assertTrue(list((self.root / 'storage/catalog/attempts').glob('*/events/*.json')))

    def test_crash_recovery_and_duplicate_worker_exclusion(self):
        worker = self.start(worker_main, self.root); self.web()
        self.wait(lambda: external_health(self.root)['healthy'])
        duplicate = self.start(worker_main, self.root); duplicate.join(5)
        self.assertEqual(duplicate.exitcode, 1)
        r = intent(mode='TS'); self.request('POST', '/api/experiments', r)
        self.wait(lambda: (self.root / 'entered').exists())
        worker.kill(); worker.join(3)
        self.assertFalse(external_health(self.root)['healthy'])
        (self.root / 'release').touch()
        self.start(worker_main, self.root)
        self.wait(lambda: self.status(r['request_id']) == 'succeeded')
        self.assertEqual(len(WebResearchJobs(self.root).store.results_for_recipe(r['feature']['id'])), 5)

    def test_graceful_drain_finishes_current_and_leaves_next_queued(self):
        worker = self.start(worker_main, self.root); self.web()
        self.wait(lambda: external_health(self.root)['healthy'])
        first = intent(mode='TS'); second = intent(mode='TS', direction='NEGATIVE')
        self.request('POST', '/api/experiments', first)
        self.wait(lambda: (self.root / 'entered').exists())
        self.request('POST', '/api/experiments', second)
        os.kill(worker.pid, signal.SIGTERM)
        self.wait(lambda: external_health(self.root)['state'] == 'draining')
        self.assertTrue(worker.is_alive())
        (self.root / 'release').touch()
        worker.join(15); self.assertEqual(worker.exitcode, 0)
        self.assertEqual(self.status(first['request_id']), 'succeeded')
        self.assertEqual(self.status(second['request_id']), 'queued')
        self.assertFalse(external_health(self.root)['healthy'])

    def test_ordinary_failure_resume_and_explicit_cancellation(self):
        self.start(worker_main, self.root); self.web()
        self.wait(lambda: external_health(self.root)['healthy'])
        r = intent(mode='TS'); self.request('POST', '/api/experiments', r)
        self.wait(lambda: (self.root / 'entered').exists())
        self.assertEqual(self.request('POST', '/api/experiments/' + r['request_id'] + '/cancel', {})[0], 200)
        self.wait(lambda: self.status(r['request_id']) == 'cancelled')
        (self.root / 'fail_once').touch(); (self.root / 'release').touch()
        self.request('POST', '/api/experiments/' + r['request_id'] + '/resume', {})
        self.wait(lambda: self.status(r['request_id']) == 'failed')
        self.request('POST', '/api/experiments/' + r['request_id'] + '/resume', {})
        self.wait(lambda: self.status(r['request_id']) == 'succeeded')

    def test_web_never_starts_worker_and_missing_stale_health_fails_closed(self):
        from api.server import make_server
        server = make_server(self.root)
        try:
            self.assertIsNone(server.research_jobs.thread)
            self.assertFalse(server.research_jobs.health()['healthy'])
            with self.assertRaises(RuntimeError): server.research_jobs.start()
            with self.assertRaises(ValueError): WebResearchJobs(self.root, start_worker=True)
            path = self.root / HEARTBEAT; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'workspace': str(self.root), 'pid': os.getpid(),
                                       'monotonic_ns': time.monotonic_ns() - 60_000_000_000, 'health': {'healthy': True}}))
            self.assertEqual(external_health(self.root)['state'], 'stale')
            value = json.loads(path.read_text()); value['monotonic_ns'] = time.monotonic_ns()
            path.write_text(json.dumps(value))
            self.assertFalse(external_health(self.root)['healthy'])  # live PID without service lock
            path.write_text('broken heartbeat')
            self.assertFalse(external_health(self.root)['healthy'])
        finally: server.server_close()

    def test_old_executor_is_not_disturbed(self):
        from research.store import lock
        with lock(self.root, 'research-executor'):
            with self.assertRaisesRegex(RuntimeError, 'existing executor is active'):
                run_service(self.root)
        self.assertFalse((self.root / HEARTBEAT).exists())
