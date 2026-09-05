"""
Low-level Bose SoundTouch HTTP + WebSocket client.
Communicates via the undocumented XML API on port 8090.
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Optional

import httpx
import websockets

logger = logging.getLogger(__name__)

SOUNDTOUCH_PORT = 8090
WS_PORT = 8080


def _xml(text: str) -> ET.Element:
    return ET.fromstring(text)


class SoundTouchClient:
    def __init__(self, ip: str):
        self.ip = ip
        self.base = f"http://{ip}:{SOUNDTOUCH_PORT}"

    async def get(self, path: str) -> ET.Element:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.base}{path}")
            r.raise_for_status()
            return _xml(r.text)

    async def post(self, path: str, body: str) -> ET.Element:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(
                f"{self.base}{path}",
                content=body,
                headers={"Content-Type": "application/xml"},
            )
            r.raise_for_status()
            return _xml(r.text)

    # ── Info ──────────────────────────────────────────────────────────────────

    async def get_info(self) -> dict:
        el = await self.get("/info")
        # deviceID is an ATTRIBUTE on <info>, not a child element
        device_id = el.get("deviceID", "") or el.findtext("deviceID", "")
        # firmware lives inside components/component/softwareVersion
        firmware = ""
        sw = el.find(".//softwareVersion")
        if sw is not None and sw.text:
            firmware = sw.text.split(" ")[0]  # keep just the version number
        # MAC: prefer the SCM networkInfo, fall back to any macAddress
        mac = ""
        for ni in el.findall("networkInfo"):
            mac_el = ni.find("macAddress")
            if mac_el is not None and mac_el.text:
                mac = mac_el.text
                if ni.get("type") == "SCM":
                    break
        return {
            "id": device_id,
            "name": el.findtext("name", ""),
            "model": el.findtext("type", ""),
            "mac": mac,
            "firmware": firmware,
            "ip": self.ip,
        }

    async def get_now_playing(self) -> dict:
        el = await self.get("/now_playing")
        source = el.get("source", "")
        track = el.findtext("track", "")
        artist = el.findtext("artist", "")
        album = el.findtext("album", "")
        art = el.findtext("art", "")
        play_status = el.findtext("playStatus", "")
        station = el.findtext("stationName", "")
        return {
            "source": source,
            "track": track or station,
            "artist": artist,
            "album": album,
            "art": art,
            "play_status": play_status,  # PLAY_STATE / PAUSE_STATE / STOP_STATE
        }

    async def get_volume(self) -> dict:
        el = await self.get("/volume")
        return {
            "actual": int(el.findtext("actualvolume", "0")),
            "target": int(el.findtext("targetvolume", "0")),
            "muted": el.findtext("muteenabled", "false") == "true",
        }

    async def get_presets(self) -> list[dict]:
        el = await self.get("/presets")
        result = []
        for p in el.findall("preset"):
            ci = p.find("ContentItem")
            result.append({
                "slot": int(p.get("id", 0)),
                "name": ci.get("itemName", "") if ci is not None else "",
                "source": ci.get("source", "") if ci is not None else "",
                "source_account": ci.get("sourceAccount", "") if ci is not None else "",
                "location": ci.get("location", "") if ci is not None else "",
                "icon_url": ci.findtext("containerArt", "") if ci is not None else "",
            })
        return result

    # ── Playback controls ─────────────────────────────────────────────────────

    async def key(self, key: str, state: str = "press"):
        body = f'<key state="{state}" sender="Gabbo">{key}</key>'
        await self.post("/key", body)

    async def press(self, key: str):
        await self.key(key, "press")
        await asyncio.sleep(0.1)
        await self.key(key, "release")

    async def play(self):
        await self.press("PLAY")

    async def pause(self):
        await self.press("PAUSE")

    async def play_pause(self):
        await self.press("PLAY_PAUSE")

    async def stop(self):
        await self.press("STOP")

    async def next_track(self):
        await self.press("NEXT_TRACK")

    async def prev_track(self):
        await self.press("PREV_TRACK")

    async def power_on(self):
        now = await self.get_now_playing()
        if now.get("source") == "STANDBY":
            await self.press("POWER")

    async def power_off(self):
        now = await self.get_now_playing()
        if now.get("source") != "STANDBY":
            await self.press("POWER")

    async def set_volume(self, level: int):
        level = max(0, min(100, level))
        await self.post("/volume", f"<volume>{level}</volume>")

    async def mute(self):
        await self.press("MUTE")

    # ── Preset ────────────────────────────────────────────────────────────────

    async def select_preset(self, slot: int):
        await self.press(f"PRESET_{slot}")

    async def set_preset(self, slot: int, source: str, location: str,
                         source_account: str = "", name: str = "",
                         icon_url: str = ""):
        account_attr = f'sourceAccount="{source_account}"' if source_account else ""
        body = f"""<presets>
  <preset id="{slot}" createdOn="0" updatedOn="0">
    <ContentItem source="{source}" type="uri" location="{location}"
      {account_attr} isPresetable="true" itemName="{name}">
      <containerArt>{icon_url}</containerArt>
    </ContentItem>
  </preset>
