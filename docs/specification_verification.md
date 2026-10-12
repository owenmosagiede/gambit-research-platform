# Specification completion and verification

Recorded: 2026-10-08T23:56:36.924754+00:00

Application root: `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`.
This report describes the specification revision after the historical foundation package;
[foundation verification](foundation_verification.md) remains unchanged as its historical record.

## Completed scope and decision status

The actual files now specify raw → PIT → optional interactions → transformations → Feature/Target
stores, reuse of inspected legacy capabilities, exact storage locations and closed record shapes,
parent Signal identity, individually tested relationships, authoritative trial/evidence ownership,
and initial submission/runtime/UI boundaries. Numbered specifications 00–12 are review drafts,
not claims that unresolved scientific formulas or production services are implemented.

User decisions recorded explicitly: retain verified legacy P1/P2 methods as versioned policies
after compatibility checks; P4 constructs sleeves and P5 allocates shared capital; one signal
represents the predictor dataset/source-view and ordered interaction/transformation recipe,
reusable across tested assets and horizons. Verified facts, proposed engineering choices and
remaining scientific questions are distinguished in the [decision register](specification_decisions.md).

The proposed `FEATURE_<hash>` and `SIGNAL_<samehash>` refer to one authoritative predictor
recipe. Target, evaluated asset/scope, horizon and direction distinguish relationships;
Research Spec, period, data and implementation bindings distinguish trials. Scope-dependent
values bind the actual universe before calculation. Library entries link all outcomes to
immutable authoritative results and do not contain independently editable metric copies.
P1 admission and P2 validation have distinct records and vocabularies. A failed P2 precheck
preserves its frozen context without creating a fictitious P2 trial or metric.

## Created and updated files

New files (17, including five empty directory placeholders):

```text
config/storage_layout.example.json
definitions/datasets/.gitkeep
definitions/interactions/.gitkeep
definitions/policies/.gitkeep
definitions/source_views/.gitkeep
definitions/transformations/.gitkeep
docs/legacy_capability_map.csv
docs/legacy_capability_map.md
docs/specification_decisions.md
docs/specification_verification.md
specs/12_data_pipeline_and_storage.md
specs/schemas/README.md
specs/schemas/platform.schema.json
tests/fixtures/specification_v0_2/README.md
tests/fixtures/specification_v0_2/catalog_records.json
tests/fixtures/specification_v0_2/observation_rows.json
tests/specifications/test_specification_schemas.py
```

Updated: root README; definitions and storage purpose notes; specification index and numbered
00–11 specifications; P5 placeholder purpose note. The existing experiment implementation,
its exported interface, v0.1 schema and 22 foundation tests remain byte-identical to the
pre-revision baseline. No production definition was registered.

## Actual validation results

All commands below were run from the application root with bytecode output disabled.
Existing interpreter: Python **3.14.0**.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_contracts.py' -v
```

**22 tests passed, exit code 0, 0.005 seconds.** Those source/test files did not change afterward;
their four recorded SHA-256 baselines were rechecked successfully at final inspection.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 -m unittest discover -s tests/specifications -v
```

**24 tests passed, exit code 0, 0.150 seconds** in the final run: 11 full JSON Schema engine
checks and 13 fixture semantic checks. **46 passing tests combined**, with no skips in these
reported runs. Timings are local observations, not performance benchmarks.

The schema engine is `jsonschema==4.25.1`, installed only under
`/private/tmp/research_platform_schema_check_v02`. No global/project dependency environment
was changed. The original foundation remains dependency-free. The new schema test group is
run explicitly as above; it reports the 11 engine tests skipped when that optional temporary
dependency is absent, rather than claiming conformance. A standard-library calendar checker
validates UTC dates without optional third-party date-format extras.

Checks cover **20 closed catalog record types**, **52 synthetic catalog examples** and two
observation rows; the original v0.1 schema/examples also pass the engine checks. Cases cover
unchanged parent identity across evaluations, recipe changes, ordered graphs, exact reference
hashes, pre-computation materialization identity, separate byte/semantic hashes, authoritative
library links, distinct P1/P2 decisions, precheck failure, and empty materializations.

