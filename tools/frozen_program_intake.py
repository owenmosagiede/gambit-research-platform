#!/usr/bin/env python3
"""Verify/resume the unchanged finite intake using a separately approved bridge.

Verification is the default. This tool cannot create or approve compatibility
records. The recommended first cutover waits for original intake to finish.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from research.contracts import ref
from runtime.execution_compatibility import for_program
from runtime.program_intake_compatibility import load_operator, bridge_class
from runtime.research_jobs import implementation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--operator', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--approval-reference', type=Path, required=True,
                        help='JSON exact reference to an already installed approved record')
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--approved-manifest-sha256')
    parser.add_argument('--receipt-directory', type=Path)
    parser.add_argument('--release-guard-fd', type=int)
    parser.add_argument('--release-guard-owner-pid', type=int)
    args = parser.parse_args()
    if args.root.resolve() != Path(__file__).resolve().parents[1]:
        parser.error('Run the installed intake bridge from the exact target workspace')
    raw = args.manifest.read_bytes(); manifest_sha = sha256(raw).hexdigest()
    operator_sha = sha256(args.operator.read_bytes()).hexdigest()
    approval = for_program(args.root, manifest_sha256=manifest_sha, operator_sha256=operator_sha,
        actual_implementation=implementation(), binding=json.loads(args.approval_reference.read_text()))
    operator = load_operator(args.operator, approval['proposal']['operator_sha256'])
    manifest = operator.validate_manifest(operator.strict_json(raw))
    cls = bridge_class(operator, approval, manifest_sha256=manifest_sha,
                       operator_sha256=operator_sha, frozen_manifest=manifest)
    bridge = cls(args.root, guard_fd=args.release_guard_fd, guard_owner=args.release_guard_owner_pid)
    result = operator.run_program(manifest, bridge, submit=args.submit, manifest_sha=manifest_sha,
        approved_manifest_sha=args.approved_manifest_sha256, receipt_folder=args.receipt_directory)
    print(json.dumps(dict(result, execution_compatibility=ref(approval)), indent=2))


if __name__ == '__main__': main()
