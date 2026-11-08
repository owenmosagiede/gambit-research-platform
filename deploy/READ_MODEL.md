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
opens its pinned generation with `mode=ro` and `query_only`. A bounded status
re-read tolerates an overlapping healthy atomic publication while preserving the
pinned immutable generation. Observed revocation and persistent status churn
still fail closed; integrity revocations
are checked before and after the query. Publication validates SQLite integrity and
foreign keys and records database hash/signature plus a semantic projection hash.
SQL work has a two-second interruption budget. Display rows are capped at 256 KiB;
page/detail JSON metadata is capped at 4 MiB. Collection pages prefer at most 1 MiB of row payload, with a whole larger
single record allowed up to the hard bound. They may return fewer rows
than requested; their cursor continues
after the last complete row, without trimming provenance fields. Oversize rows become visible
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
not a new automation). No research mutations exist in this script. The current UI loads bounded chart summaries through the optional chart cache
described below; it never opens numerical source payloads. Legacy explicit
artifact/output endpoints remain available for existing tooling; the chart projector is separate from metadata backfill.
Do not claim that those legacy heavy endpoints have become bounded.

Every response states source observation time, generation, completeness and issues.
After 60 seconds it is delayed; after five minutes (or a future-dated observation)
it is historical and current activity is unknown. Queue state is a recorded event,
not a live health check. The separate bounded activity endpoint described below observes the existing
service heartbeat and lock without changing either. Stale data is never reported as zero research or a live
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
Production-sized query qualification also exposed temporary sorting of large
provenance values. Queries now sort compact identities first, then fetch only
the rows returned plus at most one row needed to discover the byte boundary.
This preserves complete provenance and stable cursors while bounding concurrent
JSON decoding and serialization.

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


## Research interface and optional saved charts

The interface retains three existing views. The queue separates current worker
activity from dated metadata counts and ordering. The ledger separates execution
status from the P1/P2 scientific dispositions. The library lists only recipes with
verified research links, with relationship counts and unique research-stage passes.
Its exact saved relationship selector preserves scope, direction, horizon and
independent branches. Only the selected branch's trial/decision metadata is loaded;
P2 precheck failures never acquire invented validation statistics or charts.
The existing rich metrics renderer is shared with the legacy interface, but its
read-model adapter cannot call the legacy filesystem/evidence routes.

`GET /api/read-model/v1/activity` reads a bounded heartbeat, an existing service
lock (read-only, nonblocking), the selected job projection and its exact event.
It does not enumerate jobs or reconstruct history. A fresh heartbeat, live process,
held lock, stable session/request identity and matching event are required before
showing an active experiment. Missing permissions, stale state and older workers
without the new operational `activity.request_id` field show **unknown**, not idle.
The worker adds only this field to its existing heartbeat; no scientific inputs,
events, implementation fingerprint or queue behavior change. The web account
requires read permission on these existing operational files. This endpoint reports
operational activity, not a new verification of the complete scientific event chain.

Charts need an explicitly activated separate reader. The metadata projector's
numerical-read restriction remains unchanged. An example service is provided in
`deploy/examples/gambit-chart-projector.service`; normal release deployment does
not install it, create accounts or change permissions. Before activation, prepare
the separate chart account and `serving/charts` output with the appropriate shared
read permissions. The web account must remain unable to write the serving cache.
The chart account must remain unable to write research or the metadata generations.

One explicit offline pass:

```
python -B tools/project_chart_evidence.py --root /absolute/isolated/research --output /absolute/separate/serving --max-trials 4 --seconds 30
```

The builder consumes verified trial metadata in a rotating cursor, reads only
exactly referenced selected chart artifacts, checks manifest identity, scientific
key, payload size and SHA256, and publishes an atomic checksummed summary. Source
writes and subprocess launch are forbidden by its runtime guard. The separate
service's filesystem restrictions also enforce read-only research access. It never
calls preparation, inference, research execution or decision code. Unselected
payload roles are not revalidated; the UI must not imply a fresh full-artifact audit.

Bounds: four trials per default pass, 30-second cooperative deadline, 64 MiB per
selected payload, 128 MiB selected payloads per trial, 1 MiB per array element or
small diagnostic payload, 128 block rows, <=1,200 chart points, 512 KiB summary,
and 512 MiB/20,000 files for the chart cache. The example service adds CPU/memory/I/O
limits and a 60-second rest between passes. Metadata reads and chart publication
use separate locks. JSON arrays stream; every usable IC contributes to the raw
cumulative sum before deterministic display thinning. TS plots use deterministic
display thinning and the saved full-sample regression, never refit it. Signed bars
show a central zero. A cumulative IC chart is explicitly not portfolio returns.

`GET /api/read-model/v1/evidence/<trial-id>?generation=...` reads only that trial's
metadata and its small serving-cache file. It verifies exact trial/artifact refs,
cache checksum/version and age. Summaries expire after 24 hours, with background
reverification eligible at 12 hours. This is dated evidence verification, not a
claim of live payload integrity. A failed refresh revokes the cached chart. Missing,
expired, oversized or corrupt charts show unavailable while saved metrics remain
usable. No page request starts a chart job or falls back to source payload reads.
Raw observation downloads are omitted from this path. Partial trial metadata is
preserved; it does not contribute an invented research pass.

Activation requires the usual exact-commit release/preservation procedure, plus
an isolated chart shadow pass and measured resource headroom before enabling the
separate numerical reader. Verify repeated authenticated reads during research,
current activity identity, dated snapshot counts, negative-direction results,
precheck failures and chart-unavailable states. The example limits are conservative
configuration, not a measured promise about production throughput. If cache work
cannot keep up within its bounds, charts become visibly unavailable; never slow,
restart or alter research to make a page pass. Rollback changes code or disposable
serving data only, never research records or execution approval bindings.
