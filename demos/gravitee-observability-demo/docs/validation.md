# Deadline and detailed span/log validation

All execution was offline, using Python 3.12 and unchanged pinned dependencies.
Working directory: `/workspace/gravitee-observability-demo/demos/gravitee-observability-demo`.

| Check | Executed outcome |
| --- | --- |
| Rebuilt Docker package and dependency validation | Passed |
| Local regression suite | 13 passed |
| Container regression suite | 13 passed |
| Full 60-minute request model | Passed; normal state continues without redeployment |
| Latency-before-error onset | Passed; pressure ramps for 45 seconds per pod; failures follow insufficient processing budget |
| Request outcomes | Passed; successful durations stay within deadline, failed durations equal their deadline, no backend call on gateway deadline failure |
| Detailed child spans | Passed; child intervals partition parent time with no added latency |
| Trace/log correlation | Passed; each sampled detail log references its exact child span |
| Unsampled failed/slow logs | Passed; all parent/detail stages present without fabricated trace/span IDs |
| Serialized detailed error + unsampled slow request | Passed; 15 error-trace spans and 35 total logs including health records, CFS/deadline details and timeout log present |
| Native/classic operation population and protobuf encoding | Passed; added INTERNAL spans do not inflate direct RED counts |
| One-second metrics, counter/gauge semantics, healthy dependencies | Passed |
| Full accelerated 31-minute SDK pipeline | Passed; exit 0 |
| Post-rollback normal state | Passed; both limits 2 cores, normal queues and checks, zero post-recovery failures |
| Event timeline | Passed; ten observations and no automatic recurrence |
| Offline network guard | Passed |
| Toyota checkout and tracked `.env` check | Unchanged Toyota checkout; no tracked `.env` |

Complete episode command:

```bash
cd /workspace/gravitee-observability-demo/demos/gravitee-observability-demo
docker compose run --rm --no-deps gravitee-sim python -u -m sim.main --fast --duration 1860
```

Measured final result:

```json
{
  "requests": 558211,
  "failed_attempts": 71314,
  "sampled_traces": 4277,
  "metric_ticks": 1861,
  "recovered_requests": 125822,
  "recovered_failures": 0,
  "recovered_max_duration_seconds": 0.05747032165527344,
  "signals": {
    "metrics": 1861,
    "spans": 66598,
    "logs": 2261486,
    "events": 10
  },
  "release": "gateway-release-20261029.131221.908584ba2437",
  "live": false,
  "audit": {
    "full_population_requests": 558211,
    "failed_attempt_metrics_and_detailed_logs": 71314,
    "trace_parent_timing": "passed",
    "native_classic_population": "passed",
    "post_rollback_normal_state": "passed"
  },
  "pending_at_shutdown": 0
}
```

The pipeline counted 558,211 requests, 71,314 failed attempts, 66,598 exported
spans and 2,261,486 log records. All failed attempts matched detailed failure logs.
Post-recovery, 125,822 requests had zero failures and a maximum duration below
58 ms. Metric exports remain one second apart, with an extra final tick to drain
pending requests. Trace budgets remain 90 error + 90 slow + 18 ordinary per minute;
additional child spans and stage logs explain the same request population.

Captures were generated outside the checkout and not committed. No live exporter
or remote XCOR configuration was started or modified. Tenant acceptance, native
histogram mapping, and the screenshot's seconds/milliseconds display mapping
remain separate checks. Exact deployment tooling and region are still unvalidated.

Earlier revision results are preserved in [validation-release-v2.md](validation-release-v2.md)
and [validation-initial.md](validation-initial.md); their counts describe those earlier models.
