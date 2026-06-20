"""Standalone trading API server.

Mounts trading endpoints on /api/v1/trading, bypassing the broken
api.v1 package dependency chain (missing litellm, exchange-calendars, etc.).

Usage:
    uvicorn trading_server:app --host 0.0.0.0 --port 8000
"""
import importlib.machinery
import importlib.util
import sys
import types

# ============================================================
# Direct import of trading schemas (bypass broken api.v1 package)
# ============================================================
# Pre-register stub modules so api.v1.schemas.trading can be imported
for name in ["api", "api.v1", "api.v1.schemas"]:
    if name not in sys.modules:
        m = types.ModuleType(name)
        if hasattr(m, "__path__"):
            pass  # keep default
        sys.modules[name] = m

# Load schemas
loader = importlib.machinery.SourceFileLoader(
    "api.v1.schemas.trading", "api/v1/schemas/trading.py"
)
spec = importlib.util.spec_from_loader(
    "api.v1.schemas.trading", loader, origin="api/v1/schemas/trading.py"
)
schemas_mod = importlib.util.module_from_spec(spec)
sys.modules["api.v1.schemas.trading"] = schemas_mod
spec.loader.exec_module(schemas_mod)

# Load endpoints (which imports from schemas above)
loader2 = importlib.machinery.SourceFileLoader(
    "api.v1.endpoints.trading", "api/v1/endpoints/trading.py"
)
spec2 = importlib.util.spec_from_loader(
    "api.v1.endpoints.trading", loader2, origin="api/v1/endpoints/trading.py"
)
endpoints_mod = importlib.util.module_from_spec(spec2)
sys.modules["api.v1.endpoints.trading"] = endpoints_mod
spec2.loader.exec_module(endpoints_mod)

# ============================================================
# FastAPI app
# ============================================================
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="QuantWeasel Trading API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(endpoints_mod.router, prefix="/api/v1/trading")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "quantweasel-trading"}


class AuthStatusResponse(BaseModel):
    authEnabled: bool = False
    loggedIn: bool = True
    setupState: str = "enabled"


@app.get("/api/v1/auth/status")
async def auth_status():
    return AuthStatusResponse()


@app.post("/api/v1/auth/login")
async def auth_login():
    return AuthStatusResponse()


@app.get("/api/v1/auth/settings")
async def auth_settings():
    return AuthStatusResponse()


# ============================================================
# Mock endpoints for frontend API calls (non-trading, non-auth)
# ============================================================
# These return empty data so the dsa-web frontend can render
# without errors for API routes that have no backend yet.
MOCK_ENDPOINTS = {
    "/api/v1/health": {"status": "ok", "version": "3.22.0"},
    "/api/v1/stocks": {"stocks": [], "total": 0},
    "/api/v1/stocks/indices": {"indices": []},
    "/api/v1/history": {"items": [], "total": 0},
    "/api/v1/history/summary": {"total": 0},
    "/api/v1/analysis": {"analyses": [], "total": 0},
    "/api/v1/analysis/reports": {"reports": []},
    "/api/v1/backtest": {"results": []},
    "/api/v1/backtest/results": {"results": []},
    "/api/v1/portfolio": {"holdings": [], "total_pnl": 0},
    "/api/v1/portfolio/holdings": {"holdings": []},
    "/api/v1/agent": {"status": "idle"},
    "/api/v1/agent/models": {"models": []},
    "/api/v1/agent/skills": {"skills": []},
    "/api/v1/agent/experts/performance": {"performance": {}},
    "/api/v1/system": {"config": {}},
    "/api/v1/system/config": {"config": {}},
    "/api/v1/alerts": {"alerts": []},
    "/api/v1/usage": {"usage": {}},
    "/api/v1/decision-signals": {"signals": []},
    "/api/v1/alphasift": {"status": "idle"},
}

for _path, _mock_data in MOCK_ENDPOINTS.items():
    app.get(_path, include_in_schema=False)(
        lambda data=_mock_data: data
    )

# ============================================================
# Frontend static file serving (SPA)
# ============================================================
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_STATIC_DIR / "assets")),
        name="assets",
    )

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """Serve the SPA index.html for client-side routing."""
        if path.startswith("api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        index = _STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index), media_type="text/html")
        return JSONResponse({"detail": "Not Found"}, status_code=404)
else:
    import logging
    logging.warning("static/ directory not found. Build the frontend first.")
