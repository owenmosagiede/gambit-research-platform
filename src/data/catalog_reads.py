"""Dependencies for read-only UI projections, never scientific execution reuse.

An API cache opens this context while running the existing verified readers.
It records exact file identities and directory-query membership, including
ctime so a same-size edit with a restored mtime still invalidates the view.
Nothing is persisted and no writer must cooperate with invalidation.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_CURRENT = ContextVar('ui_catalog_reads', default=None)


def catalog_read_active():
    return _CURRENT.get() is not None


class CatalogChanged(ValueError):
    """The catalog changed while a projection was being constructed."""


def _signature(path):
    link = path.lstat()
    target = path.stat()
    def fields(value):
        return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns)
    return (fields(link), fields(target), str(path.resolve()))


def _listing(path, pattern):
    try:
        signature = _signature(path)
    except FileNotFoundError:
        signature = None
    return signature, tuple(sorted(path.glob(pattern)))


class CatalogReads:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.files = {}
        self.listings = {}
        self.values = {}
        self.changed = False

    def remember(self, collection, key, value):
        if collection.setdefault(key, value) != value:
            self.changed = True
            raise CatalogChanged('Catalog changed during reading')

    def unchanged(self):
        if self.changed:
            return False
        try:
            for path, signature in self.files.items():
                if _signature(path) != signature:
                    return False
            for (path, pattern), state in self.listings.items():
                if _listing(path, pattern) != state:
                    return False
        except OSError:
            return False
        return True


@contextmanager
def catalog_reads(root):
    context = CatalogReads(root)
    token = _CURRENT.set(context)
    try:
        yield context
    finally:
        # Per-read objects (stores and registries) must not survive in a cache.
        context.values.clear()
        _CURRENT.reset(token)


@contextmanager
def reading(path, *, scientific=True):
    # Execution verification has its own bounded lifecycle and dependency witnesses.
    # This hook does not turn the UI projection cache into scientific authority.
    from data.verified_inputs import reading as verified_reading
    if scientific:
        with verified_reading(path), _ui_reading(path):
            yield
    else:
        with _ui_reading(path):
            yield


@contextmanager
def _ui_reading(path):
    context = _CURRENT.get()
    if context is None:
        yield
        return
    path = Path(path).absolute()
    before = _signature(path)
    context.remember(context.files, path, before)
    try:
        yield
    finally:
        try:
            after = _signature(path)
        except OSError:
            context.changed = True
            raise
        context.remember(context.files, path, after)


def catalog_glob(path, pattern):
    path = Path(path)
    context = _CURRENT.get()
    if context is None:
        return path.glob(pattern)
    state = _listing(path, pattern)
    context.remember(context.listings, (path.absolute(), pattern), state)
    return iter(state[1])


def memo(root, key, loader):
    """Share verified reader construction only within one UI request."""
    context = _CURRENT.get()
    if context is None or Path(root).resolve() != context.root:
        return loader()
    if key not in context.values:
        context.values[key] = loader()
    return context.values[key]
