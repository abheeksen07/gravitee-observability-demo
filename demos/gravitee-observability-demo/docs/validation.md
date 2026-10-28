# Executed validation — 2026-10-28

Working directory: `/workspace/gravitee-observability-demo/demos/gravitee-observability-demo`.
Python 3.12; OTel dependencies exactly match the Toyota reference's pinned requirements.
All telemetry validation was offline. No credentials were copied or exported.

| Check | Result |
| --- | --- |
| Python dependency validation (`pip check`) | Passed |
| Container dependency validation (`python -m pip check`) | Passed |
| Gravitee regression suite, local Python | 8 passed |
| Gravitee regression suite, final Compose image | 8 passed |
| Toyota reference regression suite, unchanged checkout | 37 passed |
| Docker build and Compose configuration validation | Passed |
| Offline network-connection guard | Passed |
| Real-time offline JSONL capture | 900 completed requests; all four signals; four metric exports exactly one second apart, including final drain |
| Documented default Compose startup and graceful SIGTERM stop | Passed; offline, providers flushed |
| Full 31-minute accelerated SDK episode | Passed, process exit 0; metrics/traces/logs/events all exercised |
| Full 60-minute model plus repeat-mode regression | Passed; one incident per default launch; healthy traffic continues |
| Git whitespace checks | Passed |
| `.env` tracked-file check | No tracked `.env`; ignored by Git and Docker context |
| Toyota worktree preservation | Clean; no tracked or untracked changes |

The complete episode used:

```bash
cd /workspace/gravitee-observability-demo/demos/gravitee-observability-demo
docker compose run --rm --no-deps gravitee-sim python -u -m sim.main --fast --duration 1860
```

Measured final result:

```json
{
  "requests": 558000,
  "failed_attempts": 72000,
  "sampled_traces": 4219,
  "metric_ticks": 1861,
  "signals": {
    "metrics": 1861,
    "spans": 31764,
    "logs": 1128093,
    "events": 10
  },
  "release": "gateway-resource-config-20261028.180555.ce8517094e3d",
  "live": false,
  "audit": {
    "full_population_requests": 558000,
    "failed_attempt_metrics_and_detailed_logs": 72000,
    "trace_parent_timing": "passed",
    "native_classic_population": "passed"
  },
  "pending_at_shutdown": 0
}
```

The 1,861 metric ticks represent one-second exports over 1,860 arrival seconds
plus a final one-second interval to drain outstanding healthy requests. Metrics
and logs independently account for all 72,000 failed attempts. SDK export audits
confirm native/classic operation population equality and parent/child timing for
all sampled traces. Error/slow stage-log and ID correlation regressions cover
unsampled requests too. Events remain exactly ten after the 30-minute boundary;
healthy traffic continues without a new deployment.

Summary mode audits in-memory SDK exports without retaining payloads. A separate
real-time JSONL capture verified serialization and all four signal kinds. Generated
capture files were saved outside the checkout, not committed. No live exporters
were started, and no XCOR configuration was modified.

These results do not establish live tenant ingestion, category acceptance, native
histogram mapping, discovery/catalog rules or residency compliance. No read-only
XCOR tools were available; there are no actual XCOR query results. US region,
deployment mechanism, workload placement and the specific customer transaction
still require validation. Unique affected transactions are unknown.

Reference commit: `08184d5ae4786a9f4f1bff5c6a5f65f91f322cce`.
`docs/customer-sample-data-guide.md` was absent from the reference checkout.
