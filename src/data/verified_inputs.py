"""Bounded, execution-local reuse of verified immutable inputs.

No process-global cached data, disk cache, or persistent verification claims.
A context is discarded on restart, cancellation, failure or completion. Ordinary
values are private copies; compact lookups are recursively immutable. Both tiers
share the same total bound, with at most half reserved for compact lookups.
During member preparation one exact price entry is preferred over transient
ordinary entries; it receives no extra memory or relaxed witness checks.

A cache entry is published only after its ordinary independent verifier succeeds.
File identities (including ctime and resolved paths), negative definition lookup
directories and lineage catalog generations witness the exact reads. Hits check
those witnesses and propagate them into enclosing entries. Changed dependencies
evict the entry and run its full verifier again. No verification survives a phase
or request boundary, and standalone inspection remains independently verified.
"""
from collections import OrderedDict, Counter
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import date, timedelta
import sys
import json
import os
import stat
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from data.transformations.identity import digest, canonical_bytes
from research.performance import measure, counter, gauge

_CURRENT = ContextVar('verified_research_inputs', default=None)
_PHASE = ContextVar('verified_research_phase', default=None)
_DEPENDENCIES = ContextVar('verified_input_dependencies', default=None)


def dependency_capture():
    """Identity of a loader's read set, not a reusable verification claim.

    A reader may reuse its own records within this same load: publication still
    checks the whole read set after the verifier returns. A later or nested load
    has another identity and must independently read or use a guarded memo hit.
    """
    return _DEPENDENCIES.get()


class ChangedInput(ValueError):
    pass


