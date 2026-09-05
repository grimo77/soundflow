"""
Automatic Bose SoundTouch device discovery via SSDP/UPnP.
Falls back to manual IPs from config.
"""

import asyncio
import logging
import socket
import time

import aiosqlite

from soundtouch.client import SoundTouchClient
from soundtouch.config import settings

logger = logging.getLogger(__name__)

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MX = 3
SSDP_ST = "urn:schemas-upnp-org:device:MediaRenderer:1"

SSDP_MSG = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
    "MAN: \"ssdp:discover\"\r\n"
    f"MX: {SSDP_MX}\r\n"
    f"ST: {SSDP_ST}\r\n"
    "\r\n"
)


def _parse_location(data: bytes) -> str | None:
    for line in data.decode(errors="ignore").splitlines():
        if line.lower().startswith("location:"):
            return line.split(":", 1)[1].strip()
    return None


def _ip_from_location(location: str) -> str | None:
    try:
        from urllib.parse import urlparse
        return urlparse(location).hostname
    except Exception:
        return None


class DeviceDiscovery:
    def __init__(self):
        self._known: set[str] = set()

    async def start(self):
        await asyncio.sleep(2)  # let DB init finish
        logger.info("Starting device discovery...")
        while True:
            ips = await self._ssdp_scan()
            manual = [ip.strip() for ip in settings.manual_device_ips.split(",") if ip.strip()]
            for ip in set(ips) | set(manual):
                await self._register(ip)
            await asyncio.sleep(60)

    async def _ssdp_scan(self) -> list[str]:
        ips = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(settings.discovery_timeout)
            sock.sendto(SSDP_MSG.encode(), (SSDP_ADDR, SSDP_PORT))
            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                    location = _parse_location(data)
                    if location:
                        ip = _ip_from_location(location)
                        if ip:
                            ips.append(ip)
                except socket.timeout:
                    break
            sock.close()
        except Exception as e:
            logger.warning("SSDP scan error: %s", e)
        return ips

    async def _register(self, ip: str):
        try:
            client = SoundTouchClient(ip)
            info = await client.get_info()
            device_id = info.get("id")
            if not device_id:
                return
            async with aiosqlite.connect(settings.db_path) as db:
                await db.execute("""
                    INSERT INTO devices (id, name, ip, mac, model, firmware, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        ip=excluded.ip, name=excluded.name,
                        firmware=excluded.firmware, last_seen=excluded.last_seen
                """, (
                    device_id, info["name"], ip, info["mac"],
                    info["model"], info["firmware"], time.time()
                ))
                await db.commit()
            if device_id not in self._known:
                logger.info("Found device: %s (%s) at %s", info["name"], info["model"], ip)
                self._known.add(device_id)
        except Exception as e:
            logger.warning("Could not register %s: %s", ip, e)
