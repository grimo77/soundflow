"""
BMX (Bose Media eXchange) cloud emulation.

This is the heart of SoundFlow's cloud replacement. After Bose shuts down its
cloud (2026-05-06), speakers can no longer reach the BMX registry, the Marge
account service, or the scmudc event stream — which breaks presets and radio.

SoundFlow reimplements these endpoints locally so the speaker firmware keeps
working. The endpoint shapes are based on the community-reconstructed spec
(julius-d/ueberboese-api, SoundCork, AfterTouch).

Key endpoints the speaker calls on boot and during playback:
  GET  /bmx/registry/v1/services          → catalog of available cloud services
  GET  /marge/streaming/sourceproviders   → list of music services
  POST /v1/scmudc/{deviceId}              → event envelope (device → cloud)
  GET  /streaming/account/{acct}/device/  → account bootstrap

The scmudc ("SoundTouch Cloud Multi-Device Communication") stream is how the
speaker reports state and receives commands. We must answer it (not 405) or
the speaker considers the cloud dead and disables cloud-backed sources.
"""

import json
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from soundtouch.config import settings
from soundtouch.network import get_local_ip

logger = logging.getLogger(__name__)
router = APIRouter()


def _base_url() -> str:
    return f"http://{get_local_ip()}:{settings.port}"


# ── BMX Registry ──────────────────────────────────────────────────────────────
# The speaker asks the registry where to find each cloud service. We point every
# service back at SoundFlow itself.

@router.get("/bmx/registry/v1/services")
async def bmx_registry():
    base = _base_url()
    services = {
        "services": [
            {"name": "marge", "url": f"{base}/marge", "version": "1.0"},
            {"name": "streaming", "url": f"{base}/streaming", "version": "1.0"},
            {"name": "scmudc", "url": f"{base}/v1/scmudc", "version": "1.0"},
            {"name": "stats", "url": f"{base}", "version": "1.0"},
            {"name": "swupdate", "url": f"{base}/updates/soundtouch", "version": "1.0"},
        ]
    }
    return JSONResponse(services)


# ── scmudc event stream ───────────────────────────────────────────────────────
# The speaker POSTs its state here and long-polls for commands. We accept the
# event, log it, and return an empty command list (200 OK) so the stream stays
# alive. Command push (e.g. "play preset") will be added later.

@router.post("/v1/scmudc/{device_id}")
@router.get("/v1/scmudc/{device_id}")
async def scmudc(device_id: str, request: Request):
    body = b""
    try:
        body = await request.body()
    except Exception:
        pass

    if body:
        try:
            event = json.loads(body)
            logger.info("scmudc event from %s: %s", device_id, _summarize(event))
            # Full payload logging for protocol research (first 3000 chars)
            logger.info("scmudc FULL from %s: %s", device_id, json.dumps(event)[:3000])
        except Exception:
            logger.debug("scmudc raw from %s: %d bytes", device_id, len(body))

    # Empty envelope: acknowledge, no pending commands
    return JSONResponse({
        "deviceId": device_id,
        "events": [],
        "timestamp": int(time.time() * 1000),
    })


def _summarize(event) -> str:
    """Short human-readable summary of an scmudc event for logging."""
    if isinstance(event, dict):
        keys = list(event.keys())
        return f"keys={keys}"
    if isinstance(event, list):
        return f"list[{len(event)}]"
    return str(type(event))


# ── Marge account service ─────────────────────────────────────────────────────
# Marge handles the speaker's account. We return a minimal valid account so the
# speaker considers itself logged in and enables cloud-backed sources.

@router.get("/marge/streaming/sourceproviders")
@router.post("/marge/streaming/sourceproviders")
async def marge_sourceproviders():
    return JSONResponse({
        "sourceProviders": [
            {"id": "TUNEIN", "name": "TuneIn", "available": True},
            {"id": "LOCAL_INTERNET_RADIO", "name": "Internet Radio", "available": True},
            {"id": "SPOTIFY", "name": "Spotify", "available": True},
        ]
    })


@router.get("/streaming/account/{account_id}/device/{device_id}")
@router.get("/streaming/account/{account_id}/device/")
async def streaming_account_device(account_id: str, device_id: str = ""):
    """Account bootstrap — echo the device ID with a token so the speaker
    considers itself paired."""
    return JSONResponse({
        "accountId": account_id,
        "deviceId": device_id,
        "token": "soundflow-local-token",
        "status": "active",
    })


# ── Account full sync — provides the SOURCE LIST ──────────────────────────────
# This is the critical fix for UNKNOWN_SOURCE_ERROR. After the cloud shutdown,
# the speaker's Sources.xml collapses to only AUX. The speaker rebuilds its
# source list from this endpoint on boot. We must declare every source the
# speaker should be able to use (TUNEIN, LOCAL_INTERNET_RADIO, SPOTIFY, etc.),
# or /select will reject those sources.

