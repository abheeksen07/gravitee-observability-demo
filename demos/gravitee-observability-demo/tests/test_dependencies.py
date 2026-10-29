import unittest
from collections import Counter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.exporter.otlp.proto.common._internal.metrics_encoder import encode_metrics
from sim import config as C
from sim.dependencies import ERROR_WINDOWS, RPC_SERVICES, error_probability
from sim.main import SummarySink
from sim.model import Scenario, Traffic
from sim.offline import Metrics, Spans, Logs
from sim.sampling import Sampler
from sim.telemetry import Telemetry
from test_regression import CaptureMetrics


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.scenario=Scenario(0,expanded=True)
        self.traffic=Traffic(self.scenario)
        self.metrics=CaptureMetrics();self.spans=InMemorySpanExporter();self.logs=InMemoryLogRecordExporter()
        self.pipeline=Telemetry(0,self.metrics,self.spans,self.logs)
    def tearDown(self): self.pipeline.shutdown()
    def fault(self):
        for i in range(1000):
            req=self.traffic.request(105+i/1000)
            if req.attrs['dependency.recovered_errors']: return req
        self.fail('error window produced no dependency faults')

    def test_fanout_depth_parentage_protocols_and_wire_encoding(self):
        req=self.traffic.request(30)
        self.assertGreaterEqual(len({call.service for call in req.calls}),5)
        self.assertEqual(set(RPC_SERVICES),{c.service for c in req.calls if c.service in RPC_SERVICES})
        for call in req.calls:
            parent=next(s for s in req.stages if s.service==C.BACKEND) if call.parent is None else req.calls[call.parent]
            self.assertLessEqual(parent.start,call.start);self.assertLessEqual(call.end,parent.end)
        self.pipeline.request(req,True);self.pipeline.tick(31,self.scenario)
        spans=self.spans.get_finished_spans();by_id={s.context.span_id:s for s in spans}
        self.assertEqual(len({s.context.trace_id for s in spans}),1)
        depth=0
        for span in spans:
            chain=span;level=0
            while chain.parent:
                parent=by_id[chain.parent.span_id]
                self.assertLessEqual(parent.start_time,chain.start_time)
                self.assertLessEqual(chain.end_time,parent.end_time)
                chain=parent;level+=1
            depth=max(depth,level)
            if span.kind.name=='SERVER' and span.resource.attributes['service.name'] in RPC_SERVICES:
                caller=by_id[span.parent.span_id]
                self.assertEqual(caller.kind.name,'CLIENT')
                self.assertEqual(caller.attributes['peer.service'],span.resource.attributes['service.name'])
                self.assertEqual(caller.context.trace_id,span.context.trace_id)
        self.assertGreaterEqual(depth,8)
        # Managed DB/broker/email calls are caller-side spans, not fabricated servers.
        external=[s for s in spans if s.attributes.get('peer.service') in (C.MONGO,C.KAFKA,C.SES)]
        self.assertTrue(external)
        self.assertTrue(all(s.kind.name=='CLIENT' for s in external))
        self.assertTrue(all('http.response.status_code' not in s.attributes for s in external))
        self.assertTrue(any(s.attributes.get('db.system.name')=='mongodb' for s in external))
        self.assertTrue(any(s.attributes.get('messaging.system')=='kafka' for s in external))
        self.assertGreater(encode_metrics(self.metrics.data[-1]).ByteSize(),0)

    def test_error_bursts_fluctuate_recover_and_end_before_final_recovery(self):
        for service,start,end,peak in ERROR_WINDOWS:
            probabilities=[error_probability(service,t) for t in range(start,end)]
            self.assertGreater(max(probabilities),peak*.6)
            self.assertGreater(len({round(p,3) for p in probabilities}),20)
            self.assertTrue(all(0<=p<=peak for p in probabilities))
            self.assertEqual(error_probability(service,start-1),0)
            traffic=Traffic(Scenario(0,expanded=True),seed=13)
            errors=0
            for i in range(500):
                req=traffic.request((start+end)/2+i/1000)
                for j,call in enumerate(req.calls):
                    if call.status<500: continue
                    errors+=1;retry=req.calls[j+1]
                    self.assertEqual((retry.service,retry.parent,retry.attempt,retry.status),(call.service,call.parent,2,200))
                    self.assertAlmostEqual(retry.start,call.end)
            self.assertGreater(errors,20)
        for t in (1500,1800,3600):
            req=self.traffic.request(t)
            self.assertEqual(req.attrs['dependency.recovered_errors'],0)
            self.assertLess(req.status,500)
            self.assertLess(req.duration,1)

    def test_gateway_deadlines_never_invent_downstream_calls(self):
        failed=0
        for i in range(500):
            req=self.traffic.request(300+i/300)
            if req.status>=500:
                failed+=1;self.assertEqual(req.calls,())
                self.assertFalse(any(s.service==C.BACKEND for s in req.stages))
        self.assertGreater(failed,20)

    def test_failed_attempts_have_matching_span_log_and_population_metrics(self):
        req=self.fault();self.assertIn(req.status,(200,201))
        self.pipeline.request(req,True);self.pipeline.tick(106,self.scenario)
        errors=[c for c in req.calls if c.status>=500]
        spans=self.spans.get_finished_spans()
        bad=[s for s in spans if s.status.status_code.name=='ERROR']
        self.assertEqual(len(bad),2*len(errors)) # application CLIENT + SERVER
        self.assertTrue(all(s.attributes['error.type']=='TransientDependencyUnavailable' for s in bad))
        root=next(s for s in spans if s.parent is None)
        self.assertNotEqual(root.status.status_code.name,'ERROR')
        logs=[r.log_record for r in self.logs.get_finished_logs() if r.log_record.body=='dependency.response']
        self.assertEqual(len(logs),len(req.calls))
        failed_logs=[r for r in logs if r.attributes['dependency.status_code']>=500]
        self.assertEqual(len(failed_logs),len(errors))
        self.assertTrue(all(r.severity_text=='ERROR' and r.trace_id and r.span_id for r in failed_logs))
        error_points=[p for p in self.metrics.points('aiapi_dependency_calls_total') if p.attributes['outcome']=='error']
        self.assertEqual(sum(p.value for p in error_points),len(errors))
        for name in ('traces_span_metrics_duration','traces_span_metrics_duration_seconds'):
            points=[p for p in self.metrics.points(name) if p.attributes['status_code']=='STATUS_CODE_ERROR']
            self.assertEqual(sum(p.count for p in points),2*len(errors))

    def test_unsampled_faults_retain_errors_without_fabricated_trace_ids(self):
        req=self.fault();self.pipeline.request(req,False);self.pipeline.tick(106,self.scenario)
        self.assertEqual(self.spans.get_finished_spans(),())
        records=[r.log_record for r in self.logs.get_finished_logs() if r.log_record.body=='dependency.response']
        self.assertEqual(len(records),len(req.calls))
        self.assertTrue(all(not r.trace_id and not r.span_id for r in records))
        self.assertEqual(sum(p.value for p in self.metrics.points('aiapi_dependency_calls_total')),len(req.calls))

    def test_dependency_errors_have_a_separate_bounded_sampling_budget(self):
        sampler=Sampler();accepted=0
        for i in range(1000):
            req=self.fault()
            # Reuse a real fault plan at increasing completion times.
            from dataclasses import replace
            req=replace(req,end=100+i*.06)
            accepted+=sampler.take(req)
        self.assertGreater(accepted,80);self.assertLessEqual(accepted,98)

    def test_cross_phase_offline_pipeline_audits_all_dependency_outcomes(self):
        sink=SummarySink();pipeline=Telemetry(0,Metrics(sink),Spans(sink),Logs(sink));sampler=Sampler()
        totals=dict(requests=0,failed_attempts=0,dependency_calls=0,dependency_errors=0)
        try:
            for now in (30,105,300,450,510,840,900,1110,1170,1450,1860):
                requests=sorted((self.traffic.request(now+i/100) for i in range(100)),key=lambda r:r.end)
                for req in requests:
                    pipeline.request(req,sampler.take(req))
                    totals['requests']+=1;totals['failed_attempts']+=req.status>=500
                    totals['dependency_calls']+=len(req.calls)
                    totals['dependency_errors']+=req.attrs['dependency.recovered_errors']
                pipeline.tick(now+10,self.scenario)
            audit=sink.validate(totals)
            self.assertGreater(totals['dependency_calls'],9000)
            self.assertGreater(totals['dependency_errors'],40)
            self.assertEqual(audit['dependency_counts_errors_and_logs'],'passed')
        finally: pipeline.shutdown()

if __name__=='__main__': unittest.main()
