# AIAPI service views

This guide describes emitted data; it changes no tenant configuration. Configure
a view/discovery rule for `application="AIAPI-api-platform"`, grouping by
`lens_service`, with `instance` for the instance selector. Use
`AIAPI-api-gateway` as `$service`. All seventeen services emit `demo_service_info`;
expanded tracing models six application dependencies plus MongoDB, Kafka and SES
calls. Other unmodeled managed dependencies remain discovery-only.

Stable labels: `demo="AIAPI-api-platform"`, `demo_build="AIAPI-infrastructure-v4"`, `service`, `service_name`, `lens_service`, `service_role`,
`application`, `team`, `environment="prod-us"`, `instance`, and
`az="us-placement-unvalidated"`. The last is an explicit unvalidated grouping
value, not a claim about an Azure zone. Gateway instances are
`AIAPI-api-gateway-0` and `AIAPI-api-gateway-1`; release/version labels vary
without changing instance identities. Request/trace IDs never appear on metrics.

```promql
# Discover services. An emitted label does not create a catalog entry.
demo_service_info{application="AIAPI-api-platform"}
# Confirm canonical identities after a new launch.
count by (lens_service, service, service_name) (demo_service_info{application="AIAPI-api-platform"})
```

## Export cadence and compute

Every signal family with data is exported once per second. Traffic is generated
near 300 attempts/second (291–309), independently of release state. A chart's rate lookback is different from export cadence
and graph evaluation step. Use a **10–30-second lookback** and roughly one-second
evaluation step for detailed charts, with a short visible time range. `[1s]` often
contains fewer than two points and cannot reliably compute `rate()`. Longer
lookbacks smooth and delay visible changes; destination resolution may limit detail.

CPU is a cumulative counter in **core-seconds**: `rate()` yields CPU cores.
Memory is a **gauge in bytes**; do not use `rate()` or multiply it by 1000.
Network and disk are cumulative **byte counters**; `rate()` yields bytes/second.
The combined network counter represents receive plus transmit. Disk counters model
configuration reads and audit writes, not storage saturation. Compute is emitted
for AKS services and the illustrative caller/backend processes, not invented
process metrics for managed cloud providers.

```promql
sum by (instance, environment, az) (
  rate(process_cpu_seconds_total{lens_service="$service",instance=~"$instance"}[30s])
)
sum by (instance, environment, az) (
  process_resident_memory_bytes{lens_service="$service",instance=~"$instance"}
)
sum by (instance, environment, az) (
  rate(system_network_io_bytes_total{lens_service="$service",instance=~"$instance"}[30s])
)
sum by (instance, environment, az) (
  rate(container_fs_reads_bytes_total{lens_service="$service",instance=~"$instance"}[10s])
)
sum by (instance, environment, az) (
  rate(container_fs_writes_bytes_total{lens_service="$service",instance=~"$instance"}[10s])
)
```

AKS instances also expose `pod`, `container`, and `node` labels; disk counters
add `device="overlay"`. Node and overlay names are illustrative stable simulator
identities, not discovered infrastructure. Pod names match resource metadata.
The supplied disk queries work with these explicit labels, for example:

```promql
sum by (container, pod, instance, environment, az) (
 rate(container_fs_writes_bytes_total{container=~"$container",instance=~"$node",lens_service="$service",pod=~"$pod"}[10s])
)
```

Here `$node` must contain an instance/pod value because the query filters
`instance`; if it contains node values, use `node=~"$node"` instead. Resource
promotion is tenant-dependent; the explicit metric labels do not require it.

## HTTP RED and span duration

`http_server_requests_total` and `http_server_request_duration_seconds` count the
full modeled HTTP population, with `http_route`, `http_response_status_code` and
`build_version`. Redis operations are represented by span durations, not fabricated
HTTP server calls. Callers use `http_client_requests_total` and
`http_client_request_duration_seconds`. The caller's operation is a CLIENT span; gateway is SERVER;
expanded backend and Redis calls use paired CLIENT/SERVER spans. See
[dependency tracing](dependency-tracing.md) for nested application calls and
caller-side managed-dependency spans.

```promql
sum(rate(http_server_requests_total{lens_service="AIAPI-api-gateway"}[30s]))
100 * sum(rate(http_server_requests_total{lens_service="AIAPI-api-gateway",http_response_status_code=~"5.."}[30s]))
 / sum(rate(http_server_requests_total{lens_service="AIAPI-api-gateway"}[30s]))
histogram_quantile(0.95, sum by (le) (
 rate(http_server_request_duration_seconds_bucket{lens_service="AIAPI-api-gateway"}[30s])
))
```

Native `traces_span_metrics_duration` is an OTLP exponential histogram in seconds.
Classic `traces_span_metrics_duration_seconds` is an explicit histogram with the
same population/durations. Both include `span_name`, `span_kind`, `status_code`
(`STATUS_CODE_OK`/`STATUS_CODE_ERROR`) and `span_metrics_source="simulator"`.
Queue/internal diagnostic spans do not inflate incoming-operation metrics.
Native wire encoding is tested; tenant mapping is not verified.

