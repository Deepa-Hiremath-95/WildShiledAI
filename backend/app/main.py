import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.services.ws_manager import manager
from app.routers import auth, zones, cameras, alerts, contacts, frontend_compat, health

from app.config import settings

Base.metadata.create_all(bind=engine)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app import seed
        seed.run()
    except Exception as e:
        import logging
        logging.getLogger("wildshield").warning(f"Initial seed check: {e}")
    yield


app = FastAPI(
    title="WildShield-AI API",
    description="Backend for the AI-powered human–wildlife conflict early warning system",
    version="1.0.0",
    lifespan=lifespan,
)

# Configurable CORS origins via settings.cors_origins
origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")

app.include_router(auth.router, prefix="/api")
app.include_router(zones.router, prefix="/api")
app.include_router(cameras.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(frontend_compat.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(health.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "wildshield-ai-backend"}




@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Live push channel for the dashboard. Currently informational only (the dashboard's
    api-service.js still polls REST endpoints) — wire this up in script.js with a plain
    `new WebSocket('ws://localhost:8000/ws')` and re-run hydrateDashboard() on message
    to get instant updates instead of a polling interval.
    """
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep the connection alive; dashboard doesn't send anything yet
    except WebSocketDisconnect:
        manager.disconnect(websocket)
