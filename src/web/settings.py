"""Fail-closed production settings. Secrets and authentication state stay outside releases."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE = Path(__file__).resolve().parent
ISOLATED = os.environ.get('GAMBIT_ISOLATED_TEST') == '1'
def required(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f'{name} is required')
    return value
SECRET_KEY = Path(required('GAMBIT_SECRET_KEY_FILE')).read_text().strip()
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Use a random secret of at least 50 characters')
RESEARCH_ROOT = Path(required('GAMBIT_RESEARCH_ROOT')).resolve()
AUTH_DATABASE = Path(required('GAMBIT_AUTH_DATABASE')).resolve()
if AUTH_DATABASE.is_relative_to(RESEARCH_ROOT):
    raise ImproperlyConfigured('Authentication state must be outside the research workspace')
DOMAIN = os.environ.get('GAMBIT_DOMAIN', 'gambitsystems.xyz')
if not DOMAIN or any(c in DOMAIN for c in '/:, *'):
    raise ImproperlyConfigured('GAMBIT_DOMAIN must be a single exact hostname')
DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver'] if ISOLATED else [DOMAIN]
ROOT_URLCONF = 'web.urls'
WSGI_APPLICATION = 'web.wsgi.application'
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'web']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware',
              'django.contrib.sessions.middleware.SessionMiddleware',
              'django.contrib.auth.middleware.AuthenticationMiddleware',
              'web.middleware.AccessBoundary', 'django.middleware.csrf.CsrfViewMiddleware',
              'django.middleware.clickjacking.XFrameOptionsMiddleware']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': AUTH_DATABASE,
                        'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE / 'templates'],
              'APP_DIRS': False, 'OPTIONS': {'context_processors': ['django.template.context_processors.csrf']}}]
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 14}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_NAME = 'gambit_session'
SESSION_COOKIE_SECURE = not ISOLATED
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SECURE = not ISOLATED
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'
CSRF_FAILURE_VIEW = 'web.views.csrf_failure'
CSRF_TRUSTED_ORIGINS = []
# Gunicorn listens only on a Unix socket. Caddy overwrites this header.
SECURE_PROXY_SSL_HEADER = None if ISOLATED else ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = False
SECURE_SSL_REDIRECT = not ISOLATED
SECURE_HSTS_SECONDS = 0 if ISOLATED else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 16384
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10
FILE_UPLOAD_MAX_MEMORY_SIZE = 0
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
TIME_ZONE = 'UTC'
ALLOW_SUBMISSIONS = os.environ.get('GAMBIT_ALLOW_SUBMISSIONS') == '1'
HEALTH_STATUS_FILE = os.environ.get('GAMBIT_HEALTH_STATUS_FILE') or None
# Do not emit request URLs, bodies, headers, cookies, or tracebacks into web logs.
LOGGING = {'version': 1, 'disable_existing_loggers': False,
    'handlers': {'null': {'class': 'logging.NullHandler'}, 'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'web.read_model': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
                'web.access': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}, 'django.request': {'handlers': ['null'], 'propagate': False},
                'django.security': {'handlers': ['null'], 'propagate': False}}}

# Explicit operator switch; absent by default. Never starts a projector.
READ_MODEL_DIR = os.environ.get('GAMBIT_READ_MODEL_DIR') or None
if READ_MODEL_DIR:
    serving = Path(READ_MODEL_DIR).absolute()
    if serving.resolve() != serving or serving.is_relative_to(RESEARCH_ROOT) or RESEARCH_ROOT.is_relative_to(serving) or AUTH_DATABASE.is_relative_to(serving):
        raise ImproperlyConfigured('Serving files must be separate from research and authentication storage')
