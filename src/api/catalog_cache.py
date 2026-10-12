"""Short-lived, single-flight cache for UI catalog projections only.

Never used by submission, preparation, observation retrieval or research. Responses
are immutable snapshots for at most five seconds; failures are never cached.
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
