# Lab 5: Moderation and Discord DMs warehouse exports (handoff)

This is the step-5 handoff of `docs/warehouse-extraction.md` for Moderation and Discord DMs.
Both services implement contract version 1 in their own private repositories. This page
publishes what the ETL owner needs for step 6: the schema, the canonical endpoint addresses,
the source commits, the passing tests and the image tags.

It changes no shared configuration. `etl/sources.json`, `etl/schema.sql`,
`docker-compose.warehouse.yml` and the ETL tests belong to the ETL owner. The proposed
entries are published as machine-readable manifests for review:
[moderation-service.json](../contracts/analytics/moderation-service.json) and
[discord-dms-service.json](../contracts/analytics/discord-dms-service.json). They are
not an alternative active `etl/sources.json`. Credential **variable names only** appear
here.

## Status

| | Moderation | Discord DMs |
| --- | --- | --- |
| Source PR (private repo) | moderation-service #46, merged to `dev` | discord-dms-service #50 (and fix #49), merged to `dev` |
| Source commit | `ea8d534` (`dev` merge `10dc7e0`) | `0e6530f` (`dev` merge `19cd9f5`) |
| Image tag | `meow3r/student-id-moderation-service:lab3-0.10.0` | `meow3r/student-id-discord-dms-service:lab3-0.10.0` |
| Release | moderation-service #48, `dev` to `main` | discord-dms-service #51, `dev` to `main` |
| Proposed ETL schema | [moderation-service.json](../contracts/analytics/moderation-service.json) | [discord-dms-service.json](../contracts/analytics/discord-dms-service.json) |

The images are published by each repository's publish workflow when its release PR merges.
Until then, `lab3-0.10.0` does not exist on Docker Hub, and no current release pin
changes.

## Endpoints

| Source | Canonical address | ETL `tokenEnv` | Service variable |
| --- | --- | --- | --- |
| `moderation-service` | `http://moderation-service:8080/internal/v1/analytics/snapshot` | `MODERATION_WAREHOUSE_EXPORT_TOKEN` | `WAREHOUSE_EXPORT_TOKEN` |
| `discord-dms-service` | `http://discord-dms-service:8080/internal/v1/analytics/snapshot` | `DMS_WAREHOUSE_EXPORT_TOKEN` | `WAREHOUSE_EXPORT_TOKEN` |

**Wire behaviour.** Both endpoints implement the version-1 wire contract exactly:
- **Request:** a GET with `Authorization: Bearer <token>` and `X-Service-Name: warehouse-etl`.
- **Refusals:**
  - 401 `UNAUTHENTICATED`. The service's business credential is refused too.
  - 403 `CALLER_NOT_ALLOWED`.
  - 400 `INVALID_QUERY`.
  - 413 `EXPORT_TOO_LARGE`, above 10,000 records or 8 MiB. The whole snapshot is refused, never truncated.
  - 503 `EXPORT_UNAVAILABLE`.
  - 503 `EXPORT_NOT_CONFIGURED`, when the token is empty, malformed or reused. Startup and business routes keep working.
- **Headers:** every answer carries `Cache-Control: no-store`.

**Limits.** Each export shares its service's business admission limit (429
`TASK_LIMIT_REACHED`) and task deadline (503 `TASK_TIMEOUT`). DMs serves the export on its
private REST port only, never on the public WebSocket port. Neither route is added to the
Gateway or to the broker catalog.

**GET bodies.** A body on the GET is ignored, not rejected. The contract defines no
error code for one, and the ETL never sends one. Credential and Rules reject a body, so
this is a known difference between owners.

## `etl/sources.json` entries

These are the same two objects as the manifests in `contracts/analytics/`.

```json
{
  "source": "moderation-service",
  "url": "http://moderation-service:8080/internal/v1/analytics/snapshot",
  "tokenEnv": "MODERATION_WAREHOUSE_EXPORT_TOKEN",
  "datasets": {
    "decisions": {"sessionId": "uuid", "moderatorId": "uuid", "action": "string", "expectedAction": "string",
                  "correct": "boolean", "penalty": "integer", "scoreDelta": "integer", "penaltyRefunded": "integer",
                  "appealStatus": "string", "violatedRuleCount": "integer", "decidedAtEpochMs": "integer"}
  }
},
{
  "source": "discord-dms-service",
  "url": "http://discord-dms-service:8080/internal/v1/analytics/snapshot",
  "tokenEnv": "DMS_WAREHOUSE_EXPORT_TOKEN",
  "datasets": {
    "channels": {"sessionId": "uuid", "channel": "string", "readOnly": "boolean", "messageCount": "integer"},
    "channel-days": {"sessionId": "uuid", "channel": "string", "day": "string", "messages": "integer",
                     "playerMessages": "integer", "systemMessages": "integer", "distinctSenders": "integer"}
  }
}
```

