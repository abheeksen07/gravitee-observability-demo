import json
import socket
import unittest
from collections import Counter
from unittest.mock import patch
from opentelemetry.sdk.metrics.export import MetricExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.exporter.otlp.proto.common._internal.metrics_encoder import encode_metrics
from sim import config as C, diagnostics
from sim.events import Timeline
from sim.identity import resource_labels
from sim.model import Scenario, Traffic
from sim.sampling import Sampler
from sim.telemetry import Telemetry
from sim.main import run

class CaptureMetrics:
    def __init__(self): self.data=[]
    def export(self,data): self.data.append(data); return MetricExportResult.SUCCESS
    def shutdown(self): pass
    def points(self,name):
        return [p for d in self.data for rm in d.resource_metrics for sm in rm.scope_metrics
                for m in sm.metrics if m.name==name for p in m.data.data_points]

class ModelTests(unittest.TestCase):
    def test_complete_episode_and_continued_healthy_traffic(self):
        scenario=Scenario(0,launch_id='a'*32);traffic=Traffic(scenario)
        failures=0; phases=Counter(); events=[];timeline=Timeline(scenario); generated=0; active=0
        for second in range(3601):
            events.extend(timeline.due(second))
            count=scenario.arrivals(second)
            for i in range(count):
                req=traffic.request(second+(i+1)/(count+1))
                generated+=1;active+=req.attrs['scenario.phase']=='cpu-throttling'
                phases[req.attrs['scenario.phase']]+=1
                failures+=req.status>=500
                if req.status>=500:
                    self.assertFalse(any(s.service==C.BACKEND for s in req.stages))
                    self.assertGreaterEqual(req.duration,4.5-1e-6)
                    self.assertLessEqual(req.duration,5.5+1e-6)
                if second>=1440:
                    self.assertLess(req.duration,1)
                    self.assertLess(req.status,500)
        self.assertGreater(failures/active,.19)
        self.assertLess(failures/active,.21)
        self.assertGreater(failures,69000)
        self.assertLess(failures,75000)
        self.assertEqual(len(events),10)
        self.assertGreater(phases['cpu-throttling'],350000)
        self.assertEqual(scenario.context(3600)['build_version'],scenario.previous)
        replay=Scenario(0,repeat=True)
        self.assertTrue(replay.incident(1980)); self.assertFalse(scenario.incident(1980))
    def test_staggered_release_and_rollback_restore_each_pod(self):
        scenario=Scenario(0,launch_id='d'*32)
        a,b=C.SERVICE+'-0',C.SERVICE+'-1'
        for now,states in ((179,(False,False)),(180,(True,False)),(210,(True,True)),
                           (1380,(False,True)),(1410,(False,False)),(3600,(False,False))):
            self.assertEqual(tuple(scenario.incident(now,p) for p in (a,b)),states)
            for pod,regressed in zip((a,b),states):
                context=scenario.context(now,pod)
                self.assertEqual(context['service.version'],scenario.version if regressed else scenario.previous)
        self.assertEqual(scenario.context(210,b)['deployment.pod.timestamp'],'1970-01-01T00:03:30+00:00')
        self.assertEqual(scenario.context(1410,b)['deployment.change_type'],'rollback')
        self.assertEqual(scenario.pressure(1440,b),0)
        self.assertEqual(scenario.pressure(3600,a),0)

    def test_variance_does_not_add_a_load_surge_or_dependency_failures(self):
        scenario=Scenario(0); traffic=Traffic(scenario)
        arrivals=[scenario.arrivals(t) for t in range(3600)]
        self.assertGreater(max(arrivals)-min(arrivals),10)
        self.assertTrue(all(291<=n<=309 for n in arrivals))
        means=[sum(arrivals[a:b])/(b-a) for a,b in ((0,180),(210,1380),(1440,3600))]
        self.assertLess(max(means)-min(means),3)
        requests=[traffic.request(300+i/300) for i in range(6000)]
        deadlines={round(r.duration,2) for r in requests if r.status>=500}
        self.assertGreater(len(deadlines),30)
        for r in requests:
            for stage in r.stages:
                if stage.service in (C.REDIS,C.BACKEND):
                    self.assertEqual(stage.status,200)
                    self.assertLess(stage.end-stage.start,.05)
        baseline=[traffic.request(1500+i/300) for i in range(3000)]
        averages={route:sum(r.duration for r in baseline if r.route==route)/sum(r.route==route for r in baseline) for route in C.ROUTES}
        self.assertLess(averages[C.ROUTES[0]],averages[C.ROUTES[2]])
        self.assertLess(averages[C.ROUTES[2]],averages[C.ROUTES[1]])

    def test_latency_precedes_deadline_errors_and_budget_drives_status(self):
        rates=[]
        for offset in (0,15,30,45):
            traffic=Traffic(Scenario(0),seed=11)
            reqs=[traffic.request(180+offset) for _ in range(10000)]
            pod=[r for r in reqs if r.instance==C.SERVICE+'-0']
            rates.append(sum(r.status>=500 for r in pod)/len(pod))
            for req in reqs:
                self.assertEqual(req.status>=500,req.attrs['gateway.queue.demand_seconds']>=req.attrs['gateway.processing_budget_seconds'])
                if req.status>=500:
                    self.assertAlmostEqual(req.duration,req.attrs['request.deadline_seconds'],places=6)
                else: self.assertLess(req.duration,req.attrs['request.deadline_seconds'])
            if offset==15:
                self.assertTrue(any(r.duration>=1 for r in pod))
                self.assertTrue(all(r.status<500 for r in pod))
        self.assertEqual(rates[:2],[0,0])
        self.assertGreater(rates[2],.04)
        self.assertGreater(rates[3],rates[2]+.05)
        self.assertLess(rates[3],.23)

    def test_launch_context_and_metadata(self):
        a,b=Scenario(100),Scenario(100)
        self.assertNotEqual(a.version,b.version)
        first=Traffic(Scenario(0))
        for _ in range(100):
            request=first.request(270.01)
            if request.status==504: break
        self.assertEqual(request.status,504)
        self.assertGreaterEqual(request.start,270)
        self.assertGreaterEqual(request.end,274.5)
        self.assertEqual(a.context(1000)['build_version'],a.version)
        self.assertEqual(a.context(1480)['build_version'],a.previous)
        for svc in C.SERVICES:
            attrs=resource_labels(svc)
            self.assertEqual({attrs[x] for x in ('service','service_name','lens_service','service.name')},{svc})
            if svc in C.AKS_SERVICES:
                self.assertEqual(attrs['cloud.platform'],'azure_aks')
                self.assertNotIn('cloud.region',attrs)
            else:
                self.assertFalse(any(k.startswith(('cloud.','k8s.')) for k in attrs))
        self.assertNotIn('plant',resource_labels(C.SERVICE))
    def test_events_urls_and_timing(self):
        scenario=Scenario(100,launch_id='b'*32);timeline=Timeline(scenario)
        events=timeline.due(2000)
        self.assertEqual(len(events),10)
        by={e['type']:e for e in events}
        self.assertEqual(by['deployment']['labels']['new_version'],scenario.version)
        self.assertEqual(by['rollback']['labels']['new_version'],scenario.previous)
        self.assertEqual(by['baseline']['labels']['business_impact'],'none')
        self.assertEqual(by['recovery']['labels']['business_impact'],'none')
        self.assertEqual(by['deployment']['payload_object']['deployment.timestamp'],'1970-01-01T00:04:40+00:00')
        for event in events:
            self.assertIn(event['category'],('annotations','deploys'))
            for field in ('source_url','source_history_url','runbook_url','evidence_url'):
                self.assertTrue(event['labels'][field].startswith(C.SOURCE_REPOSITORY+'/'))
            for forbidden in ('demo','synthetic','test','scenario','deployment_url'):
                self.assertNotIn(forbidden,event['labels'])
        self.assertEqual(timeline.due(4000),[])
    def test_sampling_is_bounded_and_does_not_change_traffic(self):
        scenario=Scenario(0);a=Traffic(scenario);b=Traffic(scenario);sampler=Sampler()
        sampled=Counter()
        for i in range(18000):
            req=a.request(300+i/300)
            twin=b.request(300+i/300)
            self.assertEqual((req.status,req.duration),(twin.status,twin.duration))
            if sampler.take(req): sampled['error' if req.status>=500 else 'slow' if req.duration>=1 else 'normal']+=1
        self.assertLessEqual(sampled['error'],98);self.assertGreater(sampled['error'],80)
        self.assertLessEqual(sampled['slow'],106);self.assertLessEqual(sampled['normal'],22) # arrival window plus variable completion tails

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.metrics=CaptureMetrics();self.spans=InMemorySpanExporter();self.logs=InMemoryLogRecordExporter()
        self.p=Telemetry(0,self.metrics,self.spans,self.logs)
        self.scenario=Scenario(0,launch_id='c'*32);self.traffic=Traffic(self.scenario)
    def tearDown(self): self.p.shutdown()
    def requests(self):
        reqs=[]
        while len(reqs)<30: reqs.append(self.traffic.request(300+len(reqs)/300))
        return reqs
    def test_shared_http_outcomes_and_histogram_wire_encoding(self):
        reqs=self.requests()
        for req in reqs: self.p.request(req,True)
        self.p.tick(301,self.scenario)
        spans=self.spans.get_finished_spans()
        gateways=[s for s in spans if s.kind.name=='SERVER']
        self.assertEqual(len(gateways),30)
        statuses=Counter(r.status for r in reqs)
        points=[p for p in self.metrics.points('http_server_requests_total') if p.attributes['service']==C.SERVICE]
        actual=Counter()
        for point in points: actual[int(point.attributes['http_response_status_code'])]+=point.value
        self.assertEqual(actual,statuses)
        durations=[p for p in self.metrics.points('http_server_request_duration_seconds') if p.attributes['service']==C.SERVICE]
        self.assertAlmostEqual(sum(p.sum for p in durations),sum(r.duration for r in reqs),places=6)
        for req in reqs:
            root=next(s for s in gateways if s.attributes['request_id']==req.id)
            self.assertAlmostEqual((root.end_time-root.start_time)/1e9,req.duration,places=6)
            self.assertEqual(root.attributes['http.response.status_code'],req.status)
            record=next(x.log_record for x in self.logs.get_finished_logs() if x.log_record.body=='gateway.response' and x.log_record.attributes['request_id']==req.id)
            self.assertEqual(record.attributes['http.response.status_code'],req.status)
            self.assertEqual(record.trace_id,root.context.trace_id);self.assertEqual(record.span_id,root.context.span_id)
        native=self.metrics.points('traces_span_metrics_duration')
        classic=self.metrics.points('traces_span_metrics_duration_seconds')
        self.assertEqual(sum(x.count for x in native),sum(x.count for x in classic))
        self.assertTrue(native)
        for data in self.metrics.data:
            encoded=encode_metrics(data)
            self.assertGreater(encoded.ByteSize(),0)
        all_spans={s.context.span_id:s for s in spans}
        for span in spans:
            if span.parent:
                parent=all_spans[span.parent.span_id]
                self.assertGreaterEqual(span.start_time,parent.start_time)
                self.assertLessEqual(span.end_time,parent.end_time)
        self.assertTrue(any(s.name=='gateway.cpu.cfs_wait' for s in spans))
    def test_verbose_unsampled_logs_and_healthy_dependencies(self):
        reqs=self.requests()
        for req in reqs: self.p.request(req,False)
        self.assertEqual(len(self.spans.get_finished_spans()),0)
        records=[x.log_record for x in self.logs.get_finished_logs()]
        for req in reqs:
            selected=[r for r in records if r.attributes.get('request_id')==req.id]
            if req.status>=500 or req.duration>=1:
                self.assertEqual(len(selected),len(req.stages)+2+sum(len(diagnostics.details(req,s)) for s in req.stages))
                self.assertTrue(all(not r.trace_id and not r.span_id for r in selected))
                self.assertEqual({r.attributes['stage.name'] for r in selected if 'stage.name' in r.attributes}, {s.name for s in req.stages}|{d.name for s in req.stages for d in diagnostics.details(req,s)})
            else: self.assertEqual(selected,[])
            if req.status>=500:
                self.assertFalse(any(r.attributes['service_name']==C.BACKEND for r in selected))
        for record in records:
            svc=record.attributes['service_name']
            if svc in (C.REDIS,C.BACKEND):
                self.assertEqual(record.attributes['service.version'],'dependency-stable')
                self.assertFalse(record.attributes.get('error.type'))
                self.assertLess(record.attributes.get('stage.status_code',200),500)
    def test_detailed_spans_and_logs_share_exact_stage_plan(self):
        reqs=self.requests()
        for req in reqs: self.p.request(req,True)
        spans=self.spans.get_finished_spans()
        records=[r.log_record for r in self.logs.get_finished_logs()]
        for req in reqs:
            details=[d for stage in req.stages for d in diagnostics.details(req,stage)]
            for stage in req.stages:
                parts=diagnostics.details(req,stage)
                if parts:
                    self.assertEqual(parts[0].start,stage.start)
                    self.assertEqual(parts[-1].end,stage.end)
                    self.assertTrue(all(a.end==b.start for a,b in zip(parts,parts[1:])))
            for detail in details:
                span=next(s for s in spans if s.name==detail.name and s.attributes.get('request_id')==req.id)
                record=next(r for r in records if r.body==detail.name and r.attributes.get('request_id')==req.id)
                self.assertEqual(record.span_id,span.context.span_id)
                self.assertEqual(record.trace_id,span.context.trace_id)
                self.assertAlmostEqual((span.end_time-span.start_time)/1e9,record.attributes['stage.duration_seconds'],places=6)
                self.assertGreaterEqual(record.attributes['deadline.remaining_seconds'],0)
                self.assertEqual(span.status.status_code.name=='ERROR',detail.error)
            if req.status>=500:
                self.assertTrue(any(d.name=='gateway.response.write_timeout' and d.error for d in details))
            else:
                self.assertFalse(any(d.name=='gateway.response.write_timeout' for d in details))
        self.assertTrue(any(r.status>=500 for r in reqs))
        self.assertTrue(any(r.status<500 and r.duration>=1 for r in reqs))

    def test_one_second_cadence_health_and_counter_gauge_semantics(self):
        for second in (301,302,303,1441,1442,1470): self.p.tick(second,self.scenario)
        self.assertEqual(len(self.metrics.data),6) # one combined SDK export per second
        cpu=self.metrics.points('process_cpu_seconds_total')
        pod=[p for p in cpu if p.attributes['instance']==C.SERVICE+'-0']
        self.assertEqual([p.time_unix_nano for p in pod[:3]],[301000000000,302000000000,303000000000])
        self.assertTrue(all(b.value>=a.value for a,b in zip(pod,pod[1:])))
        memory=self.metrics.points('process_resident_memory_bytes')
        self.assertTrue(all(p.value>0 for p in memory))
        health=[r.log_record for r in self.logs.get_finished_logs() if r.log_record.body=='service.health' and r.log_record.attributes['service_name']==C.SERVICE]
        self.assertEqual(len(health),8) # two pods, three incident ticks, one quiet baseline tick
        self.assertTrue(all(.005 in p.explicit_bounds for p in self.metrics.points('jvm_gc_pause_seconds')))
        self.assertTrue(all(p.value==1 for p in self.metrics.points('gravitee_backend_probe_success')))
        self.assertTrue(all(abs(p.sum/p.count-.002)<1e-8 for p in self.metrics.points('redis_command_duration_seconds')))
    def test_per_pod_cpu_release_rollback_and_normal_final_state(self):
        times=(180,210,1380,1410,1440,1800,3600)
        for now in times: self.p.tick(now,self.scenario)
        for pod in (C.SERVICE+'-0',C.SERVICE+'-1'):
            limits=[p.value for p in self.metrics.points('container_spec_cpu_quota_cores') if p.attributes['instance']==pod]
            self.assertEqual(limits,[.25,.25,2,2,2,2,2] if pod.endswith('-0') else [2,.25,.25,2,2,2,2])
            throttled=[p.value for p in self.metrics.points('container_cpu_cfs_throttled_periods_total') if p.attributes['instance']==pod]
            self.assertEqual(throttled[-3:],[throttled[-3]]*3)
        self.assertTrue(all(p.value==1 for p in self.metrics.points('gravitee_synthetic_check_success')))
        events={e['type']:e for e in Timeline(self.scenario).due(3600)}
        self.assertIn('code release',events['deployment']['labels']['change_summary'])
        self.assertEqual(events['rollback']['labels']['previous_version'],self.scenario.version)
        self.assertEqual(events['rollback']['labels']['new_version'],self.scenario.previous)
        self.assertIn('previous gateway release',events['recovery']['labels']['change_summary'])

    def test_offline_pipeline_cannot_connect_and_safe_cli(self):
        with patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
            result=run(duration=2,fast=True)
        self.assertEqual(result['requests'],600)
        self.assertEqual(result['metric_ticks'],3) # final partial-second arrivals drain
        self.assertEqual(result['pending_at_shutdown'],0)
        self.assertFalse(result['live'])
        with self.assertRaises(ValueError): run(duration=1,fast=True,live=True)

if __name__=='__main__': unittest.main()
