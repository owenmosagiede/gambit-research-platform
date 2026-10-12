"""Manifest-only Target discovery. Research and detail reads remain strict."""
from data.alfred_onboarding import stable_read, strict_json
from data.targets.store import TargetStore, validate_manifest, target_path
from data.targets.contracts import validate_definition
from data.targets.fx import _approved_policy, _price_snapshot, _definition
from data.transformations.identity import reference
from data.fx_pipeline import list_instruments


def list_target_catalog(root):
    store = TargetStore(root)
    targets, issues, definitions = {}, [], {}
    for path in sorted(store.path('definitions/targets').glob('*/*.json')):
        try:
            record = strict_json(stable_read(path)); validate_definition(record)
            if target_path(record['id'], record['version']) != str(path.relative_to(store.root)):
                raise ValueError('Target definition path mismatch')
            body = record['body']
            economic = store.resolve(next(s for s in body['sources'] if s['role']=='instrument')['economic_policy'])['body']
            definitions[record['id']] = record
            targets[record['id']] = {'target_id':record['id'], 'name':record['display_name'],
                'investment_series':economic['investment_series_id'], 'return_basis':body['construction']['basis'],
                'representation':body['construction']['representation'], 'comparison':body['construction']['comparison'],
                'horizon':body['horizon'], 'definition_version':record['version'], 'definition_state':'valid',
                'source_eligibility':'unverified', 'materializations':[], 'readiness':'unmaterialized',
                'reason':'No stored materialization is catalogued.', 'verification_state':'catalog_metadata_only'}
        except Exception:
            issues.append({'target_id':path.parent.name, 'code':'UNAVAILABLE_TARGET', 'message':'Target definition metadata could not be verified.'})
    for path in sorted(store.path('storage/catalog/target_store').glob('*/manifest.json')):
        try:
            manifest = validate_manifest(strict_json(stable_read(path)))
            definition = store.resolve(manifest['definition']); body = definition['body']
            if path.parent.name != manifest['id'] or reference(definitions[definition['id']]) != manifest['definition']:
                raise ValueError('Target manifest ownership mismatch')
            item = targets[definition['id']]
            saved = {'id':manifest['id'], 'state':manifest['state'], 'research_readiness':manifest['research_readiness'],
                'valid_count':manifest['status_counts'].get('valid',0), 'row_count':manifest['row_count'],
                'verification_state':'catalog_metadata_only', 'reason':'Catalog metadata; observation integrity is verified on use.'}
            if manifest['schema_version'] == '0.5.0':
                policy = _approved_policy(store, manifest['input_key']['batch_policy'])
                snapshot, _ = _price_snapshot(store, manifest['price_snapshot'], policy, verify_rows=False)
                price = snapshot['body']; schedule = store.resolve(body['schedule_policy'])
                if reference(_definition(store, snapshot, policy, body['horizon']['amount'], schedule, install=False)) != manifest['definition']:
                    raise ValueError('Target differs from approved definition')
                item.update(instrument_id=price['instrument_id'], investment_series=price['economic_id'],
                    schedule={'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','holiday_exclusions':False},
                    schedule_policy=body['schedule_policy'], coverage=manifest['valid_coverage'],
                    construction=price['construction'], readiness_capabilities=manifest['readiness_capabilities'])
                saved.update(coverage=manifest['valid_coverage'], readiness_capabilities=manifest['readiness_capabilities'])
            item['materializations'].append(saved)
            item.update(source_eligibility='eligible', readiness=manifest['research_readiness'],
                        reason='Saved catalog readiness; exact observations are verified before research.')
        except Exception:
            issues.append({'target_id':None, 'code':'UNAVAILABLE_MATERIALIZATION', 'message':'Target materialization metadata could not be verified.'})
    items = list(targets.values())
    instruments = list_instruments(root, items)
    return {'schema_version':'1.0.0', 'target_count':len(items), 'targets':items, 'issues':issues,
            'instruments':instruments, 'instrument_count':len(instruments)}
