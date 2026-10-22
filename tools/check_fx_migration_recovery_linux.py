#!/usr/bin/env python3
"""Explicit synthetic systemd fault injection; never controls Gambit services.

Requires Linux root and --allow-systemd. Uses uniquely named test units, a 64 MiB
worker, and a synthetic registry. No production experiments or data are used.
"""
import argparse,json,os,subprocess,sys,tempfile,time,uuid
from pathlib import Path

FIXTURE=r'''
import hashlib,json,os,signal,subprocess,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import fx_migration_control as c
import release_server
base=Path(sys.argv[2]);unit=sys.argv[3];mode=sys.argv[4];action=sys.argv[5]
prefix=unit.removesuffix('-worker.service')
c.UNITS=release_server.UNITS=(prefix+'-web.service',prefix+'-research.service')
class Fake:
 def __init__(self):
  self.root=base/'root';self.state=base/'releases';self.backup=base/'backup'
  for p in (self.root,self.state,self.backup):p.mkdir(exist_ok=True)
 def live(self):return {u:self.status(u) for u in c.UNITS}
 def status(self,u):return subprocess.check_output(['systemctl','show',u,'--property=ActiveState','--value'],text=True).strip()
 def stop(self,u):subprocess.run(['systemctl','stop',u],check=True)
 def start(self,u):subprocess.run(['systemctl','start',u],check=True)
 def scope_commitment(self):return {'synthetic':hashlib.sha256((base/'registry').read_bytes()).hexdigest()}
 def pin_code(self,expected):assert expected=={'synthetic':'test'}
 def backup_ready(self):pass
 def idle(self):pass
 def health(self):assert all(v=='active' for v in self.live().values())
 def markers(self):return (base/'mutation-marker').exists()
 def worker_dead(self):
  v=subprocess.check_output(['systemctl','show',unit,'--property=MainPID,ActiveState'],text=True)
  d=dict(line.split('=',1) for line in v.splitlines());return d['MainPID']=='0' and d['ActiveState'] in ('failed','inactive')
 def child(self,folder,action):
  assert action=='resume-plan'
  if mode=='after-marker':(base/'mutation-marker').write_text('synthetic only')
  if mode=='oom':
   blocks=[]
   while True:blocks.append(bytearray(8*1024*1024))
  os.kill(os.getpid(),signal.SIGKILL)
if action=='run':c.run(Fake(),base/'attempt')
else:c.recover(Fake(),base/'attempt')
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--allow-systemd',action='store_true');p.add_argument('--controller-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 if not a.allow_systemd or sys.platform!='linux' or os.geteuid()!=0:raise SystemExit('Explicit Linux root synthetic-test authorization required')
 results=[]
 with tempfile.TemporaryDirectory(prefix='gambit-recovery-test-') as temp:
  top=Path(temp);fixture=top/'fixture.py';fixture.write_text(FIXTURE)
  for mode in ('sigkill','oom','after-marker'):
   base=top/mode;base.mkdir();(base/'attempt').mkdir();(base/'registry').write_bytes(b'synthetic registry, no observations')
   (base/'attempt/attempt.json').write_text(json.dumps({'code_sha256':{'synthetic':'test'}}))
   prefix='gambit-migration-test-'+uuid.uuid4().hex[:12];worker=prefix+'-worker.service';recovery=prefix+'-recovery.service'
   unit=Path('/run/systemd/system')/recovery
   apps=(prefix+'-web.service',prefix+'-research.service')
   app_files=[unit.with_name(name) for name in apps]
   for path in app_files:
    path.write_text('[Unit]\nConditionPathExists=!'+str(base/'maintenance')+'\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/bin/true\n')
   command=[sys.executable,str(fixture),str(a.controller_dir.resolve()),str(base),worker,mode]
   # Generated paths contain no whitespace and no shell interpretation is used.
   if any(any(c.isspace() for c in v) for v in command):raise ValueError('Test paths must not contain whitespace')
   template=(a.controller_dir/'systemd/gambit-fx-migration-recovery.service').read_text()
   template=template.replace('gambit-web.service',apps[0]).replace('gambit-worker.service',apps[1])
   template='\n'.join(line for line in template.splitlines() if not line.startswith(('ExecStart=','RequiresMountsFor=')))
   template=template.replace('[Install]','ExecStart='+' '.join(command+['recover'])+'\n[Install]')
   unit.write_text(template)
   try:
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','start',*apps],check=True)
    subprocess.run(['systemd-run','--unit='+worker,'--property=OnFailure='+recovery,'--property=MemoryMax=64M','--property=MemorySwapMax=0','--property=OOMPolicy=kill',*command,'run'],check=True,capture_output=True)
    deadline=time.monotonic()+45;status={}
    while time.monotonic()<deadline:
     path=base/'attempt/status.json'
     if path.exists():status=json.loads(path.read_text())
     if status.get('phase') in ('restored','recovery_required'):break
     time.sleep(.25)
    expected='recovery_required' if mode=='after-marker' else 'restored'
    assert status.get('phase')==expected,(mode,status)
    if mode=='after-marker':
     # Simulate normal boot/start attempts: the persistent gate must refuse them.
     subprocess.run(['systemctl','start',*apps],check=True)
    live={u:subprocess.check_output(['systemctl','show',u,'--property=ActiveState','--value'],text=True).strip() for u in apps}
    assert all(v==('inactive' if mode=='after-marker' else 'active') for v in live.values())
    assert (base/'maintenance').exists()==(mode=='after-marker')
    result=subprocess.check_output(['systemctl','show',worker,'--property=Result','--value'],text=True).strip()
    if mode=='oom':assert result=='oom-kill',result
    results.append({'fault':mode,'worker_result':result,'recovery_phase':status['phase'],'real_isolated_service_restart':True,'passed':True})
   finally:
    subprocess.run(['systemctl','stop',worker,recovery,*apps],capture_output=True)
    subprocess.run(['systemctl','reset-failed',worker,recovery,*apps],capture_output=True)
    for path in [unit,*app_files]:path.unlink(missing_ok=True)
    subprocess.run(['systemctl','daemon-reload'],check=True)
 a.output.write_text(json.dumps({'production_data_used':False,'production_services_changed':False,'cases':results},indent=2)+'\n')
 print(a.output.read_text())
if __name__=='__main__':main()
