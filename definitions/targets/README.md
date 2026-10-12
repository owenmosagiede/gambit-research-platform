# Canonical return Target definitions

Executable Target definitions follow schema 0.4.0 and [specification 18](../../specs/18_return_targets.md).
The production service creates content-addressed `TARGET_<64hex>/1.0.0.json` records here.
A definition binds exact source economics, return construction/representation/comparison,
anchor and interval policies, horizon, outcome vintage and availability. Registration alone
is not a materialization or historical research certificate.

Actual source values, finite anchors and label observations belong to immutable materialization
payloads. Definitions never contain large arrays or a copy of upstream raw/PIT records. Targets
are independent of Features/Signals and are not registered in the Signal library. The old
platform 0.2 Target schema remains historical and cannot silently replace this executable contract.

The production registry currently has no eligible market-source Target. The isolated acceptance
proof is stored separately, not inserted here. See the [library](../../docs/target_library.md).
