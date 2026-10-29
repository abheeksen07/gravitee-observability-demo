Gateway requests now develop modeled queue pressure over 45 seconds after each pod receives the release; timeouts emerge when queue demand exhausts the processing budget, rather than a separately sampled error flag. Release rollback still restores normal state and healthy traffic continues.

Adds queue admission/CFS/runnable-wait/resume, policy evaluation and deadline/response child spans without changing parent durations or adding dependency calls. Every failed or >=1-second request gets matching detailed stage logs regardless of sampling, with exact span IDs when traced. RED populations remain independent of trace detail.

Offline regressions cover latency-before-error onset, shared budget-driven outcomes, trace/log timing/correlation, unsampled detailed logs, and healthy recovery. See docs/validation.md for full SDK episode evidence. No live export or tenant configuration change is included.
