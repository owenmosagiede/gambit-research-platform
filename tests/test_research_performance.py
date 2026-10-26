"""Operational instrumentation must not collect data or alter scientific work."""
import unittest
from research.performance import counter, gauge, measure, profiling


class PerformanceTests(unittest.TestCase):
    def test_disabled_is_noop_and_exceptions_propagate(self):
        counter('unused'); gauge('unused', 1)
        with self.assertRaisesRegex(RuntimeError, 'scientific failure'):
            with measure('work'):
                raise RuntimeError('scientific failure')

    def test_counts_timings_and_bounded_gauge_are_copied(self):
        with profiling() as profile:
            with measure('inputs.load'):
                counter('cache.hit', 2); gauge('cache.bytes', 10)
                gauge('cache.bytes', 4)
            with self.assertRaises(ValueError):
                with measure('inputs.load'):
                    raise ValueError('unchanged failure')
        report = profile.report()
        self.assertEqual(report['counters'], {'cache.hit': 2})
        self.assertEqual(report['gauges']['cache.bytes'], {'last': 4, 'maximum': 10})
        self.assertEqual(report['timings']['inputs.load']['calls'], 2)
        self.assertEqual(report['timings']['inputs.load']['failures'], 1)
        self.assertGreater(report['peak_process_rss_bytes'], 0)
        report['counters']['cache.hit'] = 100
        self.assertEqual(profile.report()['counters']['cache.hit'], 2)

    def test_nested_contexts_do_not_share_counters(self):
        with profiling() as outer:
            counter('outer')
            with profiling() as inner:
                counter('inner')
            counter('outer')
        self.assertEqual(outer.report()['counters'], {'outer': 2})
        self.assertEqual(inner.report()['counters'], {'inner': 1})

    def test_rejects_observation_paths_and_nonfinite_values(self):
        with profiling():
            for label in ('/private/data', 'request id', '', 'a' * 97):
                with self.assertRaises(ValueError): counter(label)
            for value in (float('nan'), float('inf'), True, {'observation': 1}):
                with self.assertRaises(ValueError): gauge('safe', value)

    def test_explicit_join_preserves_outer_lifetime(self):
        with profiling() as outer:
            with profiling(join_existing=True) as joined:
                self.assertIs(joined, outer)
                counter('worker.attempt')
            self.assertIsNone(outer.finished_wall)
            counter('after.attempt')
        self.assertEqual(outer.report()['counters'], {'worker.attempt': 1, 'after.attempt': 1})


if __name__ == '__main__': unittest.main()
