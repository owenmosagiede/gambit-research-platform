# Development and controlled releases

The private source repository is `owenmosagiede/gambit-research-platform`.
The development checkout is `~/Documents/Codex/gambit-research-platform`.
The original Desktop checkout is a historical reference. Its production services
stay stopped. The DigitalOcean store remains the sole production authority.

## Daily development

1. Start a `codex/<change>` branch from current `main`.
2. Change code with relevant isolated tests. Preserve approved scientific contracts.
3. Run `python tools/run_release_checks.py` with the cloud lockfile dependencies
   and Node.js installed. Open a pull request and inspect its `Validate / checks` run.
4. Merge the reviewed, passing change. A push or merge does **not** deploy anything.

`Validate` uses Ubuntu, Python 3.14.8, Node 22, and hash-locked Python packages.
It runs bounded synthetic tests in a temporary workspace, including real HTTP,
independent workers, P1/P2, persistence, recovery, UI, and deployment safeguards.
It is not the full production-data acceptance suite. No market data, trial
records, cloud keys, or AI credentials are needed. Policy fixtures preserve the
three approved transformation specification records and their six exact files.

## Prepare a release

In GitHub Actions choose **Prepare controlled release**, select `main`, and click
**Run workflow**. It retests that exact commit and produces a `release-<commit>`
artifact containing the source archive, SHA-256 file, and passing checks receipt.
It has read-only repository permissions and no cloud deployment credentials.
Download and extract the artifact. Keep the archive and receipt together.

The archive is a source package, not a backup. Its commit and per-file hashes are
verified before deployment. It excludes live storage, authentication, local
mappings, private keys and generated outputs. Versioned definitions are present
for review/testing, but a normal deployment cannot change or add them on the server.

## Review and apply

Use the already authorized SSH key and pinned host-key file, stored outside this
repository. The control tool is installed separately at
`/opt/gambit/release-control`. It never reads GitHub credentials.

```sh
python tools/deploy_cloud.py plan \
  --ssh-key /protected/path/to/deployment-key \
  --known-hosts /protected/path/to/known_hosts \
  --archive /downloaded/gambit-COMMIT.tar.gz \
  --sha256 ARCHIVE_SHA256 --checks /downloaded/release-checks.json
```

This uploads only the verified source archive and prints a read-only plan.
Inspect changed files, migration blockers, and active requests. To apply that
exact plan, repeat with action `apply` and `--plan-sha256 PLAN_SHA256`.

Application code, UI, tools, schemas and developer docs can be updated by this
path. Existing code removal, new/changed definitions or policy configuration,
dependencies, and service/runtime changes need a separately reviewed migration.
Service installers are not executed automatically. Historical data and records
are never copied from the Mac over the cloud.

The release refuses queued/running research. Finish those submissions on their
original version first. It also requires a successful backup within 36 hours,
holds the backup lock, stops web intake, rechecks for racing submissions, and
stops the idle worker. It holds all writer/executor locks during file replacement.
No forced termination is used. Original changed code is saved with checksums,
then services restart and health is checked. Runtime Python remains unchanged.

The default invocation previews only. The explicit `apply` command is the
deployment gate, independent of GitHub plan-dependent branch protection features.
Do not treat an unenforced GitHub branch rule as an enforced approval control.

## Rollback and interrupted releases

Release receipts and before-images are in `/var/lib/gambit-releases` on the boot
disk; record their IDs in the change history and retain the GitHub source artifact.
Off-host research backups remain governed by `BACKUP_RECOVERY.txt`.

```sh
python tools/deploy_cloud.py rollback \
  --ssh-key /protected/path/to/deployment-key \
  --known-hosts /protected/path/to/known_hosts \
  --release-id COMMIT-PLANPREFIX
```

Rollback also requires idle research and a recent backup. It restores code only,
checks live bytes against the recorded before/after hashes, and refuses unexpected
edits. A failed install normally restores its original code. If restoration is
incomplete, services remain stopped and the receipt requires recovery; no further
release is allowed. If a new job arrives after restart and health fails, automatic
rollback is deferred rather than interrupting that job. Resolve operational
health, let the original version's jobs finish, then run the explicit rollback.

Code changes legitimately alter research implementation identity. Old frozen
failed/cancelled submissions may then be unable to resume; preserve their records
and create a new submission if desired. Never rewrite their IDs or fingerprints.
