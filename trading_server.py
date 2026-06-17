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
from fastapi.middleware.cors import CORSMiddleware

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
