"""Bounded, read-only operational counts, independent of the history projector.

Counts canonical job projections, not horizon outcomes, aliases or staged plans.
No registry resolution, scientific kernels, payload reads, repairs or writer locks.
"""
from datetime import datetime, timedelta, timezone
import os
from functools import lru_cache
from threading import Lock
from pathlib import Path
import re
import time

from api.live_activity import _path
from read_model.storage import DocumentChanged, Unavailable, read_document, signature
from research.contracts import digest, request_id

MAX_JOBS = 10_000
MAX_RECORD_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 4.0
STATES = {'queued', 'resolving', 'preparing', 'p1', 'p2', 'blocked', 'failed', 'cancelled', 'succeeded'}


class Counter:
    def __init__(self):
        self.records = {}
        self.lock = Lock()


@lru_cache(maxsize=4)
def _counter(root):
    return Counter()


def observe_counts(root, *, now=None):
    root = Path(root).resolve()
    counter = _counter(str(root))
    if not counter.lock.acquire(blocking=False):
        raise Unavailable('Research counts are already being captured')
    try:
        return _capture(root, now=now, records=counter.records)
    finally:
        counter.lock.release()


def _capture(root, *, now, records):
    root = Path(root).resolve()
    directory = _path(root, 'storage/catalog/operations/jobs')
    deadline = time.monotonic() + MAX_SECONDS

    def budget():
        if time.monotonic() > deadline:
            raise Unavailable('Research count deadline exceeded')

    def inventory():
        budget()
        found = {}
        with os.scandir(directory) as entries:
            for entry in entries:
                budget()
                if not entry.name.endswith('.json'):
                    continue
                rid = request_id(Path(entry.name).stem)
                if not entry.is_file(follow_symlinks=False):
                    raise Unavailable('Research job is not a regular file')
                # The parent is confined once; UUID filenames cannot traverse.
                path = directory / entry.name
                found[rid] = signature(path)
                if len(found) > MAX_JOBS:
                    raise Unavailable('Research count inventory exceeds its bound')
        return found

    # The executor atomically replaces projections. One retry handles a job
    # advancing during capture; persistent churn never produces a partial count.
    for attempt in range(2):
        observed = now or datetime.now(timezone.utc)
        if observed.tzinfo is None:
            raise ValueError('An aware observation time is required')
        start = observed - timedelta(hours=1)
        try:
            before = inventory()
            for rid in list(records):
                if rid not in before: del records[rid]
            queued = completed = used = 0

            def document(path):
                nonlocal used
                budget()
                used += signature(path)[2]
                if used > MAX_TOTAL_BYTES:
                    raise Unavailable('Research count read budget exceeded')
                return read_document(path, MAX_RECORD_BYTES)

            for rid, expected in before.items():
                path = directory / (rid + '.json')
                if signature(path) != expected:
                    raise DocumentChanged('Job advanced during capture')
                cached = records.get(rid)
                if (cached and cached['signature'] == expected
                        and expected[2] <= MAX_RECORD_BYTES
                        and time.monotonic() - cached['checked'] < 300
                        and signature(_path(root, cached['event_relative'])) == cached['event_signature']):
                    used += expected[2] + cached['event_signature'][2]
                    if used > MAX_TOTAL_BYTES or cached['event_signature'][2] > MAX_RECORD_BYTES:
                        raise Unavailable('Research count metadata exceeds its bound')
                    status, updated = cached['status'], cached['updated']
                else:
                    job = document(path)
                    if job['request_id'] != rid or job['status'] not in STATES:
                        raise ValueError('Invalid operational job')
                    attempt_id = request_id(job['attempt_id'])
                    event_hash = job['event_sha256']
                    if not isinstance(event_hash, str) or not re.fullmatch('[0-9a-f]{64}', event_hash):
                        raise ValueError('Invalid operational event')
                    event_relative = f'storage/catalog/attempts/{attempt_id}/events/RESEVENT_{event_hash}.json'
                    event_path = _path(root, event_relative)
                    event_signature = signature(event_path)
                    event = document(event_path)
                    if (event['request_id'] != rid or digest(event) != event_hash
                            or dict(event['job'], sequence=event['sequence'], event_sha256=event_hash) != job):
                        raise ValueError('Projection differs from its operational event')
                    if signature(event_path) != event_signature:
                        raise DocumentChanged('Operational event advanced')
                    updated = datetime.fromisoformat(job['updated_at'])
                    if updated.tzinfo is None:
                        raise ValueError('Invalid operational timestamp')
                    status = job['status']
                    records[rid] = {'signature': expected, 'event_relative': event_relative,
                                    'event_signature': event_signature, 'checked': time.monotonic(),
                                    'status': status, 'updated': updated}
                queued += status == 'queued'
                completed += status == 'succeeded' and start <= updated <= observed
            if _path(root, 'storage/catalog/operations/jobs') != directory or inventory() != before:
                raise DocumentChanged('Job inventory advanced during capture')
            budget()
            return {'schema_version': 'research_metrics_v1', 'observed_at': observed.isoformat(),
                    'window_start': start.isoformat(), 'window_end': observed.isoformat(),
                    'queued': queued, 'completed_last_hour': completed,
                    'counting_unit': 'canonical_research_jobs', 'jobs_observed': len(before)}
        except (DocumentChanged, FileNotFoundError):
            if not directory.is_dir():
                raise Unavailable('Research job directory is unavailable')
            if attempt:
                raise Unavailable('Research counts changed during capture')
    raise Unavailable('Research counts are unavailable')
