"""Full-population operation durations for Lens RED, independent of trace sampling.

The native-compatible OTLP exponential histogram and classic fallback record
the same completed operations and durations. Neither fabricates extra traffic.
"""
from opentelemetry.sdk.metrics.view import (
    View, ExplicitBucketHistogramAggregation, ExponentialBucketHistogramAggregation,
)
from sim.identity import service_labels
from sim import config as C

SPAN_VIEWS = [
    View(instrument_name='traces_span_metrics_duration',
         aggregation=ExponentialBucketHistogramAggregation()),
    View(instrument_name='traces_span_metrics_duration_seconds',
         aggregation=ExplicitBucketHistogramAggregation(
             [.001, .005, .01, .025, .05, .1, .25, .5, 1., 2.5, 5., 7.5, 10.])),
]


class SpanMetrics:
    def __init__(self, meter, service, instance=None):
        self.labels = {**service_labels(service, instance), 'service_name': service,
                       'span_metrics_source': 'simulator'}
        self.native = self.classic = None
        if C.EXPORT_LENS_SPAN_METRICS:
            self.native = meter.create_histogram('traces_span_metrics_duration')
            self.classic = meter.create_histogram('traces_span_metrics_duration_seconds')

    def record(self, name, duration, error=False, kind='SERVER'):
        if self.native is None: return
        labels = {**self.labels, 'span_name': name, 'span_kind': kind,
                  'status_code': 'STATUS_CODE_ERROR' if error else 'STATUS_CODE_OK'}
        self.native.record(duration, labels)
        self.classic.record(duration, labels)