</presets>"""
        await self.post("/presets", body)

    # ── Play URL / source ─────────────────────────────────────────────────────

    async def play_url(self, url: str, name: str = "Stream"):
        body = f"""<play_info>
  <app_key>DB9F207B-FE6E-4B53-9CF6-97A618A11CE9</app_key>
  <url>{url}</url>
  <service>SoundTouch Open Cloud</service>
  <reason>EXPLICIT</reason>
  <message>{name}</message>
  <volume>-1</volume>
</play_info>"""
        await self.post("/speaker", body)

    async def select_source(self, source: str, account: str = "", location: str = ""):
        body = f'<ContentItem source="{source}" sourceAccount="{account}" location="{location}"></ContentItem>'
        await self.post("/select", body)

    # ── Zone ──────────────────────────────────────────────────────────────────

    async def create_zone(self, master_mac: str, member_ips: list[str]):
        members = "".join(f'<member ipaddress="{ip}">{master_mac}</member>' for ip in member_ips)
        body = f'<zone master="{master_mac}">{members}</zone>'
        await self.post("/setZone", body)

    async def add_zone_slave(self, master_mac: str, slave_ip: str):
        body = f'<zone master="{master_mac}"><member ipaddress="{slave_ip}">{master_mac}</member></zone>'
        await self.post("/addZoneSlave", body)

    async def remove_zone_slave(self, master_mac: str, slave_ip: str):
        body = f'<zone master="{master_mac}"><member ipaddress="{slave_ip}">{master_mac}</member></zone>'
        await self.post("/removeZoneSlave", body)

    async def remove_zone(self):
        await self.post("/removeZone", "<zone></zone>")

    # ── Network config (Setup Wizard) ─────────────────────────────────────────

    async def set_name(self, name: str):
        await self.post("/name", f"<name>{name}</name>")

    async def set_cloud_server(self, host: str):
        """
        Redirect the speaker's cloud (Marge) server to a local address.
        Different firmwares expose different endpoints, so we try the known
        variants in order until one succeeds.
        host format: '192.168.1.100:7777'
        """
        url = f"http://{host}"
        # Try the known endpoint variants across firmware versions
        attempts = [
            ("/setMargeAccount", f"<marge><url>{url}</url></marge>"),
            ("/marge", f"<marge><url>{url}</url></marge>"),
            ("/setServerAddress", f"<server>{host}</server>"),
        ]
        last_error = None
        for path, body in attempts:
            try:
                await self.post(path, body)
                return path  # success
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(
            f"Kein unterstützter Redirect-Endpunkt gefunden. "
            f"Dein Gerät nutzt vermutlich DNS-Redirect. Letzter Fehler: {last_error}"
        )

    async def get_cloud_server(self) -> str:
        """
        Read the currently configured cloud server address.
        Modern firmwares expose it as <margeURL> inside /info.
        """
        try:
            el = await self.get("/info")
            marge = el.findtext("margeURL", "")
            if marge:
                return marge
        except Exception:
            pass
        return ""

    async def get_supported_urls(self) -> list[str]:
        """Return the list of endpoints this specific device supports."""
        try:
            el = await self.get("/supportedURLs")
            return [u.get("location", "") for u in el.findall("URL")]
        except Exception:
            return []

    async def set_spotify_account(self, email: str, blob_id: str = "", token: str = "") -> str:
        """
        Link a Spotify account to the speaker so it can play Spotify sources.
        Firmware versions differ, so we try the documented endpoints in order.

        Note: On most speakers Spotify is already linked via the Bose app and
        stored on the device. In that case this call is optional — SoundFlow
        only needs the email to reference the existing account when playing.
        """
        # Variant A: official setMusicServiceAccount (most common)
        account_body = f"""<credentials source="SPOTIFY" displayName="{email}">
  <user>{email}</user>
  <pass>{token}</pass>
</credentials>"""
        # Variant B: OAuth-based account
        oauth_body = f"""<credentials source="SPOTIFY" displayName="{email}">
  <sourceAccount>{email}</sourceAccount>
  <token>{token}</token>
</credentials>"""
        # Variant C: legacy setCredentials
        legacy_body = f"""<credentials>
  <source>SPOTIFY</source>
  <sourceAccount>{email}</sourceAccount>
  <blobId>{blob_id}</blobId>
  <token>{token}</token>
</credentials>"""

        attempts = [
            ("/setMusicServiceAccount", account_body),
            ("/setMusicServiceOAuthAccount", oauth_body),
            ("/setCredentials", legacy_body),
        ]
        last_error = None
        for path, body in attempts:
            try:
                await self.post(path, body)
                return path
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(
            f"Kein unterstützter Spotify-Endpunkt gefunden. Das Gerät hat "
            f"Spotify vermutlich bereits über die Bose-App gespeichert — die "
            f"E-Mail wird nur zur Referenz benötigt. Letzter Fehler: {last_error}"
        )
