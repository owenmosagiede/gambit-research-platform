"""Opt-in operational measurements, separate from immutable scientific records.

No paths, request contents, observations or scientific values are collected.
Intervals are inclusive (nested measurements must not be summed). CPU values
use the current thread, so unrelated web/worker activity is not attributed here.
The context is never enabled by an environment variable or at import time.
"""
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import math
import re
import resource
import sys
import time

_CURRENT = ContextVar('research_performance', default=None)
_NAME = re.compile(r'[a-zA-Z][a-zA-Z0-9_.-]{0,95}\Z')


def _name(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError('Performance names must be fixed operational labels')
    return value


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Performance values must be finite numbers')
    return value


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == 'darwin' else value * 1024)


class Profile:
    def __init__(self):
        self.timings = {}
        self.counters = Counter()
        self.gauges = {}
        self.started_wall = time.perf_counter()
        self.started_cpu = time.thread_time()
        self.finished_wall = None
        self.finished_cpu = None

    def report(self):
        return deepcopy({
            'schema': 'research_operational_performance_v1',
            'wall_seconds': (self.finished_wall or time.perf_counter()) - self.started_wall,
            'thread_cpu_seconds': (self.finished_cpu or time.thread_time()) - self.started_cpu,
            'peak_process_rss_bytes': peak_rss_bytes(),
            'timings': dict(sorted(self.timings.items())),
            'counters': dict(sorted(self.counters.items())),
            'gauges': dict(sorted(self.gauges.items())),
            'measurement_rules': {'intervals': 'inclusive; do not sum nested names',
                                  'cpu': 'current thread',
                                  'rss': 'process lifetime high-water mark'},
        })


@contextmanager
def profiling(*, join_existing=False):
    """Enable measurements here; callers may explicitly join an outer benchmark."""
    existing = _CURRENT.get()
    if join_existing and existing is not None:
        yield existing
        return
    profile = Profile()
    token = _CURRENT.set(profile)
    try:
        yield profile
    finally:
        profile.finished_wall = time.perf_counter()
        profile.finished_cpu = time.thread_time()
        _CURRENT.reset(token)


@contextmanager
def measure(name):
    profile = _CURRENT.get()
    if profile is None:
        yield
        return
    name = _name(name)
    wall, cpu = time.perf_counter(), time.thread_time()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        timing = profile.timings.setdefault(name, {'calls': 0, 'wall_seconds': 0.0,
                                                  'thread_cpu_seconds': 0.0, 'failures': 0})
        timing['calls'] += 1
        timing['wall_seconds'] += time.perf_counter() - wall
        timing['thread_cpu_seconds'] += time.thread_time() - cpu
        timing['failures'] += int(failed)


def counter(name, amount=1):
    profile = _CURRENT.get()
    if profile is not None:
        profile.counters[_name(name)] += _number(amount)


def gauge(name, value):
    """Retain the latest and highest observed value; bounded fixed-label cardinality."""
    profile = _CURRENT.get()
    if profile is not None:
        name, value = _name(name), _number(value)
        old = profile.gauges.get(name)
        profile.gauges[name] = {'last': value, 'maximum': max(value, old['maximum']) if old else value}
