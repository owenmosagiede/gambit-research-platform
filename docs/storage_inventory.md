# Storage inventory and proposed retention

Measured **2026-10-08 UTC; completed by 03:23:56Z**. Exact per-command start/finish times were not recorded. The separate link audit ran **03:21:52.669600–03:23:56.214622Z**. All legacy locations remained read only.

## Measurement and coverage

- macOS `du -k -P` recursively measured allocated usage without following symlinks. Reported KiB were multiplied by 1024 for CSV bytes; GiB below means 2^30 bytes. This is not apparent file length, unique physical APFS extents, or recoverable space.
- Scope: all Data top-level directories and immediate Data/derived groups, provider groups, targeted large subgroups, FX major groups and presentations. The new research_platform is excluded. Small root-level Data scripts/reports/local configuration are included in its aggregate but not individually classified. Credentials were not read.
- Metadata coverage is broader than semantic coverage. Targeted documents, a small manifest and relevant code were inspected. Datasets and notebooks were not opened for this inventory; historical payloads were not hashed; no research jobs ran.
- All completed measurement/link scans reported no traversal errors. External stores referenced from manifests were not followed or measured. No unavailable external location was guessed to have zero size.
- **Nested rows overlap. Do not sum the CSV.** Each Data descendant is already included in Data. No combined workspace total is asserted.
- A metadata-only `find -P` scan found **zero symlinks** and **117 regular-file path entries with link count greater than one** in Data, FX and presentations. This is not 117 unique inodes. Examples include prepared broad-CS `eligible-feature.parquet`. Equivalence classes and links outside these trees were not resolved. `du` deduplicates within each invocation; attribution between groups may vary in independent passes, and unlinking one path need not free blocks. APFS clones and snapshots were not inspected.
- Measurements are not an atomic snapshot. **All writer activity is UNKNOWN.** Concurrent changes were not ruled out; no group is verified inactive. WAL, SHM and lock sidecars in successor P1 storage were observed, but their presence alone does not establish a live writer. Stable sizes or no observed process cannot prove inactivity.

## Largest groups

Rows overlap and cannot be added together.

| Workspace-relative path | Allocated GiB | Proposed treatment |
| --- | ---: | --- |
| `Data` | 75.36007 | UNKNOWN |
| `Data/derived` | 60.97548 | UNKNOWN |
| `Data/derived/features` | 20.02434 | UNKNOWN |
| `Data/derived/fx-successor-process1` | 11.85532 | KEEP_SCIENTIFIC_MEMORY |
| `Data/derived/fx-successor-input-preparation` | 11.63951 | UNKNOWN |
| `Data/raw` | 8.16538 | KEEP_DATA |
| `Data/production` | 4.84021 | KEEP_DATA |
| `Data/derived/research_trials` | 3.46928 | KEEP_SCIENTIFIC_MEMORY |
| `Data/derived/signal-validation` | 3.39333 | KEEP_SCIENTIFIC_MEMORY |
| `Data/derived/process3-successor` | 2.88197 | KEEP_SCIENTIFIC_MEMORY |
| `Data/derived/fx-successor-process2` | 2.52804 | KEEP_SCIENTIFIC_MEMORY |
| `Data/catalog` | 1.34519 | KEEP_DATA |
| `FX` | 0.05854 | UNKNOWN |
| `presentations` | 0.00061 | KEEP_SCIENTIFIC_MEMORY |

## Large-group drilldown

| Workspace-relative path | Allocated GiB |
| --- | ---: |
| `Data/derived/features/v1.4.0/runs` | 10.69279 |
| `Data/derived/features/v1.1.0/runs` | 8.90992 |
| `Data/derived/fx-successor-process1/v1.0.0/FXP1OP_5C13E07FDA2B4255B3881768/bundles` | 11.08506 |
| `Data/derived/fx-successor-input-preparation/v1.0.0/FXIPRUN_D65B46A954BA6877D9F5298B/shared-broad-cs` | 9.67063 |
| `Data/raw/v1/cftc` | 4.62515 |
| `Data/raw/v1/sec` | 2.77094 |
| `Data/derived/research_trials/v1.0.0/artifacts` | 2.94141 |
| `Data/derived/research_trials/v1.0.0/ledger` | 0.15573 |
| `Data/derived/research_trials/v2.0.0/artifacts` | 0.37214 |
| `Data/derived/signal-validation/v1.0.0/artifacts` | 3.24072 |

