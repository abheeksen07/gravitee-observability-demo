import unittest
from collections import Counter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from sim import config as C
from sim.model import Scenario, Traffic
from sim.telemetry import Telemetry
from test_regression import CaptureMetrics

class BreakdownTests(unittest.TestCase):
    def test_customer_status_counts_and_latency_match_completed_population(self):
        metrics=CaptureMetrics();logs=InMemoryLogRecordExporter()
        pipeline=Telemetry(0,metrics,InMemorySpanExporter(),logs)
        scenario=Scenario(0,expanded=True);traffic=Traffic(scenario)
        requests=[traffic.request(t+i/300) for t in (30,300,1500) for i in range(600)]
        try:
            for req in sorted(requests,key=lambda r:r.end):pipeline.request(req,False)
            pipeline.tick(1510,scenario)
            points=metrics.points('api_gateway_breakdown')
            durations=metrics.points('api_gateway_breakdown_duration_seconds')
            self.assertEqual(sum(p.value for p in points),len(requests))
            self.assertEqual(sum(p.count for p in durations),len(requests))
            self.assertAlmostEqual(sum(p.sum for p in durations),sum(r.duration for r in requests))
            actual=Counter()
            for p in points:
                actual[(p.attributes['account'],int(p.attributes['status_code']))]+=p.value
                self.assertEqual(C.SERVICE,'aiapi_api_gateway')
                for field in ('service','service_name','lens_service'):
                    self.assertEqual(p.attributes[field],'aiapi_api_gateway')
            self.assertTrue(all(rm.resource.attributes['service.name']=='aiapi_api_gateway'
                for data in metrics.data for rm in data.resource_metrics
                if any(m.name=='api_gateway_breakdown' for scope in rm.scope_metrics for m in scope.metrics)))
            self.assertEqual(actual,Counter((r.attrs['account'],r.status) for r in requests))
            self.assertEqual({p.attributes['account'] for p in points},set(C.ACCOUNTS))
            self.assertGreaterEqual(len(C.ACCOUNTS),10)
            self.assertEqual({r.status for r in requests},{200,201,404,504})
            for req in requests:
                if req.status==404:
                    self.assertTrue(req.route.startswith('GET'))
                    self.assertEqual(req.attrs['business.outcome'],'not-found')
                    self.assertEqual(next(s.status for s in req.stages if s.service==C.BACKEND),404)
                if req.status==504:self.assertGreaterEqual(req.duration,4.5-1e-6)
            self.assertTrue({'slow','timeout'}<={p.attributes['latency_band'] for p in points})
            not_found_logs=[r.log_record for r in logs.get_finished_logs() if r.log_record.body=='gateway.response' and r.log_record.attributes['http.response.status_code']==404]
            self.assertEqual(len(not_found_logs),sum(r.status==404 for r in requests))
            self.assertTrue(all(r.attributes['account'] in C.ACCOUNTS for r in not_found_logs))
        finally:pipeline.shutdown()

if __name__=='__main__':unittest.main()
