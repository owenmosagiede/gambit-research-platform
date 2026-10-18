#!/usr/bin/env python3
"""Private server operator CLI. Uses the same batch API/service; never runs research.

Run as the research service account against its existing workspace. Approval is
explicit; after it succeeds the existing service resumes dispatch without this CLI.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from runtime.research_batches import ResearchBatches, checked, MAX_BODY
from services.research_worker import WebResearchJobs
from data.alfred_onboarding import strict_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Existing research workspace; no credentials are required or read')
    parser.add_argument('--output', type=Path, help='Write the complete preview/progress report as JSON')
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('preview', help='Persist manifest for background preview only; does not approve experiments')
    create.add_argument('manifest', type=Path)
    commands.add_parser('list')
    for name in ('status', 'pause', 'resume', 'approve'):
        cmd = commands.add_parser(name); cmd.add_argument('batch_id')
        if name == 'approve':
            cmd.add_argument('--preview-sha256', required=True)
            cmd.add_argument('--exclude-blocked', action='store_true', help='Explicitly exclude previewed blocked rows')
    args = parser.parse_args()
    if not (args.root / 'config/research_execution.json').is_file():
        parser.error('Use an existing, configured workspace')
    batches = ResearchBatches(WebResearchJobs(args.root))
    if args.command == 'preview':
        if args.manifest.stat().st_size > MAX_BODY: parser.error('Manifest exceeds 256 KiB')
        value = batches.create(strict_json(args.manifest.read_bytes()))
    elif args.command == 'list':
        value = {'batches': [{'batch_id': p.parent.name, 'name': checked(p)['request']['name']}
                           for p in sorted(batches.base.glob('*/manifest.json'))]}
    elif args.command == 'approve':
        value = batches.approve(args.batch_id, {'preview_sha256': args.preview_sha256, 'exclude_blocked': args.exclude_blocked})
    elif args.command == 'status': value = batches.status(args.batch_id)
    else: value = batches.control(args.batch_id, args.command)
    rendered = json.dumps(value, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(rendered)
        compact = {k: v for k, v in value.items() if k != 'items'}
        print(json.dumps(compact, indent=2)); print('Full report:', args.output)
    else: print(rendered, end='')


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, KeyError) as exc: raise SystemExit(str(exc))
