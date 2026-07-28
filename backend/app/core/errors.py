from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
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
