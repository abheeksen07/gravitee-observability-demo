"""Illustrative nested application calls and recovered transient error bursts.

Every call fits within its parent's interval. One explicit retry recovers each
injected transient fault; none of these calls access a customer system.
"""
from dataclasses import dataclass
import math
from sim import config as C

@dataclass(frozen=True)
class Call:
    service: str
    operation: str
    parent: int | None
    start: float
    end: float
    status: int = 200
    attempt: int = 1

# Absolute launch offsets (or episode offsets when explicit replay is enabled).
ERROR_WINDOWS=((C.AUTH,60,150,.22),(C.INVENTORY,420,570,.28),
               (C.PAYMENT,780,960,.25),(C.KAFKA,1080,1200,.24))
RPC_SERVICES=(C.AUTH,C.ORDERS,C.INVENTORY,C.BILLING,C.PAYMENT,C.NOTIFICATION)
EXTERNAL_SYSTEMS={C.MONGO:'mongodb',C.KAFKA:'kafka',C.SES:'email'}

def error_probability(service, position):
    for svc,start,end,peak in ERROR_WINDOWS:
        if svc==service and start<position<end:
            envelope=math.sin(math.pi*(position-start)/(end-start))**2
            pulse=.6+.4*math.sin(position/5.3)**2
            return peak*envelope*pulse
    return 0.


def plan(start, end, position, rng):
    """Sequential sibling RPCs with proper nesting and one bounded retry.

    Fractions refer to the successful attempt interval, allowing descendants to
    execute only after a failed initial attempt has recovered.
    """
    calls=[]
    def add(svc,op,parent,lo,hi,children=()):
        a,b=(start,end) if parent is None else (calls[parent].start,calls[parent].end)
        left=a+(b-a)*lo;right=a+(b-a)*hi
        failed=rng.random()<error_probability(svc,position)
        if failed:
            cut=left+(right-left)*.4
            calls.append(Call(svc,op,parent,left,cut,503,1))
            left=cut
        index=len(calls)
        calls.append(Call(svc,op,parent,left,right,200,2 if failed else 1))
        for child in children: add(*child[:2],index,*child[2:])
    mongo=(C.MONGO,'find account',.12,.72)
    inventory=(C.INVENTORY,'inventory.check',.03,.25,((C.MONGO,'find inventory',.10,.75),))
    billing=(C.BILLING,'billing.authorize',.29,.63,((C.PAYMENT,'payment.authorize',.10,.90),))
    publish=(C.KAFKA,'orders publish',.67,.77)
    notify=(C.NOTIFICATION,'notification.send',.81,.98,((C.SES,'email send',.10,.85),))
    add(C.AUTH,'auth.check',None,.02,.18,(mongo,))
    add(C.ORDERS,'orders.process',None,.21,.98,(inventory,billing,publish,notify))
    return tuple(calls)
