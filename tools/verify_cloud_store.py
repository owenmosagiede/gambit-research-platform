#!/usr/bin/env python3
"""Read-only cloud migration acceptance: immutable references and payload closure.

This checks the entire catalog graph without executing research or rewriting old
identities. Independent numerical verification remains the existing readers' job.
Never falls back to the Mac's legacy raw directories.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from data.alfred_onboarding import stable_read, strict_json
from data.transformations.identity import reference as feature_reference
from research.contracts import ref as research_reference

REFERENCE_FIELDS = {'id', 'version', 'content_sha256'}


def nested(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from nested(child)
    elif isinstance(value, list):
        for child in value: yield from nested(child)


def reference_key(value):
    return tuple(value[k] for k in ('id', 'version', 'content_sha256'))


def graph(root, *, progress=lambda value: None):
    root = Path(root).resolve()
    records = {}; required = {}; payloads = {}; counts = Counter(); files = 0
    errors = []; started = time.monotonic()
    for directory in ('definitions', 'storage/catalog', 'config'):
        for path in sorted((root / directory).rglob('*.json')):
            relative = path.relative_to(root).as_posix()
            if path.name == 'worker_service.json': continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Catalog path escapes root: ' + relative)
            value = strict_json(stable_read(path)); files += 1
            if isinstance(value, dict):
                counts[value.get('record_type', 'configuration_or_operational')] += 1
                if isinstance(value.get('id'), str) and isinstance(value.get('version'), str):
                    if value.get('record_type') and value.get('schema_version') != '0.8.0':
                        ref = feature_reference(value)
                    else:
                        ref = research_reference(value)
                    records.setdefault(reference_key(ref), relative)
            for node in nested(value):
                if set(node) == REFERENCE_FIELDS:
                    required.setdefault(reference_key(node), relative)
                if {'blob_sha256', 'format', 'byte_count'} <= node.keys():
                    key = (node['blob_sha256'], node['format'], node['byte_count'])
                    payloads.setdefault(key, relative)
                # ALFRED receipt evidence uses its original, versioned envelope.
                if set(node) == {'sha256', 'byte_count', 'row_count'}:
                    payloads.setdefault((node['sha256'], 'json', node['byte_count']), relative)
            if files % 10000 == 0:
                progress({'stage': 'catalog', 'files': files, 'elapsed_seconds': round(time.monotonic() - started, 1)})
    for ref, origin in required.items():
        if ref not in records:
            errors.append({'kind': 'unresolved_reference', 'id': ref[0], 'version': ref[1], 'origin': origin})
    verified_payloads = 0; payload_bytes = 0
    for (sha, extension, size), origin in payloads.items():
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha) or not re.fullmatch('[a-z0-9][a-z0-9_.-]{0,40}', extension):
            raise ValueError('Invalid content-addressed payload path')
        path = root / f'storage/payloads/sha256/{sha[:2]}/{sha}.{extension}'
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Payload path escapes root')
        if not path.is_file():
            errors.append({'kind': 'missing_local_payload', 'sha256': sha, 'format': extension, 'origin': origin})
            continue
        try:
            data = stable_read(path, sha)
            if len(data) != size: raise ValueError('Payload length differs')
        except ValueError:
            errors.append({'kind': 'payload_checksum_or_size_mismatch', 'sha256': sha, 'origin': origin})
            continue
        verified_payloads += 1; payload_bytes += size
        if verified_payloads % 1000 == 0:
            progress({'stage': 'payloads', 'verified': verified_payloads, 'total': len(payloads)})
    return {'status': 'FAIL' if errors else 'PASS', 'scope': 'complete_catalog_reference_and_local_payload_closure',
            'catalog_files': files, 'record_counts': dict(counts), 'unique_records': len(records),
            'unique_references': len(required), 'verified_payloads': verified_payloads,
            'payload_bytes': payload_bytes, 'errors': errors,
            'elapsed_seconds': round(time.monotonic() - started, 3), 'legacy_fallback_used': False,
            'numerical_recalculation': 'not_performed_by_graph_check'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path); args = parser.parse_args()
    result = graph(args.root, progress=lambda v: print(json.dumps(v), flush=True))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in {'record_counts', 'errors'}}), flush=True)
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__': main()
