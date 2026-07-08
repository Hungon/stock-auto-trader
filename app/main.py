"""FastAPI application factory.

Resolves settings once, stores them in the process runtime, wires the API
routers, mounts static assets, and renders the Jinja page templates.

Run the web app with either:
    python -m app.cli chart
    uvicorn app.main:create_app --factory
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import ai, backtest, market, opportunity
from app.chart.demo import demo_settings
from app.core.config import Settings, demo_build_enabled, load_settings
from app.core.runtime import Runtime, set_runtime

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _resolve_settings(env_path: Path | None) -> tuple[Settings, bool]:
    try:
        return load_settings(env_path), False
    except ValueError:
        return demo_settings(), True


def create_app(env_path: Path | None = None) -> FastAPI:
    settings, demo_mode = _resolve_settings(env_path)
    set_runtime(Runtime(settings=settings, demo_mode=demo_mode))

    app = FastAPI(title="Stock Auto Trader", version="0.2.0")

    app.include_router(market.router)
    app.include_router(backtest.router)
    app.include_router(opportunity.router)
    app.include_router(ai.router)

    page_ctx = {"demo_build": demo_build_enabled()}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "chart.html", page_ctx)

    @app.get("/backtest", response_class=HTMLResponse)
    def backtest_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "backtest.html", page_ctx)

    @app.get("/opportunity", response_class=HTMLResponse)
    def opportunity_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "opportunity.html", page_ctx)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    env_path: Path | None = None,
) -> None:
    import uvicorn

    application = create_app(env_path)
    uvicorn.run(application, host=host, port=port, log_level="info")