def _account_sources() -> list[dict]:
    return [
        {"source": "TUNEIN", "sourceAccount": "TuneIn", "status": "READY",
         "displayName": "TuneIn", "isLocal": False, "multiroomallowed": True},
        {"source": "LOCAL_INTERNET_RADIO", "sourceAccount": "", "status": "READY",
         "displayName": "Internet Radio", "isLocal": False, "multiroomallowed": True},
        {"source": "SPOTIFY", "sourceAccount": "", "status": "READY",
         "displayName": "Spotify", "isLocal": False, "multiroomallowed": True},
        {"source": "STORED_MUSIC", "sourceAccount": "", "status": "READY",
         "displayName": "Stored Music", "isLocal": False, "multiroomallowed": True},
        {"source": "AUX", "sourceAccount": "", "status": "READY",
         "displayName": "AUX", "isLocal": True, "multiroomallowed": True},
        {"source": "BLUETOOTH", "sourceAccount": "", "status": "READY",
         "displayName": "Bluetooth", "isLocal": True, "multiroomallowed": False},
    ]


@router.get("/streaming/account/{account_id}/full")
@router.get("/marge/streaming/account/{account_id}/full")
async def account_full(account_id: str):
    """Full account sync including the all-important source list."""
    return JSONResponse({
        "accountId": account_id,
        "sources": _account_sources(),
        "presets": [],
        "status": "active",
    })


@router.get("/streaming/sources")
@router.get("/marge/streaming/sources")
async def streaming_sources():
    """Explicit source-list endpoint."""
    return JSONResponse({"sources": _account_sources()})


@router.get("/streaming/sourceproviders")
async def streaming_sourceproviders_bmx():
    """
    The speaker fetches this on boot to rebuild its source list. The response
    format must declare each source so the speaker adds it to Sources.xml.
    Without this, Sources.xml collapses to only AUX → UNKNOWN_SOURCE_ERROR.
    """
    return JSONResponse({
        "sourceProviders": [
            {
                "sourceName": "TUNEIN",
                "displayName": "TuneIn",
                "accountId": "TuneIn",
                "status": "AVAILABLE",
                "username": "TuneIn",
                "sourceAccountName": "TuneIn",
            },
            {
                "sourceName": "LOCAL_INTERNET_RADIO",
                "displayName": "Internet Radio",
                "accountId": "",
                "status": "AVAILABLE",
            },
            {
                "sourceName": "SPOTIFY",
                "displayName": "Spotify",
                "accountId": "",
                "status": "AVAILABLE",
            },
        ],
        "accountSources": [
            {"source": "TUNEIN", "sourceAccountName": "TuneIn", "status": "AVAILABLE"},
            {"source": "LOCAL_INTERNET_RADIO", "sourceAccountName": "", "status": "AVAILABLE"},
            {"source": "SPOTIFY", "sourceAccountName": "", "status": "AVAILABLE"},
        ],
    })


# ── Streaming catch-all (log everything the speaker asks for) ──────────────────

@router.api_route("/streaming/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def streaming_catchall(path: str, request: Request):
    body = b""
    try:
        body = await request.body()
    except Exception:
        pass
    logger.info("streaming catch-all: %s /streaming/%s (body: %d bytes)",
                request.method, path, len(body))
    if body:
        logger.info("  body content: %s", body.decode(errors="ignore")[:1500])
    return JSONResponse({"status": "OK"})


@router.get("/marge/{path:path}")
@router.post("/marge/{path:path}")
async def marge_catchall(path: str, request: Request):
    logger.info("marge catch-all: /%s %s", request.method, path)
    return JSONResponse({"status": "OK"})


# ── Streaming support (power, playback commands) ──────────────────────────────

@router.post("/streaming/support/{action}")
@router.get("/streaming/support/{action}")
async def streaming_support(action: str, request: Request):
    """Speaker reports support events (power_on, power_off, etc.). Acknowledge."""
    logger.info("streaming support: %s", action)
    return JSONResponse({"status": "OK", "action": action})


@router.get("/streaming/device/{device_id}/streaming_token")
async def streaming_token(device_id: str):
    """Return a streaming token so the speaker considers itself authorized."""
    return JSONResponse({
        "deviceId": device_id,
        "token": "soundflow-local-streaming-token",
        "expiresIn": 86400,
    })


# ── Software update (always up to date) ───────────────────────────────────────

@router.get("/updates/soundtouch/{path:path}")
async def sw_update(path: str):
    return JSONResponse({"available": False, "mandatory": False})


# ── Stats sink (swallow telemetry) ────────────────────────────────────────────

@router.post("/stats/{path:path}")
@router.post("/v1/stats/{path:path}")
async def stats_sink(path: str):
    return Response(status_code=204)
