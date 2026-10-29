"""One request outcome drives all signals. No actual customer traffic is sent."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math
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
    """One generated release, with a 30-second rollout/rollback stagger."""
    def __init__(self, start, repeat=None, launch_id=None):
        self.start = start
        self.repeat = C.INCIDENT_REPEAT if repeat is None else repeat
        self.id = launch_id or uuid.uuid4().hex
        stamp = datetime.fromtimestamp(start, timezone.utc).strftime('%Y%m%d.%H%M%S')
        self.version = f'gateway-release-{stamp}.{self.id[:12]}'
        self.previous = 'gateway-release-stable'
        self.profile = C.PROFILES[int(self.id,16) % len(C.PROFILES)]

    def position(self, now):
        elapsed = now-self.start
        return elapsed % 1800 if self.repeat else elapsed

    @staticmethod
    def pod_index(instance=None):
        return 1 if instance == C.SERVICE+'-1' else 0

    def incident(self, now, instance=None):
        stagger = 30*self.pod_index(instance)
        return 180+stagger <= self.position(now) < 1380+stagger

    def pressure(self, now, instance=None):
        rollback = 1380+30*self.pod_index(instance)
        pos = self.position(now)
        if self.incident(now, instance): return 1.
        return max(0., (rollback+30-pos)/30) if rollback <= pos < rollback+30 else 0.

    def arrivals(self, now):
        # Bounded independent waves, never a deployment-triggered load surge.
        elapsed = now-self.start
        return round(300+6*math.sin(elapsed/17)+3*math.sin(elapsed/43))

    def context(self, now, instance=None):
        pos = self.position(now)
        cycle = int((now-self.start)//1800) if self.repeat else 0
        stagger = 30*self.pod_index(instance)
        deployed = pos >= 180+stagger
        rolled_back = pos >= 1380+stagger
        changed = 1380 if rolled_back else 180 if deployed else 0
        at = self.start+cycle*1800+changed
        active = self.version if self.incident(now,instance) else self.previous
        return {'release.id': self.id, 'workflow.name': self.profile,
                'build_version': active, 'service.version': active,
                'release.previous_version': self.previous,
                'release.candidate_version': self.version,
                'release.change_scope': 'gateway code and bundled deployment resource configuration',
                'deployment.id': f'{self.id}-{cycle}-{changed}',
                'deployment.timestamp': datetime.fromtimestamp(at, timezone.utc).isoformat(),
                'deployment.pod.timestamp': datetime.fromtimestamp(at+(stagger if changed else 0), timezone.utc).isoformat(),
                'deployment.change_type': 'rollback' if rolled_back else 'release' if deployed else 'baseline',
                'deployment.mechanism': 'unvalidated',
                'scenario.phase': 'cpu-throttling' if self.incident(now,instance) else 'recovering' if self.pressure(now,instance)>0 else 'healthy'}

class Traffic:
    def __init__(self, scenario, seed=7):
        self.scenario, self.rng, self.sequence = scenario, random.Random(seed), 0

    def request(self, arrival_at):
        self.sequence += 1
        instance = C.SERVICE+f'-{self.sequence%2}'
        incident = self.scenario.incident(arrival_at,instance)
        pressure = self.scenario.pressure(arrival_at,instance)
        route = self.rng.choices(C.ROUTES,weights=(.45,.25,.30))[0]
        # Independent request outcomes with an approximately 20% timeout rate.
        error = incident and self.rng.random() < .20
        slow = pressure > 0 and not error and self.rng.random() < .33
        status = 504 if error else 201 if route.startswith('POST') else 200
        redis = self.rng.uniform(.0015,.0025)
        processing = self.rng.uniform(.019,.029) if incident else self.rng.uniform(.004,.008)
        rejection = self.rng.uniform(.003,.005)
        deadline = self.rng.uniform(4.5,5.5)
        queue = (deadline-redis-processing-rejection if error else
                 self.rng.uniform(.9,2.2)*pressure if slow else
                 self.rng.uniform(.08,.22)*pressure if pressure else self.rng.uniform(.001,.004))
        durations = [('gateway.request_queue', C.SERVICE, queue),
                     ('redis.rate_limit.check', C.REDIS, redis),
                     ('gateway.policy.evaluate', C.SERVICE, processing)]
        if error:
            # A gateway deadline is not a transport failure or a backend call.
            durations.append(('gateway.deadline_exceeded', C.SERVICE, rejection))
        else:
            backend = dict(zip(C.ROUTES,(.018,.035,.025)))[route]*self.rng.uniform(.85,1.15)
            durations.extend([('backend.http.request', C.BACKEND, backend),
                              ('gateway.response.encode', C.SERVICE, self.rng.uniform(.002,.004))])
        start = arrival_at
        completed_at = start+sum(x[2] for x in durations)
        t=start; stages=[]
        for index,(name,svc,duration) in enumerate(durations):
            end=completed_at if index==len(durations)-1 else min(completed_at,t+duration)
            stages.append(Stage(name,svc,t,end,504 if name=='gateway.deadline_exceeded' else 200));t=end
        attrs = self.scenario.context(arrival_at,instance)
        delayed = completed_at-start >= 1
        attrs.update({'request_id': f'{self.scenario.id[:12]}-{self.sequence}',
                      'http.request.method': route.split()[0], 'http.route': route.split()[1],
                      'http.response.status_code': status,
                      'business.operation': route,
                      'business.outcome': 'failed-attempt' if error else 'delayed' if delayed else 'completed',
                      'business.impact': 'API-dependent transaction attempt not completed; reconcile before retrying writes' if error else 'response delayed' if delayed else 'none',
                      'cpu.limit.cores': .25 if incident else 2.,
                      'error.type': 'GatewayDeadlineExceeded' if error else ''})
        return Request(attrs['request_id'],instance,route,start,completed_at,status,tuple(stages),attrs)
