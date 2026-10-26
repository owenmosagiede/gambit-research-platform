"""Ensure the offline benchmark cannot label changed evidence equivalent."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('performance_benchmark', Path(__file__).resolve().parents[1] / 'tools/benchmark_research_inputs.py')
benchmark = importlib.util.module_from_spec(spec); spec.loader.exec_module(benchmark)


class BenchmarkEvidenceTests(unittest.TestCase):
    def test_changed_inputs_calculation_access_or_decision_never_pass(self):
        before = {'case': 'diff1_positive', 'loaded_inputs_sha256': {'P1.1': 'rows-and-lineage'},
                  'complete_calculation_sha256': {'P1.1': 'all-artifacts-and-metrics'},
                  'phase_access': ['P1.1'], 'horizons': [{'horizon': 1, 'p1_status': 'rejected'}],
                  'end_to_end': {'wall_seconds': 20}}
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
        before['loaded_inputs_sha256'] = {}
        with self.assertRaises(ValueError): benchmark.compare_reports(before, after)


if __name__ == '__main__': unittest.main()
