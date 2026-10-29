"""OTel SDK pipeline shared by offline and explicitly authorized live execution."""
from dataclasses import replace
from opentelemetry import trace
from opentelemetry._logs import LogRecord, SeverityNumber
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, BatchSpanProcessor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor, BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import View, ExplicitBucketHistogramAggregation
from sim import config as C
from sim.identity import service_labels, resource_labels
from sim.span_metrics import SPAN_VIEWS, SpanMetrics
from sim import diagnostics

DURATION_VIEWS=[View(instrument_name=name,aggregation=ExplicitBucketHistogramAggregation(
    [.001,.005,.01,.025,.05,.1,.25,.5,1.,2.5,5.,7.5,10.]))
    for name in ('http_server_request_duration_seconds','http_client_request_duration_seconds',
                 'jvm_gc_pause_seconds','redis_command_duration_seconds')]

class Telemetry:
    def __init__(self, start, metric_exporter, span_exporter, log_exporter, batch=False):
        self.start=start; self.metric_exporter=metric_exporter; self.providers=[]; self.services={}
        self.span_exporter=span_exporter; self.log_exporter=log_exporter
        for svc in C.SERVICES:
            for instance in ([svc+'-0',svc+'-1'] if svc==C.SERVICE else [svc+'-0']):
                resource=Resource.create(resource_labels(svc,instance))
                reader=InMemoryMetricReader()
                mp=MeterProvider(resource=resource,metric_readers=[reader],views=SPAN_VIEWS+DURATION_VIEWS)
                tp=TracerProvider(resource=resource); tp.add_span_processor(BatchSpanProcessor(span_exporter, max_queue_size=8192) if batch else SimpleSpanProcessor(span_exporter))
                lp=LoggerProvider(resource=resource); lp.add_log_record_processor(BatchLogRecordProcessor(log_exporter, max_queue_size=8192) if batch else SimpleLogRecordProcessor(log_exporter))
                self.providers.extend([mp,tp,lp])
                meter=mp.get_meter('gravitee-stream')
                counter=lambda n,u='': meter.create_counter(n,unit=u)
                gauge=lambda n,u='': meter.create_gauge(n,unit=u)
                hist=lambda n: meter.create_histogram(n,unit='s')
                self.services[(svc,instance)]={'reader':reader,'tracer':tp.get_tracer('gravitee-stream'),
                    'logger':lp.get_logger('gravitee-stream'),'labels':service_labels(svc,instance),
                    'span':SpanMetrics(meter,svc,instance),
                    'requests':counter('http_client_requests_total' if svc==C.CLIENT else 'http_server_requests_total'), 'duration':hist('http_client_request_duration_seconds' if svc==C.CLIENT else 'http_server_request_duration_seconds'),
                    'cpu':counter('process_cpu_seconds_total','s'), 'memory':gauge('process_resident_memory_bytes','By'),
                    'network':counter('system_network_io_bytes_total','By'),
                    'read':counter('container_fs_reads_bytes_total','By'), 'write':counter('container_fs_writes_bytes_total','By'),
                    'info':gauge('demo_service_info'), 'limit':gauge('container_spec_cpu_quota_cores'),
                    'periods':counter('container_cpu_cfs_periods_total'),
                    'throttled':counter('container_cpu_cfs_throttled_periods_total'),
                    'throttle_time':counter('container_cpu_cfs_throttled_seconds_total','s'),
                    'queue':gauge('gravitee_gateway_pending_requests'),
                    'gc':hist('jvm_gc_pause_seconds'), 'redis':hist('redis_command_duration_seconds'),
                    'probe':gauge('gravitee_backend_probe_success'), 'ready':gauge('kube_pod_status_ready'),
                    'node':gauge('gravitee_node_cpu_available_cores'),
                    'synthetic':gauge('gravitee_synthetic_check_success'),'queue_seconds':0.,'interval_failures':0,
                    'failed':counter('gravitee_failed_request_attempts_total')}
    def service(self, svc, instance=None): return self.services[(svc,instance or svc+'-0')]
    def log(self, svc, now, body, attrs, instance=None, span=None):
        ctx=span.get_span_context() if span else None
        error=attrs.get('http.response.status_code',200)>=500
        self.service(svc,instance)['logger'].emit(LogRecord(timestamp=int(now*1e9),observed_timestamp=int(now*1e9),
            body=body,attributes={**service_labels(svc,instance),**attrs},
            severity_number=SeverityNumber.ERROR if error else SeverityNumber.INFO,
            severity_text='ERROR' if error else 'INFO',
            trace_id=ctx.trace_id if ctx else None,span_id=ctx.span_id if ctx else None))
    def request(self, req, sampled):
        gateway=self.service(C.SERVICE,req.instance)
        client=self.service(C.CLIENT)
        for svc,inst,duration,status,name,kind in [
            (C.SERVICE,req.instance,req.duration,req.status,req.route,'SERVER'),
            (C.CLIENT,None,req.duration,req.status,req.route,'CLIENT'),
            *[(s.service,None,s.end-s.start,s.status,s.name,'CLIENT') for s in req.stages if s.service!=C.SERVICE]]:
            m=self.service(svc,inst)
            labels={**m['labels'],'build_version': req.attrs['build_version'] if svc in (C.SERVICE,C.CLIENT) else 'dependency-stable',
                    'http_route':req.route,'http_response_status_code':str(status)}
            if svc != C.REDIS:
                m['requests'].add(1,labels);m['duration'].record(duration,labels)
            m['network'].add(7600, m['labels'])
            m['span'].record(name,duration,status>=500,kind)
        gateway['read'].add(512,{**gateway['labels'],'device':'overlay'}); gateway['write'].add(1024,{**gateway['labels'],'device':'overlay'})
        gateway['queue_seconds']+=req.stages[0].end-req.stages[0].start
        if req.status>=500:
            gateway['failed'].add(1,gateway['labels']);gateway['interval_failures']+=1
        root=server=None; children=[]; detail_spans={}
        plans=[diagnostics.details(req,stage) for stage in req.stages]
        if sampled:
            root=client['tracer'].start_span(req.route,kind=trace.SpanKind.CLIENT,start_time=int(req.start*1e9),attributes=req.attrs)
            server=gateway['tracer'].start_span(req.route,context=trace.set_span_in_context(root),kind=trace.SpanKind.SERVER,
                    start_time=int(req.start*1e9),attributes=req.attrs)
            for stage in req.stages:
                m=self.service(stage.service,req.instance if stage.service==C.SERVICE else None)
                child=m['tracer'].start_span(stage.name,context=trace.set_span_in_context(server),
                    kind=trace.SpanKind.INTERNAL if stage.service==C.SERVICE else trace.SpanKind.CLIENT,
                    start_time=int(stage.start*1e9), attributes=self.stage_attrs(req,stage))
                if stage.status>=500:
                    child.set_status(trace.Status(trace.StatusCode.ERROR,'gateway deadline expired'))
                    child.add_event('exception',{'exception.type':'GatewayDeadlineExceeded',
                        'exception.message':'CPU-throttled processing exhausted the caller deadline'},timestamp=int(stage.end*1e9))
                if stage.name=='gateway.request_queue' and req.status>=500:
                    child.set_status(trace.Status(trace.StatusCode.ERROR,'queue exhausted processing budget'))
                for detail in plans[len(children)]:
                    attrs={**req.attrs,**diagnostics.attributes(req,stage,detail)}
                    attrs.pop('http.response.status_code',None)
                    sub=m['tracer'].start_span(detail.name,context=trace.set_span_in_context(child),
                        kind=trace.SpanKind.INTERNAL,start_time=int(detail.start*1e9),attributes=attrs)
                    if detail.error:
                        sub.set_status(trace.Status(trace.StatusCode.ERROR,'insufficient gateway deadline budget'))
                    sub.add_event('gateway.stage.completed',{'deadline.remaining_seconds':attrs['deadline.remaining_seconds'],
                        'diagnostic.outcome':attrs['diagnostic.outcome']},timestamp=int(detail.end*1e9))
                    detail_spans[(len(children),detail.name)]=sub
                    sub.end(int(detail.end*1e9))
                children.append(child)
            if req.status>=500:
                for span in (root,server): span.set_status(trace.Status(trace.StatusCode.ERROR,'gateway deadline exceeded'))
        # Every error and >=1s request logs every actual stage, independent of sampling.
        if req.status>=500 or req.duration>=1 or sampled:
            for i,stage in enumerate(req.stages):
                attrs={**self.stage_attrs(req,stage),'stage.name':stage.name,'stage.duration_seconds':stage.end-stage.start,
                       'stage.status_code':stage.status,'request.duration_seconds':req.duration,
                       'diagnostic.reason':'error' if req.status>=500 else 'latency' if req.duration>=1 else 'baseline'}
                if stage.status>=500:
                    attrs['exception.stacktrace']='GatewayDeadlineExceeded: gateway request deadline exceeded\n  at gateway.deadline.check\n  at gateway.request_queue.resume'
                self.log(stage.service,stage.end,stage.name,attrs,
                    req.instance if stage.service==C.SERVICE else None,children[i] if sampled else None)
                for detail in plans[i]:
                    detail_attrs={**self.stage_attrs(req,stage),**diagnostics.attributes(req,stage,detail),
                        'diagnostic.reason':'error' if req.status>=500 else 'latency' if req.duration>=1 else 'baseline'}
                    self.log(stage.service,detail.end,detail.name,detail_attrs,
                        req.instance if stage.service==C.SERVICE else None,
                        detail_spans.get((i,detail.name)))
            self.log(C.SERVICE,req.end,'gateway.response',dict(req.attrs,**{'request.duration_seconds':req.duration}),req.instance,server)
            self.log(C.CLIENT,req.end,'caller.response',dict(req.attrs,**{'request.duration_seconds':req.duration}),span=root)
        for child,stage in zip(children,req.stages): child.end(int(stage.end*1e9))
        if server: server.end(int(req.end*1e9))
        if root: root.end(int(req.end*1e9))
    @staticmethod
    def stage_attrs(req,stage):
        attrs={**req.attrs,'http.response.status_code':stage.status,'error.type':req.attrs['error.type'] if stage.status>=500 else ''}
        if stage.service != C.SERVICE:
            attrs.update({'service.version':'dependency-stable','build_version':'dependency-stable','error.type':''})
        if stage.service==C.REDIS:
            attrs.pop('http.response.status_code',None)
            attrs.update({'db.system.name':'redis','db.operation.name':'EVAL','dependency.outcome':'success'})
        return attrs
    def tick(self, now, scenario):
        for (svc,inst),m in self.services.items():
            labels=m['labels']; gateway=svc==C.SERVICE
            incident=gateway and scenario.incident(now,inst)
            pressure=scenario.pressure(now,inst) if gateway else max(scenario.pressure(now,C.SERVICE+'-0'),scenario.pressure(now,C.SERVICE+'-1'))
            m['info'].set(1,labels)
            if svc in C.AKS_SERVICES or svc in (C.CLIENT,C.BACKEND):
                m['cpu'].add(.245 if gateway and incident else .6 if gateway else .08,labels)
                m['memory'].set((620 if gateway else 240)*2**20,labels)
                m['network'].add(1024,labels);m['read'].add(4096,{**labels,'device':'overlay'});m['write'].add(2048,{**labels,'device':'overlay'})
            if svc in C.AKS_SERVICES: m['ready'].set(1,labels)
            if gateway:
                m['limit'].set(.25 if incident else 2,labels)
                m['periods'].add(10,labels);m['throttled'].add(8 if incident else 0,labels)
                m['throttle_time'].add(.75 if incident else 0,labels)
                m['queue'].set(m['queue_seconds'],labels);m['queue_seconds']=0.
                m['node'].set(6.5,labels);m['gc'].record(.004,labels)
                m['synthetic'].set(0 if m['interval_failures'] else 1,labels);m['interval_failures']=0
            if svc==C.REDIS: m['redis'].record(.002,labels)
            if svc==C.BACKEND: m['probe'].set(1,labels)
            if int(now-scenario.start)% (1 if pressure else 30)==0 and svc in (C.SERVICE,C.REDIS,C.BACKEND):
                self.log(svc,now,'service.health', {**scenario.context(now,inst),
                    'diagnostic.cpu_throttled':bool(incident),'backend.probe.success':True,
                    'redis.latency_seconds':.002,'jvm.gc.pause_seconds':.004,
                    'node.cpu.available_cores':6.5,'cpu.limit.cores':.25 if incident and gateway else 2.,
                    'business.impact':'API-dependent transactions delayed or timed out' if pressure else 'none',
                    **({'service.version':'dependency-stable','build_version':'dependency-stable'} if svc!=C.SERVICE else {})},inst)
        self.export_metrics(now)
    def export_metrics(self, now):
        # SDK aggregation is cumulative. Stamp accelerated/offline exports with the
        # same logical clock as logs/traces, rather than wall-clock collection time.
        all_resources=[];template=None
        for m in self.services.values():
            data=m['reader'].get_metrics_data()
            if data is None: continue
            template=data
            rms=[]
            for rm in data.resource_metrics:
                scopes=[]
                for scope in rm.scope_metrics:
                    metrics=[]
                    for metric in scope.metrics:
                        points=[replace(p,time_unix_nano=int(now*1e9),**({'start_time_unix_nano':int(self.start*1e9)} if hasattr(p,'start_time_unix_nano') else {})) for p in metric.data.data_points]
                        metrics.append(replace(metric,data=replace(metric.data,data_points=points)))
                    scopes.append(replace(scope,metrics=metrics))
                rms.append(replace(rm,scope_metrics=scopes))
            all_resources.extend(rms)
        if template is not None:
            result=self.metric_exporter.export(replace(template,resource_metrics=all_resources))
            if result.name!='SUCCESS': raise RuntimeError('metric export failed')
    def shutdown(self):
        for p in self.providers: p.force_flush()
        for p in self.providers: p.shutdown()
        self.metric_exporter.shutdown()
