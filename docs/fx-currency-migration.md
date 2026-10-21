# Currency-reference FX migration

This migration replaces the 18 legacy cross-sectional (CS) universe definitions
and deletes their historical research records and results. The user's explicit
request supersedes the usual retention rule for those 18 Scopes only. It does
not authorize removing the 43 canonical singleton time-series (TS) Scopes, their
research, or shared price, Feature, Target and source dependencies.

## Scientific contract

The seven new version 1 Scopes are `FX_CCY_VS_USD`, `FX_CCY_VS_EUR`,
`FX_CCY_VS_GBP`, `FX_CCY_VS_JPY`, `FX_CCY_VS_CHF`, `FX_CCY_VS_CAD` and
`FX_CCY_VS_AUD`. Each has 18 members, ordered by base currency code, from the
frozen supported inventory: AUD, CAD, CHF, CNH, CZK, EUR, GBP, HKD, HUF, ILS,
JPY, MXN, NOK, NZD, PLN, SEK, SGD, USD and ZAR. The reference currency is
excluded from its own Scope. No membership changes depend on missing data,
coverage, readiness or date. CNH is not substituted with CNY.

`fx_currency_price.1.0.0` constructs reference-currency units per base currency.
For currency C against reference R, `P(C/R) = U(C) / U(R)`, with U(C) the
USD-per-C price and U(USD)=1. The exact 18 source snapshots are supplied in the
migration request; direct prices retain source values, inverses use reciprocals,
and crosses use those fixed USD legs. There is no alternate routing, fill or
silent member omission. These are gross spot exposures: the quote/funding
reference does not imply that interest, carry, funding costs or transaction costs
have been included.

All Features run their complete recipe on the oriented price. Targets use that
same price and the approved simple-return horizons 1, 7, 21, 63 and 252 scheduled
weekdays. The 180 approved operator configurations produce 180 new reusable
recipe identities and 22,680 source-bound Features. The currency evaluation
policy has a new ID at version 2.0.0 (the transformation registry's executable
policy version), and a new CS-only application contract. Legacy Feature and TS
identities remain unchanged. Unknown availability, retrospective date alignment,
complete-date missing-data rules, ex-ante direction, periods and P1/P2 admission
remain governed by the existing approved scientific policy.

The immutable currency Research Spec has its own ID/version and pins the full
126-source/630-Target inventory. Each frozen plan pins the relevant Scope's
membership, price catalog, quote basis and exact Feature/Target inputs. It does
not inherit a mutable active-release pointer as its scientific identity.

## Code and consumers

- `transformations/fx_currency.py` defines the inventory and orientation, reusing
  the checked arithmetic in `transformations/fx.py` without changing TS recipes.
- `fx_currency_catalog.py` publishes separate registration kinds and immutable
  price catalogs. `targets/fx.py` replays both price profiles from their exact raw
  operands, including normalized legs, metadata and row summaries.
- `fx_currency_scopes.py` publishes and independently reconstructs all seven
  fixed memberships. `scopes.py` hides staged definitions and permanently blocks
  the legacy registrar after activation. Shared legacy policy/evidence code
  remains because the unchanged TS memberships require it.
- `fx_currency_features.py`, `reusable_features.py`, `feature_applications.py`,
  `feature_resolution.py` and `inputs.py` enforce matched Feature/Scope profiles.
  Currency recipes cannot run as canonical TS, and canonical recipes cannot be
  submitted against the new currency Scopes. UI labels expose the common quote.
- `fx_currency_release.py` stages definitions and Targets and verifies the release.
  `fx_currency_migration.py` plans exact deletion ownership and applies a reviewed
  hash-bound manifest. `experiment_identity.py` freezes the correct Research Spec.
- `deploy/release_server.py` treats unfinished batches, including paused and
  previewed batches, as release blockers in addition to queued/running requests.
  Changed implementations are never declared resume-compatible automatically.

## Offline release sequence

Normal code deployment does not install registry changes. Do not run this tool
against the historical Desktop store or copy its observations to production.
Run with the reviewed candidate source, locked dependencies and the sole cloud
store as `--root`. Deploy the compatible code first through the normal controlled
release, while the old registry is still active. Then stop web intake, batch
dispatch and workers for staging and application. Hold the normal backup/release
operational controls; do not restart old code after activating the new registry.

