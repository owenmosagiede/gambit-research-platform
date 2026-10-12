"""Bounded, execution-local reuse of verified immutable inputs.

No process-global cached data, disk cache, or persistent verification claims.
A context is discarded on restart, cancellation, failure or completion. Returned
values are private copies: downstream calculations cannot mutate cached evidence.
"""
from collections import OrderedDict, Counter
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import date, timedelta
import sys
from pathlib import Path
from time import perf_counter
from data.transformations.identity import digest

_CURRENT = ContextVar('verified_research_inputs', default=None)
_PHASE = ContextVar('verified_research_phase', default=None)


class VerifiedInputs:
    def __init__(self, root, implementation, *, max_bytes=128 * 1024 * 1024):
        self.root = str(Path(root).resolve())
        self.implementation = deepcopy(implementation)
        self.max_bytes = max_bytes
        self.bytes = 0
        self.entries = OrderedDict()
        self.active_phase = None
        self.counts = Counter()
        self.seconds = Counter()

    def memo(self, kind, key, loader):
        phase = _PHASE.get()
        if phase is None:
            return loader()
        identity = (phase['key'], kind, digest(key))
        if identity in self.entries:
            self.counts[kind + '.hits'] += 1
            value, size = self.entries.pop(identity)
            self.entries[identity] = (value, size)
            return deepcopy(value)
        start = perf_counter()
        # A failed loader never publishes a verification result.
        value = loader()
        self.seconds[kind] += perf_counter() - start
        self.counts[kind + '.loads'] += 1
        size = retained_size(value)
        if size <= self.max_bytes:
            while self.entries and self.bytes + size > self.max_bytes:
                _, (_, removed) = self.entries.popitem(last=False)
                self.bytes -= removed
                self.counts['evictions'] += 1
            self.entries[identity] = (deepcopy(value), size)
            self.bytes += size
        else:
            self.counts['oversize'] += 1
        return value

    def clear(self):
        self.entries.clear()
        self.bytes = 0


@contextmanager
def execution_inputs(root, implementation, **kwargs):
    context = VerifiedInputs(root, implementation, **kwargs)
    token = _CURRENT.set(context)
    try:
        yield context
    finally:
        context.clear()
        _CURRENT.reset(token)


@contextmanager
def phase_inputs(root, plan, phase):
    context = current(root)
    if context is None:
        yield
        return
    period = plan['periods'][phase]
    # plan_id is verified by the caller before entering this namespace.
    key = digest({'plan': plan['plan_id'], 'phase': phase,
                  'period': period, 'implementation': context.implementation})
    if context.active_phase != key:
        context.clear()
        context.active_phase = key
    token = _PHASE.set({'key': key,
        'end': (date.fromisoformat(period['end_exclusive']) - timedelta(days=1)).isoformat()})
    try:
        yield
    finally:
        _PHASE.reset(token)


def current(root):
    value = _CURRENT.get()
    return value if value is not None and value.root == str(Path(root).resolve()) else None


def memo(root, kind, key, loader):
    context = current(root)
    return loader() if context is None else context.memo(kind, key, loader)


def phase_end(root, fallback):
    phase = _PHASE.get()
    return phase['end'] if current(root) is not None and phase else fallback


def verified_prices(store, binding, policy, loader):
    return memo(store.root, 'prices', {'snapshot': binding, 'policy': policy},
                lambda: loader(store, binding, policy))


def retained_size(value):
    """Account retained Python containers/values, including shared references once."""
    seen = set()
    def count(item):
        if id(item) in seen:
            return 0
        seen.add(id(item))
        total = sys.getsizeof(item)
        if isinstance(item, dict):
            total += sum(count(k) + count(v) for k, v in item.items())
        elif isinstance(item, (tuple, list, set, frozenset)):
            total += sum(count(v) for v in item)
        return total
    return count(value)


@contextmanager
def fresh_inputs():
    """Standalone integrity inspection cannot inherit a worker's verification cache."""
    token = _CURRENT.set(None)
    try:
        yield
    finally:
        _CURRENT.reset(token)
