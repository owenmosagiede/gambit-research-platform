"""Seven fixed currency Scopes with explicit quote semantics and frozen membership."""
from datetime import datetime, timedelta, timezone

from data.feature_store import FeatureStore
from data.fx_records import make_record
from data.fx_currency_catalog import resolve_prices
from data.transformations import fx_currency as currency
from data.transformations.identity import reference, digest

PROFILE = 'currency_quote_scopes.1.0.0'


def _records(catalog, instruments):
    evidence=make_record('onboarding_evidence',{'kind':'currency_scope_specification','profile':PROFILE,
        'price_catalog':reference(catalog),'approval':catalog['body']['approval'],
        'member_order':'currency_code_ascending','membership':'all_supported_non_reference_currencies',
        'readiness_filtering':False,'research_basis':'currency_against_quote_reference'})
    policies=[{'schema_version':'0.2.0','record_type':'policy_definition',
        'id':'POLICY_FX_CURRENCY_'+kind.upper(),'version':'1.0.0','display_name':'Currency Scope '+kind,
        'body':{'kind':kind,'specification':reference(evidence),'parameters':[],
                'approval_state':'approved','compatibility_evidence':[]}}
        for kind in ('membership','eligibility','exclusion')]
    definitions=[{'schema_version':'0.2.0','record_type':'scope_definition','id':'FX_CCY_VS_'+q,
        'version':'1.0.0','display_name':q+' Pairs (currencies versus '+q+')',
        'body':{'kind':'universe','entity_ids':sorted(instruments[s]['economic_id'] for s in currency.members(q)),
                **{p['body']['kind']+'_policy':reference(p) for p in policies}}} for q in currency.REFERENCES]
    metadata={s:{'instrument_id':s,'economic_id':r['economic_id'],
        'base_currency':r['source_metadata']['base_currency'],'quote_currency':r['source_metadata']['quote_currency'],
        'instrument_registration':r['registration']} for s,r in instruments.items()}
    resolution=make_record('onboarding_evidence',{'kind':'currency_scope_resolution','profile':PROFILE,
        'specification':reference(evidence),'price_catalog':reference(catalog),
        'registered_instruments':[metadata[s] for s in sorted(metadata)]})
    return evidence,policies,definitions,metadata,resolution


def register(root,catalog_ref,*,registered_at=None):
    from data.scopes import _make_snapshot,_snapshot_index,_preflight
    store=FeatureStore(root);catalog,instruments=resolve_prices(root,catalog_ref)
    evidence,policies,definitions,metadata,resolution=_records(catalog,instruments)
    index=_snapshot_index(store)
    prior=[s for (identifier,version),values in index.items() if identifier in currency.SCOPE_IDS for s in values]
    when=registered_at or datetime.now(timezone.utc)
    if when.utcoffset()!=timedelta(0):raise ValueError('UTC registration timestamp required')
    period=prior[0]['period'] if prior else {'start_inclusive':when.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        'end_exclusive':(when+timedelta(microseconds=1)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}
    snapshots,payloads=[],[]
    for definition in definitions:
        snapshot,payload=_make_snapshot(definition,metadata,policies,evidence,resolution,period)
        snapshots.append(snapshot);payloads.append((snapshot['members'][0],payload))
    records=[evidence,resolution,*policies,*snapshots,*definitions]
    with store.writer():
        _preflight(store,records,payloads)
        for member,payload in payloads:store.io.blob(payload,'jsonl','membership',member['row_count'])
        for record in records:store.install_record(record)
    return [reference(d) for d in definitions]


def resolve(store,definition,index):
    from data.scopes import _make_snapshot,_readiness
    snapshots=index.get((definition['id'],definition['version']),[])
    if len(snapshots)!=1:raise ValueError('Currency Scope requires one frozen membership snapshot')
    snapshot=snapshots[0]
    if snapshot['period']['start_inclusive']>=snapshot['period']['end_exclusive']:
        raise ValueError('Invalid currency membership registration interval')
    if len(snapshot['lineage'])!=2:raise ValueError('Currency membership lineage differs')
    resolution=store.resolve(snapshot['lineage'][0])
    catalog,instruments=resolve_prices(store.root,resolution['body']['price_catalog'])
    evidence,policies,definitions,metadata,expected_resolution=_records(catalog,instruments)
    if resolution!=expected_resolution or store.resolve(snapshot['lineage'][1])!=evidence:
        raise ValueError('Currency membership specification differs')
    if definition not in definitions or store.resolve(reference(definition))!=definition:
        raise ValueError('Currency Scope definition differs from its approved frozen membership')
    for policy in policies:
        if store.resolve(reference(policy))!=policy:raise ValueError('Currency membership policy differs')
    expected,payload=_make_snapshot(definition,metadata,policies,evidence,resolution,snapshot['period'])
    if snapshot!=expected or store.payload(snapshot['members'][0])!=payload:
        raise ValueError('Currency membership rows or hash differ')
    q=definition['id'].removeprefix('FX_CCY_VS_');members=currency.members(q);binding=reference(snapshot)
    return {'id':definition['id'],'version':definition['version'],'kind':'universe','display_name':definition['display_name'],
        'reference':reference(definition),'definition_binding':reference(definition),'member_count':18,'members':members,
        'economic_entity_ids':definition['body']['entity_ids'],'membership_snapshot':binding,
        'research_basis':'currency_against_quote_reference','reference_currency':q,'price_catalog':reference(catalog),
        'readiness':_readiness(members,instruments),'experiment_scope':{'id':definition['id'],'version':definition['version']},
        'dependency':{'requirement':'required','bindings':[{'role':'membership','artifact':binding},
            {'role':'currency_prices','artifact':reference(catalog)},
            *[{'role':p['body']['kind']+'_policy','artifact':reference(p)} for p in policies]]}}
