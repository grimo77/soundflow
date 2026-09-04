import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import aiosqlite
from soundtouch.client import SoundTouchClient
from soundtouch.config import settings
from soundtouch.api.devices import _get_device_ip

router = APIRouter()


class ZoneCreateBody(BaseModel):
    name: str
    master_device_id: str
    member_device_ids: list[str]


@router.get("")
async def list_zones():
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM zones") as cur:
            rows = await cur.fetchall()
    return [
        {**dict(r), "member_ids": r["member_ids"].split(",") if r["member_ids"] else []}
        for r in rows
    ]


@router.post("")
async def create_zone(body: ZoneCreateBody):
    master_ip = await _get_device_ip(body.master_device_id)
    master_client = SoundTouchClient(master_ip)
    master_info = await master_client.get_info()
    master_mac = master_info["mac"]

    member_ips = []
    for mid in body.member_device_ids:
        ip = await _get_device_ip(mid)
        member_ips.append(ip)

    try:
        await master_client.create_zone(master_mac, member_ips)
    except Exception as e:
        raise HTTPException(502, str(e))

    zone_id = str(uuid.uuid4())
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT INTO zones (id, name, master_device_id, member_ids) VALUES (?,?,?,?)",
            (zone_id, body.name, body.master_device_id, ",".join(body.member_device_ids))
        )
        await db.commit()

    return {"id": zone_id, "name": body.name, "master": body.master_device_id, "members": body.member_device_ids}


@router.delete("/{zone_id}")
async def delete_zone(zone_id: str):
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM zones WHERE id=?", (zone_id,)) as cur:
            zone = await cur.fetchone()
    if not zone:
        raise HTTPException(404, "Zone not found")

    master_ip = await _get_device_ip(zone["master_device_id"])
    client = SoundTouchClient(master_ip)
    try:
        await client.remove_zone()
    except Exception as e:
        raise HTTPException(502, str(e))

    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM zones WHERE id=?", (zone_id,))
        await db.commit()

    return {"ok": True}
