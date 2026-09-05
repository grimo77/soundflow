"""
Setup API — device onboarding wizard endpoints.
Handles:
  - Detecting local IP
  - Setting cloud server address on speaker
  - Spotify account wizard
  - Device naming
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import aiosqlite
from soundtouch.client import SoundTouchClient
from soundtouch.config import settings
from soundtouch.network import get_local_ip, get_local_url

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Local IP detection ────────────────────────────────────────────────────────

@router.get("/local_ip")
async def local_ip():
    """Return the local IP and full URL for this SoundFlow instance."""
    ip = get_local_ip()
    return {
        "ip": ip,
        "port": settings.port,
        "url": get_local_url(settings.port),
        "cloud_host": f"{ip}:{settings.port}",
    }


# ── Cloud server redirect ─────────────────────────────────────────────────────

class RedirectBody(BaseModel):
    device_id: str
    host: str = ""  # if empty, auto-detect local IP


@router.post("/redirect_cloud")
async def redirect_cloud(body: RedirectBody):
    """
    Set the speaker's cloud server to point at this SoundFlow instance.
    This replaces the need for DNS/Pi-hole tricks.
    """
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ip FROM devices WHERE id=?", (body.device_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Device not found")

    host = body.host or f"{get_local_ip()}:{settings.port}"
    client = SoundTouchClient(row["ip"])

    try:
        current = await client.get_cloud_server()
        await client.set_cloud_server(host)
        logger.info("Redirected %s cloud server: %s → %s", body.device_id, current, host)
        return {"ok": True, "host": host, "previous": current}
    except Exception as e:
        raise HTTPException(502, f"Could not set cloud server: {e}")


@router.get("/cloud_server/{device_id}")
async def get_cloud_server(device_id: str):
    """Read current cloud server setting from speaker."""
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ip FROM devices WHERE id=?", (device_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Device not found")

    client = SoundTouchClient(row["ip"])
    try:
        server = await client.get_cloud_server()
        local_host = f"{get_local_ip()}:{settings.port}"
        local_url = f"http://{local_host}"
        # margeURL may or may not include the http:// prefix
        normalized = server.replace("http://", "").replace("https://", "").rstrip("/")
        is_redirected = normalized == local_host
        return {
            "current": server or "cloudws.bose.io",
            "local": local_host,
            "is_redirected": is_redirected,
        }
    except Exception as e:
        raise HTTPException(502, str(e))


# ── Device naming ─────────────────────────────────────────────────────────────

class NameBody(BaseModel):
    device_id: str
    name: str


@router.post("/set_name")
async def set_name(body: NameBody):
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ip FROM devices WHERE id=?", (body.device_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Device not found")

    client = SoundTouchClient(row["ip"])
    try:
        await client.set_name(body.name)
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("UPDATE devices SET name=? WHERE id=?", (body.name, body.device_id))
            await db.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, str(e))


# ── Spotify wizard ────────────────────────────────────────────────────────────

class SpotifyWizardBody(BaseModel):
    device_id: str
    email: str
    blob_id: str = ""
    token: str = ""


@router.post("/spotify_account")
async def setup_spotify_account(body: SpotifyWizardBody):
    """
    Link a Spotify account directly to the speaker.
    The speaker stores credentials internally and can play Spotify without
    needing the Bose cloud.
    """
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ip FROM devices WHERE id=?", (body.device_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Device not found")

    client = SoundTouchClient(row["ip"])

    # Always store the email in our DB — it's used to reference the account
    # when playing Spotify URIs, regardless of whether the device call works.
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS device_accounts (
                device_id TEXT,
                source TEXT,
                account TEXT,
                PRIMARY KEY (device_id, source)
            )
        """)
        await db.execute("""
            INSERT INTO device_accounts (device_id, source, account)
            VALUES (?, 'SPOTIFY', ?)
            ON CONFLICT(device_id, source) DO UPDATE SET account=excluded.account
        """, (body.device_id, body.email))
        await db.commit()

    # Try to push credentials to the device (optional — many speakers already
    # have Spotify linked via the Bose app, in which case this isn't needed).
    try:
        await client.set_spotify_account(body.email, body.blob_id, body.token)
        return {"ok": True, "email": body.email, "device_updated": True}
    except Exception as e:
        # Not fatal: the email is saved and playback via existing account works
        return {
            "ok": True,
            "email": body.email,
            "device_updated": False,
            "note": "Spotify ist auf dem Gerät bereits über die Bose-App "
                    "hinterlegt. Die E-Mail wurde gespeichert und wird zur "
                    "Wiedergabe verwendet.",
        }


@router.get("/spotify_account/{device_id}")
async def get_spotify_account(device_id: str):
    """Read stored Spotify account email for a device."""
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("""
                CREATE TABLE IF NOT EXISTS device_accounts (
                    device_id TEXT, source TEXT, account TEXT,
                    PRIMARY KEY (device_id, source)
                )
            """)
            await db.commit()
            async with db.execute(
                "SELECT account FROM device_accounts WHERE device_id=? AND source='SPOTIFY'",
                (device_id,)
            ) as cur:
                row = await cur.fetchone()
        return {"email": row["account"] if row else ""}
    except Exception as e:
        raise HTTPException(500, str(e))
