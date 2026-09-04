"""
Internet radio search via RadioBrowser API.
TuneIn stream resolver for existing device presets.
"""

import logging
from fastapi import APIRouter, Query, HTTPException
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()

RADIOBROWSER_BASE = "https://de1.api.radio-browser.info/json"
TUNEIN_BASE = "https://opml.radiotime.com"


@router.get("/search")
async def search_stations(
    q: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=100),
    country: str = Query("", description="ISO country code filter"),
):
    params = {
        "name": q,
        "limit": limit,
        "hidebroken": "true",
        "order": "votes",
        "reverse": "true",
    }
    if country:
        params["countrycode"] = country.upper()

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{RADIOBROWSER_BASE}/stations/search",
                params=params,
                headers={"User-Agent": "SoundTouch-Open-Cloud/1.0"},
            )
            stations = r.json()
    except Exception as e:
        raise HTTPException(502, f"RadioBrowser error: {e}")

    return [
        {
            "id": s.get("stationuuid"),
            "name": s.get("name", "").strip(),
            "url": s.get("url_resolved") or s.get("url"),
            "country": s.get("country", ""),
            "language": s.get("language", ""),
            "tags": s.get("tags", ""),
            "favicon": s.get("favicon", ""),
            "votes": s.get("votes", 0),
            "bitrate": s.get("bitrate", 0),
            "codec": s.get("codec", ""),
        }
        for s in stations
        if s.get("url_resolved") or s.get("url")
    ]


@router.get("/top")
async def top_stations(limit: int = Query(50, ge=1, le=100)):
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{RADIOBROWSER_BASE}/stations/topvote/{limit}",
                params={"hidebroken": "true"},
                headers={"User-Agent": "SoundTouch-Open-Cloud/1.0"},
            )
            stations = r.json()
    except Exception as e:
        raise HTTPException(502, f"RadioBrowser error: {e}")

    return [
        {
            "id": s.get("stationuuid"),
            "name": s.get("name", "").strip(),
            "url": s.get("url_resolved") or s.get("url"),
            "country": s.get("country", ""),
            "favicon": s.get("favicon", ""),
            "votes": s.get("votes", 0),
            "bitrate": s.get("bitrate", 0),
            "codec": s.get("codec", ""),
        }
        for s in stations
        if s.get("url_resolved") or s.get("url")
    ]


@router.get("/tunein/resolve")
async def resolve_tunein(guide_id: str = Query(...)):
    """
    Resolve a TuneIn guide ID to a direct stream URL.
    Used to keep existing TuneIn presets working.
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{TUNEIN_BASE}/Tune.ashx",
                params={"id": guide_id, "formats": "mp3,aac,ogg", "render": "json"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(502, f"TuneIn resolve error: {e}")

    try:
        url = data["body"][0]["url"]
        return {"url": url, "guide_id": guide_id}
    except (KeyError, IndexError, TypeError):
        raise HTTPException(404, "Could not resolve TuneIn stream")
