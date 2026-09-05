"""
Bose Diagnostic Shell client (TCP port 17000).

The SoundTouch firmware caches its cloud service URLs in NVS. The only reliable
way to redirect them to a local server is through the device's diagnostic
shell on port 17000, using 'sys configuration' commands.

This is the same mechanism SixBack and ueberboese-app use. After setting the
URLs and rebooting, the speaker contacts SoundFlow instead of Bose's cloud.

Commands sent:
  sys configuration bmxRegistryUrl http://<ip>:<port>/bmx/registry/v1/services
  sys configuration statsServerUrl http://<ip>:<port>
  sys configuration margeServerUrl http://<ip>:<port>
  sys configuration swUpdateUrl    http://<ip>:<port>/updates/soundtouch
  sys reboot
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

DIAG_PORT = 17000


class DiagnosticShell:
    def __init__(self, ip: str):
        self.ip = ip

    async def _send_commands(self, commands: list[str], reboot: bool = False) -> list[str]:
        """Open a telnet connection, send commands, collect responses."""
        responses = []
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip, DIAG_PORT), timeout=8
            )
        except Exception as e:
            raise RuntimeError(f"Diagnose-Shell auf {self.ip}:{DIAG_PORT} nicht erreichbar: {e}")

        try:
            # Give the shell a moment to present its prompt
            await asyncio.sleep(0.3)
            try:
                await asyncio.wait_for(reader.read(4096), timeout=1)  # drain banner
            except asyncio.TimeoutError:
                pass

            for cmd in commands:
                writer.write((cmd + "\r\n").encode())
                await writer.drain()
                await asyncio.sleep(0.4)
                try:
                    data = await asyncio.wait_for(reader.read(4096), timeout=2)
                    responses.append(data.decode(errors="ignore"))
                except asyncio.TimeoutError:
                    responses.append("")

            if reboot:
                writer.write(b"sys reboot\r\n")
                await writer.drain()
                await asyncio.sleep(0.3)

        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except Exception:
                pass

        return responses

    async def set_cloud_urls(self, base_url: str, reboot: bool = True) -> dict:
        """
        Point all cloud service URLs at the given base (e.g. http://192.168.10.212:7777).
        Reboots the speaker by default so the new URLs take effect.
        """
        base = base_url.rstrip("/")
        commands = [
            f"sys configuration bmxRegistryUrl {base}/bmx/registry/v1/services",
            f"sys configuration statsServerUrl {base}",
            f"sys configuration margeServerUrl {base}",
            f"sys configuration swUpdateUrl {base}/updates/soundtouch",
        ]
        responses = await self._send_commands(commands, reboot=reboot)
        logger.info("Set cloud URLs on %s → %s (reboot=%s)", self.ip, base, reboot)
        return {"ok": True, "base": base, "rebooted": reboot, "responses": responses}

    async def get_configuration(self) -> dict:
        """Read back the current cloud URL configuration."""
        commands = [
            "sys configuration bmxRegistryUrl",
            "sys configuration margeServerUrl",
            "sys configuration statsServerUrl",
        ]
        responses = await self._send_commands(commands, reboot=False)
        return {"responses": responses}

    async def revert_to_bose(self, reboot: bool = True) -> dict:
        """Restore the original Bose cloud URLs (best effort)."""
        commands = [
            "sys configuration bmxRegistryUrl https://streaming.bose.com/bmx/registry/v1/services",
            "sys configuration margeServerUrl https://streaming.bose.com",
            "sys configuration statsServerUrl https://streaming.bose.com",
        ]
        responses = await self._send_commands(commands, reboot=reboot)
        return {"ok": True, "reverted": True, "responses": responses}
