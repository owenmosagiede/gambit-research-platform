"""Exact saved-science comparison for isolated research benchmarks.

Only declared executor references and identities derived from those references
are mapped. Every mapped record is rehashed and its reference edges are checked.
Feature/source/Target references, input and sample digests, payload bytes,
metrics, evidence, decisions and all other fields remain exact.
"""
from copy import deepcopy

from research.contracts import HORIZONS, canonical, digest, ref

SCHEMA = 'research_benchmark_saved_closure_v1'
PREFIX = {'relationship':'RELATIONSHIP','trial':'TRIAL','implementation':'RESEARCHIMPLEMENTATION',
          'exposure':'EXPOSURE','admission':'ADMISSION','validation':'VALIDATION','link':'RESEARCHLINK'}


def require(condition, message):
    if not condition:
        raise ValueError('Persisted benchmark closure: ' + message)


def marker(role):
    return {'benchmark_derived_reference': role}


def checked(kind, value):
    require(value['schema_version'] == '0.8.0' and value['version'] == '1.0.0' and
            value['record_type'] == 'research_' + kind and
            value['id'] == PREFIX[kind] + '_' + digest(value['scientific_key']) and
            value['record_sha256'] == digest({k:v for k,v in value.items() if k != 'record_sha256'}),
            kind + ' record identity/checksum differs')
    return deepcopy({k:v for k,v in value.items() if k not in ('id','record_sha256')})


def edge(actual, expected, role):
    require(actual == ref(expected), role + ' reference differs')
    return marker(role)


def artifact_projection(value, binding, key, normalized_key):
    require(ref(value) == binding and value['id'] == 'ARTIFACT_' +
            digest({k:v for k,v in value.items() if k != 'id'}) and
            value['scientific_key_sha256'] == digest(key), 'artifact derivation differs')
    # Payloads were verified against these exact hashes and byte counts during
    # capture; keeping the whole member array requires byte-for-byte equality.
    require(bool(value['members']) and len({m['role'] for m in value['members']}) == len(value['members']),
            'artifact payload roles are empty or ambiguous')
    result = deepcopy({k:v for k,v in value.items() if k != 'id'})
    result['scientific_key_sha256'] = digest(normalized_key)
    return result


