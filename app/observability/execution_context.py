"""Task-local correlation; child asyncio tasks inherit the same execution identity."""
from contextlib import contextmanager
from contextvars import ContextVar

_context = ContextVar("travel_execution", default=None)
_usage_sink = ContextVar("travel_usage_sink", default=None)

def current_execution():
    return _context.get() or {}

@contextmanager
def execution_scope(task_id, session_id, usage_sink=None):
    token = _context.set({"task_id": task_id, "session_id": session_id, "trace_id": task_id})
    sink_token = _usage_sink.set(usage_sink)
    try:
        yield
    finally:
        _usage_sink.reset(sink_token)
        _context.reset(token)

def record_usage(input_tokens, output_tokens, total_tokens):
    sink = _usage_sink.get()
    if sink:
        sink({"input_tokens": input_tokens, "output_tokens": output_tokens,
              "total_tokens": total_tokens})
