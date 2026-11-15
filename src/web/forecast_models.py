"""Owner-only serving of the frozen Forecast Models readout."""

from hashlib import sha256
import json
from pathlib import Path
import re

from django.conf import settings
from django.http import HttpResponseNotAllowed, JsonResponse

FORECAST_ASSETS = {
    '/forecast-models/': ('forecast-models.html', 'text/html; charset=utf-8'),
    '/forecast-models.js': ('forecast-models.js', 'text/javascript; charset=utf-8'),
    '/forecast-models.css': ('forecast-models.css', 'text/css; charset=utf-8'),
}
SCHEMA = 'gambit_forecast_models_readout_v1'
MODEL_ID = re.compile(r'P3MODEL_[a-f0-9]{64}')
DIGEST = re.compile(r'[a-f0-9]{64}')
DEFAULT_READOUT = Path('/var/lib/gambit-forecast-models/v1')
MAX_INDEX = 256_000
MAX_DETAIL = 1_500_000


def read_file(root, name, limit):
    path = root / name
    if root.resolve() != root or path.is_symlink():
        raise ValueError('Invalid forecast readout path')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError('Forecast readout exceeds the serving limit')
    return raw


def model_readout(request, endpoint):
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(('GET', 'HEAD'))
    if request.GET:
        return error(400, 'FORECAST_QUERY_INVALID', 'Use an exact saved forecast model address.')
    model_id = endpoint.removeprefix('forecast-models/')
    library = endpoint == 'forecast-models'
    if not library and not MODEL_ID.fullmatch(model_id):
        return error(404, 'FORECAST_MODEL_NOT_FOUND', 'That saved forecast model is unavailable.')
    configured = getattr(settings, 'FORECAST_MODELS_DIR', None if settings.ISOLATED else DEFAULT_READOUT)
    root = Path(configured) if configured else None
    if root is None or not root.exists():
        if library:
            return JsonResponse({'schema':SCHEMA,'archived_through':None,'tasks':[]})
        return error(404, 'FORECAST_MODEL_NOT_FOUND', 'There is no saved Forecast Models readout.')
    try:
        catalog = json.loads(read_file(root,'index.json',MAX_INDEX))
        if catalog['schema'] != SCHEMA or not isinstance(catalog['tasks'],list):
            raise ValueError('Invalid Forecast Models index')
        if library:
            return JsonResponse({key:catalog[key] for key in ('schema','tasks','archived_through')})
        digest = catalog['model_hashes'].get(model_id)
        if digest is None:
            return error(404, 'FORECAST_MODEL_NOT_FOUND', 'That saved forecast model is unavailable.')
        raw = read_file(root,model_id+'.json',MAX_DETAIL)
        if not DIGEST.fullmatch(digest) or sha256(raw).hexdigest() != digest:
            raise ValueError('Published model readout failed verification')
        detail = json.loads(raw)
        if detail['schema'] != SCHEMA or detail['model_id'] != model_id:
            raise ValueError('Published model identity differs')
        return JsonResponse(detail,json_dumps_params={'allow_nan':False})
    except (OSError, KeyError, AttributeError, TypeError, ValueError):
        return error(503, 'FORECAST_READOUT_UNAVAILABLE', 'The saved forecast evidence could not be verified.')


def error(status, code, message):
    return JsonResponse({'error':{'code':code,'message':message},'recorded':False},status=status)
