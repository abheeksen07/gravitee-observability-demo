A generated gateway code release bundles a CPU-limit regression from 2 cores to 250m. Pod rollouts are staggered by 30 seconds, linking each pod's release change to throttling, queue waits and caller timeouts while dependencies remain healthy. Rolling back the release restores its previous revision and resource settings, then the stream remains healthy indefinitely.

Adds bounded traffic variance around 300 requests/second, route-specific healthy latency, variable deadlines and probabilistic outcomes shared across metrics/traces/logs. Extends offline regressions and full-episode auditing to verify per-pod release/rollback metadata, normal final state and continued healthy traffic. No real code-push/CI evidence is fabricated and no live export is started.

Executed validation is recorded in docs/validation.md. Tenant ingestion and exact customer deployment tooling/placement remain separate validation requirements.
