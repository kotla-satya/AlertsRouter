import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("alerts_router")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        qs = f"?{request.url.query}" if request.url.query else ""
        logger.info("→ %s %s%s", request.method, request.url.path, qs)
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        logger.info(
            "← %d %s %s%s (%.1fms)",
            response.status_code, request.method, request.url.path, qs, ms,
        )
        return response
