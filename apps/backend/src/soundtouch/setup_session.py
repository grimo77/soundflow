"""
WebSocket setup-session client for the SoundTouch speaker's SETUP state machine.

This is the missing piece: pairing a speaker with a Marge account over a
simple HTTP POST to /setMargeAccount is NOT enough. The speaker's firmware
expects a full WebSocket session (port 8080) that drives it through the
same state sequence the official Bose app uses:

    SETUP_START -> IDENTIFY_ENTER -> language -> SETUP_ENTER
    -> IDENTIFY_LEAVE -> name -> setMargeAccount -> SETUP_LEAVE

Skipping this (or sending only a minimal <accountId>+<userAuthToken>
payload to /setMargeAccount) is the documented cause of "AUX/preset
breakage" — sources never activate even though the HTTP endpoints all
return 200. This mirrors gesellix/bose-soundtouch's Session/ExecuteInitPlan.

Reference: gesellix/bose-soundtouch pkg/service/setup (setup_session.go,
init_plan.go), MIT licensed — reimplemented independently for SoundFlow.
"""

import asyncio
import json
import logging
import time
import uuid

import websockets

logger = logging.getLogger(__name__)

WS_PORT = 8080
DEFAULT_STEP_TIMEOUT = 8.0
DEFAULT_IDENTIFY_TIMEOUT_MS = 300_000

DEFAULT_MARGE_AUTH_TOKEN = "Bearer SoundFlow"
DEFAULT_MARGE_PAIRING_EMAIL = "local@soundflow.invalid"


class SetupSessionError(Exception):
    pass


class SetupSession:
    """
    Synchronous request/response WebSocket session driving the speaker's
    SETUP state machine, mirroring gesellix's Session type.
    """

    def __init__(self, ip: str, device_id: str, step_timeout: float = DEFAULT_STEP_TIMEOUT):
        self.ip = ip
        self.device_id = device_id
        self.step_timeout = step_timeout
        self._ws = None
        self._request_id = 0

    async def connect(self):
        uri = f"ws://{self.ip}:{WS_PORT}/"
        self._ws = await asyncio.wait_for(
            websockets.connect(uri, subprotocols=["gabbo"]), timeout=10
        )
        logger.info("Setup session connected to %s", self.ip)

    async def close(self):
        if self._ws:
            await self._ws.close()

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_and_wait(self, url: str, body_xml: str = "", timeout: float | None = None) -> str:
        """Send a <msg> envelope and wait for the matching response."""
        if not self._ws:
            raise SetupSessionError("not connected")

        req_id = self._next_request_id()
        envelope = (
            f'<msg><header deviceID="{self.device_id}" url="{url}" method="POST">'
            f'<request requestID="{req_id}" />'
            f'</header>{f"<body>{body_xml}</body>" if body_xml else ""}</msg>'
        )
        await self._ws.send(envelope)
        logger.debug("setup session -> %s: %s", url, envelope[:200])

        deadline = time.monotonic() + (timeout or self.step_timeout)
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=max(remaining, 0.1))
            except asyncio.TimeoutError:
                break
            logger.debug("setup session <- %s", raw[:200] if isinstance(raw, str) else "<binary>")
            if isinstance(raw, str) and f'requestID="{req_id}"' in raw:
                return raw
            # Ignore unrelated frames (state broadcasts etc.) and keep waiting
        raise SetupSessionError(f"timeout waiting for response to {url} (requestID={req_id})")

    # ── State machine steps, in the required order ──────────────────────────

    async def start(self):
        await self._send_and_wait("/SETUP_START")

    async def identify_enter(self, timeout_ms: int = DEFAULT_IDENTIFY_TIMEOUT_MS):
        await self._send_and_wait(
            "/SETUP_IDENTIFY_DEVICE_ENTER",
            f"<timeoutMs>{timeout_ms}</timeoutMs>",
            timeout=timeout_ms / 1000 + 2,
        )

    async def set_language(self, code: int = 0):
        await self._send_and_wait("/sysLanguage", f"<sysLanguage>{code}</sysLanguage>")

    async def enter(self):
        await self._send_and_wait("/SETUP_ENTER")

    async def identify_leave(self):
        await self._send_and_wait("/SETUP_IDENTIFY_DEVICE_LEAVE")

    async def set_name(self, name: str):
        if not name:
            return
        await self._send_and_wait("/name", f"<name>{name}</name>")

    async def set_marge_account(
        self,
        account_id: str,
        auth_token: str = "",
        bose_server: str = "",
        update_server: str = "",
        account_email: str = "",
    ):
        """
        Send the full PairDeviceWithAccount payload. Using only accountId +
        userAuthToken (the minimal shape) is known to leave sources
        (AUX/presets/LOCAL_INTERNET_RADIO) inactive after pairing — always
        include boseServer/updateServer/accountEmail when available.
        """
        token = auth_token or DEFAULT_MARGE_AUTH_TOKEN
        fields = f"<accountId>{account_id}</accountId><userAuthToken>{token}</userAuthToken>"
        if bose_server:
            update_server = update_server or f"{bose_server}/updates/soundtouch"
            account_email = account_email or DEFAULT_MARGE_PAIRING_EMAIL
            fields += (
                f"<boseServer>{bose_server}</boseServer>"
                f"<updateServer>{update_server}</updateServer>"
                f"<accountEmail>{account_email}</accountEmail>"
            )
        body = f"<PairDeviceWithAccount>{fields}</PairDeviceWithAccount>"
        await self._send_and_wait("/setMargeAccount", body, timeout=20)

    async def leave(self):
        await self._send_and_wait("/SETUP_LEAVE")

    async def push_customer_support_info(self):
        try:
            await self._send_and_wait("/pushCustomerSupportInfoToMarge", timeout=5)
        except SetupSessionError:
            pass  # harmless telemetry step; failure is not fatal


async def execute_init_plan(
    ip: str,
    device_id: str,
    account_id: str,
    bose_server: str,
    device_name: str = "",
    language: int = 0,
    auth_token: str = "",
) -> dict:
    """
    Run the full speaker-initialization sequence:
      SETUP_START -> IDENTIFY_ENTER -> language -> SETUP_ENTER
      -> IDENTIFY_LEAVE -> name -> setMargeAccount -> SETUP_LEAVE
      -> pushCustomerSupportInfoToMarge

    Returns a dict of {step: "ok"|"failed", ...} so callers can report
    progress. Raises SetupSessionError if a required step fails.
    """
    steps: dict[str, str] = {}
    session = SetupSession(ip, device_id)

    try:
        await session.connect()
        steps["dial_websocket"] = "ok"

        await session.start()
        steps["setup_start"] = "ok"

        await session.identify_enter()
        steps["identify_enter"] = "ok"

        await session.set_language(language)
        steps["language"] = "ok"

        await session.enter()
        steps["setup_enter"] = "ok"

        await session.identify_leave()
        steps["identify_leave"] = "ok"

        if device_name:
            await session.set_name(device_name)
            steps["name"] = "ok"
        else:
            steps["name"] = "skipped"

        await session.set_marge_account(
            account_id=account_id,
            auth_token=auth_token,
            bose_server=bose_server,
        )
        steps["pair_account"] = "ok"

        await session.leave()
        steps["setup_leave"] = "ok"

        await session.push_customer_support_info()
        steps["push_telemetry"] = "ok"

    except Exception as e:
        logger.error("Init plan failed at step after %s: %s", list(steps.keys())[-1] if steps else "connect", e)
        raise SetupSessionError(f"Init plan failed: {e}") from e
    finally:
        await session.close()

    return steps
