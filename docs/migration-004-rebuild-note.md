# Migration 004 rebuild note

The `sql/004_normalize_extended_collectors.sql` migration is intended to be safe both for a clean rebuild and for re-execution after a partial run.

It includes:

- idempotent column and index creation with `IF NOT EXISTS`;
- normalization of JSON string values equal to `"null"`;
- guarded numeric casts for nullable values;
- normalization of Aruba New Central ISO 8601 timestamps ending in `Z` before conversion to `DATETIME(6)`.

After merging, rebuild the stack from a clean database so all migrations run in order against the definitive credentials.
