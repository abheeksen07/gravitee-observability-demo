# AIAPI Redis lens presentation

These are **generated** exporter-compatible metrics, not a scraped Redis server.
Redis stays healthy during the gateway CPU regression. No tenant dashboard,
service discovery rule, monitor, or integration is installed by this repository.

## Research sources

Reviewed October 29, 2026:

- [Grafana dashboard 763](https://grafana.com/grafana/dashboards/763-redis-dashboard-for-prometheus-redis-exporter-1-x/) is the requested reference. Direct access returned HTTP 403 in this environment, so its current revision was not inspected.
- [Official redis_exporter documentation](https://github.com/oliver006/redis_exporter#readme) describes INFO/commandstats collection and the default `redis` metric namespace. It currently describes Valkey compatibility as well as Redis compatibility.
- [Official exporter metric mappings](https://github.com/oliver006/redis_exporter/blob/master/exporter/exporter.go) verify names, counter/gauge mappings, `cmd` and `db` labels.
- [Exporter-maintained Grafana dashboard](https://github.com/oliver006/redis_exporter/blob/master/contrib/grafana_prometheus_redis_dashboard.json) supplies the presentation patterns: uptime, clients, memory, commands by command, hits/misses, network, keys by database, expirations/evictions, and mean command time. These upstream references track `master`; verify version-specific availability against a real exporter before production use.

## Implemented metric set

All series include `lens_service="AIAPI-rate-limit-redis"`, `instance`, `pod`,
`node`, `container`, `namespace` and `cluster`. Only relevant families add `cmd`
or `db`; there are no per-key/client/request labels.

| Family | Type / dimensions | Presentation |
| --- | --- | --- |
| `redis_up`, `redis_uptime_in_seconds` | Gauge | Availability and uptime stats |
| `redis_connected_clients`, `redis_blocked_clients` | Gauge | Connections and blocked clients |
| `redis_memory_used_bytes`, `redis_memory_used_rss_bytes`, `redis_memory_used_peak_bytes`, `redis_memory_max_bytes` | Gauge, bytes | Used/RSS/limit overlay; utilization stat |
| `redis_mem_fragmentation_ratio` | Gauge, ratio | RSS relative to allocator usage |
| `redis_commands_processed_total` | Counter | Overall operations/s |
| `redis_commands_total` (`cmd`: `eval`, `get`, `set`) | Counter, one series per command | Stacked operations/s |
| `redis_commands_duration_seconds_total{cmd=...}` | Counter, seconds | Mean execution time per command |
| `redis_keyspace_hits_total`, `redis_keyspace_misses_total` | Counter | Hit/miss rates and hit ratio |
| `redis_net_input_bytes_total`, `redis_net_output_bytes_total` | Counter, bytes | Input/output bytes/s |
| `redis_db_keys`, `redis_db_keys_expiring` | Gauge, `db="db0"` or `db="db1"` | Key population by database |
| `redis_expired_keys_total`, `redis_evicted_keys_total` | Counter | Expirations/s and evictions/s |

EVAL count and cumulative duration come from the same completed Redis stages
used by request traces and `redis_command_duration_seconds{cmd="eval"}`.
GET/SET are additional **modeled background cache work** with bounded varying
rates, independent of the gateway deployment. GETs partition into hits/misses.
Network counters include both EVAL and background commands. Database key counts
are illustrative gauge populations; they do not reconstruct a real key lifecycle.
Evictions and blocked clients remain zero; availability stays one. Inventing
spikes in these health indicators would contradict the incident diagnosis.

## Suggested lens layout and queries

Use `$redis` = `AIAPI-rate-limit-redis`. A selector shared by all queries is
`lens_service="$redis",instance=~"$instance"`. Use 10–30-second rate windows
with a roughly one-second step for a short incident presentation; use longer
windows when the tenant retention/resolution requires them. These PromQL queries
assume standard OTLP-to-Prometheus name translation and cumulative counters;
verify the tenant's actual mapping. Do not apply `rate()` to gauges.

Row 1: availability, clients, memory utilization, hit ratio. Row 2: stacked
commands by `cmd`, command latency by `cmd`, input/output traffic. Row 3:
memory overlay, keys by `db`, expired/evicted rates. Use seconds with a
millisecond display for latency, bytes for memory, and bytes/second for traffic.

```promql
# Operations: preserve command and pod dimensions rather than summing all lines.
sum by (pod, cmd) (rate(redis_commands_total{lens_service="$redis",instance=~"$instance"}[30s]))

# Mean command duration, seconds. This is not P99.
sum by (pod, cmd) (rate(redis_commands_duration_seconds_total{lens_service="$redis",instance=~"$instance"}[30s]))
/ clamp_min(sum by (pod, cmd) (rate(redis_commands_total{lens_service="$redis",instance=~"$instance"}[30s])), 1e-9)

100 * redis_memory_used_bytes{lens_service="$redis",instance=~"$instance"}
/ redis_memory_max_bytes{lens_service="$redis",instance=~"$instance"}

100 * sum by (pod) (rate(redis_keyspace_hits_total{lens_service="$redis",instance=~"$instance"}[30s]))
/ clamp_min(sum by (pod) (rate(redis_keyspace_hits_total{lens_service="$redis",instance=~"$instance"}[30s])
+ rate(redis_keyspace_misses_total{lens_service="$redis",instance=~"$instance"}[30s])), 1e-9)

rate(redis_net_input_bytes_total{lens_service="$redis",instance=~"$instance"}[30s])
rate(redis_net_output_bytes_total{lens_service="$redis",instance=~"$instance"}[30s])
redis_db_keys{lens_service="$redis",instance=~"$instance"}
redis_db_keys_expiring{lens_service="$redis",instance=~"$instance"}
rate(redis_expired_keys_total{lens_service="$redis",instance=~"$instance"}[30s])
rate(redis_evicted_keys_total{lens_service="$redis",instance=~"$instance"}[30s])
```

Use legends `{{pod}} · {{cmd}}`, `{{pod}} · {{db}}`, and `{{pod}} · input/output`.
Avoid copying dashboard variables such as `namespace` without mapping them to the
simulator's actual labels. The metrics are compatible with the selected exporter
families; this is not a claim that the full Grafana dashboard can be imported
unchanged into a lens page.
