# M5 Deployment Runbook

Updated: 2026-08-29. Status: deployment candidate prepared; no paid resources
have been provisioned. Public v1 acceptance is still pending owner approval and
a different-network test.

## Approved Topology To Provision

The candidate uses one Fly.io Machine in Sydney and one HTTPS origin for both
the static frontend and FastAPI/KataGo process:

| Setting | Candidate value |
| --- | --- |
| Region | `syd` |
| Machine | `shared-cpu-2x`, 2 GiB RAM |
| Count | One; no autoscaler |
| Lifecycle | Always on; no auto-stop during background jobs |
| Storage | Ephemeral memory only; no database or volume |
| Search | 64 visits, one analysis thread, two search threads |
| Queue | One running and one waiting |
| Job/result lifetime | 900-second job deadline and 900-second terminal retention |

The local 235-move, 64-visit Metal benchmark peaked at 624,427,008 bytes
(595.5 MiB) child RSS and took 144.64 seconds. A 512 MiB free instance is below
the measured engine process alone. Linux/Eigen performance remains unknown until
the candidate image runs on the selected host; do not treat the local duration
as a public response-time promise.

Fly's current Sydney list price for an always-on `shared-cpu-2x` with 2 GiB is
about US$18.40/month. A dedicated IPv4, if explicitly allocated, is another
US$2/month; outbound transfer is variable. The requested owner authorization
ceiling is **US$25/month**. This is a project spending boundary, not a provider-
enforced cap: Fly documents that it has no free tier or billing alerts and that
free allowances do not cap charges. Check month-to-date billing manually and do
not add Machines, volumes, managed services, autoscaling or dedicated IPv4
without a new approval.

Sources: [Fly pricing](https://fly.io/docs/about/pricing/),
[cost management](https://fly.io/docs/about/cost-management/), and
[Sydney region](https://fly.io/docs/reference/regions/).

## Reproducible Runtime

`Dockerfile` verifies downloads before use and runs as UID 10001:

| Artifact | Pinned identity |
| --- | --- |
| KataGo source | v1.16.4, SHA-256 `51b1a9b48053b0de910f44abf2cc95160de7b6d43bb22300e0b80ea0b3ed0ca8` |
| Neural network | `kata1-b18c384nbt-s9996604416-d4316597426.bin.gz` |
| Model SHA-256 | `9d7a6afed8ff5b74894727e156f04f0cd36060a24824892008fbb6e0cba51f1d` |
| Analysis config | `config/deployment-eigen.cfg`, current SHA-256 `930a72dbf7b4e39cd6ee390a88aa391f5764d841919a1b2267ee126e04e08c81` |
| Runtime base | Python 3.14.7 slim Bookworm, pinned multi-platform image digest |
| Build base | Debian Bookworm 2026-08-24 slim, pinned multi-platform image digest |

The image compiles the Eigen CPU backend because the selected shared VM has no
GPU. KataGo's source `LICENSE`, bundled third-party license files and the official
2026 network license are copied into `/licenses`. The model is downloaded from
the official KataGo training host. No model weight, local path or private SGF is
committed to Git.

## Startup And Readiness

`scripts/container_server.py` performs a real model load plus KataGo
`query_version`/`query_models` before replacing itself with one Uvicorn worker.
Bad binary, model, config or source-commit metadata therefore fails startup.

- `GET /health` is a cheap process liveness probe and intentionally does not load KataGo.
- `GET /ready` starts a fresh engine readiness check; it is expensive and rate-limited.
- `GET /release` returns the full Git commit, ephemeral-storage declaration and real-engine label.
- Fly health checks allow five minutes for CPU model startup, then poll `/health` every 30 seconds.

The Docker image derives its exact public Host from Fly's injected
`FLY_APP_NAME`; custom domains must be added explicitly to
`GO_REVIEW_PUBLIC_HOSTS`. `GO_REVIEW_RELEASE` must be a full lowercase commit
hash on Fly, so direct deployments that omit the release build argument fail.

## Security, Privacy And Capacity

- Request bodies are capped before multipart/JSON parsing at 1 MiB plus 64 KiB overhead.
- Production validates the exact Host, disables OpenAPI/docs, sends strict CSP,
  HSTS, no-referrer, no-frame and no-sniff headers, and uses no-store responses.
- Only Fly's `Fly-Client-IP` header is trusted. Addresses become salted 16-byte
  process-local hashes for rate limiting and are never logged or persisted.
- Expensive readiness/job/compatibility analysis calls allow four per client and
  20 globally per rolling hour. Limits reset on process restart.
- Job IDs contain 192 random bits. Inputs/results live only in bounded process
  memory, disappear on restart, and expire 15 minutes after terminal state.
- Uvicorn access logs, KataGo request/response logs and engine stderr logs are
  disabled, keeping SGFs, player names, job IDs and client addresses out of
  normal logs. Sanitized startup metadata and generic failures remain visible.
- GitHub Pages is allowed as one exact CORS origin. It is not authentication and
  does not receive credentials. The complete service remains same-origin.

## Test And Deploy

Before building a release from a clean checkout, configure the local real engine
as documented in README and run:

```bash
scripts/release_check.sh
scripts/container_acceptance.sh docs/evidence/m5-container-acceptance.json
```

The first command runs all Python tests with live KataGo, all frontend tests,
dependency validation and whitespace checks. The second requires Docker, builds
the pinned Linux image, waits through real startup, and runs both SGF-upload and
equivalent-manual acceptance. This workstation does not currently have Docker,
so the image-build gate remains pending and must run before public traffic.

After explicit resource approval:

```bash
brew install flyctl
fly auth login
fly apps create <unique-app-name>
scripts/deploy_fly.sh <unique-app-name>
```

The script refuses a dirty worktree, embeds `git rev-parse HEAD`, builds remotely,
deploys `deploy/fly.toml`, then checks `/release` and `/health`. Do not run
`fly launch`; it may rewrite the reviewed sizing/lifecycle configuration.

Run acceptance from a second device or different network, using the checked-in
public sample only:

```bash
python scripts/remote_acceptance.py \
  https://<unique-app-name>.fly.dev \
  --output docs/evidence/m5-remote-acceptance.json
```

It verifies real KataGo/model/visits, complete 6/6 coverage, an engine-backed
loss of at least five points around public fixture moves 1, 3 or 5, and a
recommendation present in the returned candidate evidence. Search values may
vary; exact scores and recommendations are not asserted.

## Rollback And Shutdown

Before each update, record `fly releases --app <app> --image`. To roll back,
redeploy the previously verified image with
`fly deploy --app <app> --image <registry-image>`, then check `/release`,
`/health`, `/ready`, logs and one public-sample review. Fly notes that rollback
reuses current configuration and that registry images are not retained forever.
This release has no database migrations or persistent data to reverse.

For an incident involving privacy, runaway cost or fabricated/partial output,
stop the Machine or destroy the app from the Fly dashboard/CLI and leave the
Pages preview clearly marked unavailable. Deleting the only app is destructive;
record the release/image and billing state first.

Source: [Fly rollback guide](https://fly.io/docs/blueprints/rollback-guide/).