def scientific_projection(provenance, expected_implementation):
    """Re-derive the comparison from saved records, without trusting report hashes."""
    require(set(provenance) == {'job','horizons'}, 'unexpected provenance fields')
    job = provenance['job']
    require(set(job) == {'status','mode','horizons'} and job['status'] == 'succeeded', 'job not complete')
    require([r['horizon'] for r in job['horizons']] == list(HORIZONS), 'job horizon population differs')
    rows = provenance['horizons']
    require([r['horizon'] for r in rows] == list(HORIZONS), 'saved horizon population differs')
    result = []
    for row in rows:
        require(set(row) == {'horizon','relationship','trials','admissions','validations','link'},
                'unexpected horizon closure fields')
        h = row['horizon']; relationship = row['relationship']; link = row['link']
        checked('relationship', relationship); normalized_link = checked('link', link)
        require(relationship['scientific_key']['horizon'] == h and
                relationship['body'] == relationship['scientific_key'], 'relationship science differs')
        require(link['scientific_key'] == link['body'] and link['body']['relationship'] == ref(relationship),
                'link derivation or relationship differs')
        trials = row['trials']
        require([t['record']['scientific_key']['stage'] for t in trials] in (['P1'], ['P1','P2']),
                'saved trial stage population differs')
        require(link['body']['trial_results'] == [ref(t['record']) for t in trials], 'trial link closure differs')
        require(len(row['admissions']) == 1 and len(row['validations']) <= 1, 'decision population differs')
        p1 = trials[0]['record']; p2 = trials[1]['record'] if len(trials) == 2 else None
        normalized_trials = []
        for item in trials:
            require(set(item) == {'record','implementation','exposure','artifacts'}, 'unexpected trial closure fields')
            trial = item['record']; key = trial['scientific_key']; phase = key['stage']
            role = 'trial:' + phase + ':' + str(h)
            normal = checked('trial',trial)
            require(key['horizon'] == h and key['relationship'] == ref(relationship) and
                    trial['body']['stage'] == phase, 'trial relationship, horizon or body phase differs')
            executor = item['implementation']; checked('implementation',executor)
            require(executor['scientific_key'] == executor['body'] == expected_implementation,
                    'saved executor is not the actual benchmark implementation')
            normal['scientific_key']['implementation'] = edge(key['implementation'],executor,'actual_executor')
            if phase == 'P1':
                require(key['discovery_trial'] is None and key['discovery_effect'] is None, 'P1 discovery differs')
            else:
                normal['scientific_key']['discovery_trial'] = edge(key['discovery_trial'],p1,'trial:P1:' + str(h))
                require(key['discovery_effect'] == p1['body']['metrics']['primary_effect'] and
                        p1['body']['admission'] == 'admitted', 'P2 admission/discovery effect differs')
            exposure = item['exposure']; normal_exposure = checked('exposure',exposure)
            require(exposure['scientific_key'] == {'trial_key':digest(key)}, 'exposure trial-key derivation differs')
            require(exposure['body']['relationship'] == ref(relationship) and
                    exposure['body']['stage'] == phase and exposure['body']['period'] == key['period'],
                    'exposure scientific binding differs')
            normal_exposure['scientific_key']['trial_key'] = digest(normal['scientific_key'])
            normal['body']['exposure'] = edge(trial['body']['exposure'],exposure,'exposure:' + role)
            artifacts = item['artifacts']; bindings = trial['body']['artifact_manifests']
            require(len(artifacts) == len(bindings) and bool(artifacts), 'artifact population differs')
            normalized_artifacts = [artifact_projection(a,b,key,normal['scientific_key']) for a,b in zip(artifacts,bindings)]
            normal['body']['artifact_manifests'] = [marker('artifact:' + role + ':' + str(i)) for i in range(len(artifacts))]
            normalized_trials.append({'record':normal,'exposure':normal_exposure,'artifacts':normalized_artifacts})
        normalized_admissions = []
        require(link['body']['admission_results'] == [ref(a) for a in row['admissions']], 'admission link closure differs')
        for admission in row['admissions']:
            normal = checked('admission',admission)
            require(admission['scientific_key'] == {'trial':ref(p1)} and
                    admission['body']['relationship'] == ref(relationship) and
                    admission['body']['decision'] == p1['body']['admission'], 'admission binding/decision differs')
            normal['scientific_key']['trial'] = marker('trial:P1:' + str(h))
            normal['body']['trial'] = edge(admission['body']['trial'],p1,'trial:P1:' + str(h))
            normalized_admissions.append(normal)
        normalized_validations = []
        require(link['body']['validation_results'] == [ref(v) for v in row['validations']], 'validation link closure differs')
        require(p2 is None or len(row['validations']) == 1, 'P2 lacks saved validation')
        for validation in row['validations']:
            normal = checked('validation',validation)
            require(validation['body']['relationship'] == ref(relationship), 'validation relationship differs')
            normal['scientific_key']['discovery'] = edge(validation['scientific_key']['discovery'],p1,'trial:P1:' + str(h))
            normal['body']['discovery_trial'] = edge(validation['body']['discovery_trial'],p1,'trial:P1:' + str(h))
            if p2 is not None:
                normal['scientific_key']['evaluation'] = edge(validation['scientific_key']['evaluation'],p2,'trial:P2:' + str(h))
                normal['body']['evaluation_trial'] = edge(validation['body']['evaluation_trial'],p2,'trial:P2:' + str(h))
                require(validation['body']['decision'] == p2['body']['decision'], 'saved validation decision differs')
            else:
                require(validation['body']['evaluation_trial'] is None and 'evaluation' not in validation['scientific_key'],
                        'precheck validation refers to unexpected P2')
            normalized_validations.append(normal)
        for part in ('scientific_key','body'):
            normalized_link[part]['trial_results'] = [marker('trial:' + t['record']['scientific_key']['stage'] + ':' + str(h)) for t in trials]
            normalized_link[part]['admission_results'] = [marker('admission:' + str(h))]
            normalized_link[part]['validation_results'] = [marker('validation:' + str(h)) for _ in row['validations']]
        result.append({'horizon':h,'relationship':deepcopy(relationship),'trials':normalized_trials,
                       'admissions':normalized_admissions,'validations':normalized_validations,'link':normalized_link})
    return {'job':deepcopy(job),'executor_environment':{k:deepcopy(expected_implementation[k])
                for k in ('profile','numeric_environment')},'horizons':result}


def capture_closure(store, job, *, expected_implementation):
    """Read and verify authoritative saved results; call outside timed intervals."""
    rows = {}
    for binding in job['results']:
        link = store.resolve('link',binding)
        body = link['body']; relationship = store.resolve('relationship',body['relationship'])
        h = relationship['body']['horizon']
        require(h not in rows, 'multiple result links for one horizon')
        trials = []
        for trial_ref in body['trial_results']:
            trial = store.resolve('trial',trial_ref)
            trials.append({'record':trial,
                'implementation':store.resolve('implementation',trial['scientific_key']['implementation']),
                'exposure':store.resolve('exposure',trial['body']['exposure']),
                'artifacts':[store.verify_artifact(a) for a in trial['body']['artifact_manifests']]})
        rows[h] = {'horizon':h,'relationship':relationship,'trials':trials,
            'admissions':[store.resolve('admission',a) for a in body['admission_results']],
            'validations':[store.resolve('validation',v) for v in body['validation_results']], 'link':link}
    provenance = {'job':{k:deepcopy(job[k]) for k in ('status','mode','horizons')},
                  'horizons':[rows[h] for h in sorted(rows)]}
    scientific = scientific_projection(provenance,expected_implementation)
    return {'schema':SCHEMA,'expected_implementation':deepcopy(expected_implementation),
            'provenance':provenance,'scientific':scientific,'scientific_sha256':digest(scientific)}


def validate_capture(value):
    require(set(value) == {'schema','expected_implementation','provenance','scientific','scientific_sha256'} and
            value['schema'] == SCHEMA, 'capture schema differs')
    scientific = scientific_projection(value['provenance'],value['expected_implementation'])
    require(value['scientific'] == scientific and value['scientific_sha256'] == digest(scientific),
            'capture projection/checksum differs from its saved records')
    return scientific


def compare_closures(old, new):
    before, after = validate_capture(old), validate_capture(new)
    return {'exact_saved_scientific_equality':before == after,
            'baseline_saved_scientific_sha256':digest(before),
            'optimized_saved_scientific_sha256':digest(after),
            'mapping':'Only verified actual-executor and derived result identities; all other saved fields and payload hashes exact.'}
