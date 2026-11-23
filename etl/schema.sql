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

CREATE OR REPLACE VIEW credential_inventory AS
SELECT record_id AS credential_type_id, data->>'credentialType' AS credential_type,
       (data->>'documentCount')::bigint AS document_count,
       (data->>'issuedDateCount')::bigint AS issued_date_count,
       (data->>'expiryDateCount')::bigint AS expiry_date_count
FROM current_warehouse_records WHERE source='credential-service' AND dataset='credential-inventory';

CREATE OR REPLACE VIEW rule_policy AS
SELECT record_id AS rule_id, data->>'type' AS rule_type,
       data->>'severity' AS severity, (data->>'active')::boolean AS active
FROM current_warehouse_records WHERE source='rules-service' AND dataset='rules';

CREATE OR REPLACE VIEW applicant_claims AS
SELECT record_id AS applicant_id, (data->>'year')::bigint AS claimed_year,
       data->>'universityStatus' AS claimed_university_status, data->>'role' AS claimed_role,
       (data->>'courseCount')::bigint AS claimed_course_count
FROM current_warehouse_records WHERE source='applicant-service' AND dataset='applicants';

CREATE OR REPLACE VIEW university_record_summary AS
SELECT record_id AS record_id, data->>'status' AS university_status,
       (data->>'courseCount')::bigint AS course_count,
       (data->>'outlookGroupCount')::bigint AS outlook_group_count,
       (data->>'fcimMessageCount')::bigint AS legacy_fcim_message_count
FROM current_warehouse_records WHERE source='university-record-service' AND dataset='university-records';

CREATE OR REPLACE VIEW moderation_decisions AS
SELECT record_id AS decision_id, data->>'sessionId' AS session_id,
       data->>'moderatorId' AS moderator_id, data->>'action' AS action,
       data->>'expectedAction' AS expected_action, (data->>'correct')::boolean AS correct,
       (data->>'penalty')::bigint AS penalty, (data->>'scoreDelta')::bigint AS score_delta,
       (data->>'penaltyRefunded')::bigint AS penalty_refunded,
       data->>'appealStatus' AS appeal_status, (data->>'violatedRuleCount')::bigint AS violated_rule_count,
       (data->>'decidedAtEpochMs')::bigint AS decided_at_epoch_ms
FROM current_warehouse_records WHERE source='moderation-service' AND dataset='decisions';

CREATE OR REPLACE VIEW dms_channels AS
SELECT record_id AS channel_key, data->>'sessionId' AS session_id, data->>'channel' AS channel,
       (data->>'readOnly')::boolean AS read_only, (data->>'messageCount')::bigint AS message_count
FROM current_warehouse_records WHERE source='discord-dms-service' AND dataset='channels';

CREATE OR REPLACE VIEW dms_channel_activity AS
SELECT record_id AS channel_day_key, data->>'sessionId' AS session_id,
       data->>'channel' AS channel, data->>'day' AS utc_day,
       (data->>'messages')::bigint AS messages, (data->>'playerMessages')::bigint AS player_messages,
       (data->>'systemMessages')::bigint AS system_messages,
       (data->>'distinctSenders')::bigint AS distinct_senders
FROM current_warehouse_records WHERE source='discord-dms-service' AND dataset='channel-days';
