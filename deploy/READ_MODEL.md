# Dedicated website read model

This release implements a metadata-only serving path. It is **disabled by default**.
It does not install/start a service, create a timer, change research execution,
modify the queue, or switch existing production reads. A Git merge alone is not
activation. The scientific executor fingerprint remains
`da5400efd1086e7139b39d78aac6a256f471b48a66ad5ba41e34c08fcbe6d6c4`.

## Boundaries

`read_model.extract` uses the existing envelope, journal, event-chain and research
branch validators. It never calls a kernel, artifact/payload verifier, intake,
repair, resume, cancellation or worker start. A source guard rejects research
writes, scientific lock creation and numerical/lineage payload reads. OS account
permissions and the example hardened unit provide the stronger deployment boundary.
Only a **separate output directory** may be written; neither the auth database nor
a descendant/ancestor of research storage is allowed as the serving directory.

The current/previous source checksums are retained. A changed/deleted previously
observed immutable source revokes serving globally until investigated; a failed
refresh cannot silently bless its replacement. This intentionally conservative
first version blocks more widely than a future per-row revocation mechanism.
New incomplete/unverifiable records are excluded with visible issues. Unlinked
trial/admission/validation metadata is retained but cannot create a Signal card.
Missing receipts remain explicitly pending and never get repaired by the reader.

Sources are stat-checked on each explicit refresh, including inode, ctime and
symlink checks. A source's bytes are hash-checked on change or at least hourly.
Changed units alone are reverified; display tables/aggregates are rebuilt from the
compact verified units in a copy of the previous database. Per-request event heads
and dependency sets live in those units. A change in extractor/validator source
fingerprint forces unit re-verification without discarding source hash baselines.
There is no global timestamp watermark and no writer hook.

A build captures a finite prefix of publications. Concurrent new appends are read
next cycle. Records are visible only after their existing complete reference
validation passes. It is not a globally transactional view of the filesystem.
Original references, hypotheses, trial bodies, lineage/artifact references,
execution bindings and queue keys remain unchanged. Program membership is **not
inferred**: this release serves all verified stored research, including either
hypothesis direction, without claiming a manifest association it did not verify.

## Output and HTTP contract

A closed rollback-journal SQLite file, schema/inventory manifest and atomic pointer
form a generation. No WAL or shared mutable SQLite writer is used. Each request
opens its pinned generation with `mode=ro` and `query_only`; integrity revocations
are checked before and after the query. Publication validates SQLite integrity and
foreign keys and records database hash/signature plus a semantic projection hash.
SQL work has a two-second interruption budget. Display rows are capped at 256 KiB;
page/detail JSON metadata is capped at 4 MiB. Oversize rows become visible
verification issues, never truncated scientific records. No full database hash, metadata scan or research file open runs on normal HTTP
requests. The trusted publisher owns these files; the web account must have only
read permissions. A changed database signature makes it unavailable.

Authenticated GET/HEAD endpoints under `/api/read-model/v1/`:

- `ledger` and `queue`: 50 rows by default, at most 100. Status/recipe/scope/direction,
  date and literal search filters. Queue position and ordering use the original
  queued-at/creation-time/request-ID rules. The actual worker never reads this DB.
- `recipes`: compact cards and outcome counts; no relationship arrays or payloads.
- `recipes/<recipe-id>/branches`: independent researched branches, deduplicating
  superseded partial links exactly as the existing reader does.
- `trial/<id>`, `relationship/<id>`, `decision/<id>`, `experiment/<id>`: exact stored
  metadata on selection. Experiment aliases resolve without duplicate counts.

Cursors bind generation, query, page size and last sort keys. Expired generations
return 410; the UI offers refresh. Query errors return 400; missing/invalid serving
state returns 503 without falling back to a filesystem reconstruction. Existing
command and legacy read routes keep their authentication/CSRF behavior.

The opt-in browser uses this path for Ledger, queue, recipe cards, relationship
pages and trial metadata. It retains the no-filter-bar Library, shows freshness,
and polls the visible first queue page every 30 seconds (existing page behavior,
not a new automation). No research mutations exist in this script. Large numerical
observations/charts are **not loaded** by this initial metadata UI. Legacy explicit
artifact/output endpoints remain available for existing tooling; isolating and
indexing numerical evidence is a separate next phase, not part of metadata backfill.
Do not claim that those legacy heavy endpoints have become bounded.

Every response states source observation time, generation, completeness and issues.
After 60 seconds it is delayed; after five minutes (or a future-dated observation)
it is historical and current activity is unknown. Queue state is a recorded event,
not a live health check. This version deliberately does not acquire a service lock
to claim worker liveness. Stale data is never reported as zero research or a live
healthy worker. A pass requires actual admitted discovery in the hypothesized
direction and a matching completed authoritative P2 VALIDATED evaluation with
validation-data access. Precheck failures remain distinct from numerical failure.

