"""
SoundTouch Open Cloud — Backend API
"""

from contextlib import asynccontextmanager
import asyncio
import logging

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from soundtouch.api import devices, presets, radio, zones, system, spotify, cloud
from soundtouch.api import setup as setup_api
from soundtouch.api import websocket as ws_router
from soundtouch.ws import device_poller
from soundtouch.discovery import DeviceDiscovery
from soundtouch.database import init_db
from soundtouch.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    discovery = DeviceDiscovery()
    asyncio.create_task(discovery.start())
    asyncio.create_task(device_poller())
    logger.info("SoundTouch Open Cloud started on port %s", settings.port)
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="SoundTouch Open Cloud",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(presets.router, prefix="/api/presets", tags=["presets"])
app.include_router(radio.router, prefix="/api/radio", tags=["radio"])
app.include_router(zones.router, prefix="/api/zones", tags=["zones"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(spotify.router, prefix="/api/spotify", tags=["spotify"])
app.include_router(ws_router.router, tags=["websocket"])
app.include_router(setup_api.router, prefix="/api/setup", tags=["setup"])
app.include_router(cloud.router, prefix="/cloudws", tags=["cloud"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# Serve pre-built React frontend in production (Docker)
# Static dir: /app/static (Docker) or relative in dev
_static = os.environ.get("STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "static"))
if os.path.isdir(_static):
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        file = os.path.join(_static, full_path)
        if os.path.isfile(file):
            return FileResponse(file)
        return FileResponse(os.path.join(_static, "index.html"))

    app.mount("/assets", StaticFiles(directory=os.path.join(_static, "assets")), name="assets")
