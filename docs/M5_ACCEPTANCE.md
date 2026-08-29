# M5 Acceptance

Date: 2026-08-29. Branch: `codex/m5-deployment`, based on M4 commit `184add1`.
Status: **in progress, not public v1**. Code-side deployment controls and local
real-engine preflight are complete. Paid resource approval, Linux image build,
public deployment, Pages publication and different-network acceptance remain.

## Local Deployment-Candidate Evidence

The production ASGI entry from commit `f179c2a9565667b95e46fbb043343e4133b1a662`
was started with the deployment config, 64 visits,
strict Host/security controls and the real local KataGo 1.16.4 Metal backend.
`scripts/remote_acceptance.py` then used only `samples/m3_mistake.sgf`:

| Workflow | Result |
| --- | --- |
| Readiness | Correct KataGo version, b18 model identifier and model SHA-256 |
| SGF path | Multipart upload -> validated preview -> bounded job -> complete 6/6 report |
| Manual path | Equivalent six moves entered as canonical JSON -> complete 6/6 report |
| Obvious mistakes | Both runs selected moves 1, 3 and 5 |
| Uploaded losses | 12.63, 11.84 and 8.99 points |
| Manual losses | 12.58, 11.96 and 9.17 points |
| Traceability | Every accepted recommendation was present in that move's candidate evidence |
| Mock/unsupported prose | `engine_source=katago`; no fallback or tactical diagnosis added |

The numbers are observations, not fixed future expectations. The automated gate
requires complete coverage and at least one traceable >=5 point result around
moves 1, 3 or 5. See `evidence/m5-local-service-acceptance.json`.

The 235-move public benchmark at 64 visits used one engine process, analyzed 236
positions, performed 34 forced played-move evaluations, took 144.64 seconds and
peaked at 624,427,008 bytes child RSS on Apple M4/Metal. See
`evidence/m5-local-64-benchmark.json`. Linux/Eigen host performance is not yet
measured.

## Automated Coverage Added

The release check completed with **308 Python tests passed, zero skipped**, all
live KataGo cases enabled, **38 frontend tests passed**, no broken Python
requirements and a clean whitespace check.

- Production mode hides docs, validates Host, sets CSP/HSTS/privacy headers and
  keeps local development behavior separate.
- Sliding-window per-client/global limits are atomic and deterministic; client
  addresses are only held as salted process-local hashes.
- Fly runtime requires a source commit, exact host and trusted proxy-header name.
- Deployment contract tests pin source/model/base identities, non-root runtime,
  2 GiB single-machine topology, Pages CORS, private-data exclusions and CSP-
  compatible frontend rendering.
- Startup fails closed on real engine readiness; access logging is disabled.
- Release/container/deploy scripts refuse inappropriate or dirty inputs where relevant.

## Gate Status

| Release gate | Status |
| --- | --- |
| Fresh checkout install/start | Pending Linux container build |
| Uploaded and manual real analysis | Passed locally; pending public host |
| Obvious-loss fixture with tolerance | Passed locally; pending Linux/public rerun |
| Browser mistake position and markers | Passed M4 locally; pending public browser rerun |
| No mock/invented evidence | Passed code/local service checks |
| Missing engine, invalid input, full queue, cancellation | Passed local automated/M4 checks; image startup failure pending |
| Different-device, different-network review | Pending public resource approval and deployment |

M5 must not be marked complete until every pending item is recorded against the
deployed commit and actual HTTPS origin. See [M5 deployment runbook](M5_DEPLOYMENT.md).
