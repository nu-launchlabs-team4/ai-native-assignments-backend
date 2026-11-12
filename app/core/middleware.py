import logging
import time
import uuid
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("app.request")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Reuse the caller's X-Request-ID or create one, and return it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status and duration. Never logs bodies or query strings."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            logger.info(
                "%s %s %s %.1fms request_id=%s",
                request.method,
                request.url.path,
                status_code,
                (time.perf_counter() - start) * 1000,
                getattr(request.state, "request_id", "-"),
            )


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    response = JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers=headers,
    )
    if request_id:
        # Unhandled errors bypass RequestIDMiddleware, so set the header here too.
        response.headers[REQUEST_ID_HEADER] = request_id
    return response


def _status_code_name(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return "error"


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return error_response(
        request, exc.status_code, _status_code_name(exc.status_code), message, exc.headers
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(request, 422, "validation_error", "Request validation failed")


def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Must be sync: SlowAPIMiddleware falls back to its own plain handler for async ones.
    return error_response(request, 429, "rate_limited", f"Rate limit exceeded: {exc.detail}")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error request_id=%s", getattr(request.state, "request_id", "-"))
    return error_response(request, 500, "internal_error", "Internal server error")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
