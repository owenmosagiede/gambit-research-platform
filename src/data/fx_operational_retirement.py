"""Exact, reviewed retirement of obsolete operational projections and exports."""
from pathlib import Path
import re
from research.contracts import digest, request_id

PROGRESS='storage/catalog/operations/preparation/'
PILOT='storage/catalog/operations/batch_requests/momentum-pilot-20261018/'
PILOT_FILES={PILOT+'manifest.json',PILOT+'ready-preview.json'}


def validate_operational_files(files):
    if not isinstance(files,dict):raise ValueError('Invalid operational retirement inventory')
    for path,binding in files.items():
        if not isinstance(path,str):raise ValueError('Invalid operational retirement path')
        if path not in PILOT_FILES:
            if not path.startswith(PROGRESS) or not path.endswith('.json'):
                raise ValueError('Unreviewed operational retirement path: '+path)
            rid=path[len(PROGRESS):-5]
            if request_id(rid)!=rid:raise ValueError('Noncanonical preparation request path')
        if (not isinstance(binding,dict) or set(binding)!={'sha256','bytes'}
                or not isinstance(binding['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',binding['sha256'])
                or type(binding['bytes']) is not int or binding['bytes']<0):
            raise ValueError('Invalid operational file commitment: '+path)
    if files.keys() & PILOT_FILES and not PILOT_FILES<=files.keys():
        raise ValueError('Pilot input and preview must be reviewed together')


def validate_operational_evidence(root,index,files):
    from data.fx_currency_migration import RETIRED
    from data.alfred_onboarding import stable_read,strict_json
    from runtime.research_jobs import ResearchJobs
    from runtime.research_batches import ResearchBatches,checked
    jobs=ResearchJobs(root)
    def original(path):return strict_json(stable_read(Path(root)/path,index.files[path]['sha256']))
    for path,binding in files.items():
        if index.files.get(path)!=binding:raise ValueError('Operational inventory differs: '+path)
        if not path.startswith(PROGRESS):continue
        value=original(path);rid=path[len(PROGRESS):-5]
        fields={'request_id','attempt_id','plan','plan_id','phase','state','members_total','members_completed',
                'batches_completed','instrument','start','end','updated_at'}
        if not isinstance(value,dict) or set(value)!=fields:raise ValueError('Unknown progress schema: '+path)
        submission=jobs._submission(rid);job=jobs._read_job(rid)
        if (value['request_id']!=rid or value['state']!='complete' or value['phase'] not in ('P1','P2')
                or job is None or job['status']!='succeeded' or submission['intent']['scope']['id'] not in RETIRED
                or value['attempt_id']!=job['attempt_id'] or not job.get('plan') or value['plan']!=job['plan']
                or any(value[k] is not None for k in ('instrument','start','end'))
                or any(type(value[k]) is not int for k in ('members_total','members_completed','batches_completed'))
                or value['members_total']<=0 or value['members_completed']!=value['members_total'] or value['batches_completed']<0):
            raise ValueError('Progress is not a completed retired-CS projection: '+path)
        plan=jobs.store.resolve('plan',value['plan'])['body']
        if plan['plan_id']!=value['plan_id'] or plan['intent']!=submission['intent']:
            raise ValueError('Progress plan differs from authoritative research: '+path)
    if not files.keys() & PILOT_FILES:return
    request=original(PILOT+'manifest.json');preview=original(PILOT+'ready-preview.json')
    bid=request_id(request['batch_id']);base='storage/catalog/operations/research_batches/'+bid+'/'
    manifest=original(base+'manifest.json');state=checked(Path(root)/base/'state.json');approval=checked(Path(root)/base/'approval.json')
    # Reconciliation must already have verified the completed mixed batch. The
    # original manifest/approval are read, never replaced by these saved copies.
    replacement=index.records.overlay.get(base+'manifest.json',{})
    if (request!=manifest['request'] or state['state']!='completed'
            or replacement.get('schema')!='research_batch_retained_ts_v1'
            or approval['manifest_sha256']!=manifest['sha256']):
        raise ValueError('Pilot export is not tied to a verified completed mixed batch')
    batches=ResearchBatches(jobs);frozen=batches._preview(Path(root)/base,manifest)
    rows=batches._rows(Path(root)/base)
    items=[{k:v for k,v in row.items() if k not in ('sha256','packet_sha256')} for row in rows]
    fields={'batch_id','name','state','created_at','requested_combinations','unique_experiments','input_duplicates',
            'previewed','preview_complete','preview_sha256','preview_counts','estimates','free_bytes_on_workspace_filesystem',
            'job_counts','items','implementation_fingerprint','approved','research_results'}
    if (not isinstance(preview,dict) or set(preview)!=fields or preview['batch_id']!=bid
            or preview['name']!=request['name'] or preview['created_at']!=manifest['created_at']
            or preview['requested_combinations']!=manifest['requested_combinations']
            or preview['unique_experiments']!=len(manifest['intents']) or preview['input_duplicates']!=manifest['input_duplicates']
            or preview['previewed']!=len(rows) or preview['preview_complete'] is not True
            or preview['preview_sha256']!=digest(frozen) or preview['preview_sha256']!=approval['approval']['preview_sha256']
            or preview['preview_counts']!=frozen['counts'] or preview['estimates']!=frozen['estimates']
            or preview['approved'] is not False or preview['job_counts']!={} or preview['items']!=items
            or preview['implementation_fingerprint']!=manifest['implementation']['fingerprint']):
        raise ValueError('Pilot preview differs from its approved authoritative evidence')
    old_state=preview['state']
    if (not isinstance(old_state,dict) or set(old_state)!={'state','sha256','updated_at'}
            or old_state['state']!='ready' or old_state['sha256']!=digest({k:v for k,v in old_state.items() if k!='sha256'})):
        raise ValueError('Pilot preview state is not an original ready export')
