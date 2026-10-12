#!/usr/bin/env python3
"""Onboard the fixed, bounded CES0500000003 / 2018 ALFRED pilot.

Use --fetch to perform five official GETs, otherwise replay a saved acquisition
bundle. Legacy files are opened read-only. This command creates no scheduler.
"""
from pathlib import Path
import argparse
import datetime as dt
import gzip
import json
import platform
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from data.alfred_onboarding import (SERIES, BASE_URL, Store, canonical, sha, strict_json,
    stable_read, parse_vintages, as_of, ref, identified, now, fetch_evidence)

RAW='raw/v1/alfred/69/691e9ffebc518fec7bcf645c9bf69e6db571cf53f549829bbe6e89bdc6a86e7b.json'
RAW_HASH='691e9ffebc518fec7bcf645c9bf69e6db571cf53f549829bbe6e89bdc6a86e7b'
START='2018-01-01T00:00:00.000000Z'; END='2019-01-01T00:00:00.000000Z'
DOCS=['https://fred.stlouisfed.org/docs/api/fred/',
      'https://fred.stlouisfed.org/docs/api/fred/series_observations.html',
      'https://fred.stlouisfed.org/docs/api/fred/realtime_period.html',
      'https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html',
      'https://fred.stlouisfed.org/docs/api/api_key.html',
      'https://fred.stlouisfed.org/docs/api/fred/errors.html',
      'https://alfred.stlouisfed.org/help']

