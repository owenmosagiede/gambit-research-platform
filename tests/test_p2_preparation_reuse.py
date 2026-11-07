"""Independent Feature proof and execution history invalidation boundaries."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data.verified_inputs import execution_inputs, phase_inputs, memo
from data import fx_feature_store as fx
from research import inputs
from research.contracts import canonical, digest, ResearchError
from runtime.research_jobs import ResearchJobs
import test_verified_inputs as fixtures


class FeatureProofTests(unittest.TestCase):
    setUp = fixtures.VerifiedPreparationTests.setUp
    def test_compact_proof_outlives_observations_but_not_changed_source(self):
        plan = self.f.plan()
        prepared = inputs.prepare_phase(self.root, plan, 'P1')
        binding = prepared['members'][0]['materializations'][0]
        with execution_inputs(self.root, 'code') as cache, phase_inputs(self.root, plan, 'P1'):
            with patch.object(fx, '_read_fx_materialization', wraps=fx._read_fx_materialization) as verify:
                first = fx.read_fx_materialization(self.root, binding['id'], research=True)
                for identity in list(cache.entries):
                    cache._remove(cache.entries, identity, False)
                second = fx.read_fx_materialization(self.root, binding['id'], research=True)
                self.assertEqual(second, first)
                self.assertEqual(verify.call_count, 1)
                second['observations'][0]['value'] = 'caller mutation'
                self.assertEqual(fx.read_fx_materialization(self.root, binding['id'], research=True), first)
                part = first['manifest']['partitions'][0]; h = part['blob_sha256']
                path = self.root/'storage/payloads/sha256'/h[:2]/(h+'.'+part['format'])
                stamp = path.stat()
                path.write_bytes(b'!' * stamp.st_size)
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                with self.assertRaises(Exception):
                    fx.read_fx_materialization(self.root, binding['id'], research=True)
                self.assertEqual(verify.call_count, 2)
                self.assertLessEqual(cache.bytes, cache.max_bytes)

    def test_proof_eviction_phase_change_and_standalone_repeat_full_verifier(self):
        plan = self.f.plan()
        prepared = inputs.prepare_phase(self.root, plan, 'P1')
        binding = prepared['members'][0]['materializations'][0]
        with patch.object(fx, '_read_fx_materialization', wraps=fx._read_fx_materialization) as verify:
            with execution_inputs(self.root, 'code') as cache:
                with phase_inputs(self.root, plan, 'P1'):
                    original = fx.read_fx_materialization(self.root, binding['id'], research=True)
                    cache.clear()
                    self.assertEqual(fx.read_fx_materialization(self.root, binding['id'], research=True), original)
                with phase_inputs(self.root, plan, 'P2'):
                    self.assertEqual(fx.read_fx_materialization(self.root, binding['id'], research=True), original)
                standalone = fx.read_fx_materialization(self.root, binding['id'])
                self.assertEqual(standalone['observations'], original['observations'])
            self.assertEqual(verify.call_count, 4)


class EventHistoryTests(unittest.TestCase):
    def test_unchanged_reuse_append_cancel_tamper_and_restart(self):
        from test_research_runtime import RuntimeTests, intent, Adapter
        fixture = RuntimeTests(); fixture.setUp(); self.addCleanup(fixture.tearDown)
        jobs = ResearchJobs(fixture.root, adapter=Adapter())
        rid = intent()['request_id']
        jobs.submit(intent(rid))
        plan = {'plan_id':'isolated', 'periods':{p:{'end_exclusive':e} for p,e in
                [('P1','2020-01-01'),('P2','2023-01-01')]}}
        with execution_inputs(fixture.root, 'code'), phase_inputs(fixture.root, plan, 'P2'):
            with patch.object(jobs, '_event_snapshot', wraps=jobs._event_snapshot) as replay:
                first = jobs._events(rid)
                self.assertEqual(jobs._events(rid), first)
                self.assertEqual(replay.call_count, 1)
                # The ordinary writer appends a cancellation event. It must be
                # visible immediately, without process cooperation or a TTL.
                jobs.cancel(rid)
                self.assertTrue(jobs._cancelled(rid))
                self.assertEqual(replay.call_count, 2)
                event = first[0]
                path = next((fixture.root/'storage/catalog/attempts').glob('*/events/RESEVENT_'+digest(event)+'.json'))
                stamp = path.stat(); damaged = deepcopy(event); damaged['previous'] = 'tampered'
                path.write_bytes(canonical(damaged))
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                with self.assertRaises(ResearchError): jobs._events(rid)
        with self.assertRaises(ResearchError): ResearchJobs(fixture.root)._events(rid)

    def test_new_attempt_unreadable_unrelated_event_and_removed_event_invalidate(self):
        from test_research_runtime import RuntimeTests, intent, Adapter
        fixture = RuntimeTests(); fixture.setUp(); self.addCleanup(fixture.tearDown)
        jobs = ResearchJobs(fixture.root, adapter=Adapter())
        request = intent(); jobs.submit(request); rid = request['request_id']
        plan = {'plan_id':'isolated','periods':{'P2':{'end_exclusive':'2023-01-01'}}}
        with execution_inputs(fixture.root,'code'), phase_inputs(fixture.root,plan,'P2'):
            original = jobs._events(rid)
            parent = fixture.root/'storage/catalog/attempts/new-attempt/events'
            parent.mkdir(parents=True)
            bad = parent/('RESEVENT_'+'a'*64+'.json'); bad.write_text('{broken')
            with self.assertRaises(ResearchError): jobs._events(rid)
            bad.unlink()
            self.assertEqual(jobs._events(rid),original)
            path = next((fixture.root/'storage/catalog/attempts').glob('*/events/RESEVENT_'+digest(original[0])+'.json'))
            path.unlink()
            self.assertEqual(jobs._events(rid),[])


if __name__ == '__main__': unittest.main()