Additional final checks:

- All 105 capability-map evidence references match their recorded SHA-256 values; only the
  small referenced registries/code/documents were read/hashed, not historical payload stores.
- All 11 platform JSON files parse. Referenced schema entry names and portable storage
  templates match the published specifications.
- Both preserved source reference hashes match the foundation source manifest. No source
  document was rewritten to present it as an approved scientific specification.
- The final local Markdown-link audit resolves all links, including this report.
- No symlinks, production definition JSON, runtime storage payloads or databases are present
  under the new platform. Storage still contains only its purpose note and placeholders.

These are specification/contract checks. They do **not** establish numerical parity, PIT
correctness, readiness, production persistence/durability, research approval or scientific
performance. Synthetic examples deliberately have no real data payloads or approved policies.
The small test oracles do not implement production identity, stores or scientific engines.

## Storage and legacy reuse findings

The [reuse map](legacy_capability_map.md) and CSV contain **105 entries**: 68 base univariate
operators, 16 price-technical operators, six release-coherent operators, one binary interaction,
one parameter-grid extension, and 13 store/contract components. Names overlapping between
catalogs remain namespaced; this is not 92 proven-distinct mathematical formulas or a claim
that every legacy script has been audited. Retain/adapt/replace decisions are proposals with
explicit compatibility gates, not completed ports.

The historical storage inventory remains the measured baseline: `Data` allocated
**80,917,262,336 bytes (75.36007 GiB)**, 173 inventory groups, current writers **UNKNOWN**.
Nested groups overlap and cannot be summed. The earlier audit found zero symlinks and 117
regular-file path entries with link count greater than one, not 117 unique inodes. No unique
APFS extent or guaranteed reclaimable-byte estimate exists. This task did not rerun a bulk
storage scan or certify those stores.

Definitions are proposed under `definitions/`; Feature/Target manifests, compact trial,
admission and validation ledgers, artifacts and relationship/library records under
`storage/catalog/`; large observations/evidence under `storage/payloads/sha256/`. Detailed exact
templates are in [specification 12](../specs/12_data_pipeline_and_storage.md) and
[portable config](../config/storage_layout.example.json). Query indexes are rebuildable;
operational state is not automatically disposable. All old data remains in place, read only.
No migration, compaction, archive transfer, deletion or cleanup has been scheduled.

## Remaining decisions and next bounded task

The [decision register](specification_decisions.md) identifies each gate and the implementation
it blocks: pilot Feature/Target/Scope/Research Spec and target clock/basis; legacy numerical
compatibility; exposed-period and ex-ante direction evidence; readiness/writer/backup policies;
P3/P4 units, uncertainty definitions and estimator timelines; P4/P5 capital-feedback and
aggregate-feasibility mathematics. Readiness/lifecycle/operational event schemas and
alternative physical-representation wrappers remain explicitly deferred. No missing formula,
scientific threshold or production policy is supplied by synthetic fixture values.

**Next bounded task:** review this package, then implement the plain white five-input
submission page and minimum shared durable intake/status backend, with idempotency and truthful
states. It must not claim scientific execution without a verified executor. A later explicit
pilot can adapt and parity-check only its needed legacy data/store/P1/P2 components. P3/P4/P5
engines, full research replay and bulk migration remain outside that bounded task.

No further user input was needed to complete this review draft. The two requested ownership
and reuse decisions are recorded; other questions remain implementation gates. Work stops at
this specification package.

## Execution boundary notes

Only the new-platform deliverables were retained. Temporary schema dependency/generation work
used the system temporary area. One agent briefly created its own generator scratch under the
projectless task's `work/` directory, then removed it and relocated the scratch to temporary
storage; no deliverable remains there and no legacy file was affected. Finder `.DS_Store`
metadata observed under the platform is excluded from this deliverable manifest and was not
removed. The inherited Git root is the user's home directory; no staging, commit, push,
branch or repository-configuration change was made.
