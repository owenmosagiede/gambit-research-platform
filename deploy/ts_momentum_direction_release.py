#!/usr/bin/env python3
"""Review and apply an exact TS momentum scientific migration after a safe drain."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT / name) for name in ('src', 'tools', 'deploy')]
import release_server as release
import retired_definitions
from release_bundle import verify
from research.contracts import canonical, digest
from ts_momentum_direction_cutover import plan_cutover, write_next_manifest

STATE = Path('/var/lib/gambit-releases')
MOMENTUM = Path('/var/lib/gambit-ts-momentum')
PACED_UNIT = 'gambit-ts-momentum-paced-intake.service'
PACER_SHA256 = '31a23b67237e78bedae3c7c503949f6db668d6ebee101548eed44f1818efb2e9'
PACER = Path('/var/lib/gambit-ts-momentum-control') / ('pace-' + PACER_SHA256 + '.py')
PYTHON = '/opt/gambit/venv/bin/python'
RETIREMENT = {
    'plan': Path('/var/lib/gambit-clean-reset/plan-10c9e968f7b4/plan.json'),
    'status': Path('/var/lib/gambit-clean-reset/execute-2f7ac080/status.json'),
    'receipt': STATE / (retired_definitions.PRIOR_RELEASE_ID + '/receipt.json'),
}
RETIREMENT_SOURCE = STATE / 'incoming/post-reset-9654b7de/source.tar.gz'
SOURCE = STATE / 'incoming/ts-runner-speedup/runner-official.tar.gz'


EXTERNAL_UNIT_EXAMPLES = {
    'deploy/examples/gambit-chart-projector.service': '4efdb98af676e37ad772f7b02a769c6bf93c2042aeb75c033a4177835fc251ee',
    'deploy/examples/gambit-read-projector.service': '3435e69e55a96525c5415a15bc9b705fa914e6d7d999fb1e08a5902d19f4fc62',
}


def acknowledge_external_examples(machine, source_files, target_files):
    """The two already-installed projectors use external systemd unit files."""
    pinned = {}
    for path, expected in EXTERNAL_UNIT_EXAMPLES.items():
        file = machine.root/path
        if file.exists() or file.is_symlink():
            continue
        unit = file.name
        live = Path('/etc/systemd/system')/unit
        fragment = subprocess.check_output(['systemctl', 'show', unit, '-p', 'FragmentPath', '--value'],
                                           text=True).strip()
        if (source_files.get(path) == target_files.get(path)
                and sha256(source_files.get(path, b'')).hexdigest() == expected and Path(fragment) == live):
            pinned[path] = sha256(retired_definitions.trusted_bytes(live)).hexdigest()
    return pinned


def compute_plan(machine, target, checks):
    target_sha = sha256(retired_definitions.trusted_bytes(target)).hexdigest()
    source_sha = sha256(retired_definitions.trusted_bytes(SOURCE)).hexdigest()
    checks_bytes = retired_definitions.trusted_bytes(checks)
    manifest, files = verify(target, target_sha)
    source_manifest, source_files = verify(SOURCE, source_sha)
    check_receipt = json.loads(checks_bytes)
    if (check_receipt['schema'] != 'gambit_release_checks_v1'
            or check_receipt['commit'] != manifest['commit'] or not check_receipt['success']
            or check_receipt['dirty_checkout'] or check_receipt['production_data_used']):
        raise RuntimeError('Passing release checks for this source commit are required')
    retirement = retired_definitions.load_context(
        RETIREMENT, SOURCE, source_sha, target, target_sha, retirement_archive=RETIREMENT_SOURCE)
    before = retirement.code_plan(machine.root, source_manifest, source_files, source_sha)
    after = retirement.code_plan(machine.root, manifest, files, target_sha)
    pinned_examples = acknowledge_external_examples(machine, source_files, files)
    unexpected = [block for plan in (before, after) for block in plan['blockers']
                  if block['path'] not in pinned_examples or block['reason'] != retired_definitions.REGISTRY_BLOCKER]
    if before['changes'] or unexpected or not after['changes']:
        raise RuntimeError('Installed source or proposed changes differ from the verified archives: '
                           + str(unexpected[:3]))
    code = {key: after[key] for key in ('commit', 'changes', 'plan_sha256')}
    code['external_projector_units'] = pinned_examples
    return {'schema': 'ts_momentum_direction_release_v1', 'code': code, 'archive_sha256': target_sha,
            'checks_sha256': sha256(checks_bytes).hexdigest(),
            'queue': plan_cutover(machine.root, MOMENTUM/'manifest.json', MOMENTUM/'checkpoint.json')}, files


def stopped(machine):
    if any(machine.status(unit) != 'inactive' for unit in (*release.UNITS, PACED_UNIT)):
        raise RuntimeError('Finish the active request and stop worker, web and paced intake before the cutover')
    machine.backup_ready()
    if machine.status('gambit-backup.service') != 'inactive':
        raise RuntimeError('Wait for the ongoing backup')


def record(folder, name, body):
    release.atomic(folder/name, canonical(body) + b'\n', mode=0o600)


def review(machine, directory, target, checks):
    if sha256(retired_definitions.trusted_bytes(PACER)).hexdigest() != PACER_SHA256:
        raise RuntimeError('Paced intake script differs from the tested version')
    if (MOMENTUM/'manifest-discovery-v1.json').exists() or (MOMENTUM/'checkpoint-discovery-v1.json').exists():
        raise RuntimeError('A successor intake has already been prepared')
    with ExitStack() as guards:
        release.guard(guards, machine.state/'control.lock')
        release.guard(guards, machine.backup/'backup.lock')
        stopped(machine)
        for name in release.LOCKS:
            release.guard(guards, machine.root/'storage/catalog/operations'/(name+'.lock'))
        proposal, _ = compute_plan(machine, target, checks)
        proposal['proposal_sha256'] = digest(proposal)
        directory.mkdir(mode=0o700, exist_ok=False)
        record(directory, 'proposal.json', proposal)
        return proposal


def install_code(machine, directory, proposal, files):
    receipt = {'changes': proposal['code']['changes'], 'status': 'installing',
               'proposal_sha256': proposal['proposal_sha256'], 'code_written': False}
    for row in receipt['changes']:
        if row['before'] is None:
            continue
        raw = release.safe_target(machine.root, row['path']).read_bytes()
        if sha256(raw).hexdigest() != row['before']:
            raise RuntimeError('Original source changed before the cutover')
        release.atomic(directory/'before'/row['path'], raw, mode=0o600)
    record(directory, 'receipt.json', receipt)
    try:
        for row in receipt['changes']:
            machine.write(release.safe_target(machine.root, row['path']), files[row['path']])
        verify_installed_code(machine, proposal)
    except BaseException:
        try:
            release.restore(machine, directory, receipt)
        except BaseException:
            record(directory, 'receipt.json', dict(receipt, status='rollback_required'))
            raise
        record(directory, 'receipt.json', dict(receipt, status='rolled_back'))
        raise
    record(directory, 'receipt.json', dict(receipt, code_written=True, status='pending_queue'))


def verify_installed_code(machine, proposal):
    for row in proposal['code']['changes']:
        observed = sha256(release.safe_target(machine.root, row['path']).read_bytes()).hexdigest()
        if observed != row['after']:
            raise RuntimeError('Installed source checksum differs: ' + row['path'])


def run_queue(machine, directory, proposal):
    import pwd
    account = pwd.getpwnam('gambit')
    queue_path = directory/'queue.json'
    queue_bytes = canonical(proposal['queue']) + b'\n'
    release.atomic(queue_path, queue_bytes, mode=0o640, gid=account.pw_gid)
    # Grant the worker identity access to the pinned queue file path. The
    # release directory and contents remain root owned.
    directory.chmod(0o750)
    os.chown(directory, 0, account.pw_gid)
    script = machine.root/'tools/ts_momentum_direction_cutover.py'
    subprocess.run(['runuser', '-u', 'gambit', '--', PYTHON, '-B', str(script),
                    'apply-queued', '--root', str(machine.root), '--plan', str(queue_path),
                    '--plan-sha256', sha256(queue_bytes).hexdigest()], check=True)
    manifest = MOMENTUM/'manifest-discovery-v1.json'
    write_next_manifest(MOMENTUM/'manifest.json', manifest, proposal['queue'])
    manifest.chmod(0o644)
    checkpoint = MOMENTUM/'checkpoint-discovery-v1.json'
    if not checkpoint.exists():
        release.atomic(checkpoint, canonical({
            'manifest_sha256': sha256(manifest.read_bytes()).hexdigest(), 'next_index': 0,
            'created': 0, 'existing': 0, 'blocked': []}) + b'\n', mode=0o640)
    elif (json.loads(checkpoint.read_bytes())['manifest_sha256'] != sha256(manifest.read_bytes()).hexdigest()
            or json.loads(checkpoint.read_bytes())['next_index'] != 0):
        raise RuntimeError('The successor intake checkpoint has already advanced')
    os.chown(checkpoint, account.pw_uid, account.pw_gid)


def resume_services(machine):
    if sha256(retired_definitions.trusted_bytes(PACER)).hexdigest() != PACER_SHA256:
        raise RuntimeError('The existing paced intake operator differs from the reviewed version')
    # The metadata watcher imports its verification code once. Preserve its
    # unit and saved serving snapshots, then reload the new branch verifier.
    subprocess.run(['systemctl', 'restart', 'gambit-read-projector.service'], check=True)
    for unit in reversed(release.UNITS):
        if machine.status(unit) != 'active':
            machine.start(unit)
    machine.health()
    if machine.status('gambit-read-projector.service') != 'active':
        raise RuntimeError('The updated metadata projector did not start')
    if machine.status(PACED_UNIT) != 'active':
        catalog = machine.root/'storage/catalog'
        subprocess.run(['systemd-run', '--unit='+PACED_UNIT.removesuffix('.service'),
            '--uid=gambit', '--gid=gambit', '--property=Type=exec', '--property=Restart=on-failure',
            '--property=RestartSec=90s', '--property=MemoryMax=850M', '--property=Nice=10',
            '--property=NoNewPrivileges=yes', '--property=ProtectHome=yes', '--property=ProtectSystem=strict',
            '--property=RestrictAddressFamilies=AF_UNIX',
            '--property=ReadWritePaths='+str(catalog)+' '+str(MOMENTUM), PYTHON, '-B', str(PACER),
            '--root', str(machine.root), '--manifest', str(MOMENTUM/'manifest-discovery-v1.json'),
            '--checkpoint', str(MOMENTUM/'checkpoint-discovery-v1.json'), '--start-cursor', '0',
            '--start-terminal', '0'], check=True)


def apply(machine, directory, target, checks, expected):
    with ExitStack() as guards:
        release.guard(guards, machine.state/'control.lock')
        release.guard(guards, machine.backup/'backup.lock')
        stopped(machine)
        saved = json.loads(retired_definitions.trusted_bytes(directory/'proposal.json'))
        if saved['proposal_sha256'] != expected or digest({
                key: value for key, value in saved.items() if key != 'proposal_sha256'}) != expected:
            raise RuntimeError('The explicitly approved proposal differs from the saved plan')
        prior = directory/'receipt.json'
        if not prior.exists():
            with ExitStack() as locks:
                for name in release.LOCKS:
                    release.guard(locks, machine.root/'storage/catalog/operations'/(name+'.lock'))
                fresh, files = compute_plan(machine, target, checks)
                if digest(fresh) != expected:
                    raise RuntimeError('The proposed code or frozen momentum roster changed')
                install_code(machine, directory, saved, files)
        else:
            receipt = json.loads(retired_definitions.trusted_bytes(prior))
            if receipt['status'] != 'pending_queue' or receipt['proposal_sha256'] != expected:
                raise RuntimeError('Inspect the cutover receipt before recovering')
            verify_installed_code(machine, saved)
        run_queue(machine, directory, saved)
        record(directory, 'receipt.json', {
            'status': 'queue_ready', 'proposal_sha256': expected, 'code': saved['code'],
            'queued': len(saved['queue']['queued']), 'followups': len(saved['queue']['followups']),
            'finished_at': datetime.now(timezone.utc).isoformat()})
        resume_services(machine)
        record(directory, 'receipt.json', dict(json.loads(prior.read_bytes()), status='succeeded'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('review', 'apply', 'resume'))
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--checks', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--proposal-sha256')
    args = parser.parse_args()
    if args.directory.parent != STATE or not re.fullmatch('direction-[a-f0-9]{16}', args.directory.name):
        parser.error('Use a unique protected release directory')
    machine = release.Machine()
    if args.command == 'review':
        proposal = review(machine, args.directory, args.target, args.checks)
        queue = proposal['queue']
        print(json.dumps({'proposal': proposal['proposal_sha256'], 'commit': proposal['code']['commit'],
                          'original_states': queue['original_states'], 'staged': len(queue['staged']),
                          'p2_only': sum(len(row['skipped']) for row in queue['followups']),
                          'held': len(queue['held'])}))
    else:
        if not args.proposal_sha256:
            parser.error('Apply or resume requires the exact approved proposal hash')
        if args.command == 'apply':
            apply(machine, args.directory, args.target, args.checks, args.proposal_sha256)
        else:
            with ExitStack() as guards:
                release.guard(guards, machine.state/'control.lock')
                receipt = json.loads(retired_definitions.trusted_bytes(args.directory/'receipt.json'))
                if receipt['status'] != 'queue_ready' or receipt['proposal_sha256'] != args.proposal_sha256:
                    raise RuntimeError('Only an installed and reconciled queue can resume')
                verify_installed_code(machine, receipt)
                resume_services(machine)
                record(args.directory, 'receipt.json', dict(receipt, status='succeeded'))


if __name__ == '__main__':
    main()
