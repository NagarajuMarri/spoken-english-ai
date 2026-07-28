from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
import logging

logger = logging.getLogger("spoken_english.errors")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        request = _
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={"error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", None),
            }},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        field = next(
            (str(item) for error in exc.errors() for item in error["loc"] if item != "body"),
            "request",
        )
        codes = {
            "proficiency_level": "invalid_proficiency_level",
            "learning_goal": "invalid_learning_goal",
            "daily_goal_minutes": "invalid_daily_goal",
            "native_language": "unsupported_native_language",
            "text": "empty_message",
        }
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": codes.get(field, "validation_error"),
                    "message": f"Invalid value for {field}.",
                    "request_id": getattr(_.state, "request_id", None),
                    "details": [
                        {
                            "type": error["type"],
                            "loc": [str(item) for item in error["loc"]],
                            "msg": error["msg"],
                        }
                        for error in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(OperationalError)
    async def handle_database_error(request: Request, _: OperationalError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {
                "code": "database_unavailable",
                "message": "A required dependency is unavailable.",
                "request_id": getattr(request.state, "request_id", None),
            }},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, _: Exception) -> JSONResponse:
        logger.error(
            "unhandled_application_error request_id=%s",
            getattr(request.state, "request_id", None),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {
                "code": "internal_error",
                "message": "An internal error occurred.",
                "request_id": getattr(request.state, "request_id", None),
            }},
        )
