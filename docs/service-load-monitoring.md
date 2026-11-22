# Lab 4 Task 10: availability, service load and monitoring

Tracks CPR #168 and Broker #39; Credential #50 and Rules #46 provide live load.
This is implementation/configuration work, not a claim that the new images are
published or that unmodified teammate services expose the new load fields.

## Shared additive status contract

Services retain their current `/status` response and add:

```json
{"load":{"activeTasks":2,"capacity":32}}
```

Both fields are integers: `0 <= activeTasks <= capacity`, `1 <= capacity <= 65536`.
`activeTasks` counts admitted, unfinished business work across HTTP and gRPC,
including work still running after a caller timeout. It excludes health/status
sampling. `capacity` is the actual shared admission limit, not CPU percent or
the configured value of a separate HTTP-only limiter. Do not add identities,
secrets or business data. This change is additive; no proto or business schema changes.

The monitoring overlay sets `BROKER_LOAD_BALANCING=true` (default false supports
a coordinated opt-in rollout). Broker samples only registered addresses, off the business request path, with
200 ms timeouts, 16 KiB replies, at most eight simultaneous probes and 32 replicas
per service. Samples expire after three seconds. It chooses the lowest fresh
`activeTasks / capacity`; equal load retains round robin. If any eligible candidate
lacks a fresh valid sample, it explicitly falls back to round robin across those
candidates. Unknown load is never reported as zero. Each owner must adopt the
fields before claiming load-aware selection for that service. No Discovery schema
change is required; readiness, subscription and gRPC health gates remain mandatory.

## Failover and Task 9 durability

An open circuit excludes that instance from subsequent selections. A failed read
that trips the circuit can try one other eligible instance within the original
deadline. Read-only POST operations are explicitly allowlisted in Broker source;
arbitrary POSTs are not assumed safe. The delivery keeps its message ID, caller,
correlation ID, body and absolute deadline. A connection that was never established
may still fail over as before.

An ambiguous mutation or event is **not** blindly replayed. A timeout does not prove
that a database commit failed. Task 9's durable journal and dead letters retain
their existing recovery/receipt semantics; the change does not turn them into an
exactly-once guarantee. Established SSE/WebSocket connections are not migrated.

## Prometheus and Grafana

Use reviewed Task 10 Broker and owned-service images after their release; do not
point existing release tags at uncommitted source. Preserve the Task 9 Broker
volume and the existing Compose project name. Add a private `GRAFANA_ADMIN_PASSWORD`
to your existing deployment env file (never commit it). Set `TASK10_BROKER_IMAGE`,
`TASK10_CREDENTIAL_IMAGE` and `TASK10_RULES_IMAGE` to the reviewed published images
(targets `lab4-0.8.0`, `lab4-1.2.0`, `lab4-1.2.0` respectively). They are deliberately
required rather than silently using older images that have no metrics/load support.
Then add the monitoring file:

```powershell
docker compose --project-name <existing-project> --env-file <private-env-file> `
  -f docker-compose.yml -f docker-compose.owned-broker.yml `
  -f docker-compose.monitoring.yml up -d
```

Open Prometheus at `http://localhost:9090/targets` and Grafana at
`http://localhost:3000` (user `admin`, your configured password). Grafana provisions
the **PAD - routing and service load** dashboard automatically. Both interfaces
bind to loopback only; Broker `/metrics` stays private and is not a Gateway route.
Persistent named volumes retain dashboards and seven days / 512 MB of metric data.
Images are pinned to stable Docker Hub digests inspected on 2026-11-23.
Import `postman/monitoring.postman_collection.json` for the scrape and owned-load
checks; no player token is needed for these loopback-only operational endpoints.
Business requests continue to use Gateway with a real Player login token.

Metrics include queue depth, retained dead letters, storage state, circuit trips,
failovers, backend response status/transport, business HTTP ingress latency and
fresh per-replica utilization. Missing samples produce gaps, not fake healthy data.
Counters reset on Broker restart; durable messages/dead letters do not. Grafana is
not a log database. Existing structured container logs and Task 4's bounded,
authenticated system-log download remain the log collection mechanism.

## Demonstration and trace logs

1. Show two ready replicas registered for an instrumented service.
2. Keep work running on one; its utilization should rise and routing prefer the other.
3. Fail one replica in a disposable deployment, then issue a read. Show
   `circuit_tripped`, `route.failover` and a successful `call.in` sharing its trace ID.
4. Show the dashboard's utilization, selection, latency and failover panels.
5. Show retained dead-letter counts and the existing authenticated listing separately.

Follow live logs without exposing environment variables or credentials:

```powershell
docker compose --project-name <existing-project> --env-file <private-env-file> `
  -f docker-compose.yml -f docker-compose.owned-broker.yml `
  logs --follow --tail 30 message-broker credential-service rules-service
```

Use the normal Player login token in Postman. Set a fresh `X-Trace-Id` on the
initiating business request and find that ID in Broker and service logs. Do not use
health responses as evidence that business failover worked, and do not simulate a
failure against classmates' running replicas. Focused source tests cover selection,
failover identity and non-replay of mutations; real released-image acceptance is
a separate deployment check.

Configuration follows the official [Prometheus Docker guidance](https://prometheus.io/docs/prometheus/latest/installation/)
and [Grafana provisioning documentation](https://grafana.com/docs/grafana/latest/administration/provisioning/).
