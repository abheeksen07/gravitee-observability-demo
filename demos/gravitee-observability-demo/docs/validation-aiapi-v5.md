# AIAPI dependency tracing v5 validation

Executed October 29, 2026, offline only. No real dependency requests, live
Chronosphere exports, service-graph installation, or tenant UI edits were made.

- Python regression suite: **22 tests passed**, 26.815 seconds.
- Rebuilt Docker image regression suite: **22 tests passed**, 38.892 seconds.
- Original CPU-only tests explicitly select `Scenario(expanded=False)` so they
  continue validating the earlier incident model. The seven dependency tests
  select expanded mode and validate nested paths, parent/child containment,
  propagated IDs, paired application CLIENT/SERVER spans, managed-system protocol
  metadata, protobuf encoding, retry/error status, sampled and unsampled logs,
  bounded sampling, all four error windows, deadline exclusions and final recovery.
- Cross-phase integration exercises 1,100 requests across baseline, all error
  windows, CPU throttling and post-rollback recovery. The summary audit verifies
  nested attempt/error metrics against model totals and detailed error logs,
  parent timing, and native/classic operation population agreement.

Functional first-window run:

```bash
cd /workspace/gravitee-observability-demo/demos/gravitee-observability-demo
.venv/bin/python -u -m sim.main --fast --duration 160
```

Completed with exit status 0:

| Result | Outcome |
| --- | --- |
| Completed requests | 48,440 |
| Gateway/request failures | 0 (run ends before CPU regression) |
| Nested dependency attempts | 486,720 |
| Recovered failed dependency attempts | 2,320 |
| Sampled traces | 176 |
| Exported spans | 6,238 |
| Log records | 63,935 |
| Combined metric exports | 161 |
| Pending requests at shutdown | 0 |
| Dependency model/metric/error-log counts | Matched |
| Request population | Matched |
| Trace timing / parent containment | Passed |
| Native / classic histogram population | Matched |

The first-window run is not a full 31-minute expanded episode. Later error
windows and final recovery are covered by model and cross-phase integration tests.
Earlier v4 full-episode validation is retained as historical evidence, not a v5
full-episode claim.

The offline Compose service was recreated and confirmed to report build
`AIAPI-dependency-tracing-v5`, expanded mode enabled, and six application
dependencies. Its 120-second summary contained 363,906 nested attempts and
1,806 recovered dependency errors.

Preview artifacts in this onboarding workspace were generated from the current
model and SDK spans: `/workspace/artifacts/aiapi-nested-trace-preview.png`, raw
span JSON `/workspace/artifacts/aiapi-nested-trace.json`, and the sampled modeled
error-rate chart `/workspace/artifacts/aiapi-dependency-errors-preview.png`.
They are local illustrations, not screenshots or query results from a tenant.
Graph bubble rendering and peer virtual nodes remain tenant-dependent.
