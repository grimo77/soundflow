"""
WebSocket hub — broadcasts live device state to all connected browser clients.
Each device is polled every 2 seconds; changes are pushed to subscribers.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        logger.debug("WS client connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)
        logger.debug("WS client disconnected (%d total)", len(self._clients))

    async def broadcast(self, data: dict[str, Any]):
        if not self._clients:
            return
        payload = json.dumps(data)
        dead = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        self._clients -= dead


manager = ConnectionManager()


async def device_poller():
    """
    Background task: polls all known devices every 2 s, broadcasts state diffs.
    Imported and started in main.py lifespan.
    """
    import aiosqlite
    from soundtouch.client import SoundTouchClient
    from soundtouch.config import settings

    prev: dict[str, dict] = {}

    while True:
        try:
            async with aiosqlite.connect(settings.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT id, ip, name FROM devices") as cur:
                    devices = await cur.fetchall()

            for row in devices:
                device_id, ip, name = row["id"], row["ip"], row["name"]
                try:
                    client = SoundTouchClient(ip)
                    np, vol = await asyncio.gather(
                        client.get_now_playing(),
                        client.get_volume(),
                    )
                    state = {"now_playing": np, "volume": vol}

                    # Only broadcast when something changed
                    if prev.get(device_id) != state:
                        prev[device_id] = state
                        await manager.broadcast({
                            "type": "state",
                            "device_id": device_id,
                            "device_name": name,
                            **state,
                        })
                except Exception as e:
                    logger.debug("Poll error for %s: %s", device_id, e)
                    # Broadcast offline event only on first failure
                    if prev.get(device_id, {}).get("online", True):
                        prev.setdefault(device_id, {})["online"] = False
                        await manager.broadcast({
                            "type": "offline",
                            "device_id": device_id,
                            "device_name": name,
                        })

        except Exception as e:
            logger.warning("Poller error: %s", e)

        await asyncio.sleep(2)