def utc(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(dt.timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')

def onboard(root, legacy, acquisition):
    store=Store(root); stamped=now(); legacy=Path(legacy); acquisition=Path(acquisition)
    before={}; raw=stable_read(legacy/RAW,RAW_HASH); before[RAW]=sha(raw)
    archived=strict_json(raw); old_rows=parse_vintages(archived)
    legacy_meta={}
    for name in ['raw-ingestion-manifest.json','series-manifest.json','dataset-registry.json','source-registry.json']:
        path=f'production/alfred/series={SERIES}/{name}'
        data=stable_read(legacy/path);before[path]=sha(data);legacy_meta[name]=strict_json(data)
    old_receipt=legacy_meta['raw-ingestion-manifest.json']['ingestions'][0]
    if old_receipt['checksum']['value']!=RAW_HASH or old_receipt['response']['stored_content_transform']!='none':
        raise ValueError('legacy provenance mismatch')
    fetched={}; receipts={}; raw_bytes={}
    names=['metadata','latest','vintages_2018','asof_2018-02-02','asof_2018-03-09']
    for name in names:
        receipt=strict_json((acquisition/(name+'.receipt.json')).read_bytes());receipts[name]=receipt
        if receipt['error'] is not None or receipt['http_status']!=200:
            raise ValueError('bounded acquisition failed; sanitized receipt retained in acquisition directory')
        data=stable_read(acquisition/(name+'.json'),receipt['sha256'])
        if len(data)!=receipt['byte_count']: raise ValueError('acquisition byte count mismatch')
        raw_bytes[name]=data;fetched[name]=strict_json(data)
    metadata=fetched['metadata']['seriess']
    if len(metadata)!=1 or metadata[0]['id']!=SERIES: raise ValueError('metadata series mismatch')
    metadata=metadata[0]
    if (metadata['frequency'],metadata['units'],metadata['seasonal_adjustment'])!=('Monthly','Dollars per Hour','Seasonally Adjusted'):
        raise ValueError('series semantics changed')
    current_rows=parse_vintages(fetched['vintages_2018'])
    if {r['observation_date'] for r in current_rows}!={f'2018-{m:02d}-01' for m in range(1,13)}: raise ValueError('missing requested month')
    oldmap={(r['observation_date'],r['vintage_date']):r for r in old_rows}
    newmap={(r['observation_date'],r['vintage_date']):r for r in current_rows}
    if any(newmap.get(k)!=v for k,v in oldmap.items()): raise ValueError('legacy/current vintage conflict; investigation required')
    probes=[]
    for date in ['2018-02-02','2018-03-09']:
        source=fetched['asof_'+date]
        if source.get('count')!=1 or source.get('offset')!=0 or len(source['observations'])!=1: raise ValueError('incomplete historical probe')
        expected=[r for r in as_of(current_rows,date) if r['observation_date']=='2018-01-01']
        provider=source['observations'][0]
        if len(expected)!=1 or provider['date']!='2018-01-01' or provider['value']!=expected[0]['value']:
            raise ValueError('native as-of replay disagrees with official historical API')
        probes.append({'as_of_vintage_date':date,'observation_date':provider['date'],'value':provider['value']})
    if len(fetched['latest']['observations'])!=5 or fetched['latest']['sort_order']!='desc': raise ValueError('latest probe malformed')
    if any(r['vintage_date']>receipts['vintages_2018']['finished_at'][:10] for r in current_rows): raise ValueError('future vintage in response')

    def evidence(kind,value,description):
        data=canonical(value)+b'\n';member=store.blob(data,rows=None)
        record=identified('onboarding_evidence',{'kind':kind,'payload':{'sha256':member['blob_sha256'],'byte_count':member['byte_count'],'row_count':None},'media_type':'application/json','description':description},'EVIDENCE_')
        return store.record(record,f"storage/catalog/onboarding/evidence/{record['id']}.json")
    audit=evidence('pit_audit',{'series_id':SERIES,'reference_period':{'start_inclusive':'2018-01-01','end_exclusive':'2019-01-01'},
        'legacy_raw_sha256':RAW_HASH,'current_raw_sha256':sha(raw_bytes['vintages_2018']),
        'legacy_vintage_rows':len(old_rows),'current_vintage_rows':len(current_rows),'months':12,
        'legacy_rows_preserved_exactly':True,'historical_api_comparisons':probes,
        'as_of_2018_02_01':as_of(current_rows,'2018-02-01'),'as_of_2019_02_01':as_of(current_rows,'2019-02-01'),
        'vintage_rows':current_rows,'timing_basis':'ALFRED vintage dates, not exact release timestamps'},
        'Bounded reference-window and historical state reconstruction evidence; no inferred intraday timestamps.')
    legacy_evidence=evidence('legacy_provenance',{'files_sha256':before,'original_metadata':legacy_meta},'Preserved legacy provenance; unknown HTTP status remains unknown.')
    spec=evidence('onboarding_policy',{'policy_version':'1.0.0','series_id':SERIES,'official_sources':DOCS,
        'historical_scope':'Reconstruct the ALFRED archive information state at native vintage-date precision for the 2018 reference window.',
        'selection':'For each reference month, retain the latest change with vintage_date <= requested as-of date. A missing marker replaces the prior value with missing.',
        'availability':'Vintage dates are source archive dates. No UTC intraday availability or historic local receipt time is inferred. Date cutoffs are source-calendar labels.',
        'revision':'Preserve original wide response and every change event; no overwrite of historical values.',
        'quality':'Reject incomplete pages, duplicates, wrong series, invalid dates/decimals, conflicting archived vintages and mismatched hashes; compare two independent historical API queries.',
        'live_scope':'Official authenticated API can be pulled once daily; monthly series need not change each day. No scheduler or decision-clock certification.',
        'legacy_policy':'The old plus-one-day at 12 UTC convention is recorded as legacy evidence only, not promoted into an exact release-time claim.',
        'publication':'Immutable bytes before manifests; all references and bytes verified. Technical onboarding checks do not approve research exposure or production trading.',
        'determinism':'No randomness in parser or canonical publication. No network requests during offline replay.'},
        'Explicit bounded technical onboarding policy and reviewed official documentation URLs.')
    def definition(kind,id,label,body,folder):
        record={'schema_version':'0.2.0','record_type':kind,'id':id,'version':'1.0.0','display_name':label,'body':body}
        return store.record(record,f'definitions/{folder}/{id}/1.0.0.json')
    policies={}
    for kind in ['availability','revision','quality','selection','alignment','readiness','randomness']:
        policies[kind]=definition('policy_definition','POL_ALFRED_DATE_'+kind.upper(),'ALFRED bounded date-level '+kind,
          {'kind':kind,'specification':spec,'parameters':[],'approval_state':'approved','compatibility_evidence':[audit,legacy_evidence]},'policies')
    limits=[{'code':'DATE_PRECISION_ONLY','detail':'Native vintage dates support archive-date reconstruction; exact historical intraday publication and local receipt times are not certified.'},
            {'code':'BOUNDED_COVERAGE','detail':'Historical assessment covers reference months January through December 2018 only.'},
            {'code':'NO_DECISION_CLOCK','detail':'Daily API capability does not establish a trading cutoff, live-generation readiness, uptime guarantee or scheduled job.'}]
    provider_record=identified('provider_contract',{'provider':'FRED_ALFRED','native_series_id':SERIES,
        'official_endpoints':[{'role':'series_metadata','url':BASE_URL+'series'},{'role':'series_observations','url':BASE_URL+'series/observations'},{'role':'series_vintages','url':BASE_URL+'series/vintagedates'}],
        'official_documentation':DOCS,'units':metadata['units'],'frequency':metadata['frequency'],'seasonal_adjustment':metadata['seasonal_adjustment'],
        'availability_policy':policies['availability'],'vintage_limitations':limits,
        'requested_live_scope':{'capability':'live_api_daily_pull','cadence':'daily','decision_clock_ready':False}},'PROVIDER_')
    provider=store.record(provider_record,f"definitions/providers/{provider_record['id']}/1.0.0.json")
    dataset=definition('dataset_definition','DS_FRED_ALFRED_'+SERIES,metadata['title'],{
        'economic_entity_ids':['US'],
        'fields':[{'name':'observation_date','data_type':'token','unit':'source_calendar_date','nullable':False},
                  {'name':'vintage_date','data_type':'token','unit':'source_calendar_date','nullable':False},
                  {'name':'value','data_type':'decimal','unit':'USD_per_hour','nullable':True}],
        'event_time_field':'observation_date','availability_time_field':'vintage_date','revision_key_fields':['observation_date','vintage_date'],
        'availability_policy':policies['availability'],'revision_policy':policies['revision'],'quality_policy':policies['quality'],'source_contract':provider},'datasets')
    source_view=definition('source_view_definition','SVIEW_ALFRED_'+SERIES+'_VINTAGE_DATE','Native ALFRED vintage-date view',{
        'dataset':dataset,'entity_selection':{'kind':'fixed_entities','entity_ids':['US']},'fields':['observation_date','vintage_date','value'],'filters':[],
        'alignment_policy':policies['alignment'],'selection_policy':policies['selection']},'source_views')
    code=[]
    for path in ['src/data/alfred_onboarding.py','tools/onboard_alfred.py']:
        code.append(store.blob(stable_read(Path(root)/path),'bin',path.replace('/','.'),None))
    env=store.blob(canonical({'python':platform.python_version(),'platform':platform.system(),'jsonschema':__import__('importlib.metadata',fromlist=['version']).version('jsonschema'),'standard_library':True})+b'\n','json','environment',None)
    implementation_base={'schema_version':'0.2.0','record_type':'implementation_manifest','version':'1.0.0','code_artifacts':code,'environment_artifacts':[env],'entrypoint_id':'onboard_alfred_bounded_2018','determinism_policy':policies['randomness']}
    implementation_record=dict(implementation_base,id='IMPLEMENTATION_'+sha(canonical(implementation_base)))
    implementation=store.record(implementation_record,f"storage/catalog/implementations/{implementation_record['id']}/manifest.json")
    ingestion_refs={}; payload_members={}
    for name in ['legacy_archive']+names:
        islegacy=name=='legacy_archive'
        data=raw if islegacy else raw_bytes[name]
        count=len(archived['observations']) if islegacy else len(fetched[name].get('observations',fetched[name].get('seriess',[])))
        member=store.blob(data,role=name,rows=count);payload_members[name]=member
        request=old_receipt['request'] if islegacy else receipts[name]
        response=old_receipt['response'] if islegacy else receipts[name]
        endpoint=BASE_URL+'series/observations' if islegacy else request['endpoint']
        params=request['parameters']
        body={'mode':'legacy_import' if islegacy else 'api_download','dataset':dataset,'provider_contract':provider,
              'request':{'endpoint':endpoint,'parameters':[{'name':k,'value':str(v)} for k,v in sorted(params.items())]},
              'retrieval':{'original_started_at':None if islegacy else utc(request['started_at']),
                           'original_finished_at':utc(old_receipt['retrieved_at']) if islegacy else utc(request['finished_at']),'captured_at':stamped},
              'response':{'http_status':response['http_status'],'headers':[{'name':k.lower(),'value':str(v)} for k,v in sorted(response['headers'].items())],
                          'content_type':response['headers'].get('content-type'),'content_encoding':response['headers'].get('content-encoding')},
              'payload':{'sha256':member['blob_sha256'],'byte_count':member['byte_count'],'row_count':count},
              'source_evidence':{'legacy_store_id':'LEGACY_DATA' if islegacy else None,'legacy_relative_path':RAW if islegacy else None,'source_sha256':RAW_HASH if islegacy else None},
              'completeness':{'outcome':'partial' if name=='latest' else 'complete','reason_codes':['LATEST_FIVE_OBSERVATIONS_ONLY'] if name=='latest' else [],'errors':[]}}
        record=identified('ingestion_receipt',body,'INGESTION_')
        ingestion_refs[name]=store.record(record,f"storage/catalog/ingestions/records/{record['id']}.json")
    def snapshot(name,start,end):
        lineage_base={'schema_version':'0.2.0','record_type':'lineage_manifest','version':'1.0.0','inputs':[{'role':'ingestion_receipt','artifact':ingestion_refs[name]}],
            'operation':policies['selection'],'implementation':implementation,'policy_bindings':[{'role':'quality','artifact':policies['quality']}]}
        line_record=dict(lineage_base,id='LINEAGE_'+sha(canonical(lineage_base)))
        line=store.record(line_record,f"storage/catalog/lineage/{line_record['id']}/manifest.json")
        content=archived if name=='legacy_archive' else fetched[name]
        cutoff=utc(old_receipt['retrieved_at']) if name=='legacy_archive' else utc(receipts[name]['finished_at'])
        snap={'schema_version':'0.2.0','record_type':'snapshot_manifest','version':'1.0.0','layer':'raw','definition':dataset,'period':{'start_inclusive':start,'end_exclusive':end},
            'information_cutoff':cutoff,'members':[payload_members[name]],'semantic_content_sha256':sha(canonical(content)),
            'record_count':payload_members[name]['row_count'],'upstream_snapshots':[],'policy_bindings':[{'role':'quality','artifact':policies['quality']}],
            'implementation':implementation,'lineage':[line]}
        projection={k:v for k,v in snap.items() if k!='members'}
        record=dict(snap,id='SNAPSHOT_'+sha(canonical(projection)))
        return store.record(record,f"storage/catalog/snapshots/{record['id']}/manifest.json")
    raw_snapshot=snapshot('vintages_2018',START,END)
    legacy_dates=sorted(r['date'] for r in archived['observations']);last=dt.date.fromisoformat(legacy_dates[-1]);nextmonth=dt.date(last.year+int(last.month==12),last.month%12+1,1)
    legacy_snapshot=snapshot('legacy_archive',legacy_dates[0]+'T00:00:00.000000Z',nextmonth.isoformat()+'T00:00:00.000000Z')
    latest_dates=sorted(r['date'] for r in fetched['latest']['observations']);latest_date=dt.date.fromisoformat(latest_dates[-1]);nextmonth=dt.date(latest_date.year+int(latest_date.month==12),latest_date.month%12+1,1)
    live_snapshot=snapshot('latest',latest_dates[0]+'T00:00:00.000000Z',nextmonth.isoformat()+'T00:00:00.000000Z')
    assessments={}
    checks_hist=[{'code':'COMPLETE_REFERENCE_WINDOW','outcome':'pass','evidence':[ingestion_refs['vintages_2018'],audit],'detail':'All 12 reference months returned in one complete native-vintage page.'},
        {'code':'LEGACY_PARITY','outcome':'pass','evidence':[legacy_evidence,audit,ingestion_refs['legacy_archive']],'detail':'All archived vintage values in the selected window match the current response.'},
        {'code':'HISTORICAL_STATE_REPLAY','outcome':'pass','evidence':[audit,ingestion_refs['asof_2018-02-02'],ingestion_refs['asof_2018-03-09']],'detail':'Native change-event replay agrees with two independently requested historical as-of states.'}]
    checks_live=[{'code':'OFFICIAL_ENDPOINT_DOCUMENTED','outcome':'pass','evidence':[spec,provider],'detail':'Official v1 API supports FRED/ALFRED series retrieval; native frequency is retained.'},
        {'code':'AUTHENTICATED_CURRENT_PULL','outcome':'pass','evidence':[ingestion_refs['metadata'],ingestion_refs['latest']],'detail':'Successful official HTTP 200 metadata and latest-observations requests with the existing credential.'},
        {'code':'DAILY_POLLING_SCOPE','outcome':'pass','evidence':[spec],'detail':'One daily pull is within documented API capacity. Monthly values do not necessarily change daily. No scheduler created.'}]
    for capability,snapshot_ref,checks in [('historical_replay',raw_snapshot,checks_hist),('live_api_daily_pull',live_snapshot,checks_live)]:
        interval={'start_inclusive':START,'end_exclusive':END} if capability=='historical_replay' else {'start_inclusive':utc(receipts['metadata']['started_at']),'end_exclusive':utc(receipts['asof_2018-03-09']['finished_at'])}
        body={'capability':capability,'decision':'ready','dataset':dataset,'provider_contract':provider,'snapshot':snapshot_ref,'policy':policies['readiness'],
            'implementation':implementation,'evidence':[audit,spec]+list(ingestion_refs.values()),'interval':interval,'limitations':limits,'checks':checks,'issued_at':stamped}
        record=identified('capability_assessment',body,'READINESS_')
        assessments[capability]=store.record(record,f"storage/catalog/readiness/records/{record['id']}.json")
    store.verify_closure()
    for path,digest in before.items(): stable_read(legacy/path,digest)
    # Operational locators are installed once; later verifications do not rewrite them.
    from jsonschema import Draft202012Validator
    schema=strict_json((Path(root)/'specs/schemas/platform.schema.json').read_bytes())
    for path,(digest,size) in list(store.blobs.items()):
        locator={'schema_version':'0.2.0','record_type':'payload_locator_record','blob_sha256':digest,'store_id':'PLATFORM_LOCAL','relative_path':path,'access':'managed','verified_byte_count':size,'verified_at':stamped}
        Draft202012Validator(schema).validate(locator)
        relative=f'storage/catalog/locators/{digest}/PLATFORM_LOCAL/{sha(path.encode())}.json'
        existing=Path(root)/relative
        if existing.exists():
            old=strict_json(existing.read_bytes())
            if any(old[k]!=v for k,v in locator.items() if k!='verified_at'): raise ValueError('locator conflict')
        else: store.install(relative,canonical(locator)+b'\n')
    manifest={'schema_version':'0.1.0','status':'COMPLETE_BOUNDED_ONBOARDING','series_id':SERIES,'title':metadata['title'],'issued_at':stamped,
        'reference_period':{'start_inclusive':START,'end_exclusive':END},'dataset':dataset,'source_view':source_view,'provider_contract':provider,
        'snapshots':{'legacy_archive':legacy_snapshot,'bounded_vintages':raw_snapshot,'latest_probe':live_snapshot},'assessments':assessments,
        'ingestion_receipts':ingestion_refs,'audit':audit,'record_paths':sorted(store.paths.values()),'payload_paths':sorted(store.blobs),
        'counts':{'reference_months':12,'archived_vintage_values':len(old_rows),'current_vintage_values':len(current_rows),'official_requests_in_bundle':len(names),'records':len(store.records),'payloads':len(store.blobs)},
        'legacy_sources_verified_unchanged':before,'limitations':limits,'scheduled_jobs_created':0,'live_generation_certified':False}
    run_id='ONBOARDING_'+sha(canonical(manifest));run_path=f'storage/catalog/onboarding/runs/{run_id}.json'
    store.install(run_path,canonical(manifest)+b'\n')
    return {'run_path':run_path,'counts':manifest['counts'],'assessments':assessments,'historical_api_comparisons':probes,'legacy_unchanged':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquisition-dir',required=True,type=Path)
    parser.add_argument('--fetch',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if root.name!='research_platform': raise SystemExit('Run from the new research_platform installation only')
    legacy=root.parent/'Data'
    if args.fetch: fetch_evidence(args.acquisition_dir,legacy/'.env.local')
    print(json.dumps(onboard(root,legacy,args.acquisition_dir),indent=2))
