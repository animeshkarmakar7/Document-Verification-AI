import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "path": request.url.path,
            }
        },
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    code = "http_error"
    if 400 <= exc.status_code < 500:
        code = "bad_request"

    return error_response(
        request=request,
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled request failed",
        extra={
            "_event": "request_unhandled_exception",
            "_path": request.url.path,
            "_method": request.method,
        },
    )

    return error_response(
        request=request,
        status_code=500,
        code="internal_server_error",
        message="An unexpected error occurred.",
    )
