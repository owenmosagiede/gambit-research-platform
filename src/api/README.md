# Local research APIs

The UI/API and research worker run as separate local processes. From the
`research_platform` root, start each in its own terminal:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/run_research_worker.py
```

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/serve_research_platform.py
```

Open `http://127.0.0.1:8765`. The web server supports `--port`; it never starts a
worker. Closing/restarting the web server or browser does not stop the independent
worker. The worker polls the existing durable queue every second. Both processes
use the same workspace and Python environment. No remote service or AI is involved.

The worker heartbeat is an operational projection at
`storage/catalog/operations/worker_service.json`. Readiness requires a heartbeat
less than 15 seconds old, a live process, the matching workspace and the held
`research-worker-service` lock. Missing/stale health disables UI submission; durable
requests remain saved. Existing executor/writer locks still serialize research and
publication. Duplicate worker services fail explicitly. Normal execution exceptions
retain the existing failed/blocked states, explicit resume and bounded thread recovery.

Control-C or SIGTERM to the **new worker** drains its current submission, leaving
waiting submissions queued. Cancellation remains an explicit API action. After a
hard process crash, restarting the worker uses existing durable recovery and exact
implementation checks. OS process auto-restart/boot startup is not installed here.
Keep its terminal open (or use a separately managed service). Laptop sleep pauses
both processes; this is still local execution.

**Safe cutover from an already-running combined server:** leave it alone until all
active/queued work has finished or reached explicit terminal states. Then stop that
old server and start the two commands above. Do not use the old server's Control-C
while research is running: it does not have the new drain behavior. Worker startup
refuses an already-held executor lock; this is a safety check, not a live migration.
Do not run the old combined server alongside the new worker, even when momentarily
idle. Frozen implementation mismatches remain blocked; never rewrite hashes to
force queued submissions through.

Opening libraries or selecting inputs does not submit work. Starting a worker can
resume previously accepted work, but does not create new requests.

`config/research_execution.json` carries the exact ID, version and content hash of
approved Research Spec `RSPEC_FX_SCOPE_ROUTED_SUBMIT` **2.0.0**, stored at
`definitions/research_specs/RSPEC_FX_SCOPE_ROUTED_SUBMIT/2.0.0.json`. Readiness verifies
that registered definition before enabling Submit. It pins 43 source snapshots and
215 completed Targets independently of catalog display choices, resolving ten display
snapshot mismatches and two AUDUSD Target ambiguities without rewriting stored data.
See [specification 23](../../specs/23_p1_p2_submit_execution.md).

## Experiment execution

| Method and route | Behavior |
| --- | --- |
| `GET /api/research-readiness` | Installed state, execution gate, profile identity/hash and explicit blockers |
| `POST /api/experiments` | Durably record the four selected inputs and backend profile; return a job |
| `GET /api/experiments/<request_uuid>` | Verify event history and return current progress/outcomes |
| `POST /api/experiments/<request_uuid>/cancel` | Request cancellation at a safe checkpoint |
| `POST /api/experiments/<request_uuid>/resume` | Resume blocked/failed/cancelled work with its original frozen inputs |
| `GET /api/research-results/<recipe_id>` | Read scoped results through exact trial/admission/validation and artifact references |

Submit JSON contains exactly:

```json
{
  "request_id": "a canonical UUID",
  "feature": {"id": "an exact registered Feature or recipe ID", "version": "1.0.0"},
  "target_family": "price_return",
  "scope": {"id": "an exact registered Scope ID", "version": "1.0.0"},
  "expected_direction": "POSITIVE"
}
```

The example's identity descriptions are placeholders, not executable IDs. Direction
may be `POSITIVE` or `NEGATIVE`. There is no Research Spec or horizon dropdown field.
An individual instrument selects TS; a universe selects CS only. All five horizons
are included. P2 runs only for admitted candidates passing the direction precheck.

The horizons remain 1/7/21/63/252 scheduled Monday–Friday steps, with no holiday
exclusions and both observation and Target endpoint inside the phase. Discovery uses
all eligible history from the selected members' frozen maximum structural start through
2021-12-31. The Validation period is 2022-01-01 through 2026-08-31 inclusive.
`scheduled_weekday_hac_v2` preserves actual weekday gaps in inference;
`unresolved_required_v1` marks unavailable required evidence unresolved and available
failed criteria failed. The existing 252-day t/p diagnostic exception is retained.
Prior versions and frozen submissions keep their own policies.

