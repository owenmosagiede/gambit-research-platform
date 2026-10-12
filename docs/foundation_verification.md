# Foundation completion and verification

Recorded: 2026-10-08T03:32:06.902917+00:00

Actual root: `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`

## Completed scope

Created the requested folder skeleton, root README and purpose notes; storage inventory
in Markdown and CSV; specification index and numbered 00–11 documents; exact source copies
with hashes; proposed experiment contract, machine schema, pure Python validators and
synthetic examples/tests. All files below were newly created for this foundation. No
pre-existing substantive platform work was overwritten.

Only the common experiment identity and submission contracts are developed. Remaining
specifications are labeled stubs. No scientific engine, registry resolver, data migration,
readiness service, submission API/store, scheduler, UI, portfolio optimizer or order system
was implemented. No legacy data was deleted, moved, compacted or rewritten by this task.
No dependencies were installed and no commit or push was made.

## Actual checks and results

- Existing Python: **3.14.0**.
- Contract command, run from the new root:

  ```sh
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
  ```

  **22 tests passed, exit code 0.** Root verification reported 0.007 seconds; the final
  contract check after documentation/test-label clarification reported 0.004 seconds.
  These timings describe this small local test run, not a performance benchmark.
- Required folder skeleton: **28 specified directories exist**.
- Ignore rules: **13 exclusion probes and 9 trackable-file probes passed**, including
  local store configuration, credentials, payloads, archives, fixtures and `.gitkeep`.
- Source preservation: **both supplied text references byte-equal to their workspace
  originals**, with byte counts and SHA-256 matching `specs/references/source_manifest.json`.
  Only these small supplied text references were hashed for preservation verification.
- All **5** paths in ignored local store configuration exist and are marked read-only.
  This does not verify their data or readiness.
- All new JSON documents parsed. JSON Schema checks covered local references, closed
  object shapes and regex syntax. **Full Draft 2020-12 schema-engine conformance was not
  run**; `jsonschema` is not installed in this interpreter. Python validation additionally
  enforces reference equality and unique dependency roles.
- Storage CSV: **173 unique paths**, nonnegative measured bytes, required evidence and
  dependency notes, all five proposed treatments, and writer state UNKNOWN throughout.
- All local Markdown links resolved at inspection; new root contains no symlinks.
- Independent review of the contract/specification boundaries found no unresolved
  implementation defect within this foundation's structural scope.

Contract tests exercise required/unexpected fields, direction, pinned versions, strict JSON
parsing, deterministic normalization and frozen hash vectors, request-content separation,
claimed dependency changes, optional/inapplicable states, and locator exclusion. They do
not verify scientific truth, registry contents, readiness, persistent idempotency, actual
attempts or replay. Synthetic references/digests are not production registrations.

## Storage findings and limits

`Data` measured **80,917,262,336 allocated bytes (75.36007 GiB)**. Included within that
aggregate are features (20.02434 GiB), successor P1 (11.85532 GiB), successor prepared inputs
(11.63951 GiB), raw (8.16538 GiB), and production (4.84021 GiB). These nested rows must not
be added to the parent. The inventory details other groups and large descendants.

Raw/PIT/source evidence is proposed KEEP_DATA; definitions, ledgers, failures, lineage,
validation evidence and code/environment references are KEEP_SCIENTIFIC_MEMORY. Mixed
or unaudited groups remain UNKNOWN. Archive/cache candidates require verification and
separate approval. Known downstream consumers reference prepared inputs.

No guaranteed recoverable-space estimate is made. Measurements report allocation through
`du`, not unique APFS extents. Surveyed trees had zero symlinks and 117 regular-file path
entries with link count greater than one, not 117 unique inodes. Links outside these trees,
APFS clones/snapshots, external stores and full dependency closure remain unaudited. Writer
activity is UNKNOWN everywhere and the measurements are not an atomic snapshot.

## Contract decisions implemented as proposals

