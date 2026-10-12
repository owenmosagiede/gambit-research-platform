# Synthetic v0.2 specification examples

These fixtures are fictional structural examples, not imported legacy data,
production definitions, scientifically approved policies, readiness evidence,
working payload files or real experiment results. No fixture is registered by
reading it or by running the tests. All policy definitions are `draft`.

- `catalog_records.json`: an array of 52 records individually validated against
  `specs/schemas/platform.schema.json`. One source-derived predictor/Signal is
  tested against `ASSET_A` at one observation and `ASSET_B` at five observations.
  The parent recipe remains identical; Target/Scope/Relationship/Trial identities
  differ. Both synthetic P1 admission records (`admitted` and `rejected`) remain in
  the same library's `admission_results`. One later synthetic P2 precheck fails and
  is linked through `validation_results`, with no P2 evaluation trial or metrics.
- `observation_rows.json`: two fictional Feature rows showing a valid decimal
  observation and explicitly missing data.

The displayed numbers `0.11`, `-0.05`, `1.25`, horizons, lookback and dates are only
test values. They prescribe no return calculation, IC definition, sample period,
admission threshold, timeline, asset universe or scientific decision. Both trials
are P1 examples; an illustrative `admitted` decision cannot establish P3 eligibility.
The schema has a separate P2 validation record with `validated`, `failed` and
`unresolved` decisions. A negative test prevents interchange of the P1 and P2
vocabularies; no fixture claims to have completed P2 validation. The Research Spec
declares a separate, nonoverlapping P2 planning period. The failed precheck preserves
that planned context without claiming the absent payloads or draft policies are ready.

Feature/Signal, Relationship, Trial and Materialization IDs follow the documented domain/hash
projections, checked by tests. Other full-length record IDs and referenced payload
hashes are synthetic placeholders; the fixtures contain no corresponding raw,
Parquet, implementation, specification-document or exposure payload files. They
must not pass production readiness. Exact references to records included in this
array have verified semantic hashes; references named `SYNTHETIC_CONTRACT_*` and
other absent artifacts intentionally remain unresolved synthetic references.

The schemas accept shapes, not truth. A production resolver must additionally
implement every semantic check in the schema README and approved scientific
specifications. The test helpers are local fixture oracles, not a production
identity, storage, compatibility or scientific-validation library.
