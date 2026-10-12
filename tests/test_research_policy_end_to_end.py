"""Real v2 Submit execution on isolated synthetic stores, with actual date gaps."""
from copy import deepcopy
from datetime import date, timedelta
import json
import unittest

import test_research_end_to_end as fixture_module
from test_research_policy_inputs import scheduled_profile
from data.transformations.identity import reference
from research import inputs
from research.contracts import canonical, ref
from runtime.research_jobs import ResearchJobs


class ResearchPolicyEndToEndTests(unittest.TestCase):
    def test_immutable_v2_profile_executes_five_scoped_horizons_with_real_date_gaps(self):
        # Compose the existing fixture without inheriting and rediscovering its
        # tests. Only source admission/catalog discovery are synthetic boundaries.
        fixture = fixture_module.StoredResearchEndToEndTests(methodName='runTest')
        source_read = fixture.price
        missing_dates = {'2021-03-17', '2021-07-06', '2022-02-14'}
        def with_gaps(store, binding, policy, verify_rows=True):
            snapshot, prices = source_read(store, binding, policy, verify_rows=verify_rows)
            if verify_rows and snapshot['body']['instrument_id'] == 'AUDUSD':
                prices = [row for row in prices if row['reference_time'] not in missing_dates]
            return snapshot, prices
        fixture.price = with_gaps
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        profile = scheduled_profile(fixture.profile)
        profile['id'] = 'RSPEC_ISOLATED_SCHEDULED_WEEKDAY_END_TO_END'
        selection = profile['target_selection']
        selection.update(selection_scope='registered_fx_registry',
            source_snapshots={item['instrument_id']: item['price_snapshot'] for item in fixture.current},
            materializations={symbol: {} for symbol in fixture.symbols})
        store = inputs.TargetStore(fixture.root)
        for path in (fixture.root / 'storage/catalog/target_store').glob('*/manifest.json'):
            manifest = json.loads(path.read_bytes())
            definition = store.resolve(manifest['definition'])
            symbol = store.resolve(manifest['price_snapshot'])['body']['instrument_id']
            selection['materializations'][symbol][str(definition['body']['horizon']['amount'])] = reference(manifest)
        definition_path = fixture.root / 'definitions/research_specs' / profile['id'] / (profile['version'] + '.json')
        definition_path.parent.mkdir(parents=True)
        definition_path.write_bytes(canonical(profile) + b'\n')
        (fixture.root / 'config/research_execution.json').write_bytes(canonical({'research_spec': ref(profile)}) + b'\n')
        fixture.profile = deepcopy(profile)
        # Includes independent price/log-difference and endpoint-return arithmetic,
        # all five relationships, admitted real P2 execution, durable artifacts,
        # null availability, phase-safe endpoints and duplicate-request prevention.
        fixture.test_complete_cs_submit_uses_stored_values_real_kernels_and_durable_links()
        jobs = ResearchJobs(fixture.root); self.addCleanup(jobs.close)
        results = jobs.store.results_for_recipe(fixture.recipe['id'])
        self.assertEqual(len(results), 5)
        p2_count = 0
        for relationship in results:
            self.assertEqual(relationship['mode'], 'CS')
            for summary in relationship['results']:
                trial = jobs.store.resolve('trial', summary['authority'])
                self.assertEqual(trial['scientific_key']['research_spec']['version'], '2.0.0')
                if summary['stage'] == 'P2':
                    p2_count += 1
                    self.assertEqual(trial['body']['missing_evidence_policy'], 'unresolved_required_v1')
                    self.assertEqual(summary['metrics']['scheduled_hac']['policy'], 'scheduled_weekday_hac_v2')
                else:
                    self.assertEqual(summary['metrics']['hac_clock'], 'scheduled_weekday_hac_v2')
        self.assertGreaterEqual(p2_count, 1)
        seven = next(result for result in results if result['horizon'] == 7)
        p1 = next(result for result in seven['results'] if result['stage'] == 'P1')
        trial = jobs.store.resolve('trial', p1['authority'])
        artifact = jobs.store.verify_artifact(trial['body']['artifact_manifests'][0])
        member = next(row for row in artifact['members'] if row['role'] == 'scheduled_hac')
        sha = member['blob_sha256']
        diagnostics = json.loads((fixture.root / f'storage/payloads/sha256/{sha[:2]}/{sha}.json').read_bytes())
        self.assertEqual(diagnostics['policy'], 'scheduled_weekday_hac_v2')
        self.assertEqual(diagnostics['maxlags'], 6)
        self.assertGreater(diagnostics['missing_scheduled_period_count'], 0)
        self.assertTrue(missing_dates.isdisjoint(diagnostics['usable_dates']))
        counts = {row['lag']: row['pair_count'] for row in diagnostics['lag_pair_counts']}
        dates = {date.fromisoformat(text) for text in diagnostics['usable_dates']}
        # Count actual previous weekdays independently of retained-array indexing.
        expected_pairs = 0
        for day in dates:
            previous = day - timedelta(days=1)
            while previous.weekday() >= 5: previous -= timedelta(days=1)
            expected_pairs += previous in dates
        self.assertEqual(counts[1], expected_pairs)
        self.assertLess(counts[1], diagnostics['usable_observation_count'] - 1)
        submission_path, = (fixture.root / 'storage/catalog/submissions').glob('*.json')
        submission = json.loads(submission_path.read_bytes())
        self.assertEqual(submission['research_spec'], profile)
        job = jobs.get(submission['request_id'])
        plan = jobs.store.resolve('plan', job['plan'])['body']
        self.assertEqual(plan['periods']['P1']['start_inclusive'], '2020-10-01')
        self.assertIsNone(plan['profile']['periods']['P1']['start_inclusive'])
        self.assertEqual(plan['profile']['target_selection'], selection)
        self.assertEqual(definition_path.read_bytes(), canonical(profile) + b'\n')


if __name__ == '__main__': unittest.main()
