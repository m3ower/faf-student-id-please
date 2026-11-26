# Published Lab 5 deployment selections

Verified on 2026-11-26 against public DockerHub tags and OCI revision labels.
The CPR gitlinks select the corresponding released source commits, including
repositories whose private source is inaccessible to this account. Those
inaccessible private checkouts were not initialized or modified.

| Service | Published image tag | Source revision |
| --- | --- | --- |
| player-service | `vasiok11/student-id-player-service:lab5-1.8.0-build.50` | `93f939a870ca93cfd2f321a614badd6db2078af0` |
| session-service | `vasiok11/student-id-session-service:lab5-1.8.0-build.56` | `742f5fea9f2b4192dc21361846db5903109a10c9` |
| credential-service | `cmmarin/student-id-credential-service:lab5-1.7.3` | `e0b43ef43e745a568168ae48cc034600cabf1416` |
| rules-service | `cmmarin/student-id-rules-service:lab5-1.6.2` | `6b9a343763188266a845c6e3a2ede7039f3f6de3` |
| applicant-service | `andreiisthebest/student-id-applicant-service:lab3-1.8.0` | `3742a8be3e6340d42bb7a5c56514b532ee36445c` |
| university-record-service | `andreiisthebest/student-id-university-record-service:lab3-1.8.0` | `8e31a7665b4cc8c5e7795dc947ba0e3c28f87fe4` |
| moderation-service | `meow3r/student-id-moderation-service:lab3-0.13.2` | `29695a135e6acdbbf8f18b0f3265128e2ffeb47a` |
| discord-dms-service | `meow3r/student-id-discord-dms-service:lab3-0.13.0` | `2b3b4318b5481000241810c2651ff40b0e7ff15d` |
| message-broker | `andreiisthebest/student-id-message-broker:lab4-0.9.0` | `ca34c131990b86c4b95cf05448c4c366acee1f90` |
| gateway-service | `vasiok11/student-id-gateway-service:lab4-2.1.1-build.59` | `dd994edc82d2cefa7e57e6c01775a67ea07aeb3b` |
| service-discovery | `cmmarin/student-id-service-discovery:lab4-0.8.0` | `a4e2688ed9b135b80fccd227cae22b4804ed270f` |
| warehouse-etl | `vasiok11/student-id-warehouse-etl:lab5-0.1.0` | `90a6a2616788a33375140418e653994c6b76fbbd` |

Immutable digests are selected in `.env.example`, `.env.owned-broker.example`
and `.env.warehouse.example`. Existing Compose files retain their required
credential checks and optional profiles. Existing ignored `.env` values override
defaults: copy only the updated image/version selections into your private
environment without replacing its credentials. No private `.env` was changed.

## Executed populated acceptance

The released combination passed in disposable project `whpop-be02204a0e`:

- Real Player/team/Session setup, applicant initialization, DMs messages and two Moderation decisions through Gateway.
- All eight authenticated reporting sources and nine nonempty typed Warehouse views.
- Exact initial extraction/load comparison (24 rows), then supported updates/deletions and exact updated comparison (23 rows).
- Both run IDs replayed without duplicate committed batches.
- Stopping DMs caused EXPORT_UNAVAILABLE while preserving committed Warehouse content and batch history.

Trace: `whpop-413dca20bd68`. Sanitized local evidence is in
`docs-local/warehouse-fixed-20261126/results.md` and its linked artifacts;
these ignored local artifacts are not distributed by cloning the CPR.

This was an isolated acceptance configuration with generated disposable
credentials, one instance per business service, no host application ports, a
256 MiB Broker result-memory budget, and the existing dossier 2PC startup
switches enabled for fixture generation. It does not certify every base/replica,
cache, HA or monitoring combination. Merely updating image pins does not enable
those features or migrate existing volumes. No saga candidate was selected.

The first attempt exposed a runner assertion mixing Session penalty counts
with Moderation penalty points. Correcting that assertion required no application
change; the subsequent complete scenario passed. Test resources were removed.
