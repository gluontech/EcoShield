# src/api/errors.py
"""Structured error handlers for the EcoShield API."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError


def register_error_handlers(app: FastAPI):
    """Register custom exception handlers."""

    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation Error",
                "detail": jsonable_encoder(exc.errors()),
                "status_code": 422,
            },
        )

    @app.exception_handler(FileNotFoundError)
    async def data_not_found(request: Request, exc: FileNotFoundError):
        return JSONResponse(
            status_code=503,
            content={
                "error": "Data Unavailable",
                "detail": str(exc),
                "status_code": 503,
            },
        )

    @app.exception_handler(Exception)
    async def general_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": str(exc),
                "status_code": 500,
            },
        )