def _stat_fields(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


class _WitnessPaths:
    """Share path traversal only within one complete witness validation.

    Every file still gets both lstat and stat. Shared parent resolutions are
    rechecked, together with every lexical ancestor's identity, before accepting
    the pass. Nothing here survives a validation pass or excuses a file check.
    """
    def __init__(self):
        self.parents = {}
        self.ancestors = {}
        self.literal_parents = set()

    @staticmethod
    def ancestor_identity(path):
        value = path.lstat()
        # A directory's unrelated children may legitimately change. Only its
        # path identity matters here; symlink replacement also checks ctime.
        return (_stat_fields(value) if stat.S_ISLNK(value.st_mode)
                else (value.st_dev, value.st_ino, value.st_mode))

    def resolve_regular(self, path):
        parent, name = os.path.split(path)
        if name in ('', '.', '..'):
            return str(Path(path).resolve())
        resolved_parent = self.parents.get(parent)
        if resolved_parent is None:
            parent_path = Path(parent)
            ancestors = (parent_path, *parent_path.parents)
            for ancestor in ancestors:
                if ancestor not in self.ancestors:
                    self.ancestors[ancestor] = self.ancestor_identity(ancestor)
            # Absolute ordinary directory paths already have their resolved
            # spelling once every ancestor is known to be a real directory.
            # Repeating realpath for hundreds of sibling event directories
            # needlessly traverses the same ancestors. Recheck all identities
            # below before accepting this pass; symlinks and dot-dot paths
            # retain the independent resolver, including its final recheck.
            ordinary = (parent_path.is_absolute() and not str(parent_path).startswith('//')
                        and '..' not in parent_path.parts
                        and all(stat.S_ISDIR(self.ancestors[p][2])
                                for p in ancestors))
            resolved_parent = str(parent_path) if ordinary else str(parent_path.resolve())
            self.parents[parent] = resolved_parent
            if ordinary:
                self.literal_parents.add(parent)
        # Preserve canonical spelling without rebuilding an identical string.
        # Relative, redundant-separator and symlink parents still use the
        # independently resolved spelling. All final witness checks remain.
        # split() strips repeated separators immediately before the basename.
        # Only reuse the input when exactly one separator remains there.
        if parent == resolved_parent and len(path) == len(parent) + len(name) + 1:
            return path
        return os.path.join(resolved_parent, name)

    def unchanged(self):
        try:
            return (all(self.ancestor_identity(path) == value for path, value in self.ancestors.items())
                    and all(path in self.literal_parents or str(Path(path).resolve()) == value
                            for path, value in self.parents.items()))
        except FileNotFoundError:
            return False


def _signature(path, paths=None):
    path = os.fspath(path)
    if not path or path.endswith(('/', '/.')) or '/./' in path:
        path = str(Path(path))
    try:
        link, target = os.lstat(path), os.stat(path)
    except FileNotFoundError:
        return None
    resolved = (paths.resolve_regular(path) if paths is not None and not stat.S_ISLNK(link.st_mode)
                else str(Path(path).resolve()))
    return _stat_fields(link), _stat_fields(target), resolved


def _unchanged(dependencies):
    paths = _WitnessPaths()
    try:
        return (all(_signature(path, paths) == signature for path, signature in dependencies.items())
                and paths.unchanged())
    except FileNotFoundError:
        return False


def _remember(path, signature):
    dependencies = _DEPENDENCIES.get()
    if dependencies is not None:
        path = path if isinstance(path, str) and path.startswith('/') else str(Path(path).absolute())
        if path in dependencies and dependencies[path] != signature:
            raise ChangedInput('Verified input changed during reading: ' + path)
        dependencies[path] = signature


def probe(path):
    """Capture negative lookups too: an appended conflicting definition matters."""
    dependencies = _DEPENDENCIES.get()
    if dependencies is not None:
        path = str(Path(path).absolute())
        if path not in dependencies:
            _remember(path, _signature(path))


def probe_definition(path):
    """An absent definition is witnessed by its nearest existing directory.

    Thousands of lineage IDs cannot be definitions. Their negative lookups can
    share the frozen registry-directory witness, while any newly added alias
    still changes that witness and forces independent resolution.
    """
    if _DEPENDENCIES.get() is None:
        return
    path = Path(path)
    while not path.exists() and path.parent != path:
        path = path.parent
    probe(path)


@contextmanager
def reading(path):
    dependencies = _DEPENDENCIES.get()
    if dependencies is None:
        yield
        return
    path = str(Path(path).absolute())
    if path in dependencies:
        # The first read's witness remains authoritative. Checking the complete
        # set at publication detects a change during any repeated read, without
        # resolving and stat-ing common registry/pack paths thousands of times.
        yield
        return
    _remember(path, _signature(path))
    try:
        yield
    finally:
        _remember(path, _signature(path))


def _freeze(value):
    """No mutable containers can escape the compact cache."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if value is None or type(value) in (str, bytes, bool, int, float):
        return value
    raise TypeError('Unsupported compact verified input value')


class VerifiedInputs:
    def __init__(self, root, implementation, *, max_bytes=128 * 1024 * 1024):
        self.root = str(Path(root).resolve())
        self.implementation = deepcopy(implementation)
        self.max_bytes = max_bytes
        self.bytes = 0
        self.entries = OrderedDict()
        self.compact_entries = OrderedDict()
        self.compact_bytes = 0
        self.compact_limit = max_bytes // 2
        self.high_water_bytes = 0
        self.active_phase = None
        self.retained_price = None
        self.counts = Counter()
        self.seconds = Counter()

    def memo(self, kind, key, loader, *, compact=False, within_capture=False):
        phase = _PHASE.get()
        if phase is None:
            return _freeze(loader()) if compact else loader()
        with measure('inputs.hashing'):
            identity = (phase['key'], kind, digest(key))
        entries = self.compact_entries if compact else self.entries
        if identity in entries:
            value, size, dependencies = entries[identity]
            with measure('inputs.cache_witness'):
                counter('cache.witness_checks', len(dependencies))
                capture = _DEPENDENCIES.get()
                # A definition-directory lookup can recur thousands of times
                # inside one independent verifier. If this exact read set is
                # already witnessed by that enclosing loader, it will check
                # every dependency before publishing its result. Like reading()
                # above, reuse within that same capture needs no extra stat pass.
                # Never use this for cancellation or across independent loads.
                captured = (within_capture and bool(dependencies) and capture is not None
                            and all(path in capture and capture[path] == value
                                    for path, value in dependencies.items()))
                valid = captured or _unchanged(dependencies)
                if captured:
                    counter('cache.' + kind + '.within_capture_hits')
            if not valid:
                self._remove(entries, identity, compact)
                self.counts[kind + '.invalidations'] += 1
                counter('cache.' + kind + '.invalidations')
            else:
                for path, signature in dependencies.items():
                    _remember(path, signature)
                self.counts[kind + '.hits'] += 1
                counter('cache.' + kind + '.hits')
                entries.move_to_end(identity)
                if compact:
                    return value
                with measure('inputs.copy'):
                    return deepcopy(value)
        self.counts[kind + '.misses'] += 1
        counter('cache.' + kind + '.misses')
        start = perf_counter()
        dependencies = {}
        token = _DEPENDENCIES.set(dependencies)
        try:
            with measure('cache.load.' + kind):
                value = loader()
        finally:
            _DEPENDENCIES.reset(token)
        with measure('inputs.cache_witness'):
            counter('cache.witness_checks', len(dependencies))
            if not _unchanged(dependencies):
                raise ChangedInput('Verified input changed before cache publication')
        for path, signature in dependencies.items():
            _remember(path, signature)
        self.seconds[kind] += perf_counter() - start
        self.counts[kind + '.loads'] += 1
        counter('cache.' + kind + '.loads')
        with measure('inputs.copy'):
            stored = _freeze(value) if compact else deepcopy(value)
        size = retained_size((identity, stored, dependencies))
        limit = self.compact_limit if compact else self.max_bytes - self.compact_bytes
        if size <= limit:
            if compact:
                while self.compact_entries and self.compact_bytes + size > self.compact_limit:
                    self._evict(self.compact_entries, True)
            while self.entries and self.bytes + size > self.max_bytes:
                if not self._evict(self.entries, False):
                    break
            if self.bytes + size > self.max_bytes:
                # Transient payloads/series must not evict the current member's
                # expensive verified history. Compute normally without retaining
                # this value; the total cache budget is never extended.
                self.counts['retention_bypasses'] += 1
                counter('cache.retention_bypasses')
                return stored if compact else value
            entries[identity] = (stored, size, dependencies)
            self.bytes += size
            if compact:
                self.compact_bytes += size
            self.high_water_bytes = max(self.high_water_bytes, self.bytes)
            gauge('cache.retained_bytes', self.bytes)
            gauge('cache.compact_retained_bytes', self.compact_bytes)
        else:
            self.counts['oversize'] += 1
            counter('cache.oversize')
        return stored if compact else value

    def _remove(self, entries, identity, compact):
        _, size, _ = entries.pop(identity)
        self.bytes -= size
        if compact:
            self.compact_bytes -= size

    def _evict(self, entries, compact):
        identity = next((key for key in entries if compact or key != self.retained_price), None)
        if identity is None:
            return False
        self._remove(entries, identity, compact)
        self.counts['evictions'] += 1
        self.counts[identity[1] + '.evictions'] += 1
        counter('cache.evictions')
        counter('cache.' + identity[1] + '.evictions')
        return True

    def clear(self):
        self.entries.clear()
        self.compact_entries.clear()
        self.bytes = 0
        self.compact_bytes = 0
        self.retained_price = None
        gauge('cache.retained_bytes', 0)
        gauge('cache.compact_retained_bytes', 0)


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


def phase_active(root):
    return current(root) is not None and _PHASE.get() is not None


@contextmanager
def verified_read(root):
    """Validate a complete read-only closure before its caller can publish.

    This retains no result or verification claim. A fresh capture checks every
    dependency at the end of each closure, and propagates them to an enclosing
    verifier if present. Repeated lookups within this one read can share their
    evidence; another closure, phase or standalone read cannot inherit it.
    """
    if not phase_active(root):
        yield
        return
    dependencies = {}
    token = _DEPENDENCIES.set(dependencies)
    try:
        try:
            yield
        finally:
            _DEPENDENCIES.reset(token)
        with measure('inputs.cache_witness'):
            counter('cache.witness_checks', len(dependencies))
            if not _unchanged(dependencies):
                raise ChangedInput('Verified closure changed before acceptance')
        for path, signature in dependencies.items():
            _remember(path, signature)
    finally:
        # Readers may retain this capture's identity, but never its ended read
        # set. Propagation above copies witnesses into the enclosing capture.
        dependencies.clear()


def memo(root, kind, key, loader):
    context = current(root)
    return loader() if context is None else context.memo(kind, key, loader)


def compact_memo(root, kind, key, loader, *, within_capture=False):
    context = current(root)
    return _freeze(loader()) if context is None else context.memo(
        kind, key, loader, compact=True, within_capture=within_capture)


def record_memo(root, kind, key, loader, *, within_capture=False):
    """Retain small verified JSON records without bulk-payload eviction.

    Canonical bytes are immutable and charged to the existing compact/total
    budgets. Decode a private value on every read; all ordinary dependency and
    phase checks still apply. Standalone readers keep their ordinary verifier.
    """
    if current(root) is None or _PHASE.get() is None:
        return loader()
    data = compact_memo(root, kind, key, lambda: canonical_bytes(loader()),
                        within_capture=within_capture)
    return json.loads(data)


def phase_end(root, fallback):
    phase = _PHASE.get()
    return phase['end'] if current(root) is not None and phase else fallback


def verified_prices(store, binding, policy, loader):
    def verify():
        with measure('source_prices.verify'):
            return loader(store, binding, policy)
    if current(store.root) is None or _PHASE.get() is None:
        return verify()
    def encoded():
        first = []
        def prove():
            snapshot, prices = verify()
            with measure('inputs.price_encode'):
                data = canonical_bytes([snapshot, prices])
            first.append(data)
            # Only the independent source replay can create this evidence. Its
            # complete dependency witnesses are retained by compact_memo, under
            # the same phase/executor/root and total byte bound as other inputs.
            return sha256(data).hexdigest()
        proof = compact_memo(store.root, 'price_proof',
                             {'snapshot': binding, 'policy': policy}, prove)
        if first:
            return first[0]
        # A valid proof can outlive the large price buffer. Reload exact pinned
        # bytes with the ordinary member checksum/row validation, then bind the
        # entire decoded record and rows to the independently reproduced result.
        # The proof's witnesses propagate into the enclosing prices capture:
        # publication checks them again AFTER this read, including negative
        # definition probes, raw source files and all upstream lineage payloads.
        from data.fx_records import read_rows
        with measure('source_prices.reload'):
            snapshot = store.resolve(binding)
            prices = read_rows(store, snapshot['body']['members'])
            data = canonical_bytes([snapshot, prices])
            if sha256(data).hexdigest() != proof:
                raise ChangedInput('Reloaded prices differ from independently verified source evidence')
            return data
    data = memo(store.root, 'prices', {'snapshot': binding, 'policy': policy}, encoded)
    with measure('inputs.price_decode'):
        snapshot, prices = json.loads(data)
    return snapshot, prices


@contextmanager
def retain_price_inputs(root, binding, policy):
    """Prefer one member's price history within the existing shared byte limit.

    This is an eviction preference, never a verification exemption: every hit
    still checks and propagates all witnesses. Oversize inputs still use their
    full verifier without retention. No value escapes an execution/phase change.
    """
    context, phase = current(root), _PHASE.get()
    if context is None or phase is None:
        yield
        return
    previous = context.retained_price
    identity = (phase['key'], 'prices', digest({'snapshot': binding, 'policy': policy}))
    context.retained_price = identity
    try:
        yield
    finally:
        context.retained_price = previous if context.active_phase == phase['key'] else None


def retained_size(value):
    """Account retained Python containers/values, including shared references once."""
    seen = set()
    def count(item):
        if id(item) in seen:
            return 0
        seen.add(id(item))
        total = sys.getsizeof(item)
        if isinstance(item, Mapping):
            total += sum(count(k) + count(v) for k, v in item.items())
            if isinstance(item, MappingProxyType):
                total += sys.getsizeof(dict(item))  # include the owned backing dict
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
