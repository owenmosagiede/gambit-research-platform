"""Bounded, derived routing for the immutable research event files."""
import os
from pathlib import Path
import stat

from research.contracts import ResearchError, request_id
from research.performance import counter, measure
from research.store import read_json


def _signature(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


class EventHistory:
    """Reuse file-to-request routing after checking file identity and membership.

    File metadata is checked even for other requests so an unreadable append or
    edit anywhere has the same effect as a complete replay. Selected events
    are still read and their full chain verified. No state survives restart.
    """

    def __init__(self, directory, *, max_entries=100_000):
        self.directory = directory
        self.max_entries = max_entries
        self.routes = {}

    def _scan(self, rid):
        routes, events = {}, []
        if self.directory.resolve() != self.directory:
            return None
        if not self.directory.exists():
            return routes, events
        with os.scandir(self.directory) as attempts:
            for attempt in attempts:
                if attempt.is_symlink():
                    return None
                if not attempt.is_dir(follow_symlinks=False):
                    continue
                directory = os.path.join(attempt.path, 'events')
                if os.path.islink(directory):
                    return None
                try:
                    entries = os.scandir(directory)
                except (FileNotFoundError, NotADirectoryError):
                    continue
                with entries:
                    for entry in entries:
                        if not (entry.name.startswith('RESEVENT_') and entry.name.endswith('.json')):
                            continue
                        info = entry.stat(follow_symlinks=False)
                        if not stat.S_ISREG(info.st_mode) or len(routes) >= self.max_entries:
                            return None
                        signature = _signature(info)
                        previous = self.routes.get(entry.path)
                        event = None
                        if previous is None or previous[0] != signature:
                            event = read_json(Path(entry.path))
                            owner = request_id(event.get('request_id'))
                            counter('events.routing_files_parsed')
                        else:
                            owner = previous[1]
                        if owner == rid:
                            if event is None:
                                event = read_json(Path(entry.path))
                            events.append((entry.name[:-5], event))
                        if event is not None and signature != _signature(os.lstat(entry.path)):
                            return None
                        routes[entry.path] = (signature, owner)
        return routes, events

    def snapshot(self, rid):
        with measure('events.routing_scan'):
            try:
                result = self._scan(rid)
            except (AttributeError, OSError, TypeError, ValueError):
                # The authoritative full reader reports unreadable files and
                # reconciles unsupported layouts. Never keep a partial index.
                result = None
            if result is None:
                self.routes.clear()
                counter('events.routing_fallbacks')
                return None
            self.routes, events = result
            return {rid: events}
