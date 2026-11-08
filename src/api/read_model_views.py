"""Versioned presentation endpoints. Authentication remains the transport's job."""
import logging
import re
import time
from urllib.parse import parse_qs
from read_model import query
from read_model.storage import CursorExpired, Unavailable

log = logging.getLogger('web.read_model')
PREFIX = '/api/read-model/v1/'


def serve(route, target, directory, *, head=False):
    if not target.path.startswith(PREFIX): return False
    if not directory:
        route.error(503,'READ_MODEL_DISABLED','The dedicated read model has not been activated.',head); return True
    started = time.monotonic(); label = 'unknown'
    try:
        values = parse_qs(target.query, keep_blank_values=True, strict_parsing=True)
        if any(len(v)!=1 for v in values.values()): raise query.InvalidQuery('Duplicate query parameter')
        values = {k:v[0] for k,v in values.items() if v[0]}
        endpoint = target.path[len(PREFIX):]
        if endpoint == 'activity':
            if values: raise query.InvalidQuery('Activity accepts no query')
            from api.live_activity import observe
            label='activity'; value=observe(route.root)
        elif match := re.fullmatch(r'evidence/(TRIAL_[0-9a-f]{64})', endpoint):
            if set(values)-{'generation'}: raise query.InvalidQuery('Unsupported evidence query')
            from read_model.chart_evidence import read_evidence
            label='evidence'; value=read_evidence(directory, match[1], values.get('generation'))
        elif endpoint in ('ledger','queue','recipes'):
            label = endpoint; value=query.page(directory,endpoint,values)
        elif match := re.fullmatch(r'recipes/(FEATURE_(?:RECIPE_)?[0-9a-f]{64})/branches',endpoint):
            label='branches'; value=query.page(directory,'branches',values,recipe=match[1])
        elif match := re.fullmatch(r'(trial|relationship|decision|experiment)/([A-Za-z0-9_-]{1,128})',endpoint):
            if set(values)-{'generation'}: raise query.InvalidQuery('Unsupported detail query')
            label='metadata'; value=query.detail(directory,match[1],match[2],values.get('generation'))
        else:
            route.error(404,'NOT_FOUND','This research view is unavailable.',head); return True
        route.send_json(200,value,head)
    except CursorExpired:
        route.error(410,'CURSOR_EXPIRED','This page expired. Refresh for the latest records.',head)
    except (query.InvalidQuery, ValueError) as exc:
        if isinstance(exc, Unavailable): route.error(503,'READ_MODEL_UNAVAILABLE','Verified research views are temporarily unavailable. Research is independent of this display.',head)
        else: route.error(400,'INVALID_QUERY','Use a supported filter and page cursor.',head)
    except LookupError: route.error(404,'NOT_FOUND','This verified record is unavailable.',head)
    except Exception:
        route.error(503,'READ_MODEL_UNAVAILABLE','Verified research views are temporarily unavailable. Research is independent of this display.',head)
    finally:
        log.info('route=%s seconds=%.6f status=%s bytes=%s',label,time.monotonic()-started,route.response[0] if route.response else 503,len(route.response[1]) if route.response else 0)
    return True
