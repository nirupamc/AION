"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import router as api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger


configure_logging(settings.log_level)
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup env=%s", settings.env)
    yield
    log.info("shutdown")


app = FastAPI(
    title="AION Music Intelligence",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "aion-api",
        "env": settings.env,
        "time": datetime.now(timezone.utc).isoformat(),
    }


app.include_router(api_router, prefix="")
