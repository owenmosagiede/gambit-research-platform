# Signal and Feature catalog caching

The Signal Library summary and Feature dropdown use `CatalogCache.get_verified`.
The response shape, registered-recipe inclusion rules, historical mappings and
scientific records are unchanged. This is an in-memory UI projection cache;
submission, preparation, output retrieval and research never use its responses
as verified scientific inputs.

## Verification and refresh

A cold read runs the existing strict readers, including reference, schema,
registration, mapping and policy-evidence checks. Within that request, reusable
recipe verification runs once and output summaries share one FeatureStore.
The per-request objects are released after the read.

Each successful catalog records every instrumented file read and directory query.
A later request checks file identity, size, modification time, change time, resolved
path and directory-query membership before using the cached response. This detects
new outputs, research links, registry additions, edits, deletion, atomic replacement
and symlink changes without requiring worker notifications. Each web process
checks the shared store independently. Checks run outside the cache's global lock;
overlapping requests for the same catalog share one refresh.

The cache is bounded to 32 verified entries per process. Even unchanged entries
receive a full read after 300 seconds. Partial catalogs with issues and exceptions
are not cached. A detected change during construction retries once; continued
changes fail through the existing unavailable response instead of returning an
old successful view. Responses are copied before returning to callers.

This is ordinary filesystem change detection, not a content hash on every warm
request or a transactional snapshot of the whole store. Cold/invalidated/maximum-age
reads still run the authoritative checks. Publication can advance the store after
any completed read; the next request checks for those changes.

The catalog continues to verify metadata only. Opening a stored output or research
result uses its existing authoritative observation/artifact verifier. Catalog
presence never certifies observation integrity or research validity. Those detail
readers and their existing cache rules are unchanged.

## Validation

`tools/run_release_checks.py` includes dependency invalidation, single-flight,
response isolation, bounded retry/eviction, registry reuse and library HTTP suites.
Synthetic integration tests publish a materialization from a separate process into
a store served by two API instances and verify both warm catalogs refresh. A bounded
worker fixture publishes five research relationships and verifies their appearance
without changing existing output summaries. No production experiments are tests.

Benchmark cold, repeated and post-five-second reads separately. Compare canonical
response hashes, entry counts and issues. Warm validation has more work than the
previous unchecked five-second cache hit, but avoids the recurring full rebuild
once that old short cache expires. Cloud timings must be measured on the cloud;
local development measurements are not production promises.

Deploy through `RELEASE_WORKFLOW.md` only after the research queue is idle. No
service restart is necessary during local development or testing. A normal release
changes implementation identity for future work and does not rewrite old records.
