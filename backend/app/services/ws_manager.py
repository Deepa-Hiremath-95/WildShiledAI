import threading
import json
import logging
from datetime import datetime
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger("wildshield.ws")


class ConnectionManager:
    """
    Robust, thread-safe WebSocket connection manager for real-time dashboard updates.
    Handles multiple concurrent connections, silent disconnections, reconnects,
    and structured event broadcasting without raising uncaught exceptions.
    """
    def __init__(self):
        self.active: list[WebSocket] = []
        self._lock = threading.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self.active.append(ws)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active)}")

    async def disconnect(self, ws: WebSocket):
        with self._lock:
            if ws in self.active:
                self.active.remove(ws)
        logger.info(f"WebSocket client disconnected. Remaining connections: {len(self.active)}")

    def disconnect_sync(self, ws: WebSocket):
        """Synchronous disconnect fallback if event loop is closing."""
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, event_type: str, payload: Any):
        """
        Broadcasts an event message to all connected clients.
        Safely identifies and purges dead or disconnected client sockets.
        """
        message = json.dumps(
            {
                "type": event_type,
                "data": payload,
                "timestamp": datetime.utcnow().isoformat()
            },
            default=str
        )

        with self._lock:
            targets = list(self.active)

        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket client: {e}")
                stale.append(ws)

        if stale:
            with self._lock:
                for ws in stale:
                    if ws in self.active:
                        self.active.remove(ws)
            logger.debug(f"Cleaned up {len(stale)} disconnected WebSocket clients.")

    async def broadcast_detection(self, detection: dict):
        await self.broadcast("new_detection", detection)

    async def broadcast_alert(self, alert: dict):
        await self.broadcast("new_alert", alert)

    async def broadcast_alert_status(self, alert_id: str, status: str, read: bool):
        await self.broadcast("alert_status_changed", {"id": alert_id, "status": status, "read": read})

    async def broadcast_camera_status(self, camera_id: str, is_online: bool):
        await self.broadcast("camera_status_changed", {"camera_id": camera_id, "is_online": is_online})

    async def broadcast_siren(self, zone_id: str, siren_status: bool, reason: str = ""):
        event = "siren_on" if siren_status else "siren_off"
        await self.broadcast(event, {"zone_id": zone_id, "siren_status": siren_status, "reason": reason})

    async def broadcast_settings_updated(self, settings_dict: dict):
        await self.broadcast("settings_updated", settings_dict)


manager = ConnectionManager()
