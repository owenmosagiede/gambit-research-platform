"""Bounded operational observation. No directory scans, commands or file writes."""
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re
import time

from read_model.storage import read_document
from research.contracts import digest, request_id

ACTIVE = {'resolving', 'preparing', 'p1', 'p2'}


def _path(root, relative):
    path = root / relative
    if path.resolve() != path.absolute() or not path.is_relative_to(root):
        raise ValueError('Unconfined operational path')
    return path


def observe(root):
    root = Path(root).resolve()
    result = {'schema_version': 'live_activity_v1',
              'observed_at': datetime.now(timezone.utc).isoformat(),
              'worker': {'state': 'unknown'}, 'active': None}
    try:
        heartbeat = _path(root, 'storage/catalog/operations/worker_service.json')
        h = read_document(heartbeat, 64 * 1024)
        age = (time.monotonic_ns() - h['monotonic_ns']) / 1e9
        if h['workspace'] != str(root) or not 0 <= age <= 15:
            return result
        if type(h['pid']) is not int or h['pid'] <= 0: return result
        os.kill(h['pid'], 0)
        # Open an EXISTING lock read-only: unlike the command-side lock helper,
        # this cannot create directories or touch a production file.
        lockpath = _path(root, 'storage/catalog/operations/research-worker-service.lock')
        with lockpath.open('rb') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
                return result
        state = h['health']['state']
        if state not in {'running','idle','draining','recovering','starting','failed','stopped'}:
            return result
        result['worker'] = {'state': state, 'heartbeat_age_seconds': round(age, 2)}
        activity = h.get('activity')
        if not isinstance(activity, dict):
            result['activity_unavailable'] = True  # older service; never infer the job
            return result
        rid = activity.get('request_id')
        if rid is None: return result
        rid = request_id(rid)
        projection_path = _path(root, f'storage/catalog/operations/jobs/{rid}.json')
        job = read_document(projection_path)
        attempt = request_id(job['attempt_id'])
        event_hash = job['event_sha256']
        if not re.fullmatch('[0-9a-f]{64}', event_hash): raise ValueError('Invalid event')
        event = read_document(_path(root, f'storage/catalog/attempts/{attempt}/events/RESEVENT_{event_hash}.json'))
        expected = dict(event['job'], sequence=event['sequence'], event_sha256=digest(event))
        if expected != job or digest(event) != event_hash or event['request_id'] != rid or job['request_id'] != rid:
            raise ValueError('Operational projection differs from event')
        # A newer heartbeat may advance in time, but not switch sessions/jobs.
        latest = read_document(heartbeat, 64 * 1024)
        if any(latest.get(k) != h.get(k) for k in ('pid','session_id','activity')):
            raise ValueError('Activity changed during read')
        if job['status'] not in ACTIVE:
            return result  # finishing/starting boundary: do not claim old work is active
        result['active'] = {k: job.get(k) for k in ('request_id','attempt_id','status','stage','message','updated_at','sequence','event_sha256','plan')}
        try:
            p = read_document(_path(root, f'storage/catalog/operations/preparation/{rid}.json'), 64 * 1024)
            if p.get('attempt_id') == attempt and p.get('request_id') == rid and p.get('plan') == job.get('plan') and job.get('plan'):
                result['active']['preparation'] = {k: p.get(k) for k in ('phase','state','members_total','members_completed','batches_completed','instrument','updated_at')}
        except (OSError, ValueError, TypeError):
            pass
        return result
    except (OSError, ValueError, KeyError, TypeError):
        result['active'] = None
        result['activity_unavailable'] = True
        return result
