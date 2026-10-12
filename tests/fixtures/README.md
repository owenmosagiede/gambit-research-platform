# Synthetic structural fixtures

All `SYNTHETIC_*` IDs, UUIDs, repeated-character digests, roles and reason codes in
this directory are test-only examples. They do not exist in a production registry.
No file supplies or certifies a real Feature, Target, Scope, Research Spec,
snapshot, implementation, membership history, randomness policy or readiness check.
No Target return basis, horizon, method, threshold or portfolio rule is invented.

- `synthetic_experiment.json`: five-input intent shape.
- `synthetic_submission.json`: operational request envelope.
- `synthetic_resolved_experiment.json`: claimed immutable-binding shape, deliberately
  synthetic. Passing structural validation means only that its shape is valid.

The tests mutate in-memory copies to check rejected inputs. No executable fixture
is run, no legacy registry is modified, and no scientific job is launched.
