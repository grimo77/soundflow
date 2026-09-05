"""
DLNA/UPnP AVTransport client for Bose SoundTouch speakers.

Bose speakers run a standard UPnP MediaRenderer alongside the SoundTouch API.
While the SoundTouch API (/speaker) can't reliably play arbitrary stream URLs,
the DLNA renderer can — it accepts any HTTP(S) audio stream and plays it
continuously. This is the same approach Music Assistant uses.

We talk to the AVTransport service directly via SOAP, so no heavy UPnP
library is needed.
"""

import logging
import re
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

# Bose exposes its UPnP description on port 8091 (device description)
UPNP_DESC_PORT = 8091


class DLNARenderer:
    def __init__(self, ip: str):
        self.ip = ip
        self._control_url: str | None = None
        self._base = f"http://{ip}:{UPNP_DESC_PORT}"

    async def _discover_control_url(self) -> str | None:
        """
        Fetch the device description and locate the AVTransport control URL.
        Cached after first lookup.
        """
        if self._control_url:
            return self._control_url

        # Common description paths on Bose devices
        candidates = [
            "/",
            "/description.xml",
            "/MediaRenderer.xml",
            "/upnp/description.xml",
        ]
        for path in candidates:
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.get(f"{self._base}{path}")
                    if r.status_code != 200 or "<" not in r.text:
                        continue
                    ctrl = self._parse_control_url(r.text)
                    if ctrl:
                        # control URL may be relative
                        if ctrl.startswith("http"):
                            self._control_url = ctrl
                        else:
                            self._control_url = f"{self._base}{ctrl if ctrl.startswith('/') else '/' + ctrl}"
                        logger.info("DLNA control URL for %s: %s", self.ip, self._control_url)
                        return self._control_url
            except Exception as e:
                logger.debug("DLNA desc probe %s%s failed: %s", self._base, path, e)
                continue
        return None

    @staticmethod
    def _parse_control_url(xml_text: str) -> str | None:
        """Find the AVTransport service controlURL in a UPnP device description."""
        try:
            # Strip namespaces for easier parsing
            cleaned = re.sub(r'xmlns(:\w+)?="[^"]+"', "", xml_text)
            root = ET.fromstring(cleaned)
            for svc in root.iter("service"):
                svc_type = svc.findtext("serviceType", "")
                if "AVTransport" in svc_type:
                    return svc.findtext("controlURL", "")
        except Exception as e:
            logger.debug("parse control url failed: %s", e)
        return None

    async def _soap(self, action: str, body_inner: str) -> httpx.Response:
        control_url = await self._discover_control_url()
        if not control_url:
            raise RuntimeError(f"DLNA AVTransport nicht gefunden auf {self.ip}")

        soap_action = f'"urn:schemas-upnp-org:service:AVTransport:1#{action}"'
        envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            '<s:Body>'
            f'<u:{action} xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'{body_inner}'
            f'</u:{action}>'
            '</s:Body></s:Envelope>'
        )
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(
                control_url,
                content=envelope.encode("utf-8"),
                headers={
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": soap_action,
                },
            )
            r.raise_for_status()
            return r

    @staticmethod
    def _didl(url: str, title: str) -> str:
        """Build a minimal DIDL-Lite metadata document for the stream."""
        safe_title = (title or "Stream").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        didl = (
            '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
            '<item id="0" parentID="-1" restricted="1">'
            f'<dc:title>{safe_title}</dc:title>'
            '<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>'
            f'<res protocolInfo="http-get:*:audio/mpeg:*">{url}</res>'
            '</item></DIDL-Lite>'
        )
        return didl.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    async def play_url(self, url: str, title: str = "Stream"):
        """
        Play an arbitrary stream URL on the speaker via DLNA.
        Sets the URI, then issues Play.
        """
        metadata = self._didl(url, title)
        # SetAVTransportURI
        await self._soap(
            "SetAVTransportURI",
            f"<InstanceID>0</InstanceID>"
            f"<CurrentURI>{url}</CurrentURI>"
            f"<CurrentURIMetaData>{metadata}</CurrentURIMetaData>",
        )
        # Play
        await self._soap(
            "Play",
            "<InstanceID>0</InstanceID><Speed>1</Speed>",
        )

    async def stop(self):
        await self._soap("Stop", "<InstanceID>0</InstanceID>")
