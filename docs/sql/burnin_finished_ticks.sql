-- Finished pipeline ticks only (burn-in metrics; exclude in-flight).
SELECT
  id,
  tick_id,
  status,
  json_extract(detail_json, '$.terminal_state') AS terminal_state,
  json_extract(detail_json, '$.terminal_reason') AS terminal_reason,
  json_extract(detail_json, '$.draft_id') AS draft_id,
  drafts_created,
  failures,
  duration_ms,
  datetime(finished_at) AS finished_at
FROM pipeline_ticks
WHERE finished_at IS NOT NULL
ORDER BY id DESC
LIMIT 20;

-- In-flight / active ticks (do NOT include in burn-in rates).
SELECT id, tick_id, status, datetime(started_at) AS started_at,
       CAST((julianday('now') - julianday(started_at)) * 86400 AS INTEGER) AS running_age_sec
FROM pipeline_ticks
WHERE finished_at IS NULL
ORDER BY id DESC;

-- Tail consecutive finished count (manual): walk ids DESC until finished_at IS NULL.
-- Automated: python3 tools/burnin_validation.py check
