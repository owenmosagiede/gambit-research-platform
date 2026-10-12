# Gambit development and release rules

This is the project-only source repository. Cloud storage is the sole production
authority. The historical Desktop checkout and all legacy locations are read-only
references. Do not start a second production writer against their old stores.

Use `codex/` branches, isolated temporary fixtures, and pull requests for changes.
Run `python tools/run_release_checks.py` with the locked dependencies and Node.js.
Never run production experiments as a test without the user's instruction.

Do not commit observations, trial records, authentication databases, credentials,
private keys, local mappings, virtual environments, or backup/export bundles.
The six policy-support files under `tests/fixtures/registry_support` contain
approved transformation specifications only, verified by their manifest.

Research policies, definitions, identities, lineage, and historical references
must remain immutable. Scientific changes require appropriate versioning.
Normal code deployment does not install or change registry definitions, policies,
runtime dependencies, service definitions, or server credentials. Follow
`deploy/RELEASE_WORKFLOW.md`; do not overwrite cloud storage or force old queued
jobs through a new implementation. A Git push is not a production deployment.
