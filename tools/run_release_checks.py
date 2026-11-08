#!/usr/bin/env python3
"""Run bounded release checks in a disposable workspace with no production store."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    'test_fx_currency', 'test_fx_currency_migration', 'test_fx_migration_index', 'test_fx_catalog_preflight', 'test_fx_migration_control', 'test_feature_resolution',
    'test_scopes', 'test_scope_api', 'test_scope_ui', 'test_fx_transformations', 'test_fx_targets',
    'test_experiment_identity', 'test_execution_compatibility', 'test_program_intake_compatibility', 'test_frozen_program_status',
    'test_research_performance', 'test_performance_benchmark', 'test_benchmark_closure', 'test_fresh_feature_benchmark', 'test_preparation_benchmark', 'test_program_cutover', 'test_followup_cutover', 'test_p2_preparation_reuse', 'test_retired_definitions', 'test_retired_cutover',
    'test_research_batches', 'test_batch_retirement_release', 'test_batch_http', 'test_batch_ui',
    'test_momentum_preparation_operator', 'test_lineage_packs', 'test_fx_feature_store', 'test_verified_inputs', 'test_research_inputs',
    'test_release_workflow', 'test_contracts', 'test_transformation_numeric',
    'test_transformation_registry', 'test_transformation_engine',
    'test_research_runtime', 'test_research_recovery', 'test_scheduled_hac',
    'test_p2_evidence_policy', 'test_feature_applications',
    'test_research_policy_end_to_end', 'test_external_feature_end_to_end',
    'test_research_http', 'test_experiment_views', 'test_experiment_labels', 'test_separate_services', 'test_production_access',
    'test_production_http', 'test_production_session_js', 'test_queue_ui',
    'test_signal_recipe_ui', 'test_library_pages_ui', 'test_research_ui', 'test_research_startup',
    'test_read_model', 'test_read_model_branches', 'test_read_model_http', 'test_read_model_ui', 'test_chart_evidence', 'test_live_activity',
    'test_catalog_cache', 'test_catalog_reads', 'test_signal_recipe_summaries',
    'test_signal_library_api', 'test_feature_library_api',
    'test_reusable_feature_recipes', 'test_feature_research_dashboard',
    'test_cloud_migration', 'test_cloud_backup', 'test_cloud_health',
]


def seed_registry(root):
    fixture = root / 'tests/fixtures/registry_support'
    manifest = json.loads((fixture/'manifest.json').read_text())
    for row in manifest['files']:
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe policy fixture path')
        data = (fixture/relative).read_bytes()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Policy fixture checksum mismatch')
        target = root/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'release-checks.json')
    args = parser.parse_args()
    if not shutil.which('node'):
        raise SystemExit('Node.js is required; UI checks may not be skipped')
    started = time.monotonic()
    if (ROOT/'storage').exists():
        raise SystemExit('Use the source-only checkout; production storage is forbidden')
    try:
        commit = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=all']).strip())
    except subprocess.CalledProcessError:
        commit, dirty = None, True
    with tempfile.TemporaryDirectory(prefix='gambit-release-checks-') as tmp:
        root = Path(tmp)/'project'
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(
            '.git', '.venv*', '__pycache__', 'outputs', 'dist', 'release-checks.json',
            '*.tar.gz', '*.log', '*.local.*'),
            # The checkout must not contain a production store. Policy fixture
            # directories named storage are allowed only under tests/fixtures.
            dirs_exist_ok=False)
        if (root/'storage').exists():
            raise SystemExit('Use the source-only checkout; production storage is forbidden')
        seed_registry(root)
        (root/'outputs').mkdir()
        env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'TMPDIR', 'LANG') if k in os.environ}
        env.update(PYTHONPATH=str(root/'src')+os.pathsep+str(root/'tests'),
                   PYTHONDONTWRITEBYTECODE='1', GAMBIT_ISOLATED_TEST='1')
        result = subprocess.run([sys.executable, '-m', 'unittest', '-v', *SUITES], cwd=root, env=env)
        report = {'schema': 'gambit_release_checks_v1', 'success': result.returncode == 0,
                  'suites': SUITES, 'seconds': round(time.monotonic()-started, 3),
                  'python': sys.version, 'production_data_used': False,
                  'commit': commit if not dirty else None, 'dirty_checkout': dirty}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
