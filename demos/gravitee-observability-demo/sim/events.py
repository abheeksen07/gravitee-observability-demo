"""Scripted observations, not evidence of installed monitoring integrations."""
from datetime import datetime, timezone
from sim import config as C
from sim.identity import service_labels
MARKERS = (
 (0,'baseline','API transactions available','Gateway and backend checks healthy; CPU limit 2 cores.'),
 (180,'deployment','Gateway release rollout started','Gateway code release bundles a deployment resource change reducing CPU limits from 2 cores to 250 millicores. Pod 0 updates now; pod 1 follows in 30 seconds. Deployment mechanism requires validation.'),
 (225,'degradation','API-dependent transactions timing out','Gateway latency and HTTP 504s increase; customer transaction attempts cannot complete.'),
 (270,'investigation','API connectivity and backend slowdown investigated','Caller timeouts suggest API connectivity or backend slowdown, but healthy backend probes and short successful calls contradict those hypotheses. No network failure is observed.'),
 (300,'infrastructure-check','Nodes have available CPU capacity','Gateway pods remain ready; node CPU available while container throttling rises after deployment.'),
 (360,'dependency-check','Redis and JVM hypotheses eliminated','Redis latency 2ms and normal 4ms GC pauses; no rate-limit bottleneck or GC pressure.'),
 (600,'diagnosis','Probable cause: resource regression bundled with gateway release','Each pod begins throttling after receiving the gateway release with the 250m limit. Queue waits and deadlines increase; backend, Redis and GC evidence remain healthy.'),
 (1320,'mitigation','Roll back the gateway release','Roll back the gateway code release and its bundled deployment configuration to restore the previous release and 2-core limits. Reconcile failed transactions before retrying writes.'),
 (1380,'rollback','Gateway release rollback started','Restore the previous gateway release and its 2-core resource configuration on pod 0 now; pod 1 follows in 30 seconds. Allow queued requests to drain before confirming recovery.'),
 (1440,'recovery','API latency and synthetic checks recovered','Both pods run the previous gateway release with 2-core limits. Throttling subsides, queues drain and API latency, errors and checks return to normal. Healthy traffic continues without redeploying. Add resource checks and canary validation.'),
)
class Timeline:
    def __init__(self, scenario): self.scenario=scenario; self.sent=set()
    def due(self, now):
        s=self.scenario; cycle=int((now-s.start)//1800) if s.repeat else 0
        self.sent={x for x in self.sent if x[0]==cycle}
        result=[]
        for offset,kind,title,summary in MARKERS:
            key=(cycle,kind)
            if offset>s.position(now) or key in self.sent: continue
            self.sent.add(key); at=s.start+cycle*1800+offset
            context=s.context(at)
            root=f'{C.SOURCE_REPOSITORY}/blob/{C.SOURCE_REFERENCE}/demos/gravitee-observability-demo'
            labels={**{k:v for k,v in service_labels(C.SERVICE).items() if k not in ('instance','az','demo','demo_build','pod','container','node')},
                'change_summary':summary,'workflow_name':s.profile,'release_id':s.id,
                'affected_services':C.SERVICE+', '+C.CLIENT, 'previous_version':s.version if kind=='rollback' else s.previous, 'new_version':context['build_version'],'deployment_id':context['deployment.id'],
                'deployment_timestamp':context['deployment.timestamp'],
                'release_change_scope':context['release.change_scope'],
                'rollout_strategy':'rolling; pods staggered by 30 seconds',
                'source_url':root+'/sim/model.py',
                'source_history_url':f'{C.SOURCE_REPOSITORY}/commits/{C.SOURCE_REFERENCE}/demos/gravitee-observability-demo/sim/model.py',
                'runbook_url':root+'/docs/runbook.md', 'evidence_url':root+'/docs/service-views.md',
                'evidence':'container_cpu_cfs_throttled_periods_total; aiapi_gateway_pending_requests; backend probes; Redis latency; GC pauses',
                'business_impact':'none' if kind in ('baseline','recovery') else 'API-dependent transaction attempts fail; unique affected transactions unknown',
                'change_source':'AIAPI-platform-operations'}
            result.append({'category':'deploys' if kind in ('deployment','rollback') else 'annotations',
                'type':kind,'source':'AIAPI-platform-operations','title':title,
                'labels':labels,'payload_object':{'timestamp':datetime.fromtimestamp(at,timezone.utc).isoformat(),
                'change_summary':summary,**context}})
        return result
