"""
Bose radio adapter emulator.

Bose speakers play internet radio via LOCAL_INTERNET_RADIO sources whose
location points at content.api.bose.io. That server takes a base64 JSON blob
describing the stream and streams the audio to the speaker.

Once Bose's cloud shuts down (May 2026), that adapter dies and all internet
radio presets break. SoundFlow reimplements the same adapter locally.

Crucially, most SoundTouch models can only play HTTP streams, not HTTPS, and
some can't follow redirects. So instead of redirecting, SoundFlow PROXIES the
stream: it opens the (possibly HTTPS) source itself and pipes the raw audio
back to the speaker over plain HTTP.
"""

import base64
import json
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, Response

logger = logging.getLogger(__name__)
router = APIRouter()


def _decode_data(data: str) -> dict:
    padded = data + "=" * (-len(data) % 4)
    raw = base64.b64decode(padded)
    return json.loads(raw)


async def _stream_proxy(stream_url: str):
    """Open the upstream audio stream and yield its chunks."""
    timeout = httpx.Timeout(10.0, read=None)  # no read timeout for continuous streams
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream(
                "GET", stream_url,
                headers={"User-Agent": "SoundFlow/1.0", "Icy-MetaData": "0"},
            ) as r:
                if r.status_code >= 400:
                    logger.warning("Upstream stream error %s for %s", r.status_code, stream_url)
                    return
                async for chunk in r.aiter_bytes(chunk_size=8192):
                    yield chunk
    except Exception as e:
        logger.warning("Stream proxy error for %s: %s", stream_url, e)
        return


@router.api_route("/core02/svc-bmx-adapter-orion/prod/orion/station", methods=["GET", "HEAD"])
@router.api_route("/{prefix:path}/svc-bmx-adapter-orion/{sub:path}/station", methods=["GET", "HEAD"])
async def orion_station(request: Request, data: str = ""):
    """
    Emulate Bose's Orion radio adapter by proxying the real stream.
    HEAD → return headers only (speaker probes the stream first).
    GET  → stream the audio through, converting HTTPS to HTTP.
    """
    if not data:
        return Response("missing data", status_code=400)

    try:
        info = _decode_data(data)
        stream_url = info.get("streamUrl", "")
        name = info.get("name", "Radio")
    except Exception as e:
        logger.warning("Orion adapter decode error: %s", e)
        return Response("bad data", status_code=400)

    if not stream_url:
        logger.warning("Orion adapter: no streamUrl in %s", info)
        return Response("no stream", status_code=404)

    # Probe upstream to learn the content type
    content_type = "audio/mpeg"
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
            probe = await c.head(stream_url, headers={"User-Agent": "SoundFlow/1.0"})
            ct = probe.headers.get("content-type")
            if ct and "audio" in ct:
                content_type = ct
    except Exception:
        pass  # some servers don't support HEAD; assume mpeg

    # HEAD request from speaker: just return headers
    if request.method == "HEAD":
        return Response(status_code=200, media_type=content_type)

    logger.info("Orion adapter: proxying '%s' → %s (%s)", name, stream_url, content_type)
    return StreamingResponse(
        _stream_proxy(stream_url),
        media_type=content_type,
        headers={"icy-name": name, "Cache-Control": "no-cache"},
    )
