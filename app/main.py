"""FastAPI entrypoint for the Markdown MCP server."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import load_config
from app.errors import ErrorResponse, McpError, error_response
from app.mcp import register_mcp_handlers
from app.user_scope import (
    AUTH_EXEMPT_PATHS,
    SERVICE_TOKEN_HEADER,
    USER_ID_HEADER,
    normalize_user_id,
)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = load_config()
        app.state.config = config
        app.state.library_path = config.library_path
        yield

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def enforce_request_identity(request: Request, call_next):
        path = request.url.path
        if path in AUTH_EXEMPT_PATHS:
            return await call_next(request)

        config = getattr(request.app.state, "config", None)
        require_user_header = bool(
            getattr(config, "require_user_header", True)
        )
        service_token = getattr(config, "service_token", None)

        if require_user_header:
            raw_user_id = request.headers.get(USER_ID_HEADER)
            if raw_user_id is None:
                error = ErrorResponse(
                    code="AUTH_REQUIRED",
                    message="Missing required user identity header.",
                    details={"header": USER_ID_HEADER},
                )
                return JSONResponse(
                    status_code=401, content=error_response(error)
                )
            try:
                request.state.user_id = normalize_user_id(raw_user_id)
            except McpError as exc:
                return JSONResponse(
                    status_code=401, content=error_response(exc.error)
                )

        if service_token:
            supplied_token = request.headers.get(SERVICE_TOKEN_HEADER)
            if supplied_token != service_token:
                error = ErrorResponse(
                    code="AUTH_FORBIDDEN",
                    message="Invalid service token.",
                    details={"header": SERVICE_TOKEN_HEADER},
                )
                return JSONResponse(
                    status_code=403, content=error_response(error)
                )

        return await call_next(request)

    @app.exception_handler(McpError)
    def handle_mcp_error(request: Request, exc: McpError) -> JSONResponse:
        return JSONResponse(status_code=400, content=error_response(exc.error))

    @app.get("/health", status_code=200)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    register_mcp_handlers(app)
    return app


app = create_app()