## Field reference

### Moderation, dataset `decisions`

One record per recorded decision. The `id` is the decision UUID. The snapshot is read by
one SQL statement, so it is one PostgreSQL statement snapshot.

| Field | Type | Unit or values |
| --- | --- | --- |
| `sessionId` | uuid | The shift |
| `moderatorId` | uuid | The deciding player (an opaque id) |
| `action`, `expectedAction` | string | `ACCEPT`, `REJECT`, `FLAG` or `BAN` |
| `correct` | boolean | `action` equals `expectedAction` |
| `penalty` | integer | Points deducted for a wrong decision |
| `scoreDelta` | integer | Points the decision changed the shift score by |
| `penaltyRefunded` | integer | Points refunded by an overturned appeal |
| `appealStatus` | string | `NONE`, `UPHELD` or `OVERTURNED` |
| `violatedRuleCount` | integer | Number of rules the applicant violated |
| `decidedAtEpochMs` | integer | Milliseconds since the Unix epoch, UTC |

- **Updates and deletion:** an appeal changes `appealStatus` and `penaltyRefunded`, and a
  deleted decision is absent from the next snapshot.
- **Never exported:** the free-text reason, the applicant, rule codes, outbox payloads
  and error texts.

### Discord DMs, datasets `channels` and `channel-days`

One Redis Lua script reads every channel, history and message. Redis runs a script
atomically, so the snapshot is one point in time. Only counts leave Redis.

`channels`: one record per channel. The `id` is `<sessionId>:<channel without #>`.

| Field | Type | Unit or values |
| --- | --- | --- |
| `sessionId` | uuid | The shift |
| `channel` | string | For example `#general-mod-chat` |
| `readOnly` | boolean | Players cannot post |
| `messageCount` | integer | Messages in the current history (capped at the newest 1,000 per channel) |

`channel-days`: one record per channel per UTC day with messages. The `id` is
`<sessionId>:<channel without #>:<YYYY-MM-DD>`.

| Field | Type | Unit or values |
| --- | --- | --- |
| `sessionId`, `channel` | uuid, string | As above |
| `day` | string | UTC date, `YYYY-MM-DD` |
| `messages` | integer | Messages sent that day |
| `playerMessages`, `systemMessages` | integer | System means a sender id ending in `-service` |
| `distinctSenders` | integer | Different senders that day |

- **Updates and deletion:** a deleted message is no longer counted, and a deleted channel,
  with its messages, is absent from the next snapshot.
- **Never exported:** message text, display names and sender ids.

## Reporting views

These are proposed for `etl/schema.sql`, in the same style as `player_progression` and
`session_results`:

```sql
CREATE OR REPLACE VIEW moderation_decisions AS
SELECT record_id AS decision_id, data->>'sessionId' AS session_id, data->>'moderatorId' AS moderator_id,
       data->>'action' AS action, data->>'expectedAction' AS expected_action, (data->>'correct')::boolean AS correct,
       (data->>'penalty')::bigint AS penalty, (data->>'scoreDelta')::bigint AS score_delta,
       (data->>'penaltyRefunded')::bigint AS penalty_refunded, data->>'appealStatus' AS appeal_status,
       (data->>'violatedRuleCount')::bigint AS violated_rule_count,
       to_timestamp((data->>'decidedAtEpochMs')::bigint / 1000.0) AS decided_at
FROM current_warehouse_records WHERE source='moderation-service' AND dataset='decisions';
CREATE OR REPLACE VIEW dms_channels AS
SELECT record_id AS channel_key, data->>'sessionId' AS session_id, data->>'channel' AS channel,
       (data->>'readOnly')::boolean AS read_only, (data->>'messageCount')::bigint AS message_count
FROM current_warehouse_records WHERE source='discord-dms-service' AND dataset='channels';
CREATE OR REPLACE VIEW dms_channel_activity AS
SELECT record_id AS channel_day_key, data->>'sessionId' AS session_id, data->>'channel' AS channel,
       (data->>'day')::date AS day, (data->>'messages')::bigint AS messages,
       (data->>'playerMessages')::bigint AS player_messages, (data->>'systemMessages')::bigint AS system_messages,
       (data->>'distinctSenders')::bigint AS distinct_senders
FROM current_warehouse_records WHERE source='discord-dms-service' AND dataset='channel-days';
```

