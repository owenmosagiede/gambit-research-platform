# Fresh currency Feature preparation

This change keeps the current member's fully verified price history in the
execution-local cache while preparing its bounded Feature windows. It changes
only eviction preference. Every hit still checks the complete dependency witness
and propagates it into enclosing verifiers. Caller values remain private copies.
A source too large to retain is verified normally. Temporary payloads and series
may bypass retention rather than displacing that member's price entry. The total
retained-cache limit stays 128 MiB; compact lookups retain their 64 MiB sublimit.
The bound concerns cached objects, not total process memory.

After fresh publication starts, Feature lookup warming waits until all member
publications finish. Later lineage-pack publication therefore cannot immediately
invalidate an earlier warmed lookup. The lineage catalog/index witnesses remain
unchanged, including appended conflicting-ID detection. Preparation using only
already-published outputs can still warm each member as it goes.

There is no cross-request or cross-phase reuse, persistent cache, source admission
shortcut, skipped verification, changed kernel, altered recipe, new dependency,
or concurrency change. Completed research, partial trials, original submissions,
queue order and the running production process are not modified by this PR.

## Reproduce offline

Use the exact locked dependencies and Node.js in a source-only checkout:

```
python -B tools/run_release_checks.py
python -B tools/benchmark_preparation.py --production-shape --repeats 2 --output /tmp/fresh-preparation-proof
```

The benchmark builds an isolated seed from the deployed commit
`992ced766dd76b7a311a8bddf4dfaa05d9077679`, with 18 currencies, 12,185 synthetic
source weekdays, 449 P1 weekdays and two bounded publication windows per member.
It compares separate baseline/candidate processes in alternating order. Features
are fresh; Target outputs and frozen scientific inputs are shared exactly. The
smaller default fixture is a regression control, not a production forecast.

Timing covers fresh P1 preparation, all five horizon reads and P1 evaluation.
Independent post-run verification is outside timing. Provider/source admission
is an explicitly synthetic boundary, so its timings do not estimate the cost
of production's full source traversal. Report full-verifier call counts as well
as measured times. Nested measurements must not be added together.

The comparison proves producer code leaves and every transitive materialization
and lineage reference before translating only those references. It compares all
verified observations, operand-content digests, metadata, prepared membership,
all five aligned inputs and complete P1 decisions exactly. It rejects unknown
references, changed Target values, missingness, altered decisions or excess
retained memory. P2 admission/isolation, all configured causal recipes, corruption,
partial trial reuse and recovery remain covered by the release regression suite.

## Deployment gate and preservation

This PR is code and offline evidence only; it neither authorizes nor performs a
production cutover. Its real executor fingerprint changes. The existing approval
for the PR19–21 executor does not authorize this candidate.

Before any later deployment, prepare a successor compatibility proposal using the
bounded research-metadata review procedure in `FROZEN_PROGRAM_PERFORMANCE.md`.
Drain the single worker at an experiment boundary only under that later approval;
preserve exact original envelopes, queue order, results, trial references,
scientific definitions and program manifest. Do not restart a full storage scan.

The program now contains trials from both the original and the currently approved
executor. The current compatibility implementation represents one from/to pair;
`committed_trial` assumes historical pins belong to the proposal's `from`
implementation. A successor must explicitly reconcile the existing approval and
both historical executor generations (including partial/orphan trial intents).
Do not relabel earlier trials, reuse the old approval for a different fingerprint,
omit intermediate-executor trials, or bypass that gate. Successor approval and
reader support must be validated before calling this change deployable for the
already-running frozen program. They are not silently broadened by this cache PR.

After an authorized cutover, verify exact artifact/revision, bounded preservation,
HTTP pages and the next existing queue item before resuming one worker. If any new
research was written, recovery must preserve it; never restore an older research
snapshot over newer results.
