# Workspace inspection

Inspection recorded: 2026-10-08T03:22:25.004910+00:00

## Verified observations

- The requested workspace exists at `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model`.
  Initial top-level listing contained `Data/`, `FX/`, and two PDFs. No `research_platform/`
  existed; the new root was created for this task.
- Explicit checks found no `AGENTS.md` in `/`, `/Users`, the user home, Desktop or workspace
  root. A hidden-file-aware filename search within the workspace found none (exit 1, no matches).
  The current Codex task directory was empty except for `work/` and `outputs/`; neither is
  used for this package. No applicable repository instruction file was found.
- Both requested source files were first successfully read in Downloads. During inspection,
  those paths ceased to exist and the same basenames appeared at the workspace root. The
  PDFs appeared under `presentations/`. No task command moved those files. This external
  change prevents describing the workspace as quiescent. The preserved copies and their
  provenance are recorded under `specs/references/`.
- Version control resolves to `/Users/owenmckinleyosagiede`, not an independent repository
  inside Multi-Asset Model. The initial status reported `master` with no commits and many
  unrelated untracked home entries; it also warned of inaccessible unrelated home locations.
  Further status checks were limited to the requested workspace. No commit, staging,
  branch operation, reset, push or repository initialization was performed.
- `Data/.env.local` exists. Its contents were not opened or copied. Directory/name inspection
  is not permission to inspect credentials.
- Python 3.14.0 is available. The default interpreter does not have `jsonschema`; no package
  installation was performed. Contract checks use the standard library.

## Legacy evidence inspected (not inherited instructions)

The following documents were read as evidence about the old system, with further selected
sources listed in the specification index and storage inventory:

- `Data/docs/global-trial-ledger.md`: compact JSON records preserve trial results and failures;
  SQLite serves as an index. These are documented semantics, not a fresh audit of every record.
- `Data/docs/compact-trial-artifacts.md`: legacy and compact artifacts coexist; replay depends
  on exact manifests, upstream stores and implementation references. Reported historical
  compression benchmarks are not present-day reclaimable space measurements.
- `Data/docs/verified-pit-coverage.md`: the legacy registry binds coverage evidence to dataset
  and source-view fingerprints and policy. We verified the directory paths, not certificate
  validity or data contents. A legacy statement that a snapshot was active is not new approval.
- `Data/docs/research-specification-registry.md`: reusable evaluation definitions and pinned
  fingerprints exist. Legacy admission rules reside in a separate policy; the new Research
  Spec must explicitly include or pin its admission methodology.
- `FX/README_FX_PIPELINE.md`: describes retained notebooks, a historical selected strategy,
  experiments and an archive. Its instruction to run notebooks is outside this task and was
  not followed. `FX/Instructions/` contains financial research source documents; no legacy
  notebook or research pipeline was run.

## Proposed foundation decisions

Use a separate application root, retain external stores in place, keep authoritative definitions
separate from catalogs, and freeze strict contract normalization/version rules. These are
implemented foundation design proposals, not approved scientific estimator specifications.
The specification index distinguishes source requirements from still-unresolved science.

## Inspection limits

No full data read, historical payload hashing, scientific rerun, process termination, credential
change or schedule inspection was performed. Process absence was not used to infer writer
absence. No registry entries or retained scientific results have been re-certified. Storage
measurements are observations over an interval, not a filesystem snapshot. See the inventory
for links, hard links, coverage, overlap and retention prerequisites.
