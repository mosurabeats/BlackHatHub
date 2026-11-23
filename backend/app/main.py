"""FastAPI application factory."""
from __future__ import annotations

import ipaddress
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import auth, core, portfolio, research
from .config import get_settings
from .db import init_engine, session_scope
from .security import limiter

log = logging.getLogger("executive_hub")

ALLOWED_NETWORKS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "100.64.0.0/10",  # Tailscale CGNAT range
    "fd7a:115c:a1e0::/48",  # Tailscale IPv6
    "fe80::/10", "fc00::/7",
)]


def _ip_allowed(host: str | None) -> bool:
    if host in (None, "testclient", "testserver"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in n for n in ALLOWED_NETWORKS)


def bootstrap() -> None:
    """Create/upgrade the schema and seed reference data."""
    from .migrate import upgrade
    from .seed import seed

    s = get_settings()
    upgrade(s.resolved_database_url)
    init_engine(s.resolved_database_url)
    with session_scope() as db:
        seed(db)


def create_app(start_scheduler: bool | None = None, run_bootstrap: bool = True) -> FastAPI:
    s = get_settings()
    if start_scheduler is None:
        start_scheduler = s.scheduler_enabled and not s.is_test

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_bootstrap:
            bootstrap()
        if start_scheduler:
            from .jobs.scheduler import start_scheduler as _start

            _start()
        yield
        if start_scheduler:
            from .jobs.scheduler import stop_scheduler

            stop_scheduler()

    app = FastAPI(title="Executive Hub", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.client.host if request.client else None
        if not _ip_allowed(host):
            return JSONResponse({"detail": "Executive Hub is only reachable from the local network or Tailscale."}, status_code=403)
        if request.url.path.startswith("/api/") and not limiter.hit(f"api:{host}", s.api_rate_limit_per_minute, 60):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
        return JSONResponse({"detail": "Invalid request", "errors": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Internal error"}, status_code=500)  # never leak internals

    for r in (auth.router, core.router, research.router, portfolio.router):
        app.include_router(r)

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    static = Path(s.static_dir)
    if (static / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            f = (static / path).resolve()
            if path and f.is_file() and static.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(static / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_ui():
            return JSONResponse({"detail": "Frontend not built. Run scripts/build-frontend.sh"}, status_code=503)

    return app
