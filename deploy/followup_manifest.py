"""Read-only binding view for an already accepted negative-direction follow-up.

The original manifest bytes remain the approval identity. This derived view
only adapts its explicitly pinned parent bindings for existing cutover checks.
It cannot add submissions, redefine science, or grant execution approval.
"""
from copy import deepcopy
from hashlib import sha256
import json


def binding_view(root, raw, parent_raw=None):
    from runtime.research_jobs import ResearchJobs
    from runtime.experiment_identity import scientific_key
    from research.contracts import digest, HORIZONS
    from research.inputs import _validate_plan
    value = json.loads(raw)
    classification = 'exploratory_post_selection_negative_direction_followup'
    if value.get('classification') != classification:
        if parent_raw is not None:
            raise RuntimeError('Parent manifest supplied for an unsupported program')
        return value
    def require(ok, message):
        if not ok: raise RuntimeError('Frozen follow-up: '+message)
    require(parent_raw is not None and sha256(parent_raw).hexdigest()==value['parent_manifest_sha256'],
            'exact approved parent manifest required')
    parent = json.loads(parent_raw)
    require(value['expected_direction']=='NEGATIVE' and value['horizons']==list(HORIZONS)
            and value['preserve_original_results'] is True,'direction, horizons or preservation differs')
    require(isinstance(value['entries'],list) and bool(value['entries']),'empty cohort')
    parent_rows = {r.get('expected_existing_request_id',r['request_id']):r for r in parent['entries']}
    jobs = ResearchJobs(root,start_worker=False); events = jobs._event_snapshot()
    view = deepcopy(parent); view['entries']=[]; implementation=None; seen=set()
    for row in value['entries']:
        rid=row['request_id']; parent_id=row['parent_request_id']
        require(rid not in seen and parent_id in parent_rows,'duplicate request or unknown parent')
        seen.add(rid)
        original=jobs._submission(parent_id); child=jobs._submission(rid)
        require(original['record_sha256']==row['parent_record_sha256'],'parent envelope changed')
        require(jobs._read_job(parent_id,events)['status']=='succeeded','parent research is not complete')
        require(original['intent']['expected_direction']=='POSITIVE','parent direction differs')
        expected_intent=dict(original['intent'],expected_direction='NEGATIVE')
        require(child['intent']==row['intent']==expected_intent,'only the approved direction may differ')
        require(scientific_key(child)==row['expected_scientific_identity'],'frozen child scientific identity differs')
        require(digest(child['implementation'])==value['executor_digest'],'frozen child executor differs')
        if implementation is None: implementation=child['implementation']
        require(child['implementation']==implementation,'mixed original child executors')
        # Compare all scientific plan fields. The first accepted follow-ups
        # legitimately froze a newer optional output inventory than the parent.
        # Keep that child inventory intact: its complete original envelope hash
        # is verified by _submission and pinned by capture, never reconstructed.
        expected=deepcopy(original['frozen_plan']); expected['intent']=deepcopy(expected_intent)
        expected.pop('plan_id',None); actual=deepcopy(child['frozen_plan']); actual.pop('plan_id',None)
        for member in expected['members']+actual['members']:
            member.pop('feature_materializations',None)
        require(actual==expected and child['research_spec']==original['research_spec'],
                'child scientific inputs, membership, periods or Research Spec differ from parent')
        _validate_plan(child['frozen_plan'])
        bound=deepcopy(parent_rows[parent_id])
        for key in tuple(bound):
            if key.startswith('expected_existing_'): del bound[key]
        bound.update(request_id=rid,intent=deepcopy(row['intent']))
        view['entries'].append(bound)
    view['global_pins']['implementation_digest']=value['executor_digest']
    view['global_pins']['implementation_fingerprint']=implementation['fingerprint']
    return view
