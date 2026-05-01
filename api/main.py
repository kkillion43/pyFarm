"""
FastAPI application — entry point for the HTTP + WebSocket server.

Startup wires up the relay controller reference into the relay routes.
The WebSocket /ws/live endpoint pushes the latest sensor reading as JSON
every N seconds (configured via api.ws_push_interval_seconds in config.yaml).
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config_loader import cfg
from database.db import get_latest_reading
from api.routes import sensors, relays, automation

logger = logging.getLogger(__name__)

# Injected by main.py before uvicorn starts
_relay_controller = None
_ws_clients: Set[WebSocket] = set()


def set_relay_controller(relay) -> None:
    global _relay_controller
    _relay_controller = relay
    relays.set_relay_controller(relay)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI starting up")
    asyncio.create_task(_ws_broadcast_loop())
    yield
    logger.info("FastAPI shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Greenhouse Pi",
    description="Sensor monitoring and relay control API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # LAN / Tailscale only — no public exposure
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensors.router)
app.include_router(relays.router)
app.include_router(automation.router)


# ---------------------------------------------------------------------------
# WebSocket — live sensor feed
# ---------------------------------------------------------------------------

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """
    Connect to receive a JSON push of the latest sensor reading every
    ws_push_interval_seconds seconds.
    """
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info("WebSocket client connected (%d total)", len(_ws_clients))
    try:
        while True:
            # Keep the connection alive by reading (client can send pings)
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)
        logger.info("WebSocket client disconnected (%d remaining)", len(_ws_clients))


async def _ws_broadcast_loop() -> None:
    """Background coroutine — broadcasts latest readings to all WS clients."""
    interval = cfg["api"].get("ws_push_interval_seconds", 10)
    sensor_ids = [s["id"] for s in cfg["sensors"]["soil"]]

    while True:
        await asyncio.sleep(interval)
        if not _ws_clients:
            continue

        payload = {}
        for sid in sensor_ids:
            row = get_latest_reading(sid)
            if row:
                payload[str(sid)] = {
                    c.name: getattr(row, c.name)
                    for c in row.__table__.columns
                }

        if not payload:
            continue

        message = json.dumps(payload, default=str)
        dead: Set[WebSocket] = set()
        for ws in list(_ws_clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
