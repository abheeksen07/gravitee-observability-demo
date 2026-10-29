# Gravitee API Gateway observability stream

This simulator generates metrics, traces, logs and change observations for a
Gravitee API platform incident. It sends no actual API requests to customer systems.
A generated gateway code release bundles a deployment resource change from
**2 cores to 250m** in one
illustrative US production AKS environment. Containers throttle despite available
node CPU; gateway queues delay callers and cause HTTP 504s. Backend services stay
healthy. Restoring CPU limits and gradually rolling gateways restores service.

Traffic varies between **291 and 309 request attempts/second**, without a
release-triggered load surge. Approximately 20% of requests reaching each regressed
pod time out during its 20-minute regression: roughly **72,000 failed attempts**
across the rolling incident, with the actual count varying by request outcomes. These are not unique affected transactions. Routes model product
lookup, order submission and account entitlements; actual customer workflows,
region, workload placement and deployment mechanism require validation.

## Architecture and identities

| Canonical service name | Role and modeled location |
| --- | --- |
| `gravitee-api-gateway` | Java API Gateway; two stable AKS instances in US production |
| `gravitee-customer-applications` | Logical external callers; hosting unspecified |
| `gravitee-customer-backend` | Healthy API backend; hosting unspecified |
| `gravitee-rate-limit-redis` | Self-hosted Redis in illustrative AKS placement; healthy rate-limit checks |
| `gravitee-saas-management-api` | Java/polyglot API management services; illustrative AKS |
| `gravitee-management-console` | React console; illustrative AKS |
| `gravitee-mongodb-atlas` | Managed database dependency; placement unspecified |
| `gravitee-confluent-cloud` | Managed Kafka dependency; placement unspecified |
| `gravitee-elastic-cloud` | Managed search dependency; placement unspecified |
| `gravitee-aws-ses` | Email dependency; region unspecified |
| `gravitee-ovh-services` | Provider dependency placeholder; exact workload unspecified |

All names align across `service.name`, `service`, `service_name`, and `lens_service`.
Instances are stable across launches; release and deployment IDs are distinct.
Only known illustrative AKS workloads get Azure/AKS resource attributes. Unknown
managed dependencies and external callers receive no invented cloud, Kubernetes,
on-premises or geography attributes. No exact Azure region or AZ is asserted.
Managed dependencies emit discovery info, not fabricated request activity.
There are no manufacturing devices or Toyota identities in the emitted stream.

The actual architecture includes Azure AKS across Europe, US and Middle East,
plus GCP, AWS and Clever Cloud environments. This stream covers one US environment;
it does not claim to model every placement. UAE and France have strict residency
requirements: validate in-region processing and IP/PII masking before real data is
collected. Generated records contain no real IPs, customer payloads or user PII.

Grafana Alloy and infrastructure exporters currently feed EU self-hosted Grafana
and Grafana Cloud (Mimir/Tempo/Loki). Cortex XDOT Collector is the planned pilot
replacement, with an OTel Collector for customer exports. This package exports
directly for exploration; it installs none of those collectors or integrations.

## Incident timeline

| Launch offset | Observation |
| --- | --- |
| 00:00 | Healthy baseline, 2-core limit |
| 03:00 | Gateway release rollout starts on pod 0; bundled configuration sets 250m CPU limit |
| 03:30 | Pod 1 receives the same release and limit; both pods now throttle |
| 03:45 | API latency and timeouts observed |
| 04:30 | Customer backend hypothesis; healthy probes contradict it |
| 05:00 | Nodes have CPU capacity; pods ready; no node-capacity incident |
| 06:00 | Stable Redis and normal GC pauses eliminate those hypotheses |
| 10:00 | Diagnosis correlates quota change, CFS throttling and gateway queue waits |
| 22:00 | Rollback of the gateway release and bundled resource configuration selected |
| 23:00 | Pod 0 rolls back to the previous gateway release and 2-core limits |
| 23:30 | Pod 1 rolls back; outstanding requests and residual queues drain |
| 24:00 | Both pods run the previous release; CPU limits, latency, errors and checks normal |
| 30:00 onward | Healthy traffic continues indefinitely; no automatic redeployment |

One incident occurs per launch. `GRAVITEE_REPEAT_INCIDENT=true` explicitly opts
into 30-minute replay. Restarting the process starts a new release/episode; do not
restart to maintain healthy traffic. Historical telemetry is never rewritten, and
AI SRE may correctly identify recurring patterns in historical or replay data.
Each launch chooses a workflow description and generates a UTC/random release ID;
all signals share release, workflow, deployment IDs and timestamps. Gateway version
changes independently on each pod as it receives the release or rollback; dependency
versions remain stable. Each rollout shares one deployment ID, with per-pod
`deployment.pod.timestamp` values exposing the 30-second stagger.

The release is generated, including its code-change context; it is not a claim that
a real GitHub commit, CI run or production code deployment occurred. Its bundled
resource configuration is the actual simulated cause. Rolling back **the release**
restores both the previous code revision identity and its 2-core CPU settings.
No specific code defect or network outage is invented.