Exactly four pinned definition references plus POSITIVE/NEGATIVE direction define scientific
intent. Operational request ID is separate. Strict normalization precedes full SHA-256
identities. A resolved identity binds exact definition, data, policy, implementation,
applicable scope/readiness and randomness dependencies. Moving storage or retrying the same
frozen calculation does not change scientific identity; new actual attempts need new
operational identities. Conflicting content under one definition ID/version must block future
resolution, even though the structural helper can hash claimed bindings.

Same request ID and content must return the existing submission; conflicting reuse must
error. This is a documented future persistence requirement, not a working service.
Execution outcomes and scientific outcomes remain separate. RequiredTrade does not authorize
orders. Scope-dependent calculations must bind Scope first.

## Open decisions and next bounded task

Resolve exact calibration return basis and horizon units; forecast error variance versus
uncertainty in estimated expected returns; permitted estimation timelines for calibration,
decay, covariance and weights; and P4/P5 ownership of shared capital and aggregate limits.
Complete production definition, snapshot, certificate, trial-expansion, status, persistence,
recovery and legacy-exposure specifications. Preserve the supplied P3/P4 design; do not fill
these gaps with invented estimators or legacy defaults.

**Next bounded task:** complete and review the remaining specifications, approve the shared
submission contract and its minimum truthful persistence/status behavior, then implement the
plain white five-input submission page against that contract. No further implementation is
part of this foundation.

## Deviations and inspection precision

The originally requested Downloads references moved externally into the workspace during
inspection; both were found and preserved from their actual workspace paths. No source is
missing. The inventory records its UTC measurement date and completed-by time because exact
per-command start/finish times were not captured; the separate link-audit interval is recorded.
Full JSON Schema engine validation was unavailable without adding a dependency and was not
claimed. The inherited Git root is the user's home directory; no staging, history, branch or repository-configuration changes were made.

## Complete created-file manifest

64 files, including 24 empty `.gitkeep` placeholders. `config/storage.local.json`
is intentionally excluded from version control. Storage/archive contain only purpose notes and placeholders.
Paths below are relative to the actual root above.

```text
.gitignore
README.md
archive/README.md
archive/legacy/.gitkeep
config/.gitkeep
config/README.md
config/storage.example.json
config/storage.local.json
definitions/README.md
definitions/features/.gitkeep
definitions/mandates/.gitkeep
definitions/research_specs/.gitkeep
definitions/scopes/.gitkeep
definitions/targets/.gitkeep
definitions/venue_profiles/.gitkeep
docs/foundation_verification.md
docs/storage_inventory.csv
docs/storage_inventory.md
docs/workspace_inspection.md
specs/00_system_boundaries.md
specs/01_canonical_objects.md
specs/02_data_and_readiness.md
specs/03_features_targets_scopes.md
specs/04_experiment_submission.md
specs/05_p1_discovery.md
specs/06_p2_validation.md
specs/07_p3_forecasting.md
specs/08_p4_portfolios.md
specs/09_p5_and_execution_boundary.md
specs/10_runtime_recovery_storage.md
specs/11_ui_and_observability.md
specs/README.md
specs/references/README.md
specs/references/codex_foundation_prompt.txt
specs/references/p3_p4_design_reference.txt
specs/references/source_manifest.json
specs/schemas/contracts.schema.json
src/README.md
src/api/.gitkeep
src/contracts/__init__.py
src/contracts/experiment.py
src/data/.gitkeep
src/execution/.gitkeep
src/research/p1_discovery/.gitkeep
src/research/p2_validation/.gitkeep
src/research/p3_forecasting/.gitkeep
src/research/p4_portfolios/.gitkeep
src/research/p5_allocation/.gitkeep
src/research/p5_allocation/README.md
src/runtime/.gitkeep
storage/README.md
storage/cache/.gitkeep
storage/catalog/.gitkeep
storage/logs/.gitkeep
storage/payloads/.gitkeep
storage/temporary/.gitkeep
tests/fixtures/README.md
tests/fixtures/synthetic_experiment.json
tests/fixtures/synthetic_resolved_experiment.json
tests/fixtures/synthetic_submission.json
tests/test_contracts.py
tools/.gitkeep
ui/.gitkeep
ui/README.md
```
