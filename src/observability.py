import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

_HANDLER_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """Minimal structured-JSON log formatter -- no new dependency, stdlib
    logging only. Both the deployed Lambda and any local script send stdout
    straight to CloudWatch Logs (Lambda) or a terminal (local), so one JSON
    object per line is immediately queryable in CloudWatch Logs Insights
    (e.g. `fields duration_ms | filter event = "align_stage"`) without any
    extra AWS resource, agent, or third-party logging service.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(fields)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """Returns a logger that emits structured JSON lines. Configures the
    root handler exactly once per process -- safe to call from every module
    that wants a logger, including repeatedly in tests.
    """
    global _HANDLER_CONFIGURED
    if not _HANDLER_CONFIGURED:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(logging.INFO)
        _HANDLER_CONFIGURED = True
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emits one structured log line with `event` as both the human-readable
    message and a queryable field, plus whatever else the caller passes.
    """
    logger.info(event, extra={"fields": {"event": event, **fields}})


@contextmanager
def timed(logger: logging.Logger, event: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Times the wrapped block and logs `event` with a `duration_ms` field
    once it exits (success or exception), merged with any fields passed up
    front plus any the caller adds to the yielded dict during the block --
    for values (like a result count) only known after the work finishes.
    """
    extra: dict[str, Any] = {}
    start = time.perf_counter()
    try:
        yield extra
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        log_event(logger, event, duration_ms=duration_ms, **fields, **extra)