This is retrospective date-label research. Period-level legacy exposure is disclosed;
specific-recipe exposure is unknown, and the API does not certify an untouched holdout,
historical availability or live eligibility. CES and other non-FX entries retain their
existing visibility, but unsupported non-FX research bindings remain blocked.

A new recorded request returns 202; the same request ID and identical inputs return
200 with its existing job. Conflicting inputs under the same ID return 409. Retry an
uncertain response with the same ID. Cancellation/resume POST bodies must be `{}`.
A queue response does not mean computation succeeded. The worker checks the frozen
profile before preparation; an unresolved profile produces a blocked job. A changed
profile does not change an existing request, and changed implementation blocks reuse
of that request until a new explicitly submitted request is made.

Mutation routes require an exact same-origin `Origin` header, JSON content type and
one bounded Content-Length of 1–16384 bytes. Chunked bodies are rejected. Host/origin,
method and route checks remain explicit; unsupported mutation routes return 405.
The service is loopback-only and is not a remote/multi-user deployment.

## Feature and Scope selectors

- `GET /api/feature-library` supplies reusable FX recipe definitions and existing
  non-FX Features. Registered recipes remain visible without stored observations.
- `GET /api/feature-resolution?feature_id=...&feature_version=...&scope_id=...&scope_version=...`
  resolves exact selections against verified stored coverage, readiness and missing
  outputs per Scope member. This route does not prepare observations or start research.
- `GET /api/scope-library` lists registered individual and universe Scopes.
- `GET /api/scope-library/<scope_id>?version=...` resolves exact membership.
- `GET /api/feature-recipes` retains the historical instrument-bound recipe inspection
  API with optional `instrument_id`, `limit` and `offset`; it is not the Feature dropdown.

Scope chooses the instrument(s) for a reusable calculation. Historical bound IDs,
observations and references remain intact. See [specification 21](../../specs/21_reusable_features_and_scope.md).

## Signal Library

`GET /api/signal-library-summaries` lists only exact Feature definitions with
verified completed research relationships. Rejected, failed and unresolved
scientific outcomes remain visible. The list verifies relationship, trial,
admission, validation and definition metadata; it does not scan stored output
folders, open materialization manifests or verify numerical artifacts. Each entry
has `outputs_deferred: true` and an exact `outputs_href`.

`GET /api/signal-library-summaries/<FEATURE_OR_RECIPE_ID>/outputs` verifies that
selected definition still has completed research and returns its stored output
metadata on demand. Only that recipe's exact mapped Signal folders are read;
unrelated prepared outputs are not inspected. Missing or corrupt selected output
metadata yields explicit partial issues without removing verified research from
the main list. Both projections use dependency-tracked caches: new research
invalidates the list, while output publication invalidates the selected output
view. Full observation verification remains in the existing detail reader.

`GET /api/signal-library-outputs/<SIGNAL_ID>?materialization_id=<MATERIALIZATION_ID>`
retrieves the exact historical output underlying a grouped recipe. The existing
`GET /api/signal-library` and `/api/signal-library/<SIGNAL_ID>` routes remain for
compatibility and non-FX details. Exact IDs and references are verified. Descriptive
statistics concern only the selected materialization; overlapping versions are not
added together. Decimal values, date precision, statuses and operand lineage remain
in their stored form. Corrupt data produces a verification error, not fabricated data.

Research results are resolved through immutable relationship links and authoritative
ledgers/artifacts. Scope, Target family/horizon, direction, Research Spec and period
remain attached to each outcome. Preparing observations does not make a recipe tested;
a successful relationship does not universally validate the recipe. Partial links
remain immutable while maximal evidence branches are displayed. Independent reruns
under different Research Specs remain visible. No library metric is independently
editable. See [specifications 22](../../specs/22_signal_library_recipe_summaries.md)
and [23](../../specs/23_p1_p2_submit_execution.md).

## Target and PIT libraries

`GET /api/target-library` exposes stored Target definitions/materializations and FX
instrument construction metadata. Optional `instrument_id`, or paired
`horizon_amount`/`horizon_unit`, filter inspection. The UI presents **Price Return**,
**Total Return** and **Excess Return** categories, not individual Target definitions,
instruments or horizons. Only implemented/populated categories are enabled. Price
Return represents all 1/7/21/63/252 scheduled-weekday horizons.

