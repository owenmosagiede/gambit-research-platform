"""Immutable research authority, shared evidence payloads and rebuildable links."""
from pathlib import Path
from contextlib import contextmanager
import fcntl, hashlib, json, os, tempfile
from .contracts import canonical,digest,ref,scientific,identifier,ResearchError,ResearchConflict

FOLDERS={'relationship':'signal_library/relationships','trial':'trial_ledger/records',
 'admission':'admission_ledger/records','validation':'validation_ledger/records',
 'plan':'research_plans','exposure':'research_exposure/records','link':'signal_library/research_links',
 'implementation':'research_implementations'}
PREFIX={'relationship':'RELATIONSHIP','trial':'TRIAL','admission':'ADMISSION','validation':'VALIDATION',
 'plan':'RESEARCHPLAN','exposure':'EXPOSURE','link':'RESEARCHLINK','implementation':'RESEARCHIMPLEMENTATION'}

def inside(root,relative):
    root=Path(root).resolve();p=(root/relative).resolve()
    if not p.is_relative_to(root):raise ResearchError('Storage path escapes workspace')
    return p

def read_json(p):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ResearchError('Duplicate JSON key')
            result[k]=v
        return result
    return json.loads(p.read_bytes(),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ResearchError('Nonfinite JSON')))

def install_bytes(path,data,*,mutable=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and not mutable:
        if path.read_bytes()!=data:raise ResearchConflict('Conflicting immutable record: '+path.name)
        return
    fd,tmp=tempfile.mkstemp(prefix='.install-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
        if mutable:os.replace(tmp,path)
        else:
            try:os.link(tmp,path)
            except FileExistsError:
                if path.read_bytes()!=data:raise ResearchConflict('Conflicting immutable publication')
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

@contextmanager
def lock(root,name,nonblocking=False):
    p=inside(root,'storage/catalog/operations/'+name+'.lock');p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a+b') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|(fcntl.LOCK_NB if nonblocking else 0))
        except BlockingIOError:yield False;return
        try:yield True
        finally:fcntl.flock(f,fcntl.LOCK_UN)

class ResearchStore:
    def __init__(self,root):self.root=Path(root).resolve()
    def path(self,kind,identity):
        identifier(identity)
        if kind not in FOLDERS or not identity.startswith(PREFIX[kind]+'_'):raise ResearchError('Wrong research record type')
        return inside(self.root,'storage/catalog/'+FOLDERS[kind]+'/'+identity+'.json')
    def put(self,kind,key,body):
        record=scientific({'schema_version':'0.8.0','record_type':'research_'+kind,'version':'1.0.0',
            'id':PREFIX[kind]+'_'+digest(key),'scientific_key':key,'body':body})
        record['record_sha256']=digest(record)
        install_bytes(self.path(kind,record['id']),canonical(record)+b'\n');return record
    def get(self,kind,identity):
        p=self.path(kind,identity);record=read_json(p)
        if record.get('schema_version')!='0.8.0' or record.get('record_type')!='research_'+kind or record.get('id')!=identity or identity!=PREFIX[kind]+'_'+digest(record['scientific_key']):raise ResearchError('Research record identity mismatch')
        if record.get('record_sha256')!=digest({k:v for k,v in record.items() if k!='record_sha256'}):raise ResearchError('Research record checksum mismatch')
        if p.read_bytes()!=canonical(record)+b'\n':raise ResearchError('Noncanonical research record')
        return record
    def resolve(self,kind,reference):
        value=self.get(kind,reference['id'])
        if ref(value)!=reference:raise ResearchError('Research reference checksum mismatch')
        return value
    def find(self,kind,key):
        identity=PREFIX[kind]+'_'+digest(key)
        return self.get(kind,identity) if self.path(kind,identity).is_file() else None
    def payload(self,role,value):
        data=canonical(value)+b'\n';sha=hashlib.sha256(data).hexdigest()
        install_bytes(inside(self.root,f'storage/payloads/sha256/{sha[:2]}/{sha}.json'),data)
        return {'role':role,'blob_sha256':sha,'format':'json','byte_count':len(data)}
    def artifact(self,key,values):
        members=[self.payload(k,v) for k,v in sorted(values.items())]
        body={'schema_version':'0.8.0','record_type':'research_artifact','version':'1.0.0',
              'scientific_key_sha256':digest(key),'members':members}
        body['id']='ARTIFACT_'+digest(body)
        install_bytes(inside(self.root,'storage/catalog/trial_artifacts/'+body['id']+'/manifest.json'),canonical(body)+b'\n')
        return body
    def verify_artifact(self,reference):
        identifier(reference['id']);p=inside(self.root,'storage/catalog/trial_artifacts/'+reference['id']+'/manifest.json');a=read_json(p)
        if ref(a)!=reference or a['id']!='ARTIFACT_'+digest({k:v for k,v in a.items() if k!='id'}):raise ResearchError('Artifact manifest mismatch')
        for m in a['members']:
            sha=m['blob_sha256']
            if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ResearchError('Bad payload hash')
            data=inside(self.root,f'storage/payloads/sha256/{sha[:2]}/{sha}.json').read_bytes()
            if hashlib.sha256(data).hexdigest()!=sha or len(data)!=m['byte_count']:raise ResearchError('Artifact corruption')
        return a
    def results_for_recipe(self,recipe_id):
        """Read authority by exact recipe ID; indexes/projections are not metrics."""
        result=[];directory=inside(self.root,'storage/catalog/'+FOLDERS['relationship'])
        if not directory.exists():return []
        for p in sorted(directory.glob('RELATIONSHIP_*.json')):
            raw=read_json(p)
            if raw.get('schema_version')!='0.8.0':continue # prior profile handled by its reader
            rel=self.get('relationship',p.stem)
            if rel['body']['recipe']['id']!=recipe_id:continue
            links=inside(self.root,'storage/catalog/'+FOLDERS['link'])
            candidates=[self.get('link',lp.stem) for lp in sorted(links.glob('RESEARCHLINK_*.json'))] if links.exists() else []
            candidates=[v for v in candidates if v['body']['relationship']==ref(rel)]
            def evidence(v):return {digest(r) for k in ('trial_results','admission_results','validation_results') for r in v['body'][k]}
            # Earlier partial link projections stay immutable; show each maximal
            # completed evidence branch once, retaining independent reruns.
            for link in candidates:
                if any(evidence(link)<evidence(other) for other in candidates):continue
                trials=[self.resolve('trial',r) for r in link['body']['trial_results']]
                for trial in trials:
                    for a in trial['body']['artifact_manifests']:self.verify_artifact(a)
                admissions=[self.resolve('admission',r) for r in link['body']['admission_results']]
                validations=[self.resolve('validation',r) for r in link['body']['validation_results']]
                trial_refs={digest(ref(t)):t for t in trials}
                for trial in trials:
                    if trial['scientific_key']['relationship']!=ref(rel):raise ResearchError('Trial belongs to another relationship')
                for admission in admissions:
                    if admission['body']['relationship']!=ref(rel) or digest(admission['body']['trial']) not in trial_refs:
                        raise ResearchError('Admission does not belong to the linked relationship/trial')
                    if trial_refs[digest(admission['body']['trial'])]['body']['stage']!='P1':raise ResearchError('Admission must reference P1')
                for validation in validations:
                    body=validation['body'];origin=body['discovery_trial'];evaluation=body['evaluation_trial']
                    if body['relationship']!=ref(rel) or digest(origin) not in trial_refs or trial_refs[digest(origin)]['body']['stage']!='P1':
                        raise ResearchError('Validation discovery relationship mismatch')
                    if evaluation is not None:
                        if digest(evaluation) not in trial_refs or trial_refs[digest(evaluation)]['body']['stage']!='P2':raise ResearchError('Validation evaluation mismatch')
                        if trial_refs[digest(evaluation)]['scientific_key']['discovery_trial']!=origin:raise ResearchError('Validation refers to another discovery result')
                    elif body['decision']=='VALIDATED':raise ResearchError('Validation success requires an evaluation trial')
                result.append({'signal_id':'SIGNAL_'+rel['body']['recipe']['id'].removeprefix('FEATURE_RECIPE_').removeprefix('FEATURE_'),
                    'projection':ref(link),'relationship':ref(rel),'attempt_ids':[],**{k:link['body'][k] for k in ('trial_results','admission_results','validation_results')},
                    'scope':rel['body']['scope'],'mode':rel['body']['mode'],'horizon':rel['body']['horizon'],
                    'target_family':rel['body']['target_family'],'expected_direction':rel['body']['expected_direction'],
                    'results':[{'stage':t['body']['stage'],'metrics':t['body']['metrics'],'sample':t['body']['sample'],
                        'period':t['scientific_key']['period'],'research_spec':t['scientific_key']['research_spec'],
                        'authority':ref(t)} for t in trials],
                    'p1_status':admissions[-1]['body']['decision'] if admissions else 'unresolved',
                    'p2_status':validations[-1]['body']['decision'] if validations else 'not_run'})
        return result