The traffic model chooses each request's status and exact stage timings once.
Route selection, route-specific healthy backend latency, queue residence and
4.5–5.5-second deadlines vary using an independent seeded request generator.
Arrival-rate waves are independent of the release state. Initial connectivity
suspicions refer to caller-observed timeouts, not fabricated transport failures.
Metrics count all requests regardless of sampling; traces and logs reuse those
outcomes. Deadline errors have queue, Redis, policy and rejection stages; **no
backend request** ran for them. Successful requests include a short successful
backend call. Queue-wait and nested CFS-wait spans explain latency without adding
extra time. No database failures, retries or network faults are injected.
Requests enter near 300 arrivals/second; a bounded completion heap emits signals
only when each request actually completes on the simulated clock. Incident queue
waits cannot precede deployment. Finite runs drain pending requests before exit;
SIGTERM flushes completed telemetry and reports any unfinished modeled requests.
This is not a CPU-capacity predictor or real load test. Recovery queue depth and infrastructure health are modeled evidence.

Independent error/slow/ordinary trace token budgets refill at 90/90/18 per minute,
with at most five seconds of initial burst. Every failed and every >=1-second
request gets all stage logs and caller/gateway response logs, even when unsampled.
Sampled logs carry matching trace/span IDs; unsampled logs have no fabricated IDs.
Incident and draining health logs run every second; baseline/recovered health logs
run every 30 seconds. Metrics export every second throughout. The check-success gauge is derived from
completed request outcomes in each interval, so in-flight deadline errors remain
visible during rollback rather than disappearing solely because a phase changed.

## Prerequisites and connectivity

On macOS:

```bash
brew install git python@3.12
brew install --cask docker
open -a Docker
# Requires Docker Compose >=2.24 for optional env_file support.
docker compose version
```

Use Docker Compose as the primary launch method. The image is Python 3.12 and
uses the Toyota reference's pinned OTel 1.45.0 dependencies. Local Python commands
below use the same runtime. Docker Hub and PyPI access are needed to build; TLS
verification must remain enabled. A corporate proxy may require a trusted CA.
The Dockerfile accepts a BuildKit `proxy_ca` secret for pip trust; no CA or token
is baked into the image. The managed-cloud build was run with its trusted bundle.

Live export requires authorized secure local `CHRONOSPHERE_API_TOKEN` configuration
and destination connectivity. Never paste tokens into chat, Git commands or logs.
The stream defaults to offline, even if a token happens to be present.

| Signal | Actual destination used by this package |
| --- | --- |
| Metrics | OTLP/gRPC TLS `demo-sandbox.chronosphere.io:443`, MetricsService/Export |
| Traces | OTLP/gRPC TLS `demo-sandbox.chronosphere.io:443`, TraceService/Export |
| Logs | OTLP/HTTP protobuf `https://demo-sandbox.chronosphere.io/data/opentelemetry/v1/logs` |
| Events | JSON POST `https://demo-sandbox.chronosphere.io/api/v1/data/events` with `event` envelope |

Authentication header is `api-token` (gRPC) / `API-Token` (HTTP). In managed proxy
environments use supplied bindings and trust, never bypass the proxy. gRPC needs
HTTP/2 egress support; an HTTPS proxy binding alone does not prove gRPC access.
We have **not verified live ingestion** or sent telemetry during development.

## Build and validate offline

All commands below start from the target checkout root unless stated otherwise:

```bash
cd /path/to/gravitee-observability-demo/demos/gravitee-observability-demo
cp -n .env.example .env
# No token is needed for any offline validation command.
docker compose build
docker compose run --rm --no-deps gravitee-sim python -m pip check
docker compose run --rm --no-deps gravitee-sim python -m unittest discover -s tests -v
# Full 30-minute episode plus an extra healthy minute, accelerated and offline:
docker compose run --rm --no-deps gravitee-sim python -u -m sim.main --fast --duration 1860
# Optional detailed capture (large; keep outside Git):
mkdir -p captures
docker compose run --rm --no-deps -v "$PWD/captures:/captures" gravitee-sim python -u -m sim.main --offline /captures/episode.jsonl --fast --duration 1860
```

Without `--offline PATH`, offline execution reports counts without retaining record
payloads. With a path it appends JSONL, so choose a fresh filename per launch.
Captures can contain millions of generated log records and should be retained
only as needed. Summary mode still executes SDK metrics, tracing and logging.

