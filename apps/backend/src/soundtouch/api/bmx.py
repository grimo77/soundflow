"""
BMX (Bose Media eXchange) cloud emulation — spec-conformant.

Reimplements the Bose SoundTouch streaming cloud so speakers keep working after
the official shutdown (2026-05-06). Endpoint shapes and XML formats follow the
community-reconstructed OpenAPI spec (julius-d/ueberboese-api), saved at
docs/bose-cloud-api-reference.yaml.

The speaker contacts four API domains, all served here:
  - marge:  account, source providers, presets, recents, devices
  - stats:  telemetry (we swallow it)
  - bmx:    streaming radio services
  - swupdate: firmware (we always say up-to-date)

CRITICAL INSIGHT: The speaker rebuilds its Sources.xml from the presets and
source-providers responses on boot. Every source referenced by a preset must
also be declared, or the speaker reports INVALID_SOURCE / UNKNOWN_SOURCE_ERROR.

All responses use Content-Type application/vnd.bose.streaming-v1.2+xml.
"""

import json
import logging
import time

import aiosqlite
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from soundtouch.config import settings
from soundtouch.network import get_local_ip

logger = logging.getLogger(__name__)
router = APIRouter()

BOSE_XML_CT = "application/vnd.bose.streaming-v1.2+xml"


def xml_response(content: str, status: int = 200) -> Response:
    if not content.lstrip().startswith("<?xml"):
        content = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + content
    return Response(content=content, media_type=BOSE_XML_CT, status_code=status,
                    headers={"ETag": str(int(time.time() * 1000))})


def _base_url() -> str:
    return f"http://{get_local_ip()}:{settings.port}"


# ── Source providers ──────────────────────────────────────────────────────────
# The speaker fetches this on boot. Each <sourceprovider> tells the speaker a
# music service exists. The IDs match Bose's known provider IDs (25=TuneIn,
# 15=Spotify) so preset sourceproviderid references resolve.

SOURCE_PROVIDERS = [
    ("25", "TUNEIN"),
    ("15", "SPOTIFY"),
    ("18", "LOCAL_MUSIC"),
    ("19", "STORED_MUSIC"),
]


@router.get("/streaming/sourceproviders")
async def get_source_providers():
    items = ""
    for pid, name in SOURCE_PROVIDERS:
        items += f"""  <sourceprovider id="{pid}">
    <createdOn>2012-09-19T12:43:00.000+00:00</createdOn>
    <name>{name}</name>
    <updatedOn>2012-09-19T12:43:00.000+00:00</updatedOn>
  </sourceprovider>
"""
    return xml_response(f"<sourceProviders>\n{items}</sourceProviders>")


# ── Presets ───────────────────────────────────────────────────────────────────
# The speaker fetches presets on boot and rebuilds its preset buttons + sources.
# We serve presets stored in SoundFlow's DB, converted to Bose XML format.

async def _load_presets(device_id: str) -> list[dict]:
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM presets WHERE device_id=? ORDER BY slot", (device_id,)
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("load presets error: %s", e)
        return []


def _preset_xml(p: dict) -> str:
    slot = p.get("slot", 0)
    name = _esc(p.get("name", ""))
    location = _esc(p.get("location", ""))
    icon = _esc(p.get("icon_url", ""))
    source = p.get("source", "TUNEIN")
    # Map source to provider id
    provider_id = {"TUNEIN": "25", "SPOTIFY": "15",
                   "LOCAL_INTERNET_RADIO": "25"}.get(source, "25")
    content_type = "stationurl" if source in ("TUNEIN", "LOCAL_INTERNET_RADIO") else "tracklisturl"
    account = _esc(p.get("source_account", ""))
    return f"""  <preset buttonNumber="{slot}">
    <containerArt>{icon}</containerArt>
    <contentItemType>{content_type}</contentItemType>
    <createdOn>2018-11-26T18:40:45.000+00:00</createdOn>
    <location>{location}</location>
    <name>{name}</name>
    <source id="19989313" type="Audio">
      <createdOn>2018-08-11T08:55:41.000+00:00</createdOn>
      <credential type="token">c291bmRmbG93</credential>
      <name>{account}</name>
      <sourceproviderid>{provider_id}</sourceproviderid>
      <sourcename>{account}</sourcename>
      <sourceSettings/>
      <updatedOn>2019-07-20T17:48:31.000+00:00</updatedOn>
      <username>{account}</username>
    </source>
    <updatedOn>2018-11-26T18:40:45.000+00:00</updatedOn>
    <username>{name}</username>
  </preset>
"""


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


@router.get("/streaming/account/{account_id}/device/{device_id}/presets")
async def get_presets(account_id: str, device_id: str):
    presets = await _load_presets(device_id)
    if not presets:
        # Empty presets: return empty container (not 404, or speaker complains)
        return xml_response("<presets/>")
    body = "".join(_preset_xml(p) for p in presets)
    return xml_response(f"<presets>\n{body}</presets>")


@router.put("/streaming/account/{account_id}/device/{device_id}/preset/{button}")
async def update_preset(account_id: str, device_id: str, button: int, request: Request):
    body = await request.body()
    logger.info("preset update button %s on %s (%d bytes)", button, device_id, len(body))
    return xml_response("<preset/>", status=200)


# ── Recents ───────────────────────────────────────────────────────────────────

@router.get("/streaming/account/{account_id}/device/{device_id}/recents")
async def get_recents(account_id: str, device_id: str):
    return xml_response("<recents/>")


@router.post("/streaming/account/{account_id}/device/{device_id}/recent")
async def add_recent(account_id: str, device_id: str, request: Request):
    await request.body()
    return xml_response("<recent/>", status=201)


# ── Account / device bootstrap ────────────────────────────────────────────────

