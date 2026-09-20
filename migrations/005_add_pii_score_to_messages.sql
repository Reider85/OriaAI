-- ADR-014, Block D-5: PII score metadata in messages table.
-- Apply once the messages table exists (persistence layer lands in Phase 1 MVP).
--
--   * pii_score:     PII ratio of the message in [0,1] computed by PIIDetector at write time.
--   * pii_entities:  JSONB array of {type, start, end} only — NEVER the PII text itself.
--   * index:         partial index for the analytics query below.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS pii_score FLOAT DEFAULT NULL;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS pii_entities JSONB DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_pii_score
    ON messages (pii_score)
    WHERE pii_score IS NOT NULL;

-- Analytics query for observability docs (README § Phase 1 KMS).
-- SELECT
--   DATE(created_at) AS day,
--   AVG(pii_score) AS avg_pii_score,
--   COUNT(*) FILTER (WHERE pii_score > 0.1) AS high_pii_messages
-- FROM messages
-- WHERE created_at > NOW() - INTERVAL '30 days'
-- GROUP BY day ORDER BY day;
--