```promql
# Native request rate, errors/second and p99 seconds.
sum by (span_name, environment, az) (
 histogram_count(rate(traces_span_metrics_duration{lens_service="$service",span_metrics_source="simulator"}[30s]))
)
sum(histogram_count(rate(traces_span_metrics_duration{lens_service="$service",span_metrics_source="simulator",status_code="STATUS_CODE_ERROR"}[30s]))) or vector(0)
histogram_quantile(0.99, sum by (service_name, span_name, environment, az) (
 rate(traces_span_metrics_duration{lens_service="$service",span_metrics_source="simulator"}[30s])
))
# Classic fallback: use this family INSTEAD of native, never sum both.
sum(rate(traces_span_metrics_duration_seconds_count{lens_service="$service",span_metrics_source="simulator"}[30s]))
sum(rate(traces_span_metrics_duration_seconds_count{lens_service="$service",span_metrics_source="simulator",status_code="STATUS_CODE_ERROR"}[30s])) or vector(0)
histogram_quantile(0.99, sum by (le, service_name, span_name, environment, az) (
 rate(traces_span_metrics_duration_seconds_bucket{lens_service="$service",span_metrics_source="simulator"}[30s])
))
```

Do not add native/classic families or unfiltered tenant-derived span metrics.
Filter `span_metrics_source="simulator"`, or set `GRAVITEE_EXPORT_SPAN_METRICS=false`
in local `.env`, recreate the container, and use tenant-generated metrics instead.
Tenant metrics from sampled traces may not represent the full request population;
HTTP counters remain the authoritative full-population attempt/error counts.

## Investigation evidence

```promql
# Limit drops to 0.25 while node capacity remains available.
container_spec_cpu_quota_cores{lens_service="AIAPI-api-gateway"}
100 * rate(container_cpu_cfs_throttled_periods_total{lens_service="AIAPI-api-gateway"}[30s])
 / rate(container_cpu_cfs_periods_total{lens_service="AIAPI-api-gateway"}[30s])
rate(container_cpu_cfs_throttled_seconds_total{lens_service="AIAPI-api-gateway"}[30s])
aiapi_gateway_pending_requests{lens_service="AIAPI-api-gateway"}
aiapi_node_cpu_available_cores{lens_service="AIAPI-api-gateway"}
kube_pod_status_ready{lens_service="AIAPI-api-gateway"}
aiapi_backend_probe_success
histogram_quantile(0.95, sum by (le) (rate(redis_command_duration_seconds_bucket[30s])))
histogram_quantile(0.95, sum by (le) (rate(jvm_gc_pause_seconds_bucket[30s])))
aiapi_synthetic_check_success{lens_service="AIAPI-api-gateway"}
sum(increase(aiapi_failed_request_attempts_total[20m]))
```