@router.get("/streaming/account/{account_id}/device/{device_id}")
@router.get("/streaming/account/{account_id}/device/")
async def account_device(account_id: str, device_id: str = ""):
    return xml_response(
        f'<device id="{device_id}"><accountId>{account_id}</accountId>'
        f'<status>active</status></device>'
    )


@router.get("/streaming/account/{account_id}/devices")
async def account_devices(account_id: str):
    return xml_response("<devices/>")


# ── Full account sync — THE key endpoint that activates sources ───────────────
# The speaker calls this to rebuild its complete state: sources, devices, and
# presets. The <sources> block is what registers LOCAL_INTERNET_RADIO etc. in
# the speaker's Sources.xml. Without it, sources stay INVALID.

def _source_block(source_id: str, provider_id: str, name: str = "") -> str:
    return f"""    <source id="{source_id}" type="Audio">
      <createdOn>2018-08-11T08:55:41.000+00:00</createdOn>
      <credential type="token">c291bmRmbG93</credential>
      <name>{_esc(name)}</name>
      <sourceproviderid>{provider_id}</sourceproviderid>
      <sourcename>{_esc(name)}</sourcename>
      <sourceSettings/>
      <updatedOn>2019-07-20T17:48:31.000+00:00</updatedOn>
      <username>{_esc(name)}</username>
    </source>
"""


@router.get("/streaming/account/{account_id}/full")
async def account_full(account_id: str):
    """
    Complete account sync. The <sources> block activates each source in the
    speaker's persistence so /select accepts them. Presets are embedded per
    device so the physical buttons work.
    """
    ip = get_local_ip()

    # Sources block — activates the sources
    sources = (
        _source_block("19989313", "25", "TuneIn") +      # TuneIn
        _source_block("19989621", "15", "") +            # Spotify
        _source_block("19989314", "25", "")              # LOCAL_INTERNET_RADIO via TuneIn provider
    )

    # Devices with their presets
    devices_xml = ""
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM devices") as cur:
                devs = await cur.fetchall()
        for d in devs:
            did = d["id"]
            presets = await _load_presets(did)
            presets_body = "".join(_preset_xml(p) for p in presets) if presets else ""
            devices_xml += f"""  <device deviceid="{did}">
    <attachedProduct><name>{_esc(d['model'])}</name></attachedProduct>
    <createdOn>2018-08-11T08:55:25.000+00:00</createdOn>
    <firmwareVersion>{_esc(d['firmware'])}</firmwareVersion>
    <ipaddress>{_esc(d['ip'])}</ipaddress>
    <name>{_esc(d['name'])}</name>
    <presets>
{presets_body}    </presets>
    <recents/>
    <serialNumber>{_esc(did)}</serialNumber>
    <updatedOn>2018-08-11T08:55:25.000+00:00</updatedOn>
  </device>
"""
    except Exception as e:
        logger.warning("account_full devices error: %s", e)

    xml = f"""<account id="{account_id}">
  <accountStatus>active</accountStatus>
  <devices>
{devices_xml}  </devices>
  <mode>global</mode>
  <preferredLanguage>de</preferredLanguage>
  <sources>
{sources}  </sources>
</account>"""
    return xml_response(xml)


# ── BMX registry ──────────────────────────────────────────────────────────────

@router.get("/bmx/registry/v1/services")
async def bmx_registry():
    base = _base_url()
    services = {
        "services": [
            {"name": "marge", "url": base, "version": "1.0"},
            {"name": "streaming", "url": f"{base}/streaming", "version": "1.0"},
            {"name": "scmudc", "url": f"{base}/v1/scmudc", "version": "1.0"},
            {"name": "stats", "url": base, "version": "1.0"},
            {"name": "swupdate", "url": f"{base}/updates/soundtouch", "version": "1.0"},
        ]
    }
    return JSONResponse(services)


# ── scmudc event stream ───────────────────────────────────────────────────────

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
            events = event.get("payload", {}).get("events", [])
            for ev in events:
                etype = ev.get("type", "?")
                if etype not in ("balance-changed", "volume-change", "language-changed"):
                    logger.info("scmudc %s from %s: %s", etype, device_id,
                                json.dumps(ev.get("data", {}))[:400])
        except Exception:
            logger.debug("scmudc raw from %s: %d bytes", device_id, len(body))
    return JSONResponse({"deviceId": device_id, "events": [],
                         "timestamp": int(time.time() * 1000)})


# ── Software update (always up to date) ───────────────────────────────────────

@router.get("/updates/soundtouch/{path:path}")
@router.post("/updates/soundtouch/{path:path}")
async def sw_update(path: str):
    return xml_response("<update><available>false</available></update>")


# ── Stats / telemetry sink ────────────────────────────────────────────────────

@router.post("/streaming/support/{action}")
async def streaming_support(action: str, request: Request):
    await request.body()  # drain
    # power_on legitimately returns 500 per spec; others 200
    return Response(status_code=200)


@router.post("/stats/{path:path}")
@router.post("/v1/stats/{path:path}")
async def stats_sink(path: str):
    return Response(status_code=204)


# ── Catch-alls (log anything unexpected) ──────────────────────────────────────

@router.api_route("/streaming/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def streaming_catchall(path: str, request: Request):
    body = b""
    try:
        body = await request.body()
    except Exception:
        pass
    logger.info("streaming UNHANDLED: %s /streaming/%s (%d bytes)",
                request.method, path, len(body))
    return xml_response("<response><status>OK</status></response>")


@router.api_route("/marge/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def marge_catchall(path: str, request: Request):
    logger.info("marge UNHANDLED: %s /marge/%s", request.method, path)
    return xml_response("<response><status>OK</status></response>")
