"""Local JSONL telemetry sink. Never contacts Chronosphere or requires a token."""
import json
import threading
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk._logs.export import LogRecordExporter, LogRecordExportResult
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult

class Sink:
    def __init__(self, path):
        self.file = open(path, 'a', encoding='utf-8')
        self.lock = threading.Lock()
        self.counts = {'spans': 0, 'logs': 0, 'metrics': 0, 'events': 0}

    def write(self, kind, data):
        with self.lock:
            self.file.write(json.dumps({'signal': kind, 'data': data}) + '\n')
            self.file.flush()
            self.counts[kind] += 1

    def close(self): self.file.close()

class Spans(SpanExporter):
    def __init__(self, sink): self.sink = sink
    def export(self, spans):
        if getattr(self.sink,'summary',False): self.sink.spans(spans)
        else:
            for span in spans: self.sink.write('spans', json.loads(span.to_json()))
        return SpanExportResult.SUCCESS
    def force_flush(self, timeout_millis=30000): return True
    def shutdown(self): pass

class Logs(LogRecordExporter):
    def __init__(self, sink): self.sink = sink
    def export(self, batch):
        if getattr(self.sink,'summary',False): self.sink.logs(batch)
        else:
            for record in batch: self.sink.write('logs', json.loads(record.to_json()))
        return LogRecordExportResult.SUCCESS
    def force_flush(self, timeout_millis=30000): return True
    def shutdown(self): pass

class Metrics(MetricExporter):
    def __init__(self, sink):
        super().__init__()
        self.sink = sink
    def export(self, metrics_data, timeout_millis=10000, **kwargs):
        if getattr(self.sink,'summary',False): self.sink.metrics(metrics_data)
        else: self.sink.write('metrics', json.loads(metrics_data.to_json()))
        return MetricExportResult.SUCCESS
    def force_flush(self, timeout_millis=10000): return True
    def shutdown(self, timeout_millis=30000, **kwargs): pass
