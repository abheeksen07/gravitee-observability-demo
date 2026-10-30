"""Offline by default. --live is explicit and requires secure local credentials."""
import argparse
import json
import heapq
import os
import signal
import threading
import time
import urllib.request
from sim import config as C
from sim.events import Timeline
from sim.model import Scenario, Traffic
from sim.sampling import Sampler
from sim.telemetry import Telemetry
from sim.offline import Sink, Metrics, Spans, Logs

class SummarySink:
    """Audits SDK exports without serializing millions of payloads to disk."""
    summary=True
    def __init__(self):
        self.counts=dict(metrics=0,spans=0,logs=0,events=0)
        self.final_metrics={};self.final_state={};self.failed_logs=0;self.active_traces={};self.timing_errors=0;self.dependency_errors=0;self.dependency_metrics={};self.breakdown_metrics={}
    def write(self,kind,data): self.counts[kind]+=1
    def spans(self,spans):
        self.counts['spans']+=len(spans)
        for span in spans:
            pending=self.active_traces.setdefault(span.context.trace_id,{})
            pending[span.context.span_id]=span
            if span.parent is None:
                for child in pending.values():
                    if child.start_time>child.end_time: self.timing_errors+=1
                    if child.parent:
                        parent=pending.get(child.parent.span_id)
                        if parent is None or not parent.start_time<=child.start_time<=child.end_time<=parent.end_time:
                            self.timing_errors+=1
                del self.active_traces[span.context.trace_id]
    def logs(self,records):
        self.counts['logs']+=len(records)
        for exported in records:
            record=exported.log_record
            assert bool(record.trace_id)==bool(record.span_id)
            if record.body=='gateway.response' and record.attributes['http.response.status_code']>=500:
                self.failed_logs+=1
            if record.body=='dependency.response' and record.attributes['dependency.status_code']>=500:
                self.dependency_errors+=1
    def metrics(self,data):
        self.counts['metrics']+=1
        for rm in data.resource_metrics:
            instance=rm.resource.attributes['instance']
            native=classic=0
            for scope in rm.scope_metrics:
                for metric in scope.metrics:
                    points=metric.data.data_points
                    if metric.name in ('http_server_requests_total','aiapi_failed_request_attempts_total'):
                        self.final_metrics[(instance,metric.name)]=sum(p.value for p in points)
                    if metric.name in ('container_spec_cpu_quota_cores','aiapi_gateway_pending_requests','aiapi_synthetic_check_success'):
                        self.final_state[(instance,metric.name)]=points[-1].value
                    if metric.name=='api_gateway_breakdown':
                        self.breakdown_metrics[instance]=sum(p.value for p in points)
                    if metric.name=='aiapi_dependency_calls_total':
                        self.dependency_metrics[instance]=(sum(p.value for p in points),sum(p.value for p in points if p.attributes['outcome']=='error'))
                    if metric.name=='traces_span_metrics_duration': native=sum(p.count for p in points)
                    if metric.name=='traces_span_metrics_duration_seconds': classic=sum(p.count for p in points)
            assert native==classic
    def validate(self,totals):
        requests=sum(v for (instance,name),v in self.final_metrics.items() if instance.startswith(C.SERVICE+'-') and name=='http_server_requests_total')
        failures=sum(v for (instance,name),v in self.final_metrics.items() if name=='aiapi_failed_request_attempts_total')
        assert requests==totals['requests'], (requests,totals)
        assert sum(self.breakdown_metrics.values())==requests
        assert failures==totals['failed_attempts']==self.failed_logs
        assert sum(v[0] for v in self.dependency_metrics.values())==totals['dependency_calls']
        assert sum(v[1] for v in self.dependency_metrics.values())==totals['dependency_errors']==self.dependency_errors
        assert self.timing_errors==0 and not self.active_traces, self.timing_errors
        return {'full_population_requests':requests,'failed_attempt_metrics_and_detailed_logs':failures,
                'account_status_breakdown':'passed','dependency_counts_errors_and_logs':'passed','trace_parent_timing':'passed','native_classic_population':'passed'}
    def close(self): pass

