"""Scripted observations, not evidence of installed monitoring integrations."""
from datetime import datetime, timezone
from sim import config as C
from sim.identity import service_labels
MARKERS = (
 (0,'baseline','API transactions available','Gateway and backend checks healthy; CPU limit 2 cores.'),
 (180,'deployment','Gateway resource configuration changed','Container CPU limit reduced from 2 cores to 250 millicores. Deployment mechanism requires validation.'),
 (225,'degradation','API-dependent transactions timing out','Gateway latency and HTTP 504s increase; customer transaction attempts cannot complete.'),
 (270,'investigation','Backend slowdown investigated','Healthy backend probes and short successful backend calls contradict customer backend slowdown.'),
 (300,'infrastructure-check','Nodes have available CPU capacity','Gateway pods remain ready; node CPU available while container throttling rises after deployment.'),
 (360,'dependency-check','Redis and JVM hypotheses eliminated','Redis latency 2ms and normal 4ms GC pauses; no rate-limit bottleneck or GC pressure.'),
 (600,'diagnosis','Probable cause: gateway CPU limit regression','CFS throttling and queue waits begin with the deployment; backend services remain healthy.'),
 (1320,'mitigation','Restore prior CPU limits','Restore 2 cores and gradually roll gateways. Reconcile failed transactions before retrying writes.'),
 (1380,'rollback','Gateway CPU limits restored','Previous resource configuration restored; gradual rollout completes before recovery observation.'),
 (1440,'recovery','API latency and synthetic checks recovered','Throttling subsides; error rates, queue depth and API checks recover. Add resource checks and canary validation.'),
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
                'affected_services':C.SERVICE+', '+C.CLIENT, 'new_version':context['build_version'],'deployment_id':context['deployment.id'],
                'deployment_timestamp':context['deployment.timestamp'],
                'source_url':root+'/sim/model.py',
                'source_history_url':f'{C.SOURCE_REPOSITORY}/commits/{C.SOURCE_REFERENCE}/demos/gravitee-observability-demo/sim/model.py',
                'runbook_url':root+'/docs/runbook.md', 'evidence_url':root+'/docs/service-views.md',
                'evidence':'container_cpu_cfs_throttled_periods_total; gravitee_gateway_pending_requests; backend probes; Redis latency; GC pauses',
                'business_impact':'API-dependent transaction attempts fail; unique affected transactions unknown',
                'change_source':'gravitee-platform-operations'}
            result.append({'category':'deploys' if kind in ('deployment','rollback') else 'annotations',
                'type':kind,'source':'gravitee-platform-operations','title':title,
                'labels':labels,'payload_object':{'timestamp':datetime.fromtimestamp(at,timezone.utc).isoformat(),
                'change_summary':summary,**context}})
        return result