## Proposed treatments

These are proposals, not deletion authorization.

- **KEEP_DATA:** raw provider objects, production observations, PIT/release reconstructions, source metadata and essential availability/vintage/mapping evidence. Derived observations do not replace original sources.
- **KEEP_SCIENTIFIC_MEMORY:** definitions, Research Specs, trial/validation ledgers, rejected hypotheses, failures, admission decisions, lineage, readiness evidence, protected historical baselines, prior research-period exposure, compact summaries, and code/environment references needed to interpret retained evidence. Conservative retention does not certify the science.
- **ARCHIVE_CANDIDATE:** FX/archive is described as superseded recovery/audit material. Coldness, dependency closure and restoration needs remain unverified. Detailed old trial artifacts may warrant a later archive assessment but are conservatively retained as scientific memory here.
- **REGENERABLE_CANDIDATE:** conventional Python/test caches and selected prepared-input subgroups warrant investigation only. Input bundles also carry manifests and lineage and have known consumers. No complete bundle directory is established as disposable; indispensable evidence must first be separated and retained.
- **UNKNOWN:** mixed aggregate content and insufficiently audited calculated payload groups. Unknown dependencies are a retention block, not permission to delete.

**Guaranteed reclaimable storage is not established.** Candidate bytes are not promised savings, and no candidate-byte sum is reported. Nothing was deleted, moved, compacted, transferred or migrated.

## Verified observations and historical source claims

1. Data/README.md identifies raw/v1, production/provider observations, catalogs and pilots. Its provider descriptions distinguish native vintages from retrieval-time snapshots. Storage locations were observed; fresh PIT safety was not certified.
2. Data/docs/global-trial-ledger.md describes immutable JSON ledger records as durable compact memory, SQLite as a query index, and empirical failures as retained evidence. This does not imply that arbitrary operation SQLite databases are disposable.
3. Data/docs/compact-trial-artifacts.md retains historical v1 and requires exact feature/target/membership inputs and engine references for v2 replay. Old compaction benchmarks were not used as present measured usage or guaranteed savings. v2 presence alone proves neither duplicate content nor safe replacement.
4. Data/docs/derived-feature-store.md binds logical definitions, immutable run manifests and PIT lineage. Therefore derived/features cannot be classified wholesale as cache.
5. The small successor P1 operation_manifest.json under FXP1OP_5C13E07FDA2B4255B3881768 points to input-preparation run FXIPRUN_D65B46A954BA6877D9F5298B. Data/src/process3_universal/canonical_input.py also consumes that preparation manifest and prepared outputs. These are concrete dependencies on the large preparation group.
6. That preparation run's input_rebuild_completion_report.md states NOT_READY_FOR_DISCOVERY_AND_VALIDATION_REPLAY and 24 blocked dependencies. These are historical report claims; newer successor operations coexist. Chronology and present readiness were not reconciled here. Preserve blockers and do not infer certification from a directory name.
7. FX/README_FX_PIPELINE.md maps portfolio, diagnostics, isolated Ridge experiments, admission evidence and archived notebooks. Prior conclusions and inspected periods remain scientific memory during the rebuild.

## Unresolved decisions and later cleanup prerequisites

Retention periods, backup/archive destination and durability, separation of evidence from payloads, database recovery ownership, current writers, exact replay environments, dependency-graph completeness and old-versus-successor relationships remain unresolved.

A later cleanup task must identify precise files and owners; establish readers/writers and safe quiescence or snapshot procedures; resolve incoming references, raw/PIT lineage and immutable dependencies; preserve failures, decisions and research-period exposure; prove exact regeneration or duplication through bounded replay with recorded acceptance criteria; retain required code/environment and provider terms; verify archive integrity and restoration; estimate unique reclaimable extents accounting for hard links, clones and snapshots; and obtain explicit approval of the concrete retention action before deletion or transfer. No processes or schedules were changed.

The CSV records each path, apparent purpose, measured allocation, method/time precision, proposed treatment, supporting evidence, unresolved dependencies, writer state and overlap limits.