def run(duration=None, fast=False, path=None, live=False, seed=7):
    if fast and live: raise ValueError('accelerated live export is prohibited')
    sink=Sink(path) if path else SummarySink()
    token=os.getenv('CHRONOSPHERE_API_TOKEN','') if live else ''
    if live:
        if not token: raise ValueError('CHRONOSPHERE_API_TOKEN must be supplied securely for live export')
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        metric=OTLPMetricExporter(endpoint=C.OTLP_ENDPOINT,headers=(('api-token',token),))
        spans=OTLPSpanExporter(endpoint=C.OTLP_ENDPOINT,headers=(('api-token',token),))
        logs=OTLPLogExporter(endpoint=C.LOGS_ENDPOINT,headers={'API-Token':token})
    else: metric,spans,logs=Metrics(sink),Spans(sink),Logs(sink)
    stop=threading.Event()
    def halt(*_): stop.set()
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,halt)
    start=time.time()-(duration+10 if fast else 0)
    scenario=Scenario(start); traffic=Traffic(scenario,seed); sampler=Sampler(); timeline=Timeline(scenario)
    pipeline=Telemetry(start,metric,spans,logs,batch=live)
    totals={'dependency_calls':0,'dependency_errors':0,'requests':0,'failed_attempts':0,'sampled_traces':0,'metric_ticks':0,'recovered_requests':0,'recovered_failures':0,'recovered_max_duration_seconds':0.}
    second=0;pending=[];sequence=0
    try:
        while not stop.is_set() and (duration is None or second<duration or pending):
            if not fast and stop.wait(max(0,start+second+1-time.time())): break
            now=start+second
            for event in timeline.due(now):
                if live:
                    request=urllib.request.Request(C.EVENTS_ENDPOINT,data=json.dumps({'event':event}).encode(),
                        headers={'API-Token':token,'Content-Type':'application/json'},method='POST')
                    # Never log response bodies or authentication headers.
                    try:
                        with urllib.request.urlopen(request,timeout=15) as response:
                            print('event accepted',event['type'],response.status,flush=True)
                    except Exception as exc:
                        print('event export failed',event['type'],type(exc).__name__,getattr(exc,'code',''),flush=True)
                else: sink.write('events',event)
                pipeline.log(C.SERVICE,now,event['title'],{**scenario.context(now),'event.name':event['type'],**event['labels']})
            if duration is None or second<duration:
                count=scenario.arrivals(now)
                for index in range(count):
                    req=traffic.request(now+(index+1)/(count+1))
                    sequence+=1;heapq.heappush(pending,(req.end,sequence,req))
            while pending and pending[0][0]<=now+1:
                _,_,req=heapq.heappop(pending)
                sampled=sampler.take(req);pipeline.request(req,sampled)
                totals['dependency_calls']+=len(req.calls)
                totals['dependency_errors']+=sum(c.status>=500 for c in req.calls)
                totals['requests']+=1;totals['failed_attempts']+=req.status>=500;totals['sampled_traces']+=sampled
                if not scenario.repeat and req.start>=start+1440:
                    totals['recovered_requests']+=1
                    totals['recovered_failures']+=req.status>=500
                    totals['recovered_max_duration_seconds']=max(totals['recovered_max_duration_seconds'],req.duration)
            pipeline.tick(now+1,scenario);totals['metric_ticks']+=1;second+=1
            if second%60==0: print(json.dumps({'elapsed_seconds':second,**totals}),flush=True)
    finally:
        pipeline.shutdown();sink.close()
    audit=sink.validate(totals) if not live and isinstance(sink,SummarySink) else {}
    if not live and isinstance(sink,SummarySink) and totals['recovered_requests']:
        assert totals['recovered_failures']==0 and totals['recovered_max_duration_seconds']<1
        for pod in (C.SERVICE+'-0',C.SERVICE+'-1'):
            assert sink.final_state[(pod,'container_spec_cpu_quota_cores')]==2
            assert sink.final_state[(pod,'aiapi_synthetic_check_success')]==1
            assert sink.final_state[(pod,'aiapi_gateway_pending_requests')]<2
        audit['post_rollback_normal_state']='passed'
    result={**totals,'signals':sink.counts,'release':scenario.version,'live':live,'audit':audit,'pending_at_shutdown':len(pending)}
    print(json.dumps(result),flush=True);return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true');p.add_argument('--offline',metavar='JSONL')
    p.add_argument('--fast',action='store_true');p.add_argument('--duration',type=int)
    args=p.parse_args()
    if args.live and args.offline: p.error('--live and --offline are exclusive')
    if args.fast and (args.live or not args.duration): p.error('--fast requires finite offline --duration')
    if args.duration is not None and args.duration<=0: p.error('duration must be positive')
    run(args.duration,args.fast,args.offline,args.live)
if __name__=='__main__': main()
