CREATE TABLE IF NOT EXISTS warehouse_runs (
    run_id UUID PRIMARY KEY,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    source_count INTEGER NOT NULL,
    row_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS warehouse_sources (
    run_id UUID REFERENCES warehouse_runs ON DELETE CASCADE,
    source TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, source)
);
CREATE TABLE IF NOT EXISTS warehouse_records (
    run_id UUID NOT NULL,
    source TEXT NOT NULL,
    dataset TEXT NOT NULL,
    record_id TEXT NOT NULL,
    data JSONB NOT NULL,
    PRIMARY KEY (run_id, source, dataset, record_id),
    FOREIGN KEY (run_id, source) REFERENCES warehouse_sources ON DELETE CASCADE
);
CREATE OR REPLACE VIEW current_warehouse_records AS
SELECT source, dataset, record_id, data FROM warehouse_records
WHERE run_id = (SELECT run_id FROM warehouse_runs ORDER BY loaded_at DESC, run_id DESC LIMIT 1);
CREATE OR REPLACE VIEW player_progression AS
SELECT record_id AS player_id, (data->>'level')::bigint AS level,
       (data->>'xp')::bigint AS xp, (data->>'shiftsCompleted')::bigint AS shifts_completed,
       (data->>'accuracyTotal')::double precision AS accuracy_total,
       (data->>'disciplinaryActions')::bigint AS disciplinary_actions
FROM current_warehouse_records WHERE source='player-service' AND dataset='players';
CREATE OR REPLACE VIEW session_results AS
SELECT record_id AS session_id, data->>'teamId' AS team_id,
       data->>'difficulty' AS difficulty, data->>'state' AS state,
       (data->>'applicationsProcessed')::bigint AS applications_processed,
       (data->>'score')::bigint AS score, (data->>'penalties')::bigint AS penalties,
       (data->>'rulesetVersion')::bigint AS ruleset_version,
       (data->>'revision')::bigint AS revision
FROM current_warehouse_records WHERE source='session-service' AND dataset='sessions';