Queue depth is an estimate from full-population queue residence seconds per
one-second interval (Little's law), not an independent random series.
Quota/queue/node/probe/check metrics are gauges; CFS periods/throttled seconds and
failed attempts are cumulative counters; GC and Redis durations are second-valued
histograms. CFS counters apply to gateway containers; node CPU availability is
contextual modeled node evidence, not actual infrastructure monitoring.

Explore logs/traces by `request_id`, `release.id`, `deployment.id`, `workflow.name`
and `scenario.phase`. Timeouts show `gateway.request_queue` with nested
`gateway.cpu.cfs_wait`, then `gateway.deadline_exceeded`. No backend error spans
exist for calls that never happened. Successful slow traces preserve short backend
calls inside the same root timing. Unsampled request logs correlate by request and
deployment IDs, without invented trace IDs. Log `request.duration_seconds` is the
full request duration; `stage.duration_seconds` is that actual stage's duration.

If data is absent: verify running image/version, offline versus explicit live
mode, exporter errors and destination connectivity/authentication. Then check
recent time windows, label promotion/relabeling, native histogram support, and
service discovery rules. None of these tenant outcomes is established by local
offline tests. Do not assume UI event-category names are accepted by ingestion.

## Release rollout and restored steady state

The generated gateway code release includes its deployment resource configuration.
Pod 0 receives it at 03:00 and pod 1 at 03:30. Per-pod CPU-limit/throttling charts
should step at different times, while request throughput only varies slightly.
Use `build_version` on HTTP counters and `service.version` in traces/logs to
correlate each pod's requests with its active release. `deployment.id` is shared
for the rollout; `deployment.pod.timestamp` records each pod's change time.

Rollback starts at 23:00 on pod 0 and 23:30 on pod 1, restoring the previous
release and 2-core limits. Newly arriving requests use that pod's restored
release context; already in-flight requests retain their original context until
completion. At 24:00 both pods are healthy, and that normal state persists past
the 30-minute episode without another deployment. Counter values do not reset:
error/throttling **rates** return to zero, while cumulative totals remain.
Synthetic check success follows completed request failures in each interval.
Source release/rollback observations are generated, with no invented CI run URLs.

## Detailed duration/error investigation and display units

For requests lasting at least one second, inspect `gateway.request_queue` and its
CFS/runnable-wait children before policy/backend durations. Error requests add
`gateway.deadline.check` and `gateway.response.write_timeout`; successful slow
requests retain short, successful backend operations. All failed/slow requests
have matching stage logs, whether or not a trace was sampled. Filter by
`request_id`, `stage.name`, `diagnostic.stage_error`, and `deadline.remaining_seconds`
to follow the remaining processing budget through each stage. A single modeled
request supplies all outcomes and times. The 45-second queue-pressure ramp means
latency can rise before errors; RED is not generated from an independent error
probability. Native/classic operation histograms still count only incoming
operations, not these extra INTERNAL diagnostic spans.

**Duration samples and PromQL quantiles are in seconds.** Normal route P99 values
near `0.035`–`0.060` represent **35–60 milliseconds**, not microseconds. Incident
deadline durations around `5` represent **5 seconds**, not 5 milliseconds. Select
a seconds-aware panel display unit and check the raw query output before adding
any conversion; an extra division by 1,000 can make the screenshot appear three
orders of magnitude too small. CPU rate values are cores (for example `0.6`); use
a cores/number display if the panel title says cores rather than formatting as
60 percent. These display settings were not modified remotely or verified in the
tenant. Do not scale simulator durations to compensate for a panel-unit mismatch.

## Infrastructure detail and natural variation

The current build is `AIAPI-infrastructure-v4`. CPU consumption, memory,
filesystem traffic, GC pauses and network housekeeping include bounded,
reproducible waves, per-series fine noise and short bursts. The independent
infrastructure generator does not consume the request RNG or create extra HTTP
failures. CPU quota, readiness, Redis availability and successful dependency
probes remain exact. Healthy indicators need not be noisy.

Each AKS process exposes four logical scheduling CPU series in
`container_cpu_usage_seconds_total{cpu="0"..."3"}`. Their deltas sum exactly
to `process_cpu_seconds_total`; they divide consumption across schedulable CPUs,
not four dedicated cores or four replicas. During regression their aggregate
remains below the 0.25-core quota. Two illustrative nodes each expose eight
`node_cpu_seconds_total` CPU series with `mode="user|system|idle"`. Per CPU,
the modes sum to one CPU-second per simulation tick. Node counters are emitted
once per node, without pod/container metric labels, so they are not duplicated
for every workload. Their OTel resource still identifies the emitting simulator;
use the explicit `node`, `cpu`, and `mode` labels for node charts.

Network counters now have `device="eth0"` and `direction="receive|transmit"`.
Sum directions for the previous combined view, or keep them for richer charts.
Pod, node, container, namespace and cluster are stable illustrative dimensions;
request IDs, release IDs and timestamps are not added to infrastructure labels.

```promql
# Eight lines: two gateway pods x four CPU scheduling series. Unit: cores.
sum by (pod, node, cpu) (
  rate(container_cpu_usage_seconds_total{lens_service="AIAPI-api-gateway"}[10s])
)
# Node utilization per CPU, percent. 16 lines, not summed per pod.
100 * (1 - rate(node_cpu_seconds_total{application="AIAPI-api-platform",mode="idle"}[10s]))
# Four lines: pod x network direction. Unit: bytes/s.
sum by (pod, node, direction) (
  rate(system_network_io_bytes_total{lens_service="AIAPI-api-gateway"}[10s])
)
# Two pod memory lines; retain pod instead of reducing everything to one value.
process_resident_memory_bytes{lens_service="AIAPI-api-gateway"}
```

Use a stacked area chart for per-CPU consumption, separate charts for node CPU
and pod CPU, and legends `{{pod}} / CPU {{cpu}}` or `{{pod}} / {{direction}}`.
A CPU-core value must not use a percent display unless explicitly normalized to
the relevant capacity/quota. The CPU limit remains a step line because it is a
configuration change. Longer rate windows intentionally smooth short bursts.
See [Redis lens presentation](redis-lens.md) for exporter research and queries.

### Migrating the existing lens

New service identities use the uppercase `AIAPI-` prefix, including
`AIAPI-api-gateway` and `AIAPI-rate-limit-redis`; application is
`AIAPI-api-platform`, and custom metrics use the conventional lowercase
`aiapi_` prefix. Update service discovery selectors, lens titles, monitors,
dashboard queries and catalog descriptions in the destination tenant to match.
Old history is not rewritten or deleted. No tenant edits or live exports are
performed by this code change. `AIAPI_EXPORT_SPAN_METRICS`,
`AIAPI_REPEAT_INCIDENT` and `AIAPI_SOURCE_REF` take precedence over legacy
`GRAVITEE_*` variables, which remain accepted for existing local settings.
The repository URL and checkout directory keep their actual GitHub names.

Current build: `AIAPI-dependency-tracing-v5`. The v4 infrastructure dimensions
and jitter remain. [Dependency tracing](dependency-tracing.md) adds the nested
map, explicit recovered error windows, separate sampling budget and edge queries.
