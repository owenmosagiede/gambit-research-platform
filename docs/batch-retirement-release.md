# Research batch retirement release review

## Behavior

Batch creation, preview, approval, pause/resume and automatic dispatch are retired.
The old API returns `410 BATCH_RETIRED` with `recorded: false`. The old operator
command exits before opening a workspace. The worker processes explicit ordinary
experiment submissions only, including recovery of interrupted intake journals.
An approved or partly prepared historical batch cannot schedule another request.

The ordinary experiment API, exact-request retries, duplicate experiment checks,
five-horizon research, worker recovery, Trial Ledger and Signal Library remain.
Numerical preparation chunks are unrelated to this retired scheduling feature.
No source prices, Features, Targets, seven currency universes, 43 single-pair
Scopes, trials or result records are removed or rewritten.

## Historical evidence and deployment compatibility

`data.legacy_batch_evidence` contains read-only checksum, row and frozen-preview
readers. The frozen preview representation retains the exact previous hash format,
so old approvals remain auditable by the migration readers. It performs no input
resolution, preparation, scheduling or state repair.

`runtime.research_batches.checked` remains as an import-compatible reader for the
already-installed release controller. The retired class cannot be constructed and
has no preview, approval or dispatch methods. The former CLI and browser asset are
inert compatibility files. There are no code-file deletions requiring a separate
file-retirement migration.

The updated release-controller source independently rejects unfinished,
incomplete, corrupt, redirected and orphaned batch evidence. Normal code rollout
does **not** replace `/opt/gambit/release-control`; its existing checksum/completed
state checks continue through the retained import. Installing the stricter
controller is a separate explicit operator change, not an implied deployment step.
Both versions independently reject an active ordinary experiment queue.

## Exact implementation review

Removing operational Python code changes the recorded implementation fingerprint.
The before/after file hashes and the previously recorded cloud Python build are
pinned in `tests/fixtures/batch_retirement_review.json`. The old code fingerprint
is `bd1557ec216b03866c54dc93a5c0a9b4ae273a690471caa801ecf915ef45bdb7`.
The reviewed source parent is commit
`65146dc8ca1cc83aee6e7515d30cf4aa6318bbd4` (the interface/Signal Library PR).
The cloud Python build recorded in prior read-only inventory is
`3.14.8 (main, Oct 11 2026, 23:02:34) [GCC 13.3.0]`.

The only fingerprinted source changes are the removal of batch scheduling and
private batch overrides in `runtime/research_jobs.py`, the inert batch service,
the two historical migration-reader imports, and the new pure historical reader.
All numerical kernels, Feature/Target construction, data contracts, research
policies and scientific-key construction retain their original bytes. The worker
also recovers an ordinary intake journal when no submission/job file exists yet;
this restores its original request and does not resolve a replacement experiment.

The registry contains one exact forward equivalence pair for that code and Python
build. It permits linking an already completed, verified experiment to a new
request receipt. It does not change its IDs, recorded implementation, results or
exposure history. It does not authorize resuming old frozen execution or treat
other Python builds/code changes as equivalent. No blanket fingerprint waiver or
mutable server setting is introduced.

Evidence:

- `test_batch_retirement_release`: exact hashes and environment, existing five
  outcomes reused without further kernel calls or immutable envelope edits,
  no old-execution resume, unknown/reverse pairs remain unreviewed.
- `test_research_batches`, `test_experiment_identity`, `test_research_runtime`,
  `test_research_recovery`: no dispatch from old manifests; ordinary submissions,
  duplicates, provenance, results and interrupted intake recover normally.
- `test_release_workflow`: frozen preview hash compatibility and read-only release
  gates, including unfinished or malformed legacy evidence.
- `test_batch_http`, `test_production_access`, `test_batch_ui`: retirement without
  writes, authentication/CSRF/origin protection, no served executable batch asset.
- Legacy migration/preflight tests retain mixed-batch references and published
  time-series outcomes using synthetic archived evidence, not a live scheduler.

## Release sequence

1. Merge the interface/Signal Library PR before this dependent retirement PR.
   Require the isolated release checks and source packaging checks to pass.
2. Before production apply, verify the current batch inventory, authoritative
   ordinary queue and complete implementation/environment digests. Match the live
   pair to the exact registry entry. The previously captured local inventory is
   review evidence, not a substitute for this final live check.
3. Require an idle ordinary queue and no unfinished/unverifiable legacy batches.
   If unexpected historical work exists, review its disposition explicitly; do
   not mark it completed, delete it, resume it on new code or bypass the gate.
4. Reconcile actual history, take the normal current backup, prepare the official
   source artifact and apply only the reviewed code-deployment plan. Normal file
   deployment must carry the compatibility registry together with its code.
5. Check web/worker health, the retired API response, the existing completed
   result references, seven CS universes and 43 TS Scopes. Do not launch a
   production experiment as a smoke test. New research remains a separate request.

This code retirement requires no production storage reset or currency numerical
migration. The repository release suite uses disposable synthetic data. No merge,
controller replacement, production deployment or historical-record change is
performed by implementing this PR.
