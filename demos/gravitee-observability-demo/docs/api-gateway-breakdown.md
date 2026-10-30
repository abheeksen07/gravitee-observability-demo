# Gateway breakdown by customer account and status

Build marker: `AIAPI-account-breakdown-v6`.

The gateway emits the OTLP cumulative counter **`api_gateway_breakdown`** and
histogram **`api_gateway_breakdown_duration_seconds`**. The counter counts
completed gateway requests, once per request, regardless of trace sampling.
The histogram records those same requests' actual end-to-end durations.

Both belong to `lens_service="aiapi_api_gateway"` and
`application="AIAPI-api-platform"`. Explicit dimensions include:

| Label | Values |
| --- | --- |
| `account` | `account-001` through `account-012` (12 fixed fictional customer IDs) |
| `status_code` | `200`, `201`, `404`, `504` |
| `http_route` | Existing catalog, order submission, and account-entitlement route templates |
| `latency_band` | `fast` (<100 ms), `elevated` (100 ms–<1 s), `slow` (>=1 s), or `timeout` (504) |
| `pod`, `instance`, `node` | Existing stable gateway instance / infrastructure labels |

Accounts are assigned in a round-robin sequence independent of request RNG and
CPU incident state. Each account receives traffic across the existing routes.
There are no real customer names, account secrets, request IDs or timestamps in
metric dimensions. The account is also attached to request trace and log context.

- **200**: successful GET; **201**: successful order submission.
- **404**: modeled missing resource on GET requests that reached the backend.
  Every 37th request is eligible (about 2% of all traffic after GET filtering),
  independent of CPU state; deadline failures take precedence. Backend and
  gateway status codes agree. These client errors do not count as failed 5xx
  attempts or indicate CPU throttling. They can also have delayed responses.
- **504**: existing queue/deadline model; latency and status are determined once
  and reused by all metrics, logs and traces. Backend work is not invented for
  these requests. CPU throttling remains the incident's timeout cause.

Latency bands are display buckets, not an incident detector or an asserted SLO.
Healthy expanded order requests can exceed 100 ms. Infrastructure regression
continues to create slow successful requests and long 504 responses; counts and
histograms reflect that actual model rather than independently sampled errors.

## Example queries

Standard Prometheus counter translation commonly exposes the OTLP counter as
`api_gateway_breakdown_total`; confirm the tenant's actual metric-name mapping.
If the tenant preserves `api_gateway_breakdown`, substitute that exact name.
Histogram queries assume standard `_bucket`, `_sum`, `_count` translation.

```promql
# Request rate per customer and status code.
sum by (account, status_code) (
  rate(api_gateway_breakdown_total{lens_service="aiapi_api_gateway"}[30s])
)
# Customer-facing 404s; keep separate from incident 504s.
sum by (account) (
  rate(api_gateway_breakdown_total{lens_service="aiapi_api_gateway",status_code="404"}[30s])
)
# Incident timeouts per customer.
sum by (account) (
  rate(api_gateway_breakdown_total{lens_service="aiapi_api_gateway",status_code="504"}[30s])
)
# Latency mix per customer, including successful slow responses.
sum by (account, latency_band) (
  rate(api_gateway_breakdown_total{lens_service="aiapi_api_gateway"}[30s])
)
# Per-customer P99 latency in seconds. Retain le for classic histograms.
histogram_quantile(0.99,
  sum by (account, le) (
    rate(api_gateway_breakdown_duration_seconds_bucket{lens_service="aiapi_api_gateway"}[30s])
  )
)
```

Use `{{account}} / {{status_code}}` as the traffic legend. To compare success and
failure latency, retain `status_code` in the histogram aggregation as well.
Do not add the histogram count to the counter: they describe the same population.
Do not sum both pods' per-account P99s; aggregate histogram buckets first.

Validation checks all 12 account IDs, all four status codes, gateway/backend 404
agreement, timeout duration, 404 request logs, and exact agreement of the new
counter and histogram with the request population. The offline summary audit also
compares the breakdown counter with gateway HTTP request totals.
