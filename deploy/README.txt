GAMBIT CLOUD OPERATIONS

CURRENT ACCEPTANCE
See cloud-cutover-verification.txt (task) and outputs/cloud_cutover_verification.txt
(project) for dated activation status, exact evidence and remaining limitations.
This runbook describes the installed design. Do not infer an acceptance PASS from
the existence of a configuration file or from an old pre-deployment report.

HOST AND STORAGE
DigitalOcean gambit-research-01 (608233107), 64.23.188.70, SFO3, Ubuntu24.04LTS.
2 vCPU,4GiB RAM,80GB boot disk;100GiB attached research volume at /srv/gambit.
UUID609a0a34-e482-4873-9893-6ed1163837ec must be mounted before any research service.
Scientific authority: /srv/gambit/research_platform/storage.
Code/specifications: /srv/gambit/research_platform, root-owned, group-readable.
Authentication SQLite: /srv/gambit/auth, writable only by gambit and root.
Administrative settings: /etc/gambit. Never package or expose these settings.
Runtime: /opt/gambit/python-3.14.8; virtual environment: /opt/gambit/venv.
Dependencies are hash-locked in requirements-cloud.lock; do not copy a Mac venv.

REQUEST AND EXECUTION PATH
Caddy terminates HTTPS and proxies only to the Gunicorn Unix socket. Django
requires an active owner session for the app, assets and research APIs. Writes
also require exact origin and CSRF validation. The web adapter uses the existing
shared application routes and persistent submission records.
gambit-worker.service owns execution independently of Gunicorn/browser/Codex.
The same registered preparation, P1/P2 methods, persistence and recovery code run
on Linux. No AI agent or LLM credentials are required. P3/P4 remain future work.
Client disconnection never cancels a stored experiment. Do not automatically
resubmit after a network error: reconcile the same frozen submission ID.

SERVICES
gambit-web.service: two Gunicorn processes, two threads each, private socket.
gambit-worker.service: one independent worker; competing owners are rejected.
SIGTERM drains an active submission; there is no forced shutdown timeout.
gambit-health.timer: checks worker ownership/heartbeat, mounted volume, disk
capacity and backup freshness every minute. Public /healthz exposes only a
generic200/503 status. Private details are /run/gambit-health/status.json.
gambit-backup.timer: daily11UTC plus up to10min jitter, with missed-run recovery.
Caddy certificate renewal is automatic. Deployment markers intentionally gate
worker/backup activation; GAMBIT_ALLOW_SUBMISSIONS gates cloud writes.

ACCESS
Domain gambitsystems.xyz. Login username owenosa; email is an identity contact,
not an enabled email-reset service. No public signup/admin route. Owner password
changes are interactive via tools/manage_web.py changepassword owenosa under the
configured environment. Never pass passwords as arguments or print settings.
SSH uses the approved deployment key and pinned server identity. Both cloud and
host firewalls restrict SSH to the verified deployment source (4.35.154.2 at
cutover), while80/443 are public. IPQoS=none resolved fresh SSH connection stalls;
the firewall was not broadened. If the owner's network changes, update only to a
separately verified intended address, using the provider console if necessary.

BACKUP AND RESTORE
Read deploy/BACKUP_RECOVERY.txt. Restic encrypts the research store, owner database
and configuration into the private NYC3 Spaces bucket. Backup drains worker,
pauses web, holds writer locks, verifies a consistent copy, then restarts services
before upload. Many small files mean the maintenance pause can take minutes.
Retention:7daily/4weekly tagged production snapshots. Boot-disk staging must fit
the source bytes plus10% and1GiB; monitor boot and research disks separately.
The volume's advertised capacity is not the available backup staging capacity.
VM backups do not include the attached volume. Restic copies are encrypted but
not immutable/WORM. Both access credentials and the separate encryption password
are necessary for recovery; protected outside-server copies are retained on Mac.

RELEASES
The migration manifest is the receipt of the original byte-verified import.
Do not rewrite it to conceal later releases. Record subsequent code/deployment
checksums separately. Keep original records, scientific references and payloads
immutable. Verify new releases against isolated fixtures before changing a live
worker. Check queue, prevent new writes, drain and stop worker before a scientific
code/runtime update. Never force old frozen jobs through a changed implementation.
The full sys.version is part of implementation identity; a Linux build legitimately
differs from the old Mac build even with equivalent scientific source.

SINGLE AUTHORITY AND ROLLBACK
Cloud activation makes the cloud the only writable production authority. Keep the
old Mac services stopped. Before any cloud writes, the untouched local snapshot
is a rollback option. After cloud writes, drain/export/reconcile those records
before selecting another authority. Never silently switch to a stale Mac store.
On a replacement server restore into an isolated directory first, verify full
hash/reference/SQLite/reader closure, install permissions/services with Submit
disabled, and activate only after recovery acceptance. Do not expose data while
troubleshooting. Closing the laptop is independent; losing the cloud VM is not.

COST AND MONITORING
Baseline VM$24 + volume$10 + daily VM backup$7.20 + Spaces$5 = $46.20/month before
tax, overages and domain. Disk75%,memory85%,budget$40/$60/$80 email alerts are
configured. The availability check targets /healthz in four regions. See the
acceptance report for its activated alert threshold. Alerts are not spending caps.
No paid agent, GPU, managed database or additional hosting tier is required.
Consider a larger VM only after measuring worker memory/throughput; performance
improvements are separate from proving correctness and off-laptop operation.
