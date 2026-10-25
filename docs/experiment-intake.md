# Canonical experiment intake

Authenticated experiment requests call `ResearchJobs.submit`. The UI is a read-only
contract reference; the retired batch workflow cannot submit work. Intake resolves
metadata only and freezes the exact plan before recording a new experiment.
Preparation and P1/P2 remain the existing worker's responsibility.

## Identity and release compatibility

The scientific key includes the normalized intent, exact Research Spec and frozen
plan: membership, source snapshots, definitions, target selections, phase periods,
policies and Feature application. It excludes only `plan_id` (a derived hash) and
`feature_materializations` (the reusable output inventory). It does not exclude
source or Target snapshots, input versions, direction or phase boundaries.

The complete implementation and Python environment remain in every envelope.
Different implementations are **unreviewed by default**. An exact pair of complete
implementation digests may be classified `equivalent` or `different` in
`src/runtime/research_compatibility.json`, with review evidence and test references.
That file travels through the source review/release workflow; it is not a server
switch. It is deliberately outside the Python-source fingerprint to avoid a hash
that refers to itself. No compatibility is inferred from filenames, version names,
or omitted numerical modules. Intake journals preserve the review registry used.

`equivalent` permits linking an existing experiment. It does **not** authorize
resuming its frozen execution on different code. Resume still requires the exact
original implementation. `different` permits a new execution for the same input
metadata when a reviewed scientific implementation change warrants one. Unknown
release differences require reconciliation rather than a silent rerun.

Cross-release approvals are limited to the exact implementation/environment pairs
listed in that registry. Historical results must be reconciled and the live pair
matched to its review before deployment. See `batch-retirement-release.md` for the
batch retirement review. Unknown runtime differences remain unreviewed.

## Atomic publication and recovery

Under `research-writer`, intake checks the index and writes an immutable request
journal reserving the canonical experiment. It then publishes the canonical
submission, its first event, a request receipt, and the rebuildable identity index.
The journal precedes all other writes. Crashes before the first job event can be
finished by the worker or a retry, without resolving new inputs or creating a new
experiment. A missing receipt is rebuilt from its journal. A request UUID cannot
be reused with a different intent.

- Queued/running: return the existing canonical job.
- Completed, including scientific rejection/unresolved scientific outcomes: verify
  saved result evidence and return the existing results.
- Failed/cancelled/blocked: return that job with recovery availability; never resume
  automatically or allocate a replacement.
- Corrupt evidence, unresolved historical inputs, multiple matching historical
  authorities, or unreviewed release compatibility: require reconciliation.

The index is a checksummed projection with submission/journal directory generation
checks. It avoids reopening every submission on each intake. Matching execution
chains and result artifacts are still verified; this is not a bypass of evidence
integrity. Manual edits of immutable authority are unsupported. Rebuild after any
controlled history repair; never repair by changing saved scientific records.

## Response contract

The response still contains `job`. Its `request_id` is the canonical experiment
UUID and may differ from the submitted UUID. `job.submission_receipt` contains:

- `request_id`: submitted UUID;
- `canonical_request_id`: canonical job UUID;
- `scientific_identity`: exact scientific key;
- `journal_sha256`: authoritative journal checksum.

`intake_action` is `created`, `view_existing`, `view_results` or `recover_existing`.
GET by the original submitted UUID resolves the same canonical job, including after
browser reload. Cancel/Resume actions use the canonical job UUID. A different job
ID without a matching receipt is not an accepted submission response.

## History reconciliation and release gate

Run `tools/reconcile_experiments.py --root WORKSPACE` on a protected copy or the
existing cloud workspace. It verifies submissions, journals, event/plan references and linked result
artifacts, reports unresolved bindings, duplicate science groups, orphan job
projections and pending publications. It does not select a winning historical
trial or launch research. `--rebuild-index` writes only the rebuildable lookup.
Historical duplicates and validation-exposure records are retained.

Before controlled deployment:

1. Run passing isolated release checks and review the PR.
2. Reconcile the actual live history; resolve any ambiguity explicitly.
3. Review exact deployed/new implementation compatibility using the live numerical
   environment. Add only justified, tested compatibility attestations.
4. Wait for idle research and use the normal verified artifact/backup/release plan.
5. Verify reuse and receipt GET in production without launching a test experiment.

No migration rewrites existing trials, results, source data or exposure history.
Rollback to an older intake implementation requires draining intake and reviewing
new request journals first; the old implementation does not understand aliases.
