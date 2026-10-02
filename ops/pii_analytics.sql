-- PII Analytics Query for messages table (ADR-014 D-5)
-- 
-- Run this to get daily PII metrics from the messages table.
-- Shows average PII score and count of high-PII messages per day.
--
-- Usage:
-- psql -d llm_client -f pii_analytics.sql

SELECT
  DATE(created_at) AS day,
  AVG(pii_score) AS avg_pii_score,
  COUNT(*) FILTER (WHERE pii_score > 0.1) AS high_pii_messages,
  COUNT(*) AS total_messages
FROM messages
WHERE created_at > NOW() - INTERVAL '30 days'
  AND role = 'user'  -- Only user messages have PII scores
GROUP BY day
ORDER BY day DESC;

-- Optional: Show top PII messages for investigation
-- SELECT
--   id,
--   session_id,
--   created_at,
--   pii_score,
--   pii_entities,
--   content
-- FROM messages
-- WHERE created_at > NOW() - INTERVAL '7 days'
--   AND pii_score > 0.5
-- ORDER BY pii_score DESC
-- LIMIT 10;