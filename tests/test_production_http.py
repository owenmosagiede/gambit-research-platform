"""Real Gunicorn/Django HTTP, separate worker, real P1/P2 kernels; isolated inputs."""
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
import socket
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
import urllib.request
from urllib.error import HTTPError, URLError
from test_research_runtime import profile, intent

PROJECT=Path(__file__).resolve().parents[1]
class ProductionHTTPTests(unittest.TestCase):
    def test_authenticated_submit_survives_web_disconnect_and_restart(self):
        with TemporaryDirectory(prefix='gambit_gunicorn_e2e_') as tmp:
            base=Path(tmp);root=base/'workspace';(root/'config').mkdir(parents=True)
            (root/'config/research_execution.json').write_text(json.dumps(profile()))
            shutil.copytree(PROJECT/'ui',root/'ui')
            (base/'secret').write_text('disposable-fixture-secret-'*5)
            # Allowlist environment: no agent, cloud, provider or LLM credentials survive.
            env={'PATH':os.environ['PATH'],'PYTHONPATH':str(PROJECT/'src')+os.pathsep+str(PROJECT/'tests'),
                'PYTHONDONTWRITEBYTECODE':'1','GAMBIT_ISOLATED_TEST':'1','GAMBIT_ALLOW_SUBMISSIONS':'1',
                'GAMBIT_SECRET_KEY_FILE':str(base/'secret'),'GAMBIT_RESEARCH_ROOT':str(root),
                'GAMBIT_AUTH_DATABASE':str(base/'auth.sqlite3'),'DJANGO_SETTINGS_MODULE':'web.settings'}
            subprocess.run([sys.executable,str(PROJECT/'tools/manage_web.py'),'migrate','--noinput','--verbosity','0'],env=env,check=True,capture_output=True)
            subprocess.run([sys.executable,'-c',"import django;django.setup();from django.contrib.auth import get_user_model;get_user_model().objects.create_user('fixture_owner',password='Temporary-test-only-Password!',is_superuser=True)"],env=env,check=True,capture_output=True)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            origin=f'http://127.0.0.1:{port}';processes=[]
            with (base/'services.log').open('w') as log:
                def start_web():
                    p=subprocess.Popen([sys.executable,'-m','gunicorn','cloud_http_fixture:web()', '--bind',f'127.0.0.1:{port}', '--no-control-socket','--workers','1','--threads','2','--timeout','60'],env=env,stdout=log,stderr=log,cwd=PROJECT)
                    processes.append(p);return p
                worker=subprocess.Popen([sys.executable,str(PROJECT/'tests/cloud_http_fixture.py')],env=env,stdout=log,stderr=log,cwd=PROJECT);processes.append(worker)
                def wait(predicate,limit=25):
                    end=time.monotonic()+limit
                    while time.monotonic()<end:
                        try:
                            result=predicate()
                            if result:return result
                        except (URLError,ConnectionError,FileNotFoundError):pass
                        time.sleep(.05)
                    self.fail('Fixture timed out: '+(base/'services.log').read_text()[-3000:])
                def request(client,path,data=None,token=None):
                    headers={'Origin':origin}
                    if isinstance(data,dict):data=json.dumps(data).encode();headers['Content-Type']='application/json'
                    if token:headers['X-CSRFToken']=token
                    req=urllib.request.Request(origin+path,data=data,headers=headers)
                    try:
                        with client.open(req,timeout=5) as r:return r.status,r.read()
                    except HTTPError as e:
                        try:return e.code,e.read()
                        finally:e.close()
                try:
                    web=start_web(); client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
                    wait(lambda:request(client,'/healthz')[0]==200)
                    self.assertEqual(request(client,'/api/experiments')[0],401)
                    code,html=request(client,'/login/')
                    token=re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"',html)[1].decode()
                    from urllib.parse import urlencode
                    form=urlencode({'username':'fixture_owner','password':'Temporary-test-only-Password!','csrfmiddlewaretoken':token}).encode()
                    self.assertEqual(request(client,'/login/',form)[0],200,(base/'services.log').read_text()[-4000:])
                    # Login rotates CSRF token. The login page issues the current masked token.
                    _,html=request(client,'/login/')
                    token=re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"',html)[1].decode()
                    r=intent(mode='TS');code,body=request(client,'/api/experiments',r,token)
                    self.assertEqual(code,202,body);self.assertEqual(json.loads(body)['job']['status'],'queued')
                    wait(lambda:(root/'entered').exists())
                    web.terminate();web.wait(5)
                    self.assertIsNone(worker.poll())
                    (root/'release').touch()
                    jobpath=root/'storage/catalog/operations/jobs'/f"{r['request_id']}.json"
                    # Read the durable projection without any live web server or initiating client.
                    job=wait(lambda: (j if (j:=json.loads(jobpath.read_bytes())).get('status')=='succeeded' else None))
                    self.assertEqual(len(job['horizons']),5)
                    start_web();wait(lambda:request(client,'/healthz')[0]==200)
                    code,data=request(client,'/api/research-results/'+r['feature']['id'])
                    self.assertEqual(code,200,data);rows=json.loads(data)['relationships']
                    self.assertEqual(len(rows),5);self.assertTrue(any(any(x['stage']=='P2' for x in row['results']) for row in rows))
                    self.assertEqual(request(client,'/api/experiments',r,token)[0],200)
                    self.assertEqual(len(list((root/'storage/catalog/submissions').glob('*.json'))),1)
                    self.assertTrue(list((root/'storage/catalog/trial_ledger/records').glob('*.json')))
                    print('HTTP evidence: accepted once; 5 horizon relationships; real P1/P2 results; web restart independent; no agent credentials.')
                finally:
                    (root/'release').touch()
                    for p in processes:
                        if p.poll() is None:p.terminate()
                    for p in processes:
                        try:p.wait(5)
                        except subprocess.TimeoutExpired:p.kill();p.wait()

if __name__=='__main__':unittest.main()
