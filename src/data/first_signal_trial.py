"""One configured archive-date PIT -> stored Signal path; no research or network.

Source interpretation is delegated upstream. The recipe, engine, evaluation
schedule, publication and fresh reads use canonical provider-neutral contracts.
"""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.metadata
import platform
from pathlib import Path

from data.alfred_onboarding import Store, identified, strict_json, stable_read
from data.stored_pit_source import load_source
from data.pit_feature_adapter import adapt_pit_history
from data.feature_evaluation import execute_scheduled_recipe
from data.feature_store import FeatureStore, publish_feature, retrieve_signal
from data.feature_store_contracts import validate_record
from data.transformations.registry import Registry
from data.transformations.identity import (canonical_bytes, digest, reference, make_feature_definition,
    normalize_recipe, normalize_bindings)

POLICY_ID='POL_TRANSFORM_EVALUATION_NATIVE_VINTAGES'
POLICY_VERSION='2.0.0'
RULES={'cutoff_schedule':'all_observed_native_vintage_dates',
       'current_reference':'latest_reference_month_at_cutoff',
       'denominator_reference':'previous_calendar_month','missing_required':'retain_null',
       'history_mode':'resolved_state','temporal_precision':'date','interpretation':'archive_date_replay'}


def approved_policy_records(source_view):
    """Encode the user's explicitly approved rule; never infer or auto-approve it.

    Used only by the separately requested publication of this approved policy.
    Native dates/counts are materialization coverage, not recipe identity limits.
    """
    policy_text={'schema_version':'1.0.0','title':'Approved archive-date single-feature evaluation policy',
        'approval':'Explicit user approval in this task: one output per stored vintage date; latest reference month divided by the immediately preceding calendar month from the same state, less one.',
        'source_view':source_view,'rules':RULES,
        'limitations':['Archive date replay only; no exact release event or intraday trading-decision availability claim.',
                      'Required missing monthly operands and zero denominators retain scheduled null rows; no filling or skipping.',
                      'The observed cutoff list and coverage belong to each materialization, not the logical Signal.']}
    payload=canonical_bytes(policy_text)+b'\n'
    import hashlib
    sha=hashlib.sha256(payload).hexdigest()
    evidence=identified('onboarding_evidence',{'kind':'transform_execution_policy',
        'payload':{'sha256':sha,'byte_count':len(payload),'row_count':None},'media_type':'application/json',
        'description':'User-approved source-associated archive-date evaluation rule; exact schedules remain materialization evidence.'},'EVIDENCE_')
    parameters=[{'name':name,'unit':'policy_setting','value':{'kind':'token','value':value}} for name,value in sorted(RULES.items())]
    parameters.append({'name':'source_view','unit':'source_view','value':{'kind':'reference','value':source_view}})
    policy={'schema_version':'0.2.0','record_type':'policy_definition','id':POLICY_ID,'version':POLICY_VERSION,
        'display_name':'Native archive-date evaluation of one monthly percentage-change feature',
        'body':{'kind':'selection','specification':reference(evidence),'parameters':parameters,
                'approval_state':'approved','compatibility_evidence':[]}}
    return policy,evidence,payload


def install_approved_policy(root, source_view):
    policy,evidence,payload=approved_policy_records(source_view)
    store=FeatureStore(root)
    store.io.blob(payload,'json','approved_evaluation_policy',None)
    store.install_record(evidence);store.install_record(policy)
    return reference(policy)


def build_recipe(request, source, registry):
    if request.get('evaluation_policy') is None:raise ValueError('Blocked: an explicitly approved source-associated evaluation policy is required')
    entry=registry.resolve(request['operator']);contract=entry['body']['execution_contract']
    if entry['id']!='TR_BASE_change_pct' or entry['version']!='2.0.0' or contract['kernel']!='change.pct' or request['parameters']!={'k':1}:
        raise ValueError('This bounded invocation permits exactly generic change.pct version2 with k=1')
    if request['history_mode']!='resolved_state' or request['output_unit']!='dimensionless':raise ValueError('Wrong calculation mode or output unit')
    recipe={'sources':[{'alias':'source','source_view':reference(source['source_view'])}],
        'steps':[{'node':'monthly_fractional_change','phase':'transformation','operator':reference(entry),'inputs':['source'],
                  'parameters':[{'name':'k','unit':'observations','value':{'kind':'integer','value':'1'}}]}],
        'output_node':'monthly_fractional_change','output_unit':'dimensionless','calculation_scope_requirement':'none','scope_policy':None,
        'selection':request['selection'],'history_mode':'resolved_state',
        'history_policy':reference(registry.get_policy('POL_TRANSFORM_HISTORY')),
        'execution_policy':reference(registry.get_policy('POL_TRANSFORM_EXECUTION')),
        'evaluation_policy':request['evaluation_policy']}
    return normalize_recipe(recipe)


