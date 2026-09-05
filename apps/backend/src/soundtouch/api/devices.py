import time
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import aiosqlite
from soundtouch.client import SoundTouchClient
from soundtouch.config import settings
from soundtouch.network import get_local_ip

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_device_ip(device_id: str) -> str:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ip FROM devices WHERE id=?", (device_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, f"Device {device_id} not found")
    return row["ip"]


@router.get("")
async def list_devices():
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM devices ORDER BY name") as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{device_id}/now_playing")
async def now_playing(device_id: str):
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        return await client.get_now_playing()
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/{device_id}/volume")
async def get_volume(device_id: str):
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        return await client.get_volume()
    except Exception as e:
        raise HTTPException(502, str(e))


class VolumeBody(BaseModel):
    level: int


@router.post("/{device_id}/volume")
async def set_volume(device_id: str, body: VolumeBody):
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        await client.set_volume(body.level)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, str(e))


class KeyBody(BaseModel):
    action: str  # play|pause|play_pause|stop|next|prev|power_on|power_off|mute


@router.post("/{device_id}/key")
async def send_key(device_id: str, body: KeyBody):
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        match body.action:
            case "play":        await client.play()
            case "pause":       await client.pause()
            case "play_pause":  await client.play_pause()
            case "stop":        await client.stop()
            case "next":        await client.next_track()
            case "prev":        await client.prev_track()
            case "power_on":    await client.power_on()
            case "power_off":   await client.power_off()
            case "mute":        await client.mute()
            case _:             raise HTTPException(400, f"Unknown action: {body.action}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))


class PlayUrlBody(BaseModel):
    url: str
    name: str = "Stream"
    image_url: str = ""


@router.post("/{device_id}/play_url")
async def play_url(device_id: str, body: PlayUrlBody):
    """
    Play an internet radio stream.

    Uses the LOCAL_INTERNET_RADIO source with SoundFlow acting as the radio
    adapter (replacing Bose's content.api.bose.io). The speaker fetches our
    adapter URL, which 302-redirects it to the real stream. This is the only
    method that plays arbitrary streams continuously on all SoundTouch models
    and keeps working after Bose's cloud shuts down.
    """
    import base64
    import json

    ip = await _get_device_ip(device_id)

    # Build the base64 stream descriptor exactly like Bose does
    descriptor = {
        "streamUrl": body.url,
        "name": body.name,
        "imageUrl": body.image_url,
    }
    data = base64.b64encode(json.dumps(descriptor).encode()).decode()

    # Point the location at SoundFlow's own adapter endpoint
    local = f"{get_local_ip()}:{settings.port}"
    location = (
        f"http://{local}/core02/svc-bmx-adapter-orion/prod/orion/station?data={data}"
    )

    content_item = (
        f'<ContentItem source="LOCAL_INTERNET_RADIO" type="stationurl" '
        f'location="{location}" sourceAccount="" isPresetable="true">'
        f'<itemName>{body.name}</itemName></ContentItem>'
    )

    try:
        client = SoundTouchClient(ip)
        await client.post("/select", content_item)
        return {"ok": True, "method": "local_internet_radio"}
    except Exception as e:
        raise HTTPException(502, f"Wiedergabe fehlgeschlagen: {e}")


@router.post("/{device_id}/refresh")
async def refresh_device(device_id: str):
    """Re-fetch device info and update DB."""
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        info = await client.get_info()
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute(
                "UPDATE devices SET name=?, model=?, firmware=?, last_seen=? WHERE id=?",
                (info["name"], info["model"], info["firmware"], time.time(), device_id)
            )
            await db.commit()
        return info
    except Exception as e:
        raise HTTPException(502, str(e))


class SetupBody(BaseModel):
    name: str


@router.post("/{device_id}/setup/name")
async def setup_name(device_id: str, body: SetupBody):
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        await client.set_name(body.name)
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("UPDATE devices SET name=? WHERE id=?", (body.name, device_id))
            await db.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, str(e))


@router.post("/scan")
async def manual_scan():
    """Trigger an immediate re-scan."""
    from soundtouch.discovery import DeviceDiscovery
    import asyncio
    disc = DeviceDiscovery()
    ips = await disc._ssdp_scan()
    for ip in ips:
        await disc._register(ip)
    return {"scanned": len(ips)}
