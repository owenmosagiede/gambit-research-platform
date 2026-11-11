"""Prospective horizon and period changes preserve the old frozen contract."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json

from research.contracts import HORIZONS, canonical, profile_blockers, ref
from research.schedule import CONFIG, apply_schedule, load_schedule, period_for, resolved_periods
from runtime.research_jobs import ResearchJobs
from test_research_policy_inputs import scheduled_profile
from test_research_runtime import Adapter, KernelSpy, intent, profile


SCHEDULE_PATH = Path(__file__).resolve().parents[1] / (
    'definitions/research_specs/RSPEC_PROSPECTIVE_FX_HORIZONS/1.0.0.json')


class ScheduledAdapter(Adapter):
    def resolve_plan(self, root, intent, profile):
        plan = super().resolve_plan(root, intent, profile)
        plan.update(resolved_periods(profile, '2010-01-04'))
        return plan

    def prepare_phase(self, root, plan, phase, progress=None, cancelled=None, admission=None, *, horizon=None):
        prepared = super().prepare_phase(root, plan, phase, progress, cancelled, admission)
        prepared['period'] = period_for(plan, phase, horizon)
        return prepared

    def load_phase(self, root, plan, prepared, phase, horizon, admission=None):
        assert prepared['period'] == period_for(plan, phase, horizon)
        return super().load_phase(root, plan, prepared, phase, horizon, admission)


class ResearchScheduleTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'config').mkdir()
        self.schedule = json.loads(SCHEDULE_PATH.read_bytes())
        self.base = scheduled_profile(profile())
        self.base['exposure_classification'] = {'untouched_holdout_claim': False}
        self.ts = apply_schedule(self.base, self.schedule, price_time_series=True)

    def test_exact_definition_and_phase_boundaries(self):
        destination = self.root / SCHEDULE_PATH.relative_to(SCHEDULE_PATH.parents[3])
        destination.parent.mkdir(parents=True)
        destination.write_bytes(SCHEDULE_PATH.read_bytes())
        (self.root / CONFIG).write_bytes(canonical(ref(self.schedule)) + b'\n')
        self.assertEqual(load_schedule(self.root), self.schedule)
        self.assertFalse(profile_blockers(self.ts))
        plan = resolved_periods(self.ts, '2010-01-04')
        self.assertEqual(plan['horizons'], [1, 7, 21, 63])
        self.assertEqual(period_for(plan, 'P1', 63),
                         {'start_inclusive': '2010-01-04', 'end_exclusive': '2017-01-01'})
        self.assertEqual(period_for(plan, 'P2', 63),
                         {'start_inclusive': '2017-01-01', 'end_exclusive': '2025-01-01'})
        self.assertEqual(period_for(plan, 'P2', 21),
                         {'start_inclusive': '2022-01-01', 'end_exclusive': '2025-01-01'})
        new_pair = resolved_periods(self.ts, '2020-04-14')
        self.assertEqual(new_pair['horizons'], [1, 7, 21])
        self.assertEqual(new_pair['excluded_horizons'], {'63': 'NO_STRUCTURAL_DISCOVERY_HISTORY'})
        self.assertEqual(resolved_periods(self.base, '2010-01-04')['horizons'], list(HORIZONS))

    def test_queue_and_runner_freeze_each_horizon_period(self):
        (self.root / 'config/research_execution.json').write_bytes(canonical(self.ts) + b'\n')
        kernels, adapter = KernelSpy(), ScheduledAdapter()
        jobs = ResearchJobs(self.root, adapter=adapter, kernels=kernels)
        self.addCleanup(jobs.close)
        request = intent(mode='TS')
        queued, created = jobs.submit(request)
        self.assertTrue(created)
        self.assertEqual(queued['progress']['total'], 4)
        jobs.run_pending_once()
        result = jobs.get(request['request_id'])
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertEqual(set(kernels.calls), {(stage, h) for stage in ('P1', 'P2') for h in (1, 7, 21, 63)})
        self.assertEqual(adapter.preparations, ['P1', 'P1', 'P2', 'P2'])
        for summary in jobs.store.results_for_recipe(request['feature']['id']):
            for entry in summary['results']:
                key = jobs.store.resolve('trial', entry['authority'])['scientific_key']
                expected = period_for(resolved_periods(self.ts, '2010-01-04'), key['stage'], key['horizon'])
                self.assertEqual(key['period'], expected)
                self.assertEqual(key['prepared']['period'], expected)
