# Batch submission

This is a private operator tool and authenticated API around the existing Submit
queue, not another research engine. The normal five-input experiment interface is
unchanged. No batch is populated or approved by installation, and completing
Momentum observation preparation does not launch this tool or any research.

## Workflow

1. Supply an explicit manifest of exact Feature and Scope IDs/versions. The tool
   expands their Cartesian product, preserves input order, and collapses repeated
   identical combinations with a visible duplicate count. One combination is one
   existing five-horizon submission; universes remain CS, instruments remain TS.
2. Create a preview. The existing independent worker resolves one combination per
   idle intake step, using the same registered research/input contracts. This can
   take time because stored input references are verified. No data preparation,
   label evaluation, P1, P2, or exposure record is produced by preview. Queued
   ordinary research has priority. The web/CLI can disconnect while preview runs.
3. Review the complete JSON report: new/reused/blocked counts, selected universe
   members, fixed direction, Research Spec identities/hashes, periods, workload
   bounds, and estimates. Preview is not a promise of sufficient statistical data.
4. Approve that exact preview SHA. Approval is immutable and idempotent. A preview
   with blocked rows cannot be approved unless `exclude_blocked` is explicitly true;
   every excluded row and its reason stays in the report. A corrected selection or
   changed policy/implementation needs a new batch ID and preview.
5. The existing cloud worker durably submits one item when the ordinary queue is
   idle. Each job then follows normal preparation → P1 → admitted P2 → persistence.
   All results remain attached to their own Scope, Target, direction and horizon.

The worker discovers persisted manifests/approvals on startup. Neither a browser,
CLI, laptop, AI session nor an additional service is needed after creation/approval.
Existing service supervision remains responsible for process restarts. Batch
errors become `needs_attention` with a persisted reason; `resume` retries intake
using the same IDs. It does not automatically resume failed/cancelled child jobs.

## Manifest

The IDs below are illustrative, not production selections. Up to 5,000 input
combinations and a 256 KiB HTTP/CLI manifest are supported. Direction is explicit;
there is no default direction or automatic sign selection.

```json
{
  "batch_id": "10000000-0000-4000-8000-000000000001",
  "name": "Reviewed Momentum program",
  "features": [{"id": "FEATURE_RECIPE_EXAMPLE", "version": "1.0.0"}],
  "scopes": [{"id": "SCOPE_EXAMPLE", "version": "1.0.0"}],
  "target_family": "price_return",
  "expected_direction": "POSITIVE",
  "duplicate_policy": "reuse_exact"
}
```

The optional `estimate_basis` must explain a measured or assumed calibration and
provide integer ranges for **one complete five-horizon experiment**, not per trial:

```json
{
  "description": "Illustrative assumption only; replace with representative measurements",
  "seconds_per_experiment": [60, 600],
  "bytes_per_experiment": [1000000, 10000000]
}
```

The report multiplies these ranges only by new submissions. Without calibration,
time and output storage estimates are **unknown**, not zero. Scheduled member/date
rows for P1 and possible P2 are upper bounds before warmup, missing data, endpoints
and admission. They are not independent sample counts. The report also gives free
bytes on the workspace filesystem; this is a snapshot, not a capacity reservation.
Estimates do not provision servers, workers, storage or cloud spending. P2 can run
for fewer than the five possible horizons. Existing queue time is not included.

## Operator CLI

Run the installed tool on the server as the existing research service account,
against the authoritative workspace. Do not copy the cloud store to a laptop or
start a second writer. No API tokens or browser session cookies are needed by this
server-local operator interface; OS/SSH access is the authorization boundary.

```sh
python tools/research_batch.py --root /srv/gambit/research_platform --output /private/report.json preview /private/manifest.json
python tools/research_batch.py --root /srv/gambit/research_platform --output /private/report.json status BATCH_UUID
python tools/research_batch.py --root /srv/gambit/research_platform approve BATCH_UUID --preview-sha256 REVIEWED_SHA
python tools/research_batch.py --root /srv/gambit/research_platform pause BATCH_UUID
python tools/research_batch.py --root /srv/gambit/research_platform resume BATCH_UUID
python tools/research_batch.py --root /srv/gambit/research_platform list
```

