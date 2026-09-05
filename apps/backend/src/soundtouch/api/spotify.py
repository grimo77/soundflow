"""
Spotify OAuth 2.0 PKCE flow.
The backend acts as a proxy so client_id/client_secret never leave the server.

Flow:
  1. GET  /api/spotify/auth          → redirect to Spotify login
  2. GET  /api/spotify/callback      → exchange code for token, store in DB
  3. GET  /api/spotify/status        → check if connected
  4. POST /api/spotify/play          → play a Spotify URI on a device
  5. DELETE /api/spotify/disconnect  → remove stored token
"""

import base64
import hashlib
import os
import secrets
import time
import logging

import aiosqlite
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from soundtouch.config import settings
from soundtouch.client import SoundTouchClient

logger = logging.getLogger(__name__)
router = APIRouter()

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"

# In-memory PKCE verifier storage (per session, short-lived)
_pkce_store: dict[str, str] = {}


async def _get_token() -> str | None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS spotify_token (
                id INTEGER PRIMARY KEY,
                access_token TEXT,
                refresh_token TEXT,
                expires_at REAL
            )
        """)
        await db.commit()
        async with db.execute("SELECT access_token, refresh_token, expires_at FROM spotify_token LIMIT 1") as cur:
            row = await cur.fetchone()

    if not row:
        return None

    access_token, refresh_token, expires_at = row

    # Refresh if expired (with 60 s buffer)
    if time.time() > expires_at - 60:
        if not settings.spotify_client_id or not settings.spotify_client_secret:
            return None
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(SPOTIFY_TOKEN_URL, data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.spotify_client_id,
                }, headers=_basic_auth_header())
                r.raise_for_status()
                data = r.json()
            access_token = data["access_token"]
            new_expires = time.time() + data["expires_in"]
            new_refresh = data.get("refresh_token", refresh_token)
            async with aiosqlite.connect(settings.db_path) as db:
                await db.execute(
                    "UPDATE spotify_token SET access_token=?, refresh_token=?, expires_at=?",
                    (access_token, new_refresh, new_expires)
                )
                await db.commit()
        except Exception as e:
            logger.warning("Spotify token refresh failed: %s", e)
            return None

    return access_token


def _basic_auth_header() -> dict:
    creds = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
    encoded = base64.b64encode(creds.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


@router.get("/auth")
async def spotify_auth(request: Request):
    if not settings.spotify_client_id:
        raise HTTPException(400, "STOC_SPOTIFY_CLIENT_ID not configured")

    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()
    _pkce_store[state] = verifier

    redirect_uri = settings.spotify_redirect_uri
    params = {
        "response_type": "code",
        "client_id": settings.spotify_client_id,
        "scope": "user-read-playback-state user-modify-playback-state streaming",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    from urllib.parse import urlencode
    url = f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/auth_url")
async def spotify_auth_url():
    """Return the Spotify authorization URL as JSON (for the manual flow)."""
    if not settings.spotify_client_id:
        raise HTTPException(400, "STOC_SPOTIFY_CLIENT_ID nicht konfiguriert")

    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()
    _pkce_store[state] = verifier

    from urllib.parse import urlencode
    params = {
        "response_type": "code",
        "client_id": settings.spotify_client_id,
        "scope": "user-read-playback-state user-modify-playback-state streaming",
        "redirect_uri": settings.spotify_redirect_uri,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    return {
        "url": f"{SPOTIFY_AUTH_URL}?{urlencode(params)}",
        "state": state,
        "redirect_uri": settings.spotify_redirect_uri,
    }


@router.get("/callback")
async def spotify_callback(request: Request, code: str, state: str):
    verifier = _pkce_store.pop(state, None)
    if not verifier:
        raise HTTPException(400, "Invalid state — try connecting again")

    redirect_uri = settings.spotify_redirect_uri

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(SPOTIFY_TOKEN_URL, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.spotify_client_id,
                "code_verifier": verifier,
            })
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(502, f"Spotify token exchange failed: {e}")

    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "")
    expires_at = time.time() + data["expires_in"]

    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM spotify_token")
        await db.execute(
            "INSERT INTO spotify_token (access_token, refresh_token, expires_at) VALUES (?,?,?)",
            (access_token, refresh_token, expires_at)
        )
        await db.commit()

    return RedirectResponse("/?spotify=connected")


class ManualCodeBody(BaseModel):
    code: str
    state: str = ""


@router.post("/manual_exchange")
async def spotify_manual_exchange(body: ManualCodeBody):
    """
    Manual OAuth code exchange — for setups without a reachable redirect URI.
    The user authorizes at Spotify, copies the 'code' from the redirected URL,
    and pastes it here. Works even when the redirect points to 127.0.0.1.
    """
    # Use the most recent verifier if state matches, else the last stored one
    verifier = _pkce_store.pop(body.state, None)
    if not verifier and _pkce_store:
        # Fall back to the last stored verifier
        verifier = list(_pkce_store.values())[-1]
        _pkce_store.clear()
    if not verifier:
        raise HTTPException(400, "Keine aktive Autorisierung. Bitte erneut auf 'Verbinden' klicken.")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(SPOTIFY_TOKEN_URL, data={
                "grant_type": "authorization_code",
                "code": body.code.strip(),
                "redirect_uri": settings.spotify_redirect_uri,
                "client_id": settings.spotify_client_id,
                "code_verifier": verifier,
            })
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(502, f"Spotify token exchange failed: {e}")

    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "")
    expires_at = time.time() + data["expires_in"]

    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM spotify_token")
        await db.execute(
            "INSERT INTO spotify_token (access_token, refresh_token, expires_at) VALUES (?,?,?)",
            (access_token, refresh_token, expires_at)
        )
        await db.commit()

    return {"ok": True}


@router.get("/status")
async def spotify_status():
    token = await _get_token()
    if not token:
        return {"connected": False}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SPOTIFY_API_URL}/me",
                                 headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            user = r.json()
        return {
            "connected": True,
            "display_name": user.get("display_name"),
            "email": user.get("email"),
            "product": user.get("product"),
        }
    except Exception:
        return {"connected": False}


@router.get("/search")
async def spotify_search(q: str, type: str = "track,album,artist", limit: int = 20):
    token = await _get_token()
    if not token:
        raise HTTPException(401, "Spotify not connected")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{SPOTIFY_API_URL}/search", params={
                "q": q, "type": type, "limit": limit,
            }, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(502, str(e))


class SpotifyPlayBody(BaseModel):
    device_id: str           # SoundTouch device ID
    spotify_uri: str         # spotify:track:... or spotify:album:...
    source_account: str = "" # Spotify account email linked on the speaker


@router.post("/play")
async def spotify_play(body: SpotifyPlayBody):
    """
    Play a Spotify URI on a SoundTouch speaker via its built-in Spotify source.
    The speaker must have Spotify configured and logged in via the Bose app.
    """
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT ip FROM devices WHERE id=?", (body.device_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Device not found")

    client = SoundTouchClient(row["ip"])
    try:
        await client.select_source("SPOTIFY", body.source_account, body.spotify_uri)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, str(e))


@router.delete("/disconnect")
async def spotify_disconnect():
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM spotify_token")
        await db.commit()
    return {"ok": True}
