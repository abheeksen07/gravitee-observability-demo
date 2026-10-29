# Gravitee service views

This guide describes emitted data; it changes no tenant configuration. Configure
a view/discovery rule for `application="gravitee-api-platform"`, grouping by
`lens_service`, with `instance` for the instance selector. Use
`gravitee-api-gateway` as `$service`. All eleven services emit `demo_service_info`;
managed dependencies are discovery-only until their actual request paths are known.

Stable labels: `demo="gravitee-api-platform"`, `demo_build="gravitee-release-rollback-v2"`, `service`, `service_name`, `lens_service`, `service_role`,
`application`, `team`, `environment="prod-us"`, `instance`, and
`az="us-placement-unvalidated"`. The last is an explicit unvalidated grouping
value, not a claim about an Azure zone. Gateway instances are
`gravitee-api-gateway-0` and `gravitee-api-gateway-1`; release/version labels vary
without changing instance identities. Request/trace IDs never appear on metrics.

```promql
# Discover services. An emitted label does not create a catalog entry.
demo_service_info{application="gravitee-api-platform"}
# Confirm canonical identities after a new launch.
count by (lens_service, service, service_name) (demo_service_info{application="gravitee-api-platform"})
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
backend and Redis dependency spans follow the Toyota dependency-map convention.

```promql
sum(rate(http_server_requests_total{lens_service="gravitee-api-gateway"}[30s]))
100 * sum(rate(http_server_requests_total{lens_service="gravitee-api-gateway",http_response_status_code=~"5.."}[30s]))
 / sum(rate(http_server_requests_total{lens_service="gravitee-api-gateway"}[30s]))
histogram_quantile(0.95, sum by (le) (
 rate(http_server_request_duration_seconds_bucket{lens_service="gravitee-api-gateway"}[30s])
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
container_spec_cpu_quota_cores{lens_service="gravitee-api-gateway"}
100 * rate(container_cpu_cfs_throttled_periods_total{lens_service="gravitee-api-gateway"}[30s])
 / rate(container_cpu_cfs_periods_total{lens_service="gravitee-api-gateway"}[30s])
rate(container_cpu_cfs_throttled_seconds_total{lens_service="gravitee-api-gateway"}[30s])
gravitee_gateway_pending_requests{lens_service="gravitee-api-gateway"}
gravitee_node_cpu_available_cores{lens_service="gravitee-api-gateway"}
kube_pod_status_ready{lens_service="gravitee-api-gateway"}
gravitee_backend_probe_success
histogram_quantile(0.95, sum by (le) (rate(redis_command_duration_seconds_bucket[30s])))
histogram_quantile(0.95, sum by (le) (rate(jvm_gc_pause_seconds_bucket[30s])))
gravitee_synthetic_check_success{lens_service="gravitee-api-gateway"}
sum(increase(gravitee_failed_request_attempts_total[20m]))
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
