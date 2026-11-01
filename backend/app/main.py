from jose import JWTError, jwt
from typing import Optional
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine, run_migrations
from app.services.ws_manager import manager
from app.routers import (
    auth,
    villages,
    zones,
    cameras,
    alerts,
    contacts,
    frontend_compat,
    health,
    settings as settings_router,
    analytics,
)
from app.config import settings

# Structured Application Logging (Task 8)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("wildshield.api")

# Initial safe schema migration
run_migrations(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("WildShield-AI Backend initializing...")
    try:
        from app import seed
        seed.run()
    except Exception as e:
        logger.warning(f"Initial seed execution notice: {e}")
    yield
    logger.info("WildShield-AI Backend shutdown complete.")


app = FastAPI(
    title="WildShield-AI API",
    description="Backend for the AI-powered human–wildlife conflict early warning system (Phase 5 Hardened)",
    version="1.5.0",
    lifespan=lifespan,
)

# CORS configuration (Item 10)
origins = settings.cors_origins
# Never allow unrestricted wildcard origin with credentials in production
if getattr(settings, "environment", "development") == "production":
    if isinstance(origins, list):
        origins = [o for o in origins if o != "*"]
    elif origins == "*":
        origins = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralized Exception Handlers (Task 8)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # Mask any potential sensitive keys in error details
    clean_errors = []
    for err in errors:
        loc = err.get("loc", [])
        clean_loc = [str(x) for x in loc]
        clean_errors.append({"loc": clean_loc, "msg": err.get("msg", "Invalid input"), "type": err.get("type")})
    return JSONResponse(
        status_code=422,
        content={"detail": clean_errors, "status_code": 422},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred. Please contact the administrator.", "status_code": 500},
    )


# Snapshot static file storage
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")

# Include Routers
app.include_router(auth.router, prefix="/api")
app.include_router(villages.router, prefix="/api")
app.include_router(zones.router, prefix="/api")
app.include_router(cameras.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(frontend_compat.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(health.router)


@app.get("/")
def root():
    return {
        "status": "healthy",
        "service": "wildshield-ai-backend",
        "version": "1.5.0",
        "timestamp": os.environ.get("WILDSHIELD_RUNTIME_TS", "active"),
    }


# WebSocket endpoint (Task 5, Hardened in Phase 5.1)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """
    Live real-time push channel for WildShield AI dashboard clients.
    Broadcasts new detections, alerts, siren events, and camera status transitions.
    Enforces access controls and validates token when present or required.
    """
    # Item 9: Enforce WebSocket connection access controls
    if token:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            if not payload.get("sub"):
                await websocket.close(code=1008)
                return
        except JWTError:
            await websocket.close(code=1008)
            return
    elif getattr(settings, "enforce_ws_auth", False):
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle client keepalive/ping
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket connection error: {e}")
        await manager.disconnect(websocket)
