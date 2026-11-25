import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request

trace_id_var = ContextVar("trace_id", default=None)

logger = logging.getLogger("soa.observability")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def setup_observability(app, service_name):

    @app.middleware("http")
    async def trace_requests(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID")

        if not trace_id or len(trace_id) > 128:
            trace_id = uuid.uuid4().hex

        token = trace_id_var.set(trace_id)
        start = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Trace-ID"] = trace_id
            return response

        finally:
            duration_ms = round(
                (time.perf_counter() - start) * 1000, 2
            )

            logger.info(json.dumps({
                "event": "http_request",
                "service": service_name,
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "timestamp": time.time()
            }, ensure_ascii=False))

            trace_id_var.reset(token)