`GET /api/target-library/<TARGET_ID>?materialization_id=<MATERIALIZATION_ID>` verifies
an exact stored output. Optional `training_cutoff`/`cutoff_precision` must be paired.
Optional `start_inclusive`, `end_exclusive` and `range_precision` select a range with
at least one bound and matching precision. Inspection preferences never substitute
for exact research snapshot/materialization selection. Retrospective readiness,
historical replay and live readiness remain separate decisions. See
[specification 18](../../specs/18_return_targets.md) and
[specification 19](../../specs/19_fx_sources_and_return_targets.md).

`GET /api/pit-library` retains verified ALFRED completion and FX snapshot discovery,
including date-level coverage, exact sources, readiness and limitations. The redundant
2018 pilot remains removed; full-history ALFRED and original FX source readers remain
in place. Unknown FX availability is not replaced with invented historical vintages.

## Serving and verification boundary

`api.server` serves an explicit UI asset/API allowlist, not the filesystem. JSON
responses use `Cache-Control: no-store`; browser policy restricts assets/connections
to the local application. Unexpected hosts/origins, traversal and unsupported query
shapes are rejected. GET library/resolution calls do not create scientific records;
only durable Submit work may prepare inputs or publish research results. Operational
status access may maintain lock files used to coordinate readers/writers.

The implementation is tested with synthetic temporary stores. From the platform root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_research_kernels test_scheduled_hac test_p2_evidence_policy test_research_runtime test_research_recovery test_research_http -v
```

These checks exercise code and isolated fixtures, including independent weekday HAC
oracles, required versus diagnostic evidence, exact source/Target bindings, phase
boundaries, recovery and read-only selection. They are not production experiments;
installation does not create a production request or run research.

## Catalog performance and preparation checkpoints (2026-10-10)

The main server's PIT and Target list routes use metadata projections. They validate
exact manifests/definitions and display saved counts, coverage and readiness with
`verification_state: catalog_metadata_only`; they do not read all observation bytes.
The strict PIT/Target readers remain unchanged and research still validates its exact
inputs. Signal summaries likewise defer observation and research-artifact reads.

Catalog GETs share a bounded, per-server single-flight cache (32 keys, five-second
TTL). Concurrent identical reads share work; exceptions are not cached. This cache
is not used by Submit, preparation, coverage resolution, exact observation retrieval,
or research-result verification. A catalog may lag newly published data by five
seconds. PIT loading starts only on navigation to that page.

The application uses `api.preparation_progress.ObservedResearchJobs` to observe the
existing native preparation callback. Native submission validation is preserved: a
thread-local adapter is visible only inside worker execution. The wrapper forwards
all original inputs, cancellation callbacks and return values. It does not alter
calculation code, the scientific implementation fingerprint, or stored results.

Operational preparation checkpoints are written atomically to
`storage/catalog/operations/preparation/<request_id>.json`. Public jobs include
`preparation_progress` only when request, attempt and frozen plan match. Checkpoints
contain phase, current instrument/date range, processed instrument and batch counts,
and update time. Batch completion is confirmed by the next callback or successful
phase return; an interrupted current batch is not counted. Processed batches can
include explicit unavailable intervals. Reused coverage is not counted as newly
prepared batches. External preparation with no batch callbacks reports phase start
and completion, without invented intermediate counts.

The card's last checkpoint is not a heartbeat or ETA. No within-batch percentage is
claimed. P1/P2 horizon outcomes remain separate. Progress files are operational
projections, not authoritative research evidence. Missing progress on older jobs
means no instrumentation was recorded, not stalled research.

A running Python service must be restarted to import these API changes. Do not
interrupt active work merely to activate presentation updates. Older frozen
submissions still obey their original implementation-compatibility checks.


## Verified input reuse (2026-10-10)

Research execution now owns a bounded, phase-separated verified-input cache.
Exact Feature/source references, policies, cutoff, plan and implementation remain
part of its scope. FX history is calculated once per instrument/phase and checked
by a separate numerical verification pass, then published in existing bounded
windows. Verified windows and shared prices/schedules are reused across horizons.
Target arithmetic and P1/P2 outcomes remain separate per horizon. Failed verification
is not cached; eviction causes full re-verification. Standalone Feature inspection
bypasses the execution cache. Contexts clear on phase transition and execution exit.
No saved scientific output is migrated or rewritten. New implementation identities
are preserved; old frozen requests are not silently upgraded.

See [implementation and verification report](../../outputs/verified_inputs_optimization_report.txt)
for exact tests, measured fixture timings, activation evidence and rollback boundary.
