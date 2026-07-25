-- Aruba New Central may return wirelessChannel as a textual value
-- (for example channel labels or values containing band information).
-- Preserve the source value instead of coercing it to an integer.

ALTER TABLE client_current
  MODIFY COLUMN wireless_channel VARCHAR(64) NULL;
