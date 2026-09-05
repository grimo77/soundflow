"""
Bose radio adapter emulator.

Bose speakers play internet radio via LOCAL_INTERNET_RADIO sources whose
location points at content.api.bose.io. That server takes a base64 JSON blob
describing the stream and redirects the speaker to the actual audio stream.

Once Bose's cloud shuts down (May 2026), that adapter dies and all internet
radio presets break. SoundFlow reimplements the same adapter locally so the
speaker can keep playing any stream.

The speaker requests:
  /core02/svc-bmx-adapter-orion/prod/orion/station?data=<base64-json>

The base64 JSON contains: {"streamUrl": "...", "name": "...", "imageUrl": "..."}
We decode it and redirect (302) the speaker to the real streamUrl.
"""

import base64
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

logger = logging.getLogger(__name__)
router = APIRouter()


def _decode_data(data: str) -> dict:
    # base64 may be URL-encoded or padded incorrectly; fix padding
    padded = data + "=" * (-len(data) % 4)
    raw = base64.b64decode(padded)
    return json.loads(raw)


@router.get("/core02/svc-bmx-adapter-orion/prod/orion/station")
@router.get("/{prefix:path}/svc-bmx-adapter-orion/{sub:path}/station")
async def orion_station(request: Request, data: str = ""):
    """
    Emulate Bose's Orion radio adapter.
    Decodes the stream descriptor and redirects the speaker to the real stream.
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

    logger.info("Orion adapter: redirecting '%s' → %s", name, stream_url)
    # 302 redirect the speaker straight to the real audio stream
    return RedirectResponse(stream_url, status_code=302)
