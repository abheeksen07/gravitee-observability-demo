# AIAPI infrastructure v4 validation

Executed October 29, 2026 in the managed cloud environment, offline only.
No live ingestion or tenant configuration changes were performed.

- Python 3.12 virtual environment: `python -m pip check` passed.
- `python -m unittest discover -s tests -v`: 15 tests passed locally (18.924s) and in the rebuilt Docker image (25.141s).
- Added coverage verifies four CPU scheduling series per pod, CPU conservation below the incident quota, two nodes with eight CPUs and three modes, memory variation, directional traffic, AIAPI identities, exporter-style Redis dimensions, actual EVAL count/duration agreement, GET hit/miss accounting, and healthy Redis state.
- Image rebuilt with the managed combined CA bundle through the Dockerfile's `proxy_ca` secret; TLS verification stayed enabled.
- Recreated continuous offline Compose service reports `AIAPI-api-gateway`, build `AIAPI-infrastructure-v4`, and emitted its first 60- and 120-second progress reports.

Full functional check:

```bash
cd /workspace/gravitee-observability-demo/demos/gravitee-observability-demo
.venv/bin/python -u -m sim.main --fast --duration 1860
```

Completed with exit status 0:

| Result | Count / outcome |
| --- | --- |
| Completed requests | 558,211 |
| Failed attempts during incident | 71,314 |
| Recovery requests | 125,822 |
| Recovery failures | 0 |
| Maximum recovery duration | 0.05747032165527344 seconds |
| Sampled traces | 4,277 |
| Exported spans | 66,598 |
| Log records | 2,261,486 |
| Combined metrics exports | 1,861 |
| Events | 10 |
| Pending requests at shutdown | 0 |
| Request metrics / detailed failed logs | Matched |
| Trace parent/child timing | Passed |
| Native / classic histogram population | Matched |
| Post-rollback normal state | Passed |

The failure population matches the previous offline build: infrastructure
variation is independent of request outcome generation. Grafana dashboard 763
was inaccessible (HTTP 403); research used the official Redis exporter README,
metric mappings and exporter-maintained Grafana dashboard instead. PromQL and
lens layout recommendations are documented but have not been executed in a
Chronosphere tenant. Historical Gravitee data and saved tenant selectors are
not migrated by these changes.
