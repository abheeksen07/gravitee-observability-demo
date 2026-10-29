"""Bounded synthetic infrastructure variation, independent of request RNG.

These are illustrative workload shapes, not hardware capacity predictions.
Counter deltas are nonnegative; stable dimensions never contain request IDs.
"""
import hashlib
import math


def variation(second, identity, signal):
    """Reproducible waves, fine noise and short bursts in approximately [-1, 1]."""
    digest=hashlib.blake2s(f'{identity}:{signal}'.encode(),digest_size=8).digest()
    phase=int.from_bytes(digest,'big')/2**64*math.tau
    tick=math.floor(second)
    noise=int.from_bytes(hashlib.blake2s(f'{identity}:{signal}:{tick}'.encode(),digest_size=4).digest(),'big')/2**32*2-1
    burst=max(0.,math.sin(second/11+phase))**12
    return .40*math.sin(second/19+phase)+.22*math.sin(second/4.7+phase*2)+.23*noise+.15*burst


def cpu_shares(second, identity):
    weights=[1+.35*variation(second,identity,f'cpu-{i}') for i in range(4)]
    total=sum(weights)
    return [w/total for w in weights]


# redis_exporter INFO / commandstats names. No exporter or Redis is installed.
REDIS_GAUGES=(
    'up','uptime_in_seconds','connected_clients','blocked_clients',
    'memory_used_bytes','memory_used_rss_bytes','memory_used_peak_bytes','memory_max_bytes',
    'mem_fragmentation_ratio','db_keys','db_keys_expiring',
)
REDIS_COUNTERS=(
    'commands_processed_total','commands_total','commands_duration_seconds_total',
    'keyspace_hits_total','keyspace_misses_total','expired_keys_total','evicted_keys_total',
    'net_input_bytes_total','net_output_bytes_total',
)


def redis_tick(m, elapsed):
    """Healthy cache housekeeping; EVAL stats come from actual modeled requests.

    GET/SET are explicitly synthetic background cache work (no added traces or
    HTTP requests). Stable db/cmd dimensions match redis_exporter conventions.
    """
    labels=m['labels']; instruments=m['redis_metrics']; identity=labels['instance']
    wave=variation(elapsed,identity,'cache')
    used=(180+12*wave)*2**20
    m['redis_peak']=max(m.get('redis_peak',0),used)
    values=dict(up=1,uptime_in_seconds=max(0,elapsed),connected_clients=24+round(4*wave),
                blocked_clients=0,memory_used_bytes=used,memory_used_rss_bytes=used*(1.16+.03*wave),
                memory_used_peak_bytes=m['redis_peak'],memory_max_bytes=512*2**20,
                mem_fragmentation_ratio=1.16+.03*wave)
    for name,value in values.items(): instruments[name].set(value,labels)
    for db,base in [('db0',18000),('db1',6000)]:
        keys=round(base*(1+.04*variation(elapsed,identity,db)))
        instruments['db_keys'].set(keys,{**labels,'db':db})
        instruments['db_keys_expiring'].set(round(keys*.72),{**labels,'db':db})
    counts={'get':round(90+18*wave),'set':round(30+8*wave)}
    for cmd,count in counts.items():
        attrs={**labels,'cmd':cmd}
        instruments['commands_total'].add(count,attrs)
        instruments['commands_duration_seconds_total'].add(count*(.00015 if cmd=='get' else .00025)*(1+.2*wave),attrs)
    total=sum(counts.values())
    hits=round(counts['get']*(.96+.015*wave))
    for name,value in dict(commands_processed_total=total,keyspace_hits_total=hits,
                           keyspace_misses_total=counts['get']-hits,expired_keys_total=round(8+3*wave),
                           evicted_keys_total=0,net_input_bytes_total=total*80,net_output_bytes_total=counts['get']*320+counts['set']*16).items():
        instruments[name].add(value,labels)