`pause` stops further preview/dispatch at the current item boundary. Already
accepted experiments continue; use their existing explicit cancel actions if
necessary. `resume` preserves the approval, frozen packets and experiment IDs;
failed child outcomes are still failures. Do not use `resume` as a fresh research
run. Approval retry after a lost response does not unpause a deliberately paused
batch. The CLI never starts a worker or runs a kernel.

## API

All routes use existing owner authentication, same-origin and CSRF protection.
The existing deployment activation gate also protects batch approval/resume.

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/batches` | Persist a manifest for preview only; retry the same ID |
| GET | `/api/batches` | List saved batches |
| GET | `/api/batches/<uuid>` | Complete preview, timestamps, progress and job links |
| POST | `/api/batches/<uuid>/approve` | `{"preview_sha256":"…","exclude_blocked":false}` |
| POST | `/api/batches/<uuid>/pause` | Empty object; pause further intake |
| POST | `/api/batches/<uuid>/resume` | Empty object; resume the same batch intake |

Child jobs are visible through the existing Trial Queue and Trial Ledger. The
Experiment page also has a read-only Research batches panel: saved completion
counts, per-experiment preparation/P1/P2 status, timestamps in the viewer's time
zone, and explicit stale-connection warnings. It refreshes every 15 seconds and
shows 25 items per page. Counts are derived from durable submissions rather than
a process-local counter. This panel never creates or approves batches. Configuration
and approval remain in the API/operator tool.

## Identity and duplicates

Each item gets a deterministic UUID derived from its batch UUID and normalized
intent. Crash after durable submission but before the dispatch receipt is recovered
through ordinary Submit with that same UUID. Batch dispatch and its duplicate check
hold the ordinary submission writer lock together. Two overlapping approved
batches therefore link exact existing work rather than racing to create it twice.
Normal individual Submit semantics are unchanged.

Exact equivalence includes the full frozen plan (Feature/source/Target references,
Scope membership, periods, policies, direction) and implementation. Only existing
Feature materialization lists and the derived plan ID are omitted from equivalence:
these windows are verified reusable caches, not new hypotheses. Worker verification
and normal trial artifact verification remain authoritative.

`reuse_exact` links an exact active or succeeded submission. Completion still means
execution, not scientific validation. `reject` blocks exact duplicates. Exact
failed/cancelled/blocked history requires explicit review, not an automatic rerun.
An unresolved matching queued submission is ambiguous and blocked during preview.
Different snapshots, policies, horizons, memberships or implementations are not
silently treated as equivalent. Previewed reuse that becomes unavailable never
turns into an unreviewed new submission. A new duplicate appearing after preview
can reduce new work, but cannot increase the approved count.

## Persistence and deployment

Operational evidence lives under
`storage/catalog/operations/research_batches/<uuid>/`: immutable manifest, frozen
packets, per-row previews, exact approval and dispatch receipts; atomic status
includes UTC timestamps. Existing submissions/events/scientific records retain
their original formats and locations. Backup must continue covering the entire
catalog/operations tree, as in the current backup policy.

Use the normal branch/tests/PR/controlled-release workflow. This change alters the
research implementation fingerprint, so deploy only after existing research and
Momentum preparation finish or are safely paused under a separately reviewed plan.
Before later code updates, pause unfinished batches and account for their remaining
items. A changed implementation halts old preview/dispatch; never rewrite frozen
packets to force continuation. Existing queued jobs also retain their usual
implementation-change protection. No deployment or production batch approval is
part of development testing.

## Owner launch controls

The Research batches panel on the Experiment page lists operator-prepared batches.
Select a batch, inspect the selections and resource estimates, click **Review
batch**, then **Launch reviewed batch**. This approves the exact saved preview
through the existing submission API. Incomplete or blocked previews cannot be
launched from this panel; prepare a corrected batch first. A changed preview
requires another review. Unknown time and storage estimates remain labeled as
uncalibrated.

**Pause batch** stops future intake, not already queued or running experiments.
**Resume approved batch** continues the approved intake; **Resume checks** only
continues an unapproved preview. Closing the browser does not stop cloud work.
The panel never launches on page load, never retries a launch automatically,
and refreshes saved status after a request with an uncertain outcome. It uses
owner authentication and the existing CSRF-protected same-origin API.

Preparation stays within each submitted experiment's existing preparation → P1
→ conditional P2 pathway. These controls do not restart the full historical-input
sweep, provision capacity, or alter research identities and scientific policies.