## Compose overlay additions

These mirror the Player and Session entries in `docker-compose.warehouse.yml`:

```yaml
  warehouse-etl:
    environment:
      MODERATION_WAREHOUSE_EXPORT_TOKEN: ${MODERATION_WAREHOUSE_EXPORT_TOKEN:?set a separate Moderation reporting credential}
      DMS_WAREHOUSE_EXPORT_TOKEN: ${DMS_WAREHOUSE_EXPORT_TOKEN:?set a separate DMs reporting credential}

  moderation-service: &warehouse-moderation
    image: ${WAREHOUSE_MODERATION_IMAGE:?set the reviewed lab5 Moderation export image}
    environment:
      WAREHOUSE_EXPORT_TOKEN: ${MODERATION_WAREHOUSE_EXPORT_TOKEN:?set a separate Moderation reporting credential}
  moderation-service-2:
    <<: *warehouse-moderation
    profiles: [replicas]

  discord-dms-service: &warehouse-dms
    image: ${WAREHOUSE_DMS_IMAGE:?set the reviewed lab5 DMs export image}
    environment:
      WAREHOUSE_EXPORT_TOKEN: ${DMS_WAREHOUSE_EXPORT_TOKEN:?set a separate DMs reporting credential}
  discord-dms-service-2:
    <<: *warehouse-dms
    profiles: [replicas]
```

`.env.warehouse.example` additions (names only):
`MODERATION_WAREHOUSE_EXPORT_TOKEN=`, `DMS_WAREHOUSE_EXPORT_TOKEN=`,
`WAREHOUSE_MODERATION_IMAGE=` and `WAREHOUSE_DMS_IMAGE=`.

**ETL tests.** `etl/tests/test_etl.py` is scoped to Player and Session. However,
`etl/tests/test_owned_exports.py` asserts that the shared `sources.json` loads exactly
four sources. Registering these two entries therefore needs that count updated, plus
fixtures for `decisions`, `channels` (one dataset) and `channel-days` (a second dataset
in the same source), with a distinct token per source.

## Verification

### Service test suites (in each service's CI)

| Service | Result |
| --- | --- |
| Moderation | `mvn verify`: 200 tests pass, 90.8% line coverage |
| DMs | `go test -race ./...`: all packages pass, 76.0% coverage |

The export tests run against each service's real database-backed handler and cover:
- auth failures: no, wrong or non-Bearer token, the business token, wrong or missing caller, query strings;
- privacy: exactly the allowlist, with no reason, text, names or sender ids;
- real data, and empty datasets as `[]`;
- updates and deletion;
- a source failure (503, never partial);
- overflow (413 at 10,001 records, 10,000 served);
- the export turned off;
- the shared admission limit and the task deadline.

### Live acceptance with this branch's ETL

This ran `etl/run.py` at `13f42b9`, unmodified, with `psycopg[binary]==3.3.9`.

- **Setup:** real PostgreSQL 16 (Moderation's database and a separate `warehouse`
  database) and real Redis. Both services were built from the export commits above. The
  sources file held the two entries above.
- **Result:** 7/7 checks pass. None of the 10 run-generated secrets, nor any seeded
  private text, appeared in any log or warehouse row.

| Check | Result |
| --- | --- |
| A0 | Both exports answer 401 (no, wrong or business token), 403 (wrong caller), 400 (query) and 200 |
| E1 | Both empty snapshots load: every dataset present with no records |
| E2 | 3 decisions, 2 channels and 2 channel-days load, and the views above read them back with the right types, counts and UTC times |
| E3 | Replaying a run id returns `replayed: true` and duplicates nothing |
| E4 | The next batch reflects an appeal, a deleted decision, a deleted message and a deleted channel; the earlier batch stays as history |
| E5 | With DMs stopped, the batch fails with `EXPORT_UNAVAILABLE` and the current views are unchanged |
| E6 | A wrong reporting credential refuses the whole batch |

### Not verified

- **Docker:** the published images, and `etl/verify_live.py` with real containers. Docker
  was unavailable on the verifying machine.
- **Shared stack:** the full team stack with the overlay.
