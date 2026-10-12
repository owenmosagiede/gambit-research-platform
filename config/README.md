# External store references

`storage.example.json` is a portable example, not a loader or a readiness assertion.
`storage.local.json` records this machine's observed paths and is excluded from version control.
It contains no credentials. The bounded ALFRED pilot reads its explicitly selected legacy
files; the general configured-store resolver remains unimplemented.

Store keys identify locations for discovery; they are not scientific data identities. A future
resolver must bind exact immutable manifests/content, versions, availability policies and
valid readiness evidence. Moving a physical path must not change experiment identity.
All legacy accesses remain read only. The ALFRED pilot preserves one small original response
in the new platform alongside fresh bounded official API responses; no bulk migration occurred.

The mapped directories exist. Their contents, completeness, ongoing writer activity, and
fitness for a requested calculation have not been certified. See the storage inventory.