def pin_implementation(root, determinism_policy):
    """Store exact code/schema/environment evidence under existing shared paths."""
    root=Path(root).resolve();store=FeatureStore(root)
    code_paths=['src/data/first_signal_trial.py','src/data/feature_store.py','src/data/feature_store_contracts.py',
        'src/data/feature_evaluation.py','src/data/stored_pit_source.py','src/data/pit_feature_adapter.py','src/data/pit_selection.py',
        'src/data/alfred_onboarding.py','src/data/alfred_pit.py','src/data/alfred_full_history.py','src/data/alfred_full_acquisition.py',
        'src/api/pit_library.py','src/contracts/experiment.py',
        'src/data/transformations/__init__.py','src/data/transformations/numeric.py','src/data/transformations/registry.py',
        'src/data/transformations/contracts.py','src/data/transformations/identity.py','src/data/transformations/engine.py',
        'specs/schemas/feature_store.schema.json','specs/schemas/platform.schema.json','specs/schemas/onboarding.schema.json',
        'specs/schemas/transformation_execution.schema.json','tools/run_first_signal_trial.py']
    artifacts=[store.io.blob(stable_read(root/path),'bin',path.replace('/','.'),None) for path in code_paths]
    environment={'python':platform.python_version(),'implementation':platform.python_implementation(),
        'jsonschema':importlib.metadata.version('jsonschema'),'arithmetic':'IEEE754_binary64','serialization':'canonical_decimal_strings'}
    env=store.io.blob(canonical_bytes(environment)+b'\n','json','environment',None)
    record={'schema_version':'0.2.0','record_type':'implementation_manifest','version':'1.0.0',
        'code_artifacts':artifacts,'environment_artifacts':[env],'entrypoint_id':'first_signal_trial',
        'determinism_policy':determinism_policy}
    record['id']='IMPLEMENTATION_'+digest(record)
    return record


def run_trial(root, request):
    root=Path(root).resolve()
    source=load_source(root,request)
    registry=Registry(root)
    recipe=build_recipe(request,source,registry)
    adapted=adapt_pit_history(dataset=source['dataset'],source_view=source['source_view'],pit_snapshot=source['pit_snapshot'],
        raw_snapshots=source['raw_snapshots'],rows=source['rows'],mapping=source['mapping'],history_policy=recipe['history_policy'],
        provenance={'provider':source['source_metadata']['provider'],'native_series_id':source['source_metadata']['native_series_id']})
    # Validate the approved rule before installing any execution evidence.
    from data.feature_evaluation import resolve_native_schedule
    cutoffs=resolve_native_schedule(adapted['series'],recipe,registry)
    if cutoffs!=adapted['available_vintages']:raise ValueError('Evaluation coverage differs from complete stored native dates')
    feature=make_feature_definition(recipe,source['dataset']['display_name']+' - monthly fractional change')
    implementation=pin_implementation(root,reference(registry.get_policy('POL_TRANSFORM_EXECUTION')))
    executed=execute_scheduled_recipe(adapted['series'],recipe,registry=registry,implementation=reference(implementation))
    result=executed['result']
    if len(result['observations'])!=len(cutoffs) or result['execution']['cutoffs']!=cutoffs:
        raise ValueError('Scheduled outputs do not cover the exact source schedule')
    policies=normalize_bindings([{'role':'execution','artifact':recipe['execution_policy']},
        {'role':'history','artifact':recipe['history_policy']},{'role':'evaluation','artifact':recipe['evaluation_policy']},
        *source['source_policy_bindings']])
    metadata={'dataset':reference(source['dataset']),'source_view':reference(source['source_view']),
        'selection':result['selection'],'unit':result['unit'],'value_semantics':result['value_semantics'],
        'cadence':result['cadence'],'history_policy':recipe['history_policy'],'history_mode':'resolved_state',
        'temporal_precision':'date','availability_semantics':'derived_at_cutoff','source_policy_bindings':source['source_policy_bindings']}
    used={ref['id'] for links in executed['operand_links'] for ref in links.values()}
    publication=publish_feature(root,feature=feature,input_series=adapted['series'],result=result,metadata=metadata,
        operand_links=executed['operand_links'],operand_records=[r for r in adapted['operand_records'] if r['id'] in used],
        supporting_records=[],implementation=implementation,policy_bindings=policies)
    retrieved=retrieve_signal(root,publication['signal_id'],publication['materialization']['id'])
    # Separate operational audit does not enter recipe/materialization identity.
    import uuid
    attempt=str(uuid.uuid4());audit={'schema_version':'0.3.0','record_type':'feature_execution_audit',
        'attempt_id':attempt,'state':'succeeded','executed_at':result['execution']['executed_at'],
        'completed_at':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        'signal_id':publication['signal_id'],'feature':publication['feature'],'materialization':publication['materialization'],
        'reused':publication['reused'],'row_count':len(result['observations'])}
    audit_path=f'storage/catalog/attempts/{attempt}/events/{digest(audit)}.json'
    validate_record(audit)
    FeatureStore(root).io.install(audit_path,canonical_bytes(audit)+b'\n')
    return {**publication,'audit_path':audit_path,'coverage':{'first_cutoff':cutoffs[0],'last_cutoff':cutoffs[-1],'scheduled_rows':len(cutoffs)},
        'status_counts':retrieved['manifest']['status_counts'],'unit':retrieved['manifest']['metadata']['unit'],
        'availability_precision':'date','materialization_state':retrieved['materialization_state'],'scientific_state':retrieved['scientific_state']}
