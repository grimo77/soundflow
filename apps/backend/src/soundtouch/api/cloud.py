"""
Bose Cloud API emulator.

The speaker contacts this endpoint on every boot to:
  - Register itself
  - Get account info
  - Sync presets
  - Check for updates (we always say: up to date)

DNS or host-redirect points cloudws.bose.io → this container.
All endpoints return minimal valid XML that satisfies the speaker firmware.
"""

import logging
import time
import xml.etree.ElementTree as ET

import aiosqlite
from fastapi import APIRouter, Request
from fastapi.responses import Response

from soundtouch.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def xml_response(content: str) -> Response:
    return Response(content=content, media_type="application/xml")


# ── Speaker registration / heartbeat ─────────────────────────────────────────

@router.post("/device/register")
@router.get("/device/register")
async def cloud_register(request: Request):
    """Speaker registers itself on boot. We ACK and store its IP."""
    body = await request.body()
    device_id = ""
    ip = request.client.host if request.client else ""

    try:
        root = ET.fromstring(body)
        device_id = root.findtext("deviceID", "") or root.get("deviceID", "")
        name = root.findtext("name", "SoundTouch")
    except Exception:
        name = "SoundTouch"

    if device_id and ip:
        try:
            async with aiosqlite.connect(settings.db_path) as db:
                await db.execute("""
                    INSERT INTO devices (id, name, ip, mac, model, firmware, last_seen)
                    VALUES (?, ?, ?, '', '', '', ?)
                    ON CONFLICT(id) DO UPDATE SET ip=excluded.ip, last_seen=excluded.last_seen
                """, (device_id, name, ip, time.time()))
                await db.commit()
            logger.info("Cloud register: %s (%s) from %s", name, device_id, ip)
        except Exception as e:
            logger.warning("Cloud register DB error: %s", e)

    return xml_response("""<?xml version="1.0" encoding="UTF-8"?>
<registered>
  <status>OK</status>
  <deviceID>{}</deviceID>
</registered>""".format(device_id))


@router.get("/device/status")
@router.post("/device/status")
async def cloud_status():
    return xml_response("""<?xml version="1.0" encoding="UTF-8"?>
<status>
  <available>true</available>
  <maintenance>false</maintenance>
</status>""")


@router.get("/device/ping")
@router.post("/device/ping")
async def cloud_ping():
    return xml_response("<pong/>")


# ── Account info ──────────────────────────────────────────────────────────────

@router.get("/account")
@router.post("/account")
async def cloud_account():
    """Return a minimal valid account so the speaker doesn't show 'Not logged in'."""
    return xml_response("""<?xml version="1.0" encoding="UTF-8"?>
<account>
  <id>soundflow-local</id>
  <name>SoundFlow Local</name>
  <email>local@soundflow</email>
  <type>premium</type>
  <status>active</status>
</account>""")


@router.get("/account/login")
@router.post("/account/login")
async def cloud_login():
    return xml_response("""<?xml version="1.0" encoding="UTF-8"?>
<login>
  <status>OK</status>
  <token>soundflow-local-token</token>
</login>""")


# ── Presets sync ──────────────────────────────────────────────────────────────

@router.get("/presets")
@router.post("/presets")
async def cloud_presets(request: Request):
    """Return presets stored in local DB for this device."""
    device_id = request.query_params.get("deviceID", "")

    presets_xml = ""
    if device_id:
        try:
            async with aiosqlite.connect(settings.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM presets WHERE device_id=? ORDER BY slot", (device_id,)
                ) as cur:
                    rows = await cur.fetchall()

            for p in rows:
                account_attr = f'sourceAccount="{p["source_account"]}"' if p["source_account"] else ""
                presets_xml += f"""
  <preset id="{p['slot']}" createdOn="0" updatedOn="0">
    <ContentItem source="{p['source']}" type="uri"
      location="{p['location']}" {account_attr}
      isPresetable="true" itemName="{p['name']}">
      <containerArt>{p['icon_url']}</containerArt>
    </ContentItem>
  </preset>"""
        except Exception as e:
            logger.warning("Cloud presets DB error: %s", e)

    return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<presets>{presets_xml}
</presets>""")


# ── TuneIn / radio sources ────────────────────────────────────────────────────

@router.get("/tunein/search")
async def cloud_tunein_search(query: str = ""):
    """Proxy TuneIn search through local RadioBrowser as fallback."""
    return xml_response("""<?xml version="1.0" encoding="UTF-8"?>
<results>
  <status>OK</status>
</results>""")


# ── Spotify OAuth relay ───────────────────────────────────────────────────────

@router.get("/spotify/token")
@router.post("/spotify/token")
async def cloud_spotify_token():
    """Return stored Spotify token so speaker can authenticate."""
    from soundtouch.api.spotify import _get_token
    token = await _get_token()
    if token:
        return xml_response(f"""<?xml version="1.0" encoding="UTF-8"?>
<spotifyToken>
  <token>{token}</token>
  <status>OK</status>
</spotifyToken>""")
    return xml_response("""<?xml version="1.0" encoding="UTF-8"?>
<spotifyToken>
  <status>NOT_CONFIGURED</status>
</spotifyToken>""")


# ── Firmware / update check ───────────────────────────────────────────────────

@router.get("/firmware/update")
@router.post("/firmware/update")
async def cloud_firmware():
    """Tell speaker it's always up to date — prevent unwanted Bose firmware pushes."""
    return xml_response("""<?xml version="1.0" encoding="UTF-8"?>
<update>
  <available>false</available>
  <mandatory>false</mandatory>
</update>""")


# ── Catch-all for unknown cloud endpoints ─────────────────────────────────────

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def cloud_catchall(path: str, request: Request):
    logger.debug("Unhandled cloud endpoint: /%s %s", path, request.method)
    return xml_response("""<?xml version="1.0" encoding="UTF-8"?>
<response><status>OK</status></response>""")
