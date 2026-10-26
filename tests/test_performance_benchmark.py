"""Ensure the offline benchmark cannot label changed evidence equivalent."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('performance_benchmark', Path(__file__).resolve().parents[1] / 'tools/benchmark_research_inputs.py')
benchmark = importlib.util.module_from_spec(spec); spec.loader.exec_module(benchmark)


class BenchmarkEvidenceTests(unittest.TestCase):
    @patch.object(benchmark, 'compare_saved_closures', return_value={'exact_saved_scientific_equality': True})
    def test_changed_inputs_calculation_access_or_decision_never_pass(self, compare_saved):
        before = {'case': 'diff1_positive', 'loaded_inputs_sha256': {'P1.1': 'rows-and-lineage'},
                  'complete_calculation_sha256': {'P1.1': 'all-artifacts-and-metrics'},
                  'phase_access': ['P1.1'], 'horizons': [{'horizon': 1, 'p1_status': 'rejected'}],
                  'end_to_end': {'wall_seconds': 20}, 'saved_scientific_closure': {'verified_separately': True}}
        after = deepcopy(before); after['end_to_end']['wall_seconds'] = 1
        self.assertTrue(benchmark.compare_reports(before, after)['exact_scientific_equality'])
        changes = {'loaded_inputs_sha256': {'P1.1': 'changed-lineage'},
                   'complete_calculation_sha256': {'P1.1': 'changed-metric'},
                   'phase_access': ['P1.1', 'P2.1'],
                   'horizons': [{'horizon': 1, 'p1_status': 'admitted'}], 'case': 'different'}
        for key, value in changes.items():
            with self.subTest(key=key):
                altered = deepcopy(after); altered[key] = value
                self.assertEqual(benchmark.compare_reports(before, altered)['differing_evidence'], [key])
        compare_saved.return_value = {'exact_saved_scientific_equality': False}
        self.assertEqual(benchmark.compare_reports(before, after)['differing_evidence'], ['saved_scientific_closure'])
        missing = deepcopy(before); missing.pop('saved_scientific_closure')
        with self.assertRaises(ValueError): benchmark.compare_reports(missing, after)
        before['loaded_inputs_sha256'] = {}
        with self.assertRaises(ValueError): benchmark.compare_reports(before, after)


if __name__ == '__main__': unittest.main()
