"""Isolated authentication, authorization and shared-route tests; no production writes."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

AUTH_TEMP = tempfile.TemporaryDirectory(prefix='gambit_auth_test_')
AUTH_ROOT = Path(AUTH_TEMP.name)
(AUTH_ROOT / 'secret').write_text('isolated-test-secret-' * 5)
os.environ.update(GAMBIT_ISOLATED_TEST='1', GAMBIT_SECRET_KEY_FILE=str(AUTH_ROOT/'secret'),
    GAMBIT_RESEARCH_ROOT=str(AUTH_ROOT/'workspace'), GAMBIT_AUTH_DATABASE=str(AUTH_ROOT/'auth.sqlite3'),
    DJANGO_SETTINGS_MODULE='web.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, override_settings
from api.application import ASSETS
from web.models import RequestBudget
from web.views import services
from test_research_runtime import profile, intent, Adapter
from services.research_worker import WebResearchJobs

PROJECT = Path(__file__).resolve().parents[1]

class ProductionAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
    @classmethod
    def tearDownClass(cls):
        from django.db import connections
        connections.close_all()
        AUTH_TEMP.cleanup()
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gambit_private_fixture_')
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        shutil.copytree(PROJECT/'ui', self.root/'ui')
        self.options = override_settings(RESEARCH_ROOT=self.root, ALLOW_SUBMISSIONS=True)
        self.options.enable()
        self.addCleanup(self.options.disable)
        self.addCleanup(self.temp.cleanup)
        get_user_model().objects.all().delete()
        RequestBudget.objects.all().delete()
        self.owner = get_user_model().objects.create_user('owner', password='Isolated-fixture-only-password!', is_superuser=True)
        self.viewer = get_user_model().objects.create_user('viewer', password='Isolated-fixture-only-password!')
        self.client = Client(enforce_csrf_checks=True)
        self.jobs = WebResearchJobs(self.root, adapter=Adapter())
        patcher = patch('web.views.services', return_value=(self.jobs, __import__('api.catalog_cache', fromlist=['CatalogCache']).CatalogCache()))
        patcher.start(); self.addCleanup(patcher.stop); self.addCleanup(self.jobs.close)
    def login(self):
        self.client.force_login(self.owner)
        response = self.client.get('/app/')
        self.assertEqual(response.status_code, 200)
        return re.search(r'<meta name="csrf-token" content="([^"]+)"', response.content.decode())[1]
    def post(self, data, token=None, path='/api/experiments', **headers):
        return self.client.post(path, data=json.dumps(data), content_type='application/json',
            HTTP_ORIGIN='http://testserver', **({'HTTP_X_CSRFTOKEN': token} if token else {}), **headers)
    def test_all_private_assets_and_routes_require_owner(self):
        routes = ['/app/', '/session.js', '/api/experiments', '/api/research-readiness',
            '/api/feature-library', '/api/signal-library-summaries', '/api/pit-library',
            '/api/scope-library', '/api/target-library', '/api/trial-evidence/TRIAL_'+'a'*64,
            '/api/feature-research/FEATURE_RECIPE_'+'a'*64, '/api/research-results/FEATURE_RECIPE_'+'a'*64]
        routes += sorted(set(ASSETS)-{'/', '/index.html'})
        for route in routes:
            with self.subTest(route=route):
                response=self.client.get(route)
                self.assertIn(response.status_code, (302,401))
                self.assertNotIn(b'FEATURE_RECIPE_', response.content)
        self.client.force_login(self.viewer)
        for route in routes:
            with self.subTest(viewer_route=route): self.assertEqual(self.client.get(route).status_code,403)
        self.assertFalse((self.root/'storage').exists())
    def test_public_has_no_private_bundle_or_research_metadata(self):
        for route in ('/', '/about/', '/login/', '/healthz', '/public/site.css', '/public/gambit-app-mark.svg'):
            r=self.client.get(route); self.assertEqual(r.status_code,200)
            for forbidden in (b'/api/', b'/signals.js', b'/submission.js', b'FEATURE_RECIPE_', b'CES050'):
                self.assertNotIn(forbidden,r.content)
        for path in ('/src/web/settings.py','/storage/catalog/submissions/a.json','/.env','/index.html',
                     '/public/../session.js','/public/%2e%2e/session.js','/public/%2fapp','/admin/'):
            self.assertEqual(self.client.get(path).status_code,404,path)
    def test_csrf_and_origin_reject_before_persistence(self):
        token=self.login(); body=intent()
        r=self.post(body); self.assertEqual(r.status_code,403);self.assertIs(r.json()['recorded'],False)
        r=self.client.post('/api/experiments', data=json.dumps(body), content_type='application/json',
            HTTP_X_CSRFTOKEN=token,HTTP_ORIGIN='https://evil.example')
        self.assertEqual(r.status_code,403);self.assertEqual(r.json()['error']['code'],'INVALID_ORIGIN')
        self.assertFalse((self.root/'storage/catalog/submissions').exists())
        r=self.post(body,token); self.assertEqual(r.status_code,202)
        self.assertEqual(self.post(body,token).status_code,200)
        changed=dict(body,expected_direction='NEGATIVE')
        self.assertEqual(self.post(changed,token).status_code,409)
        self.assertEqual(len(list((self.root/'storage/catalog/submissions').glob('*.json'))),1)
        self.assertIsNone(self.jobs.thread)
    def test_expired_session_does_not_misclassify_or_submit(self):
        token=self.login(); self.client.logout()
        r=self.post(intent(),token);self.assertEqual(r.status_code,401)
        self.assertIs(r.json()['recorded'],False)
        self.assertFalse((self.root/'storage/catalog/submissions').exists())
    def test_session_logout_revokes_old_cookie(self):
        token=self.login(); old=self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertEqual(self.client.get('/logout/').status_code,405)
        r=self.client.post('/logout/',{'csrfmiddlewaretoken':token},HTTP_ORIGIN='http://testserver')
        self.assertEqual(r.status_code,302)
        stale=Client();stale.cookies[settings.SESSION_COOKIE_NAME]=old
        self.assertEqual(stale.get('/api/experiments').status_code,401)
    def test_login_rate_limit_is_persisted_and_generic(self):
        r=self.client.get('/login/')
        token=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',r.content.decode())[1]
        for _ in range(8):
            r=self.client.post('/login/',{'csrfmiddlewaretoken':token,'username':'owner','password':'wrong'},HTTP_ORIGIN='http://testserver')
            self.assertEqual(r.status_code,200)
        other=Client(enforce_csrf_checks=True);r=other.get('/login/')
        token=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',r.content.decode())[1]
        r=other.post('/login/',{'csrfmiddlewaretoken':token,'username':'owner','password':'wrong'},HTTP_ORIGIN='http://testserver')
        self.assertEqual(r.status_code,429)
        self.assertTrue(all(len(x)==64 for x in RequestBudget.objects.values_list('key',flat=True)))
    def test_real_password_login_rotates_session_and_issues_cookie(self):
        r=self.client.get('/login/')
        token=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',r.content.decode())[1]
        r=self.client.post('/login/',{'csrfmiddlewaretoken':token,'username':'owner','password':'Isolated-fixture-only-password!'},HTTP_ORIGIN='http://testserver')
        self.assertEqual(r.status_code,302);self.assertEqual(r['Location'],'/app/')
        self.assertTrue(r.cookies[settings.SESSION_COOKIE_NAME]['httponly'])
        self.assertEqual(r.cookies[settings.SESSION_COOKIE_NAME]['samesite'],'Strict')
        self.assertEqual(self.client.get('/api/experiments').status_code,200)
    def test_cloud_activation_gate_and_api_rate_limit(self):
        token=self.login()
        with override_settings(ALLOW_SUBMISSIONS=False):
            r=self.post(intent(),token);self.assertEqual(r.status_code,503)
            self.assertIs(r.json()['recorded'],False)
            self.assertFalse(self.client.get('/api/research-readiness').json()['execution_enabled'])
        with patch('web.views.consume',return_value=False):
            self.assertEqual(self.post(intent(),token).status_code,429)
        self.assertFalse((self.root/'storage/catalog/submissions').exists())
    def test_production_https_and_exact_host(self):
        self.assertEqual(self.client.get('/healthz',HTTP_HOST='evil.example').status_code,400)
        with override_settings(SECURE_SSL_REDIRECT=True,ALLOWED_HOSTS=['gambitsystems.xyz'],SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')):
            secure_client=Client();r=secure_client.get('/healthz',HTTP_HOST='gambitsystems.xyz');self.assertEqual(r.status_code,301)
            r=secure_client.get('/healthz',HTTP_HOST='gambitsystems.xyz',HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(r.status_code,200)
    def test_body_size_duplicate_keys_and_method_guards(self):
        token=self.login()
        for body in ('{"x":NaN}','{"x":1,"x":2}'):
            r=self.client.post('/api/experiments',data=body,content_type='application/json',HTTP_ORIGIN='http://testserver',HTTP_X_CSRFTOKEN=token)
            self.assertEqual(r.status_code,400)
        r=self.client.post('/api/experiments',data='x'*16385,content_type='application/json',HTTP_ORIGIN='http://testserver',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code,413)
        self.assertEqual(self.client.delete('/api/experiments').status_code,405)
        self.assertFalse((self.root/'storage/catalog/submissions').exists())
    def test_configured_health_fails_closed_without_exposing_private_checks(self):
        import time
        path = self.root / 'health.json'
        with override_settings(HEALTH_STATUS_FILE=str(path)):
            response = self.client.get('/healthz')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {'status': 'unavailable'})
            path.write_text(json.dumps({'checked_at': time.time(), 'healthy': True, 'checks': {'private': 'secret'}}))
            response = self.client.get('/healthz')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'status': 'ok'})
            self.assertEqual(response['Cache-Control'], 'no-store')

if __name__=='__main__': unittest.main()
