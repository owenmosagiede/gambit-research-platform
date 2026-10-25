"""Narrow reconciliation of completed, approved legacy-CS/canonical-TS batches.

Scientific records and retained per-item evidence are never rewritten. Only the
batch's operational manifest becomes an explicitly read-only retained-TS view.
The original approval remains unchanged and is linked by its original hashes.
"""
from copy import deepcopy
import hashlib
import uuid

from research.contracts import canonical, digest, normalize_submission, request_id

SCHEMA = 'research_batch_retained_ts_v1'
PREFIX = 'storage/catalog/operations/research_batches/'


def reconcile(root, files, records, retired, ts_ids):
    from data.legacy_batch_evidence import preview
    from runtime.research_jobs import ResearchJobs
    jobs = ResearchJobs(root)
    replacements, reconciled, blockers = {}, set(), []

    def checked(path):
        value = records[path]
        if (value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'})
                or hashlib.sha256(canonical(value) + b'\n').hexdigest() != files[path]['sha256']):
            raise ValueError('Noncanonical or corrupt batch evidence: ' + path)
        return value

    for path in sorted(records):
        if not path.startswith(PREFIX) or not path.endswith('/manifest.json'):
            continue
        original = records[path]
        intents = original.get('intents', [])
        scopes = {i.get('scope', {}).get('id') for i in intents}
        if not (scopes & retired and scopes & ts_ids):
            continue
        base = path.removesuffix('manifest.json')
        try:
            m = checked(path)
            if m.get('schema') != 'research_batch_v1' or not scopes <= retired | ts_ids:
                raise ValueError('Only original canonical-TS/legacy-CS batches can be reconciled')
            bid = request_id(m['batch_id'])
            if base != PREFIX + bid + '/':
                raise ValueError('Batch path differs from its identity')
            state = checked(base + 'state.json')
            if state.get('state') != 'completed':
                raise ValueError('Mixed batch must be completed before reconciliation')
            request = m['request']
            if request['batch_id'] != bid:
                raise ValueError('Batch request identity differs')
            expected = {}
            for feature in request['features']:
                for scope in request['scopes']:
                    intent = normalize_submission(dict(request_id=bid, feature=feature, scope=scope,
                        target_family=request['target_family'], expected_direction=request['expected_direction']))
                    intent.pop('request_id')
                    expected.setdefault(digest(intent), intent)
            combinations = len(request['features']) * len(request['scopes'])
            if (list(expected.values()) != intents or m['requested_combinations'] != combinations
                    or m['input_duplicates'] != combinations - len(intents)):
                raise ValueError('Batch request and frozen intents differ')
            approval = checked(base + 'approval.json')
            if approval['manifest_sha256'] != m['sha256']:
                raise ValueError('Approval does not reference the original manifest')
            # This is a pure preview computation over existing rows: no resolve,
            # materialization, queue repair, or fresh approval is performed.
            if approval['approval']['preview_sha256'] != digest(preview(root / base, m)):
                raise ValueError('Original approved preview differs')
            known = {path, base + 'approval.json', base + 'state.json'}
            retained = {}
            indices = []
            for index, intent in enumerate(intents):
                row_path, dispatch_path = base + f'rows/{index}.json', base + f'dispatch/{index}.json'
                row, dispatch = checked(row_path), checked(dispatch_path)
                known.update((row_path, dispatch_path))
                rid = str(uuid.uuid5(uuid.UUID(bid), digest(intent)))
                if (row['index'] != index or row['intent'] != intent or row['request_id'] != rid
                        or row['disposition'] not in ('new', 'reuse') or dispatch['index'] != index
                        or dispatch['state'] not in ('submitted', 'linked')):
                    raise ValueError('Unverifiable completed batch row or dispatch')
                packet_path = base + 'packets/' + row['packet_sha256'] + '.json'
                packet = checked(packet_path)
                known.add(packet_path)
                if (packet['sha256'] != row['packet_sha256'] or packet['intent'] != intent
                        or packet['implementation'] != m['implementation']):
                    raise ValueError('Frozen packet differs from its original batch')
                target = request_id(dispatch['request_id'])
                allowed = {rid}
                if row.get('existing_request_id'):
                    allowed.add(request_id(row['existing_request_id']))
                if target not in allowed or (dispatch['state'] == 'submitted' and target != rid):
                    raise ValueError('Dispatch does not identify its original request')
                submission = jobs._submission(target)
                job = jobs._read_job(target)
                if submission['intent'] != intent or job is None or job['status'] != 'succeeded':
                    raise ValueError('Completed batch research is not verifiable and succeeded')
                if intent['scope']['id'] in ts_ids:
                    indices.append(index)
                    for p in (row_path, dispatch_path, packet_path):
                        retained[p] = files[p]
            if known != {p for p in files if p.startswith(base)}:
                raise ValueError('Unknown or missing batch files require explicit review')
            replacement = deepcopy(m)
            replacement.pop('sha256')
            replacement['schema'] = SCHEMA
            replacement['request']['name'] = 'Retained time-series research'
            replacement['request']['scopes'] = [s for s in request['scopes'] if s['id'] in ts_ids]
            replacement['intents'] = [intents[i] for i in indices]
            count = len(request['features']) * len(replacement['request']['scopes'])
            replacement.update(requested_combinations=count, input_duplicates=count - len(indices))
            replacement['reconciliation'] = {
                'kind': 'completed_legacy_cs_removal', 'original_manifest_sha256': m['sha256'],
                'original_manifest_file_sha256': files[path]['sha256'],
                'original_preview_sha256': approval['approval']['preview_sha256'],
                'approval_file_sha256': files[base + 'approval.json']['sha256'],
                'retained_indices': indices, 'retained_files': retained,
            }
            replacement['sha256'] = digest(replacement)
            replacements[path] = replacement
            reconciled.add(base)
        except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
            blockers.append('Mixed batch reconciliation blocked: ' + path + ': ' + str(exc))
    return replacements, reconciled, blockers
