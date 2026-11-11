# Initialize the Message Broker from the CPR

The custom Lab 4 broker is a private Git submodule, like Gateway and Service
Discovery:

| Item | Value |
| --- | --- |
| Repository | [Andreiisthebest/student-id-message-broker](https://github.com/Andreiisthebest/student-id-message-broker) |
| CPR path | `services/message-broker` |
| Pinned source | `86374ea0637dba8ae94f25b72ca4ba70a85ccfd2` |
| Reviewed change | [Broker PR #6](https://github.com/Andreiisthebest/student-id-message-broker/pull/6), merged into `dev` |
| Runtime | Python 3.12+ / FastAPI, version `0.1.0` |
| Container port | `8093` |

The pin contains the initialized runtime, Dockerfile, tests and contribution
workflow. The broker's default `main` branch still contains only the repository
bootstrap; the reviewed runtime is on `dev`. Initializing the CPR submodule
checks out the exact pinned commit, regardless of that default branch. It does
not follow future branch changes automatically.

## Access

Authenticate Git with the GitHub account that has accepted the private broker
repository invitation. `CmMarin`, `m3ower` and `Vasiok11` have accepted write
access as of 2026-11-11. New contributors must ask the repository owner for
access and accept their invitation before cloning. A CPR checkout alone does
not grant access to its private submodules.

With GitHub CLI installed, check the authenticated account and repository access:

```bash
gh auth status
gh repo view Andreiisthebest/student-id-message-broker
```

An authenticated `Repository not found` usually means that account lacks private
repository access. Use your own Git credential manager or SSH setup; never put a
token into `.gitmodules`, a Git URL, or a committed file.

## New CPR checkout

```bash
git clone --branch dev --recurse-submodules https://github.com/m3ower/faf-student-id-please.git
cd faf-student-id-please
git -C services/message-broker rev-parse HEAD
```

The last command must print the pin in the table above. Recursive cloning also
requires access to every other private service. To initialize only the broker,
clone the CPR without `--recurse-submodules`, then use the next section's two
submodule commands.

## Existing CPR checkout

First update your CPR checkout to the reviewed `dev` commit containing this
submodule. From the CPR root, run:

```bash
git submodule sync -- services/message-broker
git submodule update --init --recursive -- services/message-broker
git -C services/message-broker rev-parse HEAD
git -C services/message-broker status --short
```

The commit must match the pin and the status must be clean. A detached HEAD in a
submodule is normal: the CPR records a commit, not a developer's current branch.
Plain `git pull` in the CPR does not initialize a new submodule. Avoid
`git submodule update --remote` for reproducing this checkout; it selects a
branch tip instead of the reviewed CPR pin.

## Run and contribute

The broker's [README](../services/message-broker/README.md) contains the local
Python environment, repository checks, application tests, Docker build and smoke
commands. Its operational routes are `GET /health`, `GET /health/ready` and
`GET /status`; they report process readiness. There is no message-delivery API
in this version. The custom Python broker is separate from the planned RabbitMQ
transport described elsewhere in the CPR.

To develop, work inside `services/message-broker`, create an assigned issue in
the broker repository, fetch `origin`, and create a `feature/`, `fix/`, `docs/`
or `chore/` branch from `origin/dev`. Follow its
[CONTRIBUTING.md](../services/message-broker/CONTRIBUTING.md) and PR template.
The broker's `main` and `dev` rules require two approvals, code-owner review,
resolved conversations and the current passing `broker-repository-checks` job.
Feature PRs target `dev` and squash merge; release PRs go from `dev` to `main`
using a merge commit. Do not commit new work on the detached submodule HEAD.

After a broker change is reviewed and merged, advance the CPR gitlink in a
separate issue-linked PR to CPR `dev`. Publish the referenced source before
updating that gitlink, and keep private credentials out of both repositories.
Initializing this source checkout does not start the broker, publish a release,
alter Compose, or move Gateway/service communication to it.

## Grade 5: service routing (candidate)

[Broker #7](https://github.com/Andreiisthebest/student-id-message-broker/issues/7) turns the
broker into the service-to-service router: it routes the operations of the
[HTTP operation catalog](http-operation-catalog.md) with per-caller and per-target
credentials, Discovery-backed round-robin load balancing and a per-instance circuit breaker,
all moved from the Gateway. Version `0.2.0`. It needs `DISCOVERY_URL`,
`DISCOVERY_REGISTRATION_TOKEN`, `BROKER_CALLER_TOKENS_JSON` and the `<TARGET>_INTERNAL_TOKEN`
values; see its README. The CPR pin above and the shared Compose file change only after the
broker, Moderation and Discord DMs releases are reviewed and published.
