"""A bounded, shared stage plan for trace children and detailed request logs.

Children partition existing stage time. They add no requests, latency or retries.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Detail:
    name: str
    start: float
    end: float
    error: bool = False

def details(req, stage):
    if stage.name=='gateway.request_queue':
        wait=('gateway.cpu.cfs_wait' if req.attrs['cpu.limit.cores']==.25 else
              'gateway.queue.backlog_wait' if req.attrs['gateway.queue.pressure']>0 else 'gateway.queue.worker_wait')
        plan=(('gateway.queue.enqueue',.01), (wait,.80),
              ('gateway.scheduler.runnable_wait',.18),('gateway.queue.resume',.01))
    elif stage.name=='gateway.policy.evaluate':
        plan=(('gateway.policy.authentication',.35),('gateway.policy.authorization',.35),
              ('gateway.policy.rate_limit_decision',.30))
    elif stage.name=='gateway.deadline_exceeded':
        plan=(('gateway.deadline.check',.5),('gateway.response.write_timeout',.5))
    elif stage.name=='gateway.response.encode':
        plan=(('gateway.response.serialize',.65),('gateway.response.flush',.35))
    else: return ()
    t=stage.start; result=[]
    for i,(name,fraction) in enumerate(plan):
        end=stage.end if i==len(plan)-1 else min(stage.end,t+(stage.end-stage.start)*fraction)
        error=req.status>=500 and name in ('gateway.queue.resume','gateway.deadline.check','gateway.response.write_timeout')
        result.append(Detail(name,t,end,error));t=end
    return tuple(result)

def attributes(req, stage, detail):
    remaining=req.attrs['request.deadline_seconds']-(detail.end-req.start)
    return {'request_id':req.id, 'stage.parent':stage.name,'stage.name':detail.name,
            'stage.duration_seconds':detail.end-detail.start,
            'request.duration_seconds':req.duration,
            'request.http.response.status_code':req.status,
            'request.elapsed_seconds':detail.end-req.start,
            'deadline.remaining_seconds':max(0.,remaining),
            'diagnostic.stage_error':detail.error,
            'diagnostic.outcome':'insufficient-deadline-budget' if detail.error else 'completed',
            'error.type':'GatewayDeadlineExceeded' if detail.error else ''}
