"""FastAPI entry point for event ingestion and as-of execution reports."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
import sqlite3
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from . import __version__
from .events import AlertLimits, ExecutionBatch, Key
from .execution import build_execution_report
from .scope import ReportScope
from .storage import LedgerStore, RecordConflict


def create_app(database: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        path = database if database is not None else os.getenv("EXECUTION_DB", "reports/execution.sqlite3")
        application.state.ledger = LedgerStore(path)
        yield

    app = FastAPI(title="Execution Quality Monitor", version=__version__, lifespan=lifespan)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request: Request, exc: sqlite3.OperationalError):
        code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return JSONResponse({"detail": "execution ledger temporarily busy"}, 503, headers={"Retry-After": "1"})
        return JSONResponse({"detail": "execution ledger operation failed"}, 500)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/v1/ledger")
    def ledger(request: Request) -> dict:
        return request.app.state.ledger.statistics()

    @app.post("/v1/events")
    def ingest(batch: ExecutionBatch, request: Request) -> dict:
        try:
            return request.app.state.ledger.ingest(batch)
        except RecordConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/report")
    def report(
        request: Request,
        as_of: Annotated[AwareDatetime | None, Query()] = None,
        slippage_bps: Annotated[float, Query(ge=0, le=100_000)] = 40,
        latency_ms: Annotated[float, Query(gt=0, le=1e9)] = 1_000,
        missing_after_ms: Annotated[float, Query(gt=0, le=1e9)] = 5_000,
        venue: Annotated[Key | None, Query()] = None,
        route: Annotated[Key | None, Query()] = None,
        symbol: Annotated[Key | None, Query()] = None,
    ) -> dict:
        limits = AlertLimits(slippage_bps=slippage_bps, latency_ms=latency_ms, missing_after_ms=missing_after_ms)
        batch = request.app.state.ledger.snapshot(as_of)
        scope = ReportScope(venue=venue, route=route, symbol=symbol)
        return build_execution_report(batch, as_of=as_of, limits=limits, scope=scope)

    return app


app = create_app()
