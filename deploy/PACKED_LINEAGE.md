# FX lineage storage rollout and recovery

This physical format stores the unchanged canonical `fx_feature_lineage_record`
objects in bounded gzip packs. Existing loose lineage, scheduled input records,
Feature/Signal identities, policy bindings, observation payloads, materialization
schemas and research results remain unchanged. New execution still fingerprints
its actual implementation, including the adapter. Historical records are never
rewritten. No old loose files are removed by this release.

## Activation boundary

1. Run isolated release checks and merge a reviewed PR. Deploy the exact checked
   artifact through `RELEASE_WORKFLOW.md` with an idle queue and fresh backup.
   Readers support both formats immediately; writes remain loose by default.
2. Before any packed production output, install the exact reviewed
   `deploy/release_server.py` in `/opt/gambit/release-control`, preserving and
   checking the previous helper. This is an explicit control-tool update,
   separate from the normal application deployment. Its compatibility guard
   refuses a deploy/rollback to a reader lacking packed-lineage support once
   immutable pack catalogs exist. Do not use an older control helper afterward.
3. Verify old production materializations and library reads. Measure complete
   representative preparation in an isolated destination; include observations,
   catalogs, shared scheduled inputs, index growth and backup staging. Account
   separately for shared inputs and marginal additional recipes. Require space
   and inode reserves before the bulk job.
4. Enable `GAMBIT_FX_LINEAGE_STORAGE=packed_v1` for the approved preparer. If
   enabling future UI/worker publications too, separately update their shared
   environment and restart only while idle under the release/backup/executor
   maintenance locks. Absent variable means `loose`; unknown values fail closed.
   The flag changes physical storage only, not scientific identity.
5. Preparation operators must hold `research-executor.lock` for their lifetime,
   verify there is no active research before starting, respect cancellation,
   checkpoint completed materializations, and stop before exhausting space or
   inodes. Backups and deployment use the same lock. Never fabricate P1 admission
   to prepare P2, and never launch research as part of a storage rollout.

## Authority, publication, and bounds

`storage/catalog/lineage_packs/<sha256>.json` is an immutable catalog, whose hash
covers its format, ordered exact record references, compressed payload reference,
uncompressed size and checksum. The content-addressed `.bin` payload contains
canonical JSON lines compressed with gzip. A pack contains at most 1,024 records;
compressed and decompressed byte limits are each 8 MiB. Normal preparation uses
one pack per existing bounded output window (at most 366 calendar days).

The disposable SQLite locator is `storage/temporary/lineage-packs.sqlite3`.
The authoritative pack catalogs can rebuild it automatically. Record identity
hashes, schemas, counts, bounds, canonical framing, compressed/uncompressed
checksums and requested references are checked on reading; research still
independently recalculates Feature values from the pinned source.

Publication order is payload → catalog → index → independently verified
materialization → library entry. A crash can leave unreferenced immutable
payloads/catalogs; retries reconcile them. Such an orphan is not a completed
materialization. Lock order is executor/maintenance → Feature publication → pack
index. Concurrent readers rebuild under the index lock and detect catalog changes.
Only two decompressed packs and 2,048 locators are retained per reader.

## Backup and recovery

The existing quiescent backup copies/checksums immutable catalogs and payloads.
No backup exclusions are added. Its service drain and research locks also exclude
an approved preparation operator. The index may be copied while quiescent, but
is never authoritative: restored directory identities invalidate it, and an
absent or corrupt SQLite index is reconstructed in application code. A malformed
catalog, corrupt pack or conflicting scientific reference fails explicitly; it
is never replaced with invented data. Isolated tests copy/seal/verify a backup,
remove the derived index and numerically replay restored materializations.

After packed outputs exist, roll back write behavior by setting the flag to
`loose`, retaining a packed-capable reader. Do not expand all packs into loose
files: that may exceed capacity. A rollback to pre-adapter readers is blocked.
This first rollout does not compact historical files or garbage-collect orphans.

## Approved Momentum preparation operator

`tools/prepare_momentum_population.py` is specific to the approved 53-recipe,
43-instrument, 18-universe discovery-input program. It requires a checksum-pinned
manifest bundle and revalidates exact registered recipe mappings, source/Target
pins, Scope membership snapshots, research policy and phase boundaries. Use
`--dry-run` to inspect metadata without publication; only explicit `--apply`
can publish, and that additionally requires all 215 numerical Target preflight
results. It imports no research execution kernel and never creates P1/P2 trials.

The operator uses the existing numerical publisher and independent reader, with
one execution/phase input context per instrument. All 53 recipes retain their own
exact Feature cache keys. It splits storage windows at year and universe-start
boundaries so overlapping universes can reuse instrument outputs. Historical
outputs are independently replayed before reuse; partially overlapping outputs
are not double-counted. All-null windows are explicit, not silently dropped.

Each publication holds the research executor lock, refuses an active research
queue, checks application/profile stability and retains at least 20 GiB and one
million file slots on the data volume. It also checks room for a full backup
staging copy plus 10 GiB on the boot disk. Checkpoints follow completed verified
publications. A stopped/failed run is resumed with the same checked bundle; it
re-inventories and verifies existing materializations. A live-code change,
capacity breach or contention pauses explicitly. This operator does not start,
stop or reconfigure services; running it as a managed job is a separate reviewed
operational step. `--max-windows` bounds a production preparation pilot.

Its scope report distinguishes prepared rows, valid Feature rows, unavailable
windows and source/Target verification from paired-sample sufficiency and actual
research validation. Validation-period preparation remains deferred until real
P1 admission. The general research batch-submission tool remains separate work.
