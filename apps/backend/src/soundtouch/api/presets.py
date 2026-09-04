from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import aiosqlite
from soundtouch.client import SoundTouchClient
from soundtouch.config import settings
from soundtouch.api.devices import _get_device_ip

router = APIRouter()


@router.get("/{device_id}")
async def get_presets(device_id: str):
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        presets = await client.get_presets()
        # sync to DB
        async with aiosqlite.connect(settings.db_path) as db:
            for p in presets:
                await db.execute("""
                    INSERT INTO presets (device_id, slot, name, source, source_account, location, icon_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, slot) DO UPDATE SET
                        name=excluded.name, source=excluded.source,
                        source_account=excluded.source_account,
                        location=excluded.location, icon_url=excluded.icon_url
                """, (device_id, p["slot"], p["name"], p["source"],
                      p["source_account"], p["location"], p["icon_url"]))
            await db.commit()
        return presets
    except Exception as e:
        raise HTTPException(502, str(e))


@router.post("/{device_id}/{slot}/select")
async def select_preset(device_id: str, slot: int):
    if slot < 1 or slot > 6:
        raise HTTPException(400, "Slot must be 1–6")
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        await client.select_preset(slot)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, str(e))


class PresetBody(BaseModel):
    name: str
    source: str
    location: str
    source_account: str = ""
    icon_url: str = ""


@router.put("/{device_id}/{slot}")
async def set_preset(device_id: str, slot: int, body: PresetBody):
    if slot < 1 or slot > 6:
        raise HTTPException(400, "Slot must be 1–6")
    ip = await _get_device_ip(device_id)
    client = SoundTouchClient(ip)
    try:
        await client.set_preset(
            slot, body.source, body.location,
            body.source_account, body.name, body.icon_url
        )
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                INSERT INTO presets (device_id, slot, name, source, source_account, location, icon_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id, slot) DO UPDATE SET
                    name=excluded.name, source=excluded.source,
                    source_account=excluded.source_account,
                    location=excluded.location, icon_url=excluded.icon_url
            """, (device_id, slot, body.name, body.source,
                  body.source_account, body.location, body.icon_url))
            await db.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, str(e))
