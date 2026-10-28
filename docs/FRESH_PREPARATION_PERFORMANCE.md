# Fresh currency Feature preparation

This change keeps the current member's fully verified price history in the
execution-local cache while preparing its bounded Feature windows. It changes
only eviction preference. Every hit still checks the complete dependency witness
and propagates it into enclosing verifiers. Fully verified snapshot/price values
are retained as lossless canonical JSON bytes, reducing the retained object graph
and repeated deep copies. Every caller receives private decoded containers;
decimal strings, large integers, nulls and all provenance fields remain exact.
The small proof of full source replay is retained separately from the large price
buffer. It binds the complete canonical snapshot and prices with SHA256 and the
full verifier's file witnesses. A buffer eviction therefore permits a checksum
checked reload of the pinned price payload, followed by exact comparison to that
proof, without reconstructing unchanged provider sources and normalized legs.
Witnesses are checked before the reload, propagated to enclosing entries, and
checked again before publication. Changed dependencies trigger full verification;
changed reloaded values fail. The proof can itself be evicted and never survives
a phase, executor, root, request, restart or standalone inspection boundary.

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
python -B tools/benchmark_source_preparation.py --long-history --repeats 2 --output /tmp/full-preparation-proof
```

The full-source benchmark builds an isolated seed from the deployed commit
`992ced766dd76b7a311a8bddf4dfaa05d9077679`, with 18 currencies against CHF, long
synthetic source histories, 449 P1 weekdays and two bounded publication windows per member.
It compares separate baseline/candidate processes in alternating order. Features
are fresh; Target outputs and frozen scientific inputs are shared exactly. The
smaller default fixture is a regression control, not a production forecast.

The provider adapter, source-closure verification, normalized legs, cross/inverse
price construction, Feature publication and independent replay are real. Only
registry discovery for the isolated Scope/recipe is supplied by the fixture;
no price verifier is mocked. The 18 synthetic provider files remain fixed for all
runs. No production files or credentials are read.

Timing covers fresh P1 preparation, all five horizon reads and P1 evaluation.
Independent post-run verification is outside timing. Provider/source admission
and Target publication happen once while building the shared seed, just as they
already exist before a queued experiment. Full source traversal during preparation
is included in measured time. Report full-verifier call counts during preparation
separately from loading. Nested measurements must not be added together.

The performance gate requires two reversed-order runs with at least 10% lower
preparation time in each, fewer full source replays, lower combined time and exact
scientific equality. A faster loading stage cannot satisfy a slower preparation
stage. These local measurements establish this mechanism, not a production ETA.

The earlier `benchmark_preparation.py` mode retains its explicitly mocked source
boundary as a smaller regression control. Its timings alone cannot establish
that the production preparation bottleneck has improved.

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
