# Gateway throttling investigation and recovery

1. Confirm caller degradation in API error percentage, latency and synthetic
   checks. Scope to `aiapi_api_gateway`, `environment=prod-us` and launch release.
2. Inspect request queue/CFS-wait traces and detailed error/slow-request logs.
   Follow queue enqueue, CFS/runnable wait, resume and deadline-check child spans.
   Use remaining-budget and stage-duration log fields to explain long waits.
   Correlate by request ID and deployment ID; unsampled requests have no trace IDs.
3. Eliminate backend slowdown with healthy probes and short successful calls.
   A 504 produced at the gateway does not imply a backend request was made.
4. Compare Redis command latency and JVM GC pauses with baseline. Both stay normal.
5. Correlate the 03:00 gateway release (pod 1 follows at 03:30) with CPU limit 2 -> 0.25 cores,
   throttling and queues. Node CPU capacity remains available. Probable cause is
   the container quota regression; actual deployment mechanism needs validation.
6. Roll back the gateway release, including its bundled deployment resource
   configuration. This restores the previous release identity and 2-core limits.
   Pod 0 rolls back at 23:00, pod 1 at 23:30; queued/in-flight requests drain
   before both pods return to normal by 24:00. Keep the stream running afterward;
   there is no automatic redeployment. This is not a real Kubernetes operation.
7. Confirm throttling, API latency/error rates and synthetic checks recover.
   Reconcile failed transactions before retrying writes; attempts are not unique
   transactions. Add resource-configuration checks and canary validation.

The simulator's observations are scripted evidence, not actual monitor detections,
Kubernetes audit records, CI runs or execution instructions against customer AKS.
Do not use this runbook to modify infrastructure without verifying its placement
and deployment ownership. France/UAE residency and IP/PII masking must be validated
before moving real telemetry. No real customer data is produced by this package.
