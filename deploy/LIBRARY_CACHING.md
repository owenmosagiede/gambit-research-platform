# Signal and Feature catalog caching

The Signal Library summary, selected recipe's stored outputs, and Feature dropdown
use `CatalogCache.get_verified`. Signal summaries include only exact definitions
with verified completed research. Stored outputs are loaded separately when a
reader opens that section; the summary never scans materialization folders.
Historical mappings and scientific records are unchanged. This is an in-memory UI projection cache;
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
overlapping requests for the same catalog share one refresh. A waiting request
returns unavailable after one second rather than occupying a web thread
indefinitely. The refresh owner continues and can populate the cache for retries.

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

The queue and Trial Ledger use a separate read-only event view. Each request reads
execution events once and verifies their chains, envelopes and intake references.
It never takes `research-writer`, publishes receipts, repairs projections or wakes
the worker. Incomplete or corrupt records are reported as issues; normal command
and worker recovery remain responsible for repair. Missing display labels never
hide a verified job. Loading and failed refreshes are distinct from empty results
in the interface, and failed refreshes retain clearly marked last-known records.

Benchmark cold, repeated and post-five-second reads separately. Compare canonical
response hashes, entry counts and issues. Warm validation has more work than the
previous unchecked five-second cache hit, but avoids the recurring full rebuild
once that old short cache expires. Cloud timings must be measured on the cloud;
local development measurements are not production promises.

Deploy through `RELEASE_WORKFLOW.md` only after the research queue is idle. No
service restart is necessary during local development or testing. A normal release
changes implementation identity for future work and does not rewrite old records.