Equivalent Python validation, from the same demo directory:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -u -m sim.main --fast --duration 1860
```

Tests exercise the full 60-minute model, bounded failure-rate/count checks, staggered pod release/rollback, single launch and
explicit replay, dependency boundaries, HTTP outcomes, full-population native and
classic histograms, protobuf encoding, parent/child timings, IDs/log correlation,
verbose unsampled logs, counter/gauge semantics, events and one-second exports.
An offline network guard proves the offline pipeline cannot connect externally.
See [validation evidence](docs/validation.md) for executed outcomes.

## Start, monitor, update and stop

From `demos/gravitee-observability-demo`:

```bash
# Safe default: continuous offline telemetry, one episode then healthy forever.
docker compose up -d --build
docker compose logs --tail 50 -f gravitee-sim
docker compose ps
# Graceful stop sends SIGTERM; shutdown flushes SDK providers.
docker compose stop -t 30
# Start the stopped container: starts a NEW process/episode, same image.
docker compose start
# Restart also starts a NEW process/episode and does not rebuild.
docker compose restart gravitee-sim
# Apply pulled source changes by rebuilding and recreating:
docker compose up -d --build --force-recreate
# Remove stopped containers when finished:
docker compose down --timeout 30
```

**Pulling source and restarting containers do not rebuild an image.** Rebuild and
recreate to run changed code. The local `.env` is loaded by Compose from this demo
directory, excluded from Git and Docker context; no existing `.env` was copied or
tracked. Python invocation uses process variables and does not implicitly read
`.env`. Inspect identities without printing credentials:

```bash
docker compose run --rm --no-deps gravitee-sim python -c 'from sim import config as C; print(C.SERVICE, C.METRIC_EXPORT_INTERVAL_SECONDS, C.INCIDENT_REPEAT)'
```

Only when live export is separately authorized, enter the token securely into the
local `.env`, confirm network access and run (these commands **start live export**):

```bash
cd /path/to/gravitee-observability-demo/demos/gravitee-observability-demo
docker compose run -d --name gravitee-live --no-deps gravitee-sim python -u -m sim.main --live
docker logs --tail 50 -f gravitee-live
docker stop --time 30 gravitee-live
docker rm gravitee-live
```

Do not run both modes unintentionally: stop the default service first with
`docker compose stop -t 30`. To rebuild a live runner after pulling source:
`docker compose build`, stop/remove `gravitee-live`, then run the explicit live
command again. No live command was executed for this delivery.

## Events, service views and catalog

The ten observations use `deploys` for deployment/rollback and `annotations` for
other observations. These are **offline candidate categories**, not verified tenant
API acceptance; a visible UI category is insufficient proof. Event exporter errors
report HTTP status without response bodies or secrets. No XCOR rules, alerts,
collectors, catalog definitions, monitoring integrations or dashboards are created.

Customer-facing labels carry source/history/runbook/evidence links and useful
summary, evidence, affected-service and business-impact context. They do not carry
synthetic/demo/test markers. The documentation clearly states data is generated.
URLs reference this repository's working branch and source files. No commit, PR,
CI run, audit trail or deployment-run URL is fabricated. Source links are code
references, not evidence of a real infrastructure deployment; they become usable
only once the branch is pushed. Override `GRAVITEE_SOURCE_REF` to the actual ref if
you publish another branch. There are no optional run-link variables that could
silently imply a verified deployment.

See [service views](docs/service-views.md) and [incident runbook](docs/runbook.md).
**Telemetry labels alone do not create service catalog entries.** Configure and
validate matching discovery/service definitions separately in the target tenant.

Suggested catalog description:

> Gravitee API Gateway secures and routes enterprise API requests to backend
> services, applying access and Redis-backed rate-limit policies. Gateway queue
> depth, CPU throttling, API latency and failed request attempts measure its effect
> on customer applications; backend probes and dependency latency support diagnosis.

## GitHub workflow

From the checkout root, after offline checks pass:

```bash
cd /path/to/gravitee-observability-demo
git status --short --branch
git diff --check
git add README.md .gitignore demos/gravitee-observability-demo
git commit -m "Model gateway release rollback and controlled request variance"
git push -u origin work
# Optional review PR:
gh pr create --base main --head work --title "Model Gravitee release rollback and traffic variance" --body-file demos/gravitee-observability-demo/docs/pull-request.md
```

Both `work` and `main` now exist. Work and validate on `work`, then use a PR
for review. When explicitly authorized to fast-forward `main` after validation,
use `git push origin work:main` without force-pushing. The supplied PR body can be edited before invoking that example. Never reset local work to work around a push failure.

## Reference and limitations

Reference: Toyota repository at `08184d5ae4786a9f4f1bff5c6a5f65f91f322cce`.
Its production-operations README, service-view guide, source and regression tests
were inspected. `docs/customer-sample-data-guide.md` was absent from that checkout.
Only `sim/offline.py`, `sim/span_metrics.py`, `sim/__init__.py`, and the pinned
requirements were copied; all customer modeling and tests are new. No `.env`,
credentials, virtual environments or captures were copied. Toyota remains unchanged.
The span-metric view and offline exporter patterns follow the reference.

No read-only XCOR tools are available in this session, so there are no actual
XCOR query results. Ingestion, API categories, native-histogram mapping, tenant
relabeling and service discovery remain unverified. Runtime instrumentation,
actual AKS placement, real deployment tooling and the number of unique affected
customer transactions require customer validation.