1. Merge and validate the prerequisite shared experiment-intake change and this
   change. Obtain the exact release artifact and checks receipt. Keep the cloud
   Python/runtime unchanged. Complete or explicitly cancel active requests on
   their original implementation first. Reconcile every unfinished retained TS
   batch; a paused batch still contains frozen old implementation inputs. Unfinished
   batches are a release blocker, including old-only batches awaiting explicit
   disposal; do not run unwanted experiments merely to clear the gate. Install
   the reviewed `deploy/release_server.py` in the separately managed release-control
   directory as an explicit operator change. Apply the normal controlled code
   release while services are healthy, then stop them for the registry migration.
   This code supports the old registry during that intermediate window.
2. Create an explicit request JSON outside the platform catalog with
   `source_snapshots` (all 18 provider symbols mapped to exact content references),
   `return_policy` (the existing approved five-horizon policy), and `request_text`
   documenting authorization to install currency Scopes and delete the 18 old CS
   definitions/history. No latest-source inference is supported.
3. With services stopped, stage the release using the reviewed candidate tool:

   ```sh
   python tools/migrate_fx_currency.py --root /cloud/platform stage \
     --request /review/currency-request.json --output /review/currency-release.json
   ```

   Staging installs a complete, independently verified release but does not make
   the seven Scopes selectable. It creates no trials or scientific approvals.
   Rerunning the same request is idempotent; conflicting immutable inputs block.
4. Produce the deletion manifest outside the platform tree:

   ```sh
   python tools/migrate_fx_currency.py --root /cloud/platform plan \
     --release /review/currency-release.json --output /review/currency-delete.json
   ```

   Review exact paths, hashes, blockers and all 86 protected TS definition and
   membership files. The v2 manifest also lists explicit operational batch
   replacements under `replace`. Completed mixed batches can be reconciled only
   when their original checksummed manifest, approved preview, every row and
   frozen packet, dispatch receipts and successful authoritative jobs agree.
   Only original legacy-CS/canonical-TS batches qualify; unfinished, excluded,
   corrupt, unknown-file and new-currency mixed batches remain blockers.

   Reconciliation replaces only the operational batch manifest with a distinctly
   versioned `research_batch_retained_ts_v1` read-only view. It keeps the original
   batch ID and original TS row indices, removes retired CS selections, and pins
   the original manifest/approval hashes and every retained per-item file hash.
   TS submissions, trials, results, frozen packets, rows and dispatch receipts
   remain byte-identical. The original approval stays unchanged as historical
   evidence; it never authorizes the replacement view to dispatch or resume work.
   The UI exposes retained completed history without launch/resume controls.
   No copy of the old mixed manifest or discarded CS research is archived.

   Unsupported mixed batches, unsupported historical schemas,
   unverifiable queue histories, symlinks and retained references to deleted
   records block application. Resolve these explicitly; never widen the delete
   list or delete a whole catalog directory to bypass a blocker.
5. Apply exactly the reviewed manifest:

   ```sh
   python tools/migrate_fx_currency.py --root /cloud/platform apply \
     --manifest /review/currency-delete.json --expected-sha256 MANIFEST_SHA256
   ```

   The tool rechecks ownership and inventory under writer/executor locks,
   publishes a maintenance marker, removes old-only history and unshared owned
   payloads, verifies TS bytes and activates the currency release. The mutable
   intake lookup is discarded and rebuilt from retained authority. No archive
   copies of the discarded definitions or results are created. The migration
   receipt contains hashes, paths and the retained-TS operational replacements;
   it contains no discarded CS records. Interrupted replacement/deletion resumes
   only from the identical reviewed v2 manifest, accepting each replacement's
   exact before or after bytes and rejecting any other retained-data change.
6. With the matching code already installed, verify 50
   active Scopes (43 TS, seven CS), 18 frozen members each, no legacy CS selections,
   correct application compatibility, and retained TS references. Restart services
   only with matching registry and code. Selection checks must not launch research.

If interrupted, keep services stopped and rerun `apply` with the identical
manifest/digest. Changed retained bytes or deletion candidates block resumption.
The maintenance marker prevents intake, resume, recovery and batch dispatch until completion. The deletion is
irreversible through this tool. Code rollback alone cannot undo this registry
migration; any disaster recovery uses the existing operational backup process.

## Validation and limits

The release suite includes pure orientation, persisted source replay, complete
release installation, frozen input resolution, TS preservation, shared artifact
retention, mixed-batch rejection, unknown-schema rejection, symlink rejection,
changed-inventory rejection and forged-manifest rejection. Existing Scope,
Feature, Target, intake, recovery, batch and UI tests remain release checks.

Local validation uses synthetic temporary stores. Production deletion counts and
any historical-schema/mixed-batch blockers can only be established by a plan on
the authoritative cloud store. This PR does not execute a production purge or
certify old queued jobs under the new implementation.
