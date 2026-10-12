"""Bounded, single-flight caches for UI catalog projections only.

Never used by submission, preparation, observation retrieval or research. Responses
use a five-second TTL by default. Signal/Feature catalogs also check their exact
read dependencies on every request, with a five-minute full verification limit.
Failures and partial/unavailable views are never retained by that cache.
"""
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from threading import Lock
from time import monotonic


class CatalogCache:
    def __init__(self, ttl=5.0, limit=32, clock=monotonic):
        self.ttl, self.limit, self.clock = ttl, limit, clock
        self.lock = Lock()
        self.entries = OrderedDict()
        self.pending = {}
        self.verified_entries = OrderedDict()

    def get_verified(self, key, root, read, *, max_age=300.0):
        from pathlib import Path
        from data.catalog_reads import catalog_reads, CatalogChanged
        key = ('verified', str(Path(root).resolve()), key)
        with self.lock:
            cached = self.verified_entries.get(key)
            future = self.pending.get(key)
            owner = future is None
            if owner:
                future = self.pending[key] = Future()
        if not owner:
            return deepcopy(future.result())
        try:
            # File IO and verification do not hold the cache's global lock.
            if cached and self.clock() - cached[0] < max_age and cached[2].unchanged():
                with self.lock:
                    # Another catalog may evict this entry during dependency IO.
                    # The verified local value is still safe for this response.
                    if key in self.verified_entries:
                        self.verified_entries.move_to_end(key)
                result = cached[1]
            else:
                with self.lock:
                    self.verified_entries.pop(key, None)
                for attempt in range(2):
                    try:
                        with catalog_reads(root) as dependencies:
                            result = read()
                        if not dependencies.unchanged():
                            raise CatalogChanged('Catalog changed during reading')
                        break
                    except CatalogChanged:
                        if attempt:
                            raise
                if not result.get('issues'):
                    with self.lock:
                        self.verified_entries[key] = (self.clock(), deepcopy(result), dependencies)
                        self.verified_entries.move_to_end(key)
                        while len(self.verified_entries) > self.limit:
                            self.verified_entries.popitem(last=False)
            future.set_result(result)
            return deepcopy(result)
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self.lock:
                self.pending.pop(key, None)

    def get(self, key, read):
        with self.lock:
            cached = self.entries.get(key)
            if cached and self.clock() - cached[0] < self.ttl:
                self.entries.move_to_end(key)
                return deepcopy(cached[1])
            future = self.pending.get(key)
            owner = future is None
            if owner:
                future = self.pending[key] = Future()
        if not owner:
            return deepcopy(future.result())
        try:
            result = read()
            with self.lock:
                self.entries[key] = (self.clock(), deepcopy(result))
                self.entries.move_to_end(key)
                while len(self.entries) > self.limit:
                    self.entries.popitem(last=False)
            future.set_result(result)
            return deepcopy(result)
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self.lock:
                self.pending.pop(key, None)
