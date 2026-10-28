"""One request outcome drives all signals. No actual customer traffic is sent."""
from dataclasses import dataclass
from datetime import datetime, timezone
import random
import uuid
from sim import config as C

@dataclass(frozen=True)
class Stage:
    name: str
    service: str
    start: float
    end: float
    status: int = 200

@dataclass(frozen=True)
class Request:
    id: str
    instance: str
    route: str
    start: float
    end: float
    status: int
    stages: tuple
    attrs: dict
    @property
    def duration(self): return self.end - self.start

class Scenario:
    def __init__(self, start, repeat=None, launch_id=None):
        self.start = start
        self.repeat = C.INCIDENT_REPEAT if repeat is None else repeat
        self.id = launch_id or uuid.uuid4().hex
        stamp = datetime.fromtimestamp(start, timezone.utc).strftime('%Y%m%d.%H%M%S')
        self.version = f'gateway-resource-config-{stamp}.{self.id[:12]}'
        self.previous = 'gateway-resource-config-cpu-2-cores'
        self.profile = C.PROFILES[int(self.id,16) % len(C.PROFILES)]
    def position(self, now):
        elapsed = now-self.start
        return elapsed % 1800 if self.repeat else elapsed
    def incident(self, now): return 180 <= self.position(now) < 1380
    def pressure(self, now):
        pos=self.position(now)
        return 1. if self.incident(now) else max(0., (1440-pos)/60) if 1380 <= pos < 1440 else 0.
    def context(self, now):
        pos = self.position(now)
        cycle = int((now-self.start)//1800) if self.repeat else 0
        changed = 1380 if pos >= 1380 else 180 if pos >= 180 else 0
        deployment = f'{self.id}-{cycle}-{changed}'
        return {'release.id': self.id, 'workflow.name': self.profile,
                'build_version': self.version if self.incident(now) else self.previous,
                'service.version': self.version if self.incident(now) else self.previous,
                'deployment.id': deployment,
                'deployment.timestamp': datetime.fromtimestamp(self.start+cycle*1800+changed, timezone.utc).isoformat(),
                'deployment.mechanism': 'unvalidated', 'scenario.phase': 'cpu-throttling' if self.incident(now) else 'recovering' if self.pressure(now)>0 else 'healthy'}

class Traffic:
    def __init__(self, scenario, seed=7):
        self.scenario, self.rng, self.sequence = scenario, random.Random(seed), 0
    def request(self, arrival_at):
        self.sequence += 1
        incident = self.scenario.incident(arrival_at)
        # Exactly one in five requests times out during the 20-minute incident.
        error = incident and self.sequence % 5 == 0
        pressure = self.scenario.pressure(arrival_at)
        slow = pressure > 0 and not error and self.sequence % 3 == 0
        status = 504 if error else 201 if self.sequence % 3 == 1 else 200
        route = C.ROUTES[self.sequence % len(C.ROUTES)]
        if route.startswith('GET') and not error: status = 200
        queue = 4.97 if error else self.rng.uniform(1.1,2.0)*pressure if slow else .14*pressure if pressure else .002
        processing = .024 if incident else .006
        durations = [('gateway.request_queue', C.SERVICE, queue),
                     ('redis.rate_limit.check', C.REDIS, .002),
                     ('gateway.policy.evaluate', C.SERVICE, processing)]
        if error:
            # Deadline expires in the gateway. No customer backend call ran.
            durations.append(('gateway.deadline_exceeded', C.SERVICE, .004))
        else:
            durations.extend([('backend.http.request', C.BACKEND, .025), ('gateway.response.encode', C.SERVICE, .003)])
        start = arrival_at
        completed_at = start+sum(x[2] for x in durations)
        t=start; stages=[]
        for index,(name,svc,duration) in enumerate(durations):
            end=completed_at if index==len(durations)-1 else min(completed_at,t+duration)
            stages.append(Stage(name,svc,t,end,504 if name=='gateway.deadline_exceeded' else 200));t=end
        attrs = self.scenario.context(arrival_at)
        attrs.update({'request_id': f'{self.scenario.id[:12]}-{self.sequence}',
                      'http.request.method': route.split()[0], 'http.route': route.split()[1],
                      'http.response.status_code': status,
                      'business.operation': route, 'business.outcome': 'failed-attempt' if error else 'delayed' if completed_at-start>=1 else 'completed',
                      'business.impact': 'API-dependent transaction attempt not completed; reconcile before retrying writes' if error else 'response delayed' if slow else 'none',
                      'cpu.limit.cores': .25 if incident else 2.,
                      'error.type': 'GatewayDeadlineExceeded' if error else ''})
        return Request(attrs['request_id'], C.SERVICE+f'-{self.sequence%2}',route,start,completed_at,status,tuple(stages),attrs)