## Explicit offline use

```
python -B tools/project_read_model.py --root /absolute/isolated/research --output /absolute/separate/serving
```

Without `--watch-seconds`, this performs **one** build. Nothing is scheduled.
`--watch-seconds 30` is an explicit continuous-projector option for a separately
authorized service. One output-only lock prevents two builders. The default build
budget is 600 seconds, 200,000 captured metadata files, 64 MiB per source record,
1 GiB per closed database and 4 GiB for the serving directory.
The initial production shadow exceeded the earlier 256 MiB pilot database cap.
Production shadow also exposed all-branch retention of full trial metadata.
Branch selection now retains compact summaries and hydrates one verified SQLite
unit at a time, preserving the same evidence-set supersession and stored records.
Generation checksums now stream in 1 MiB chunks, including verification before an
incremental copy, so a larger disk allowance does not require loading a database
into publisher memory. Current and previous generations remain protected; cleanup
reserves room for the next bounded build. Check free disk space before activation. The service example
caps memory at 256 MiB and CPU at 25%; these are pilot limits, not measured proof
that current production backfill meets them. Resource failure leaves the previous
published snapshot, which visibly ages. No pressure response changes research.

Cleanup removes expired generation files (default one hour), always retaining
the current and previous generations. It can expire older cursors earlier under
disk pressure to reserve 1 GiB for the next build; those clients receive 410
and refresh. This bounds retention without starving continuous publication. A build interrupted before pointer publication
leaves the previous generation. If interrupted after pointer and before clearing
integrity status, serving remains conservatively unavailable until a successful
refresh. Investigate source integrity failures; do not delete a checksum baseline
just to make a build pass. A corrupted derived database can be recovered from a
verified retained generation or an explicitly reviewed clean backfill; authoritative
research is never restored or replaced.

## Production activation gates — not performed by this PR

1. Verify exact installed code and currently active positive/negative programs with
   read-only metadata. Preserve original envelopes, queue keys/order, event heads,
   partial/completed trials and result references. Do not scan numerical storage.
2. Inspect permissions/headroom; provision the separate reader/output directory only
   through an authorized operational change. Use the example unit as a reviewed
   template, not an automatic installer. Neither account nor service is created here.
3. Run a bounded shadow backfill with the research worker continuing normally. Compare
   exact fields/refs/decisions and aliases against existing readers on a captured
   prefix. Verify all issues, metadata size, RSS/CPU/I/O and refresh lag.
4. Qualify representative P1 preparation/evaluation and P2 activity: 1/4/8 clients,
   cold/warm web caches, current and 10x metadata, >=100 requests per scenario and
   a >=30-minute mixed-load soak. Targets remain p95 <2 seconds rendered first page,
   <500ms common queries, no timeouts and <=5% controlled research-throughput impact.
   Local query benchmarks do not establish these production gates.
5. Use the official exact-commit release workflow and established code deployment
   procedure. This PR does not bypass any required worker-preservation or recovery
   step. Set `GAMBIT_READ_MODEL_DIR=/var/lib/gambit-read-model` **only for the web
   service**, after shadow checks pass. Verify authentication, homepage, data-bearing
   pages, repeated reads and stale/error states. Do not reset/resubmit experiments.
6. Serving rollback removes that web setting or selects verified prior web code.
   It never rewinds research storage, restores snapshots over new results, or
   changes execution approval bindings. Stopping a projector affects freshness only.

Tests cover byte-for-byte source preservation, both directions, actual/precheck P2,
partial links, aliases, incomplete receipts, event gaps, source mutation/symlinks,
concurrent append and pointer swap, failed publication/disk bounds, query-only SQL,
no source opens on page reads, cursor expiration, browser pagination/staleness, and
existing private-route access boundaries. Production parity and active-research soak
remain explicit release gates.

## Reproducible synthetic query benchmark

`python -B tools/benchmark_read_model.py --output /tmp/read-model-benchmark.json`
creates and deletes isolated synthetic serving databases; it cannot accept a
research source. The fixture sizes are 500/5,000 experiments and 2,500/25,000
relationships, with 53 recipe cards. Each endpoint runs 100 times with 1/4/8
clients (3,000 requests total). Every request opens a new read-only connection.
This qualifies query/serialization scaling only. OS caches are uncontrolled; it
does not measure projector throughput, browser rendering, authentication, network
latency or interference with production research. The production gates above
remain necessary.
