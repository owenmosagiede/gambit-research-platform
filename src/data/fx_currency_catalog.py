"""Explicit publication and exact resolution of currency/reference price catalogs.

This catalog is separate from the 43 canonical TS instrument registrations. No
read path selects a latest source, changes membership, or publishes observations.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore
from data.fx_records import make_record, write_rows
from data.transformations import fx, fx_currency as currency
from data.transformations.identity import canonical_bytes, digest, reference
from data.targets.fx import _approved_policy, readiness, _coverage, _price_snapshot
from research.store import install_bytes

ACTIVE = 'storage/catalog/fx_currency/active.json'


def add(store, kind, body, name=None):
    record = make_record(kind, body, name)
    store.install_record(record)
    return record


def publish_prices(root, source_snapshots, batch_policy, request_text):
    """Build all 126 exposures from exactly 18 supplied, verified source snapshots."""
    from data.fx_onboarding import read_source
    if not isinstance(request_text, str) or not request_text.strip():
        raise ValueError('Explicit currency migration request evidence is required')
    if set(source_snapshots) != set(fx.SOURCE_SYMBOLS):
        raise ValueError('Exactly the frozen 18 source snapshot references are required')
    store = FeatureStore(root)
    batch = _approved_policy(store, batch_policy)
    evidence = add(store, 'onboarding_evidence', {'kind': 'fx_currency_migration_approval',
        'request_text': request_text, 'references': list(currency.REFERENCES),
        'currencies': list(currency.CURRENCIES), 'price_profile': currency.PROFILE,
        'return_policy': batch, 'delete_legacy_cs_history': True,
        'preserve_canonical_ts': True, 'funding_costs_included': False})
    alignment = {'id': 'FX_CURRENCY_DATE_ALIGNMENT', 'version': '1.0.0',
        'mode': 'retrospective_date_label', 'approval_state': 'approved',
        'approval_evidence': batch['approval_evidence'], 'max_date_gap': 0,
        'max_valuation_gap_seconds': None}
    sources, metadata = {}, {}
    for symbol, binding in sorted(source_snapshots.items()):
        source = read_source(root, binding)
        meta = source['metadata']
        if meta['provider_symbol'] != symbol:
            raise ValueError('Source snapshot belongs to another currency')
        metadata[symbol] = {k: meta[k] for k in ('base_currency','quote_currency','unit','price_field','price_basis','timing')}
        metadata[symbol]['source_view'] = source['manifest']['body']['definition']
        sources[symbol] = [{k: row[k] for k in ('reference_time','value','status','reason_code','lineage','available_at','original_ingested_at','vintage_id')}
                           for row in source['observations']]
        for row in sources[symbol]:
            if row['original_ingested_at'] is not None:
                row['original_ingested_at'] = datetime.fromisoformat(row['original_ingested_at'].replace('Z','+00:00')).isoformat(timespec='microseconds').replace('+00:00','Z')
        if not sources[symbol]:
            raise ValueError('Empty source history cannot establish currency price coverage: ' + symbol)
    determinism = add(store, 'policy_definition', {'kind': 'fx_currency_determinism',
        'approval': reference(evidence), 'profile': currency.PROFILE,
        'arithmetic': 'decimal_50_then_binary64_guard', 'fallback': 'none'})
    project = Path(__file__).resolve().parents[2]
    implementation = {'schema_version': '0.2.0', 'record_type': 'implementation_manifest', 'version': '1.0.0',
        'code_artifacts': [store.io.blob(stable_read(project/name), 'txt', name.replace('/','_'), None)
            for name in ('src/data/transformations/fx.py','src/data/transformations/fx_currency.py','src/data/fx_currency_catalog.py','src/data/fx_records.py')],
        'environment_artifacts': [store.io.blob(canonical_bytes({'python':sys.version,'decimal_precision':50}), 'json','fx_currency_runtime',1)],
        'entrypoint_id': 'publish_currency_prices', 'determinism_policy': reference(determinism)}
    implementation['id'] = 'IMPLEMENTATION_' + digest(implementation)
    store.install_record(implementation)
    legs = {}
    for c, rows in fx.normalize_legs(sources, source_metadata=metadata).items():
        legs[c] = reference(add(store,'snapshot_manifest', {'kind':'fx_normalized_leg','profile':currency.PROFILE,
            'currency':c,'implementation':reference(implementation),'upstream_snapshots':[source_snapshots[fx.SOURCE_BY_CURRENCY[c]]],
            'members':write_rows(store,rows,'normalized_fx_leg'),'record_count':len(rows),'semantic_content_sha256':digest(rows)}))
    instruments = []
    for q in currency.REFERENCES:
        for symbol in currency.members(q):
            spec = currency.instrument_spec(symbol)
            recipe = add(store,'transformation_definition', {'profile':currency.PROFILE,**currency.recipe(symbol,metadata,alignment)['body']})
            meta = {k:spec[k] for k in ('base_currency','quote_currency','unit')}
            meta.update(price_field='close',price_basis='unknown',timing={'timezone':None,'bar_boundary':None,'session_convention':None,'synchronization':'unverified'})
            dataset = add(store,'dataset_definition', {'kind':'fx_constructed_dataset','profile':currency.PROFILE,
                'instrument_id':symbol,'economic_id':spec['economic_id'],'recipe':reference(recipe),'source_metadata':meta})
            view = add(store,'source_view_definition', {'kind':'fx_constructed_view','profile':currency.PROFILE,
                'dataset':reference(dataset),'recipe':reference(recipe),'source_metadata':meta})
            construction = {'method':spec['method'],'version':'1.0.0','price_basis':'unknown','alignment':alignment['mode'],'policy':reference(recipe)}
            rows = currency.construct_prices(symbol,sources,source_metadata=metadata,alignment_policy=alignment)
            valid = [r for r in rows if r['status']=='valid']
            body = {'kind':'fx_constructed_prices','profile':currency.PROFILE,'instrument_id':symbol,'economic_id':spec['economic_id'],
                'definition':reference(view),'recipe':reference(recipe),'implementation':reference(implementation),
                'construction':construction,'source_metadata':meta,'upstream_snapshots':[source_snapshots[s] for s in spec['source_symbols']],
                'normalized_legs':[legs[c] for c in (spec['base_currency'],q) if c!='USD'],
                'members':write_rows(store,rows,'currency_fx_price'),'record_count':len(rows),'semantic_content_sha256':digest(rows),
                'coverage':_coverage(rows),'valid_coverage':_coverage(valid),'status_counts':dict(Counter(r['status'] for r in rows)),
                'reason_counts':dict(Counter(r['reason_code'] for r in rows if r['reason_code'])),
                'readiness_capabilities':readiness(True,len(valid),batch['approval_evidence'])}
            snapshot = add(store,'snapshot_manifest',body)
            registration = add(store,'onboarding_evidence', {'kind':'fx_currency_registration','profile':currency.PROFILE,
                'instrument_id':symbol,'economic_id':spec['economic_id'],'source_metadata':meta,
                'price_snapshot':reference(snapshot),'source_inputs':body['upstream_snapshots'],
                'price_coverage':body['valid_coverage'],'price_row_count':len(rows),
                'readiness_capabilities':body['readiness_capabilities'],'approval':reference(evidence)})
            instruments.append(reference(registration))
    return add(store,'onboarding_evidence', {'kind':'fx_currency_price_catalog','profile':currency.PROFILE,
        'references':list(currency.REFERENCES),'currencies':list(currency.CURRENCIES),'approval':reference(evidence),
        'source_snapshots':deepcopy(source_snapshots),'return_policy':batch,'instruments':instruments})


def resolve_prices(root, catalog_ref, *, verify_rows=False):
    store = FeatureStore(root); catalog = store.resolve(catalog_ref); body = catalog['body']
    if (body.get('kind')!='fx_currency_price_catalog' or body.get('profile')!=currency.PROFILE
            or body.get('references')!=list(currency.REFERENCES) or body.get('currencies')!=list(currency.CURRENCIES)
            or set(body.get('source_snapshots',{}))!=set(fx.SOURCE_SYMBOLS)):
        raise ValueError('Unsupported currency price catalog')
    batch = _approved_policy(store,body['return_policy']); result = {}
    for binding in body['instruments']:
        record=store.resolve(binding); row=record['body']; symbol=row['instrument_id']
        spec=currency.instrument_spec(symbol)
        if row.get('kind')!='fx_currency_registration' or row.get('profile')!=currency.PROFILE or symbol in result:
            raise ValueError('Invalid or duplicate currency registration')
        snapshot,_=_price_snapshot(store,row['price_snapshot'],batch,verify_rows=verify_rows)
        if (snapshot['body']['instrument_id']!=symbol or row['source_metadata']!=snapshot['body']['source_metadata']
                or row['economic_id']!=spec['economic_id'] or row['approval']!=body['approval']
                or row['source_inputs']!=[body['source_snapshots'][s] for s in spec['source_symbols']]
                or snapshot['body']['upstream_snapshots']!=row['source_inputs']
                or row['price_coverage']!=snapshot['body']['valid_coverage']
                or row['price_row_count']!=snapshot['body']['record_count']
                or row['readiness_capabilities']!=snapshot['body']['readiness_capabilities']):
            raise ValueError('Currency catalog source mapping differs')
        result[symbol] = dict(row,registration=binding)
    if set(result)!={s for q in currency.REFERENCES for s in currency.members(q)}:
        raise ValueError('Currency catalog must contain all 126 frozen exposures')
    return catalog,result


def active_release(root):
    path=Path(root)/ACTIVE
    from data.catalog_reads import catalog_glob
    if not list(catalog_glob(path.parent,path.name)):
        return None
    value=strict_json(stable_read(path))
    if set(value)!={'schema','release'} or value['schema']!='fx_currency_active_v1':
        raise ValueError('Invalid active currency release')
    record=FeatureStore(root).resolve(value['release'])
    if record['body'].get('kind')!='fx_currency_release':
        raise ValueError('Invalid active currency release reference')
    return record


def activate(root, release):
    if release['body'].get('kind')!='fx_currency_release':
        raise ValueError('Expected verified currency release')
    FeatureStore(root).install_record(release)
    install_bytes(Path(root)/ACTIVE,canonical_bytes({'schema':'fx_currency_active_v1','release':reference(release)})+b'\n',mutable=True)
