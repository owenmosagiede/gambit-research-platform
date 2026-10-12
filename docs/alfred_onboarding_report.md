# ALFRED CES0500000003 — completed bounded onboarding

> Subsequent update: the redundant 2018 raw/PIT sample package was physically removed at the user’s request. The full-history dataset remains intact. See [the removal report](alfred_sample_removal.md). The results below describe the earlier task.

Series: **Average Hourly Earnings of All Employees, Total Private**. Native frequency:
monthly; units: dollars per hour; seasonally adjusted. Original publisher: BLS; API/archive:
FRED/ALFRED, Federal Reserve Bank of St. Louis.

## Result

The pilot is onboarded into the new research_platform. The historical assessment is **ready
for ALFRED vintage-date reconstruction** over reference months January–December 2018. The
separate **live_api_daily_pull assessment is ready** under the user's explicit definition:
an official API exists and can be queried daily. This is a point-in-time technical assessment,
not a permanent service guarantee or a certificate for a particular trading deadline.

There are 12 reference months and **77 vintage values** in the selected window. Every one
of the 77 archived values agrees with the current official response. Two independent historical
API queries verify January 2018's value: **26.74** at vintage **2018-02-02**, then **26.71** at
vintage **2018-03-09**. Replay keeps both states and excludes the later revision before its
vintage date. The separate latest-values probe returned September 2026 at 37.81; it is only
five observations, explicitly recorded as a partial history rather than a complete backfill.

Exact historical intraday release times and historic receipt times are **not certified**.
The legacy convention of vintage date plus one day at 12 UTC is preserved as source evidence
but is not promoted into a measured publication timestamp. The registered source view is
ALFRED's native date-based information state, not a feature-store history with verified
intraday `available_at` values. No `live_generation` or trading readiness is claimed.

## Actual acquisition and storage

The completion manifest is [the immutable onboarding run](../storage/catalog/onboarding/runs/ONBOARDING_124af5ecbbd0cc30b35459763b2a254b2b3bdba2c1887770e8673539aec5b67e.json). It is the entry
point for the exact record and payload paths, identities, checksums and assessments.

- Exact original legacy raw response preserved unchanged: **55,836 bytes**, SHA-256
  `691e9ffebc518fec7bcf645c9bf69e6db571cf53f549829bbe6e89bdc6a86e7b`. Its 246 reference-period
  rows cover more than the certified 2018 sample; copying this one small original response
  preserves evidence, and does not certify its entire history.
- Fresh bounded official requests: series metadata, latest five observations, all native
  vintages for the 2018 reference window, and two one-observation historical as-of requests.
  **All five returned HTTP 200.** Their actual capture times and relevant response headers
  are saved; the final bundle was captured on **2026-10-09 UTC** (October 8 locally).
- Three preliminary connectivity requests also succeeded before the final five-request
  bundle. Eight official requests were made in total; preliminary scratch remains temporary
  and only the consistent final five-response bundle is published.
- The original archive's HTTP status and retrieval-start time were unknown. Its recorded
  retrieval end, 2026-09-07T17:45:52Z, was retained separately from the new import time.
- **28 typed records**, **12 immutable payloads totaling 114,736 bytes**, 12 operational
  locator records and one completion manifest. Provider/dataset/view/policy definitions are
  under definitions; receipts, raw snapshots, lineage, code/environment and assessments are
  under storage/catalog; exact bytes are under storage/payloads/sha256.
- Saved requests exclude the API key. The existing credential was read privately from the
  legacy configuration and used only with the official API. No credential was copied into
  the new platform or included in saved errors/URLs.

Both old and new raw bytes remain intact. No legacy file was modified or deleted; five selected
source/provenance files were checksum-verified again after publication. No bulk migration,
scientific trial, transformation engine, feature/target materialization or scheduled job ran.

## Files added

- [Bounded ingestion and storage helpers](../src/data/alfred_onboarding.py).
- [Pilot command](../tools/onboard_alfred.py).
- [Additive four-record onboarding schema](../specs/schemas/onboarding.schema.json).
- [Ingestion/PIT boundary tests](../tests/test_alfred_onboarding.py) and
  [schema tests](../tests/test_onboarding_schema.py).
- [Onboarding contract and operating instructions](../specs/13_provider_onboarding.md).
- One real dataset definition, one source-view definition, one provider contract and seven
  technical policies. These policies approve only the specified bounded technical checks;
  they do not approve research-period use, forecasts or trading.

The immutable completion manifest enumerates every generated record/payload path. The existing
experiment and platform schemas and their identity rules were not changed. The new onboarding
schema has its own 0.1.0 profile; this does not revise the existing experiment 0.1.0 contract.

## Verification actually performed

From the platform root, with Python 3.14.0 and the existing temporary jsonschema 4.25.1 tool:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 -m unittest discover -s tests/specifications -v
```

**42 tests passed in 0.061s + 24 tests passed in 0.151s = 66 passed, no skips.**
New cases cover revision lookahead, withdrawn values, incomplete pages, malformed data,
source corruption, immutable overwrite rejection, damaged stored payloads, wrong payload
formats, credential-safe failure receipts and capability boundaries.

The real-data package was first exercised in isolated temporary staging, then published in
research_platform. A separate final read of the actual published package validated all
**28 record schemas**, resolved **105 exact immutable references**, and verified all 12
payload hashes and byte counts. The selected legacy files were unchanged; an exact-value
credential scan of every published record, payload and completion manifest passed.

## Limits and follow-on work

Certification covers the selected reference window and documented vintage-date semantics.
ALFRED release/vintage dates do not prove exact historic delivery into this computer, and
archive changes can occur later. Future pulls must preserve changes and rerun affected checks.
Failed pulls retain sanitized attempt receipts and cannot produce a completed ready package.

Daily polling is possible; this monthly series will not produce a new economic observation
every day. No daily automation was requested or created. A scheduler, monitoring, expiry/
revocation service, backup deployment and general catalog query service remain unimplemented.
Source-vintage replay does not authorize research use of previously exposed periods.
Legacy rights classifications differ between older catalog and production metadata; both
remain source evidence, and this technical audit makes no new redistribution assertion.

A later bounded task can materialize the approved date-based PIT source view, with an explicit
availability policy for its intended use, before applying transformations or building features.

## Official references checked

FRED v1 supports both FRED and ALFRED, with authenticated series and observation requests:
[API overview](https://fred.stlouisfed.org/docs/api/fred/),
[observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html),
[API keys](https://fred.stlouisfed.org/docs/api/api_key.html).

Real-time boundaries are date-based and inclusive; historical as-of requests use the same
start/end vintage date. Vintage-date lists cover new or changed observations:
[real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html),
[vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html).

API limits permit this low-volume daily retrieval pattern; the live assessment additionally
includes actual successful authenticated pulls. Release dates and archival availability
have limitations that prevent an exact intraday claim:
[API errors/limits](https://fred.stlouisfed.org/docs/api/fred/errors.html),
[ALFRED help](https://alfred.stlouisfed.org/help).
