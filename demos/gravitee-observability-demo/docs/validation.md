# Release rollout and rollback validation

Working directory: `/workspace/gravitee-observability-demo/demos/gravitee-observability-demo`.
Python 3.12 and the unchanged reference-pinned OTel dependencies were used.
All runs were offline; no live exporter or XCOR configuration change was made.

| Check | Executed result |
| --- | --- |
| Local dependency validation (`pip check`) | Passed |
| Container dependency validation (`python -m pip check`) | Passed |
| Local regression suite | 11 passed |
| Rebuilt final Docker image regression suite | 11 passed |
| Full 60-minute model | Passed; one launch incident, no automatic recurrence, both pods normal after 24:00 |
| Per-pod release/rollback | Passed; pod 0 at 03:00 / 23:00, pod 1 at 03:30 / 23:30 |
| Variance | Passed; arrivals 291–309/s, no release-induced surge, route latency and deadlines vary |
| Shared HTTP outcomes, stage logs, trace IDs and parent timing | Passed |
| Native/classic histogram equality and protobuf encoding | Passed |
| Offline network guard | Passed |
| Full accelerated 31-minute SDK episode | Passed; exit 0, final outstanding requests drained |
| Final normal-state audit | Passed; 2-core limits, normal queues, successful checks, no post-recovery failures |
| Real-time Docker JSONL capture | All four signals; four metric exports exactly one second apart; 11 discovery and 6 compute services |
| Baseline/recovery event labels | Passed; business impact is `none`, no invented CI/commit/deployment-run URLs |
| Toyota preservation | Reference checkout remains clean |
| Whitespace and tracked `.env` check | Passed; no tracked `.env` |

The complete episode command was:

```bash
cd /workspace/gravitee-observability-demo/demos/gravitee-observability-demo
docker compose run --rm --no-deps gravitee-sim python -u -m sim.main --fast --duration 1860
```

Measured SDK export result:

```json
{
  "requests": 558211,
  "failed_attempts": 72111,
  "sampled_traces": 4288,
  "metric_ticks": 1861,
  "recovered_requests": 125822,
  "recovered_failures": 0,
  "recovered_max_duration_seconds": 0.05771517753601074,
  "signals": {
    "metrics": 1861,
    "spans": 32258,
    "logs": 1089039,
    "events": 10
  },
  "release": "gateway-release-20261029.011723.fdc666c4b46e",
  "live": false,
  "audit": {
    "full_population_requests": 558211,
    "failed_attempt_metrics_and_detailed_logs": 72111,
    "trace_parent_timing": "passed",
    "native_classic_population": "passed",
    "post_rollback_normal_state": "passed"
  },
  "pending_at_shutdown": 0
}
```

The run generated 558,211 requests and 72,111 failed attempts, all counted by
metrics and detailed failure logs. After minute 24, 125,822 completed requests had
zero failures and a maximum duration below 58 ms. The final normal-state audit
also verified both 2-core CPU limits, normal queue levels and successful checks.
Counters retain history; their error/throttling rates return to baseline rather
than erasing historical totals. The extra metric tick drains pending requests.

The final recovery-event label correction was verified by the rebuilt image's
regression suite; the SDK episode exercises the same request and infrastructure
model. Generated capture files remain outside the checkout and are not committed.

Initial fixed-rate-model validation is preserved separately in
[validation-initial.md](validation-initial.md); its exact fixed counts do not
describe this revised variable-rate stream.

Live tenant ingestion, category acceptance, native-histogram mapping and service
catalog discovery are not established by offline checks. Exact region, deployment
mechanism and customer transactions remain unvalidated. Release events describe
generated code/deployment changes, not real GitHub commits, CI runs or audit logs.
