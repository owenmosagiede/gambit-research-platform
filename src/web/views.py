"""Authenticated adapters around the same application routes as local HTTP."""
from functools import lru_cache
from pathlib import Path
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.views.decorators.http import require_http_methods
from api.application import ApplicationRoutes, ASSETS, is_retired_batch_path, BATCH_RETIRED_MESSAGE
from api.catalog_cache import CatalogCache
from data.alfred_onboarding import stable_read
from data.alfred_pit import inside
from services.research_worker import WebResearchJobs
from .middleware import PUBLIC_ASSETS, denied
from .security import consume

@lru_cache(maxsize=4)
def services(root):
    return WebResearchJobs(root), CatalogCache()

@require_http_methods(['GET', 'HEAD'])
def about(request):
    return render(request, 'web/about.html')

@require_http_methods(['GET', 'HEAD', 'POST'])
def sign_in(request):
    form = AuthenticationForm(request, data=request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        # Trusted proxy IP is set by Caddy; isolated tests use REMOTE_ADDR.
        ip = request.META.get('REMOTE_ADDR', '')
        if not settings.ISOLATED:
            ip = request.META.get('HTTP_X_REAL_IP', '')
        name = request.POST.get('username', '').strip().lower()[:254]
        allowed = consume('login-ip', ip, 30, 900) and consume('login-name', name, 8, 900)
        if not allowed:
            return render(request, 'web/login.html', {'form': form, 'limited': True}, status=429)
        if form.is_valid():
            user = form.get_user()
            if user.is_active and user.is_superuser:
                login(request, user)
                return redirect('/app/')
            form.add_error(None, 'This account has no research access.')
    return render(request, 'web/login.html', {'form': form})

@require_http_methods(['POST'])
def sign_out(request):
    logout(request)
    return redirect('/login/')

def csrf_failure(request, reason=''):
    return denied(request, 403, 'CSRF_FAILED', 'Your session needs refreshing. Sign in again before retrying with the same submission ID.')

@require_http_methods(['GET', 'HEAD'])
def public_asset(request, name):
    if name not in PUBLIC_ASSETS:
        return HttpResponse(status=404)
    content = (Path(__file__).parent / 'public' / name).read_bytes()
    return HttpResponse(content, content_type='image/svg+xml' if name.endswith('.svg') else 'text/css; charset=utf-8')

@require_http_methods(['GET', 'HEAD'])
def private_asset(request):
    if request.path == '/session.js':
        return HttpResponse((Path(__file__).parent / 'session.js').read_bytes(), content_type='text/javascript; charset=utf-8')
    asset = ('index.html', 'text/html; charset=utf-8') if request.path == '/app/' else ASSETS.get(request.path)
    if not asset:
        return HttpResponse(status=404)
    name, kind = asset
    content = stable_read(inside(settings.RESEARCH_ROOT, 'ui/' + name))
    if name == 'index.html':
        if settings.READ_MODEL_DIR:
            content = content.replace(b'name="gambit-read-model" content="disabled"', b'name="gambit-read-model" content="enabled"')
        token = escape(get_token(request))
        content = content.replace(b'</head>', (f'<meta name="csrf-token" content="{token}"></head>').encode())
        content = content.replace(b'<script ', b'<script src="/session.js" defer></script>\n  <script ', 1)
    return HttpResponse(content, content_type=kind)

@require_http_methods(['GET', 'HEAD', 'POST'])
def api(request, endpoint):
    if not consume('api', str(request.user.pk), 360, 60):
        response = denied(request, 429, 'RATE_LIMITED', 'Too many requests. Retry shortly using the same submission ID.')
        response['Retry-After'] = '60'
        return response
    if is_retired_batch_path(request.path):
        return denied(request, 410, 'BATCH_RETIRED', BATCH_RETIRED_MESSAGE)
    if request.method in ('GET', 'HEAD') and request.path.startswith('/api/read-model/v1/'):
        jobs, catalogs = None, None
    else:
        jobs, catalogs = services(str(settings.RESEARCH_ROOT))
    route = ApplicationRoutes(settings.RESEARCH_ROOT, jobs, catalogs, request.method, request.get_full_path(), read_model_dir=settings.READ_MODEL_DIR)
    if request.method == 'POST':
        if not settings.ALLOW_SUBMISSIONS and (request.path == '/api/experiments' or request.path.endswith('/resume')):
            return denied(request, 503, 'DEPLOYMENT_NOT_ACTIVATED', 'Cloud submissions are disabled until migration and recovery checks pass.')
        if request.content_type != 'application/json' or request.headers.get('Transfer-Encoding'):
            return denied(request, 415, 'INVALID_BODY', 'Use a bounded JSON request.')
        try:
            length = int(request.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 1 <= length <= 16384:
            return denied(request, 413, 'INVALID_LENGTH', 'Request body exceeds the endpoint limit.')
        if len(request.body) != length:
            return denied(request, 400, 'INVALID_BODY', 'Incomplete request.')
        route.write(request.body)
    else:
        route.read(request.method == 'HEAD')
    status, content, kind, allow = route.response
    if request.path == '/api/research-readiness' and status == 200 and not settings.ALLOW_SUBMISSIONS:
        import json
        value = json.loads(content)
        value['execution_enabled'] = False
        value['blockers'].append({'code': 'DEPLOYMENT_NOT_ACTIVATED', 'message': 'Cloud submissions are disabled until migration and recovery checks pass.'})
        content = json.dumps(value, allow_nan=False).encode()
    response = HttpResponse(content, status=status, content_type=kind)
    if allow:
        response['Allow'] = 'GET, HEAD'
    return response

@require_http_methods(['GET', 'HEAD'])
def health(request):
    from .health import healthy
    available = healthy(settings.HEALTH_STATUS_FILE)
    response = JsonResponse({'status': 'ok' if available else 'unavailable'}, status=200 if available else 503)
    response['Cache-Control'] = 'no-store'
    return response
