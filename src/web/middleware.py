import logging
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from api.application import ASSETS

PUBLIC_ASSETS = {'site.css', 'gambit-app-mark.svg'}
PUBLIC = {'/', '/about/', '/login/', '/healthz'} | {'/public/' + name for name in PUBLIC_ASSETS}
PRIVATE = set(ASSETS) - {'/', '/index.html'} | {'/app/', '/session.js', '/logout/'}

def denied(request, status, code, message):
    if request.path.startswith('/api/'):
        return JsonResponse({'error': {'code': code, 'message': message}, 'recorded': False}, status=status)
    return HttpResponse(message, status=status, content_type='text/plain; charset=utf-8')

class AccessBoundary:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        request.get_host()  # Validate before views, including public pages.
        path = request.path
        private = path in PRIVATE or path.startswith('/api/')
        if path not in PUBLIC and not private:
            response = HttpResponse('Not found', status=404)
        elif private and not request.user.is_authenticated:
            response = denied(request, 401, 'LOGIN_REQUIRED', 'Sign in to continue. Nothing was submitted.') if path.startswith('/api/') else redirect('/login/')
        elif private and not (request.user.is_active and request.user.is_superuser):
            response = denied(request, 403, 'OWNER_REQUIRED', 'This account has no research access.')
        elif request.method not in ('GET', 'HEAD', 'POST'):
            response = denied(request, 405, 'METHOD_NOT_ALLOWED', 'Unsupported method.')
        elif request.method == 'POST' and request.headers.get('Origin') != f'{request.scheme}://{request.get_host()}':
            response = denied(request, 403, 'INVALID_ORIGIN', 'Use this application to submit requests.')
        else:
            response = self.get_response(request)
        response['Cache-Control'] = 'no-store'
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        logging.getLogger('web.access').info('web_response method=%s surface=%s status=%s',
            request.method if request.method in ('GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS') else 'other',
            'api' if path.startswith('/api/') else 'private' if private else 'public', response.status_code)
        return response
