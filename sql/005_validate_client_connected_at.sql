-- Validation helper for the client connectedAt normalization.
-- This migration intentionally performs no schema change.
-- It documents and validates the timestamp format expected from Aruba New Central.

SELECT
  COUNT(*) AS invalid_connected_at_count
FROM client_current
WHERE NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedAt')), 'null'), '') IS NOT NULL
  AND STR_TO_DATE(
    REPLACE(
      REPLACE(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedAt')), 'T', ' '),
      'Z',
      ''
    ),
    '%Y-%m-%d %H:%i:%s.%f'
  ) IS NULL;
