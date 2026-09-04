"""
Tests for SoundTouch Open Cloud REST API.
Device calls are mocked so no real speakers are needed.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio


# ── Health ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── System ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_version(client):
    r = await client.get("/api/system/version")
    assert r.status_code == 200
    assert "version" in r.json()


@pytest.mark.anyio
async def test_update_check_no_crash(client):
    """Update check should not crash even when GitHub is unreachable."""
    with patch("soundtouch.api.system.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get.side_effect = Exception("network")
        r = await client.get("/api/system/update_check")
    assert r.status_code == 200
    data = r.json()
    assert data["has_update"] is False


# ── Devices ───────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_devices_empty(client):
    r = await client.get("/api/devices")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.anyio
async def test_device_not_found(client):
    r = await client.get("/api/devices/nonexistent/now_playing")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_scan_returns_count(client):
    """Scan endpoint should return without error even with no devices on network."""
    with patch("soundtouch.discovery.DeviceDiscovery._ssdp_scan", new_callable=AsyncMock, return_value=[]):
        r = await client.post("/api/devices/scan")
    assert r.status_code == 200
    assert "scanned" in r.json()


# ── Presets ───────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_preset_invalid_slot(client):
    """Slot 0 and 7 are invalid."""
    import os, aiosqlite
    async with aiosqlite.connect(os.environ["STOC_DB_PATH"]) as db:
        await db.execute(
            "INSERT OR IGNORE INTO devices (id, name, ip, mac, model, firmware, last_seen) VALUES (?,?,?,?,?,?,?)",
            ("test-id", "Test Speaker", "192.168.1.99", "AA:BB:CC:DD:EE:FF", "SoundTouch 10", "27.0.6", 0)
        )
        await db.commit()

    r = await client.post("/api/presets/test-id/0/select")
    assert r.status_code == 400

    r = await client.post("/api/presets/test-id/7/select")
    assert r.status_code == 400


@pytest.mark.anyio
async def test_preset_set_and_read(client):
    """Set a preset (mocked device) and verify it's stored in DB."""
    with patch("soundtouch.client.SoundTouchClient.set_preset", new_callable=AsyncMock):
        r = await client.put("/api/presets/test-id/1", json={
            "name": "WDR 2",
            "source": "TUNEIN",
            "location": "s87683",
            "source_account": "",
            "icon_url": "",
        })
    assert r.status_code == 200

    # Verify stored in DB
    import os, aiosqlite
    async with aiosqlite.connect(os.environ["STOC_DB_PATH"]) as db:
        async with db.execute(
            "SELECT name FROM presets WHERE device_id='test-id' AND slot=1"
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == "WDR 2"


# ── Radio ─────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_radio_search_requires_query(client):
    r = await client.get("/api/radio/search")
    assert r.status_code == 422  # missing q param


@pytest.mark.anyio
async def test_radio_search_mocked(client):
    mock_stations = [
        {
            "stationuuid": "abc", "name": "Test FM", "url": "http://stream.test/live",
            "url_resolved": "http://stream.test/live", "country": "DE",
            "language": "de", "tags": "pop", "favicon": "",
            "votes": 1000, "bitrate": 128, "codec": "MP3"
        }
    ]
    with patch("soundtouch.api.radio.httpx.AsyncClient") as MockClient:
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_stations
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        r = await client.get("/api/radio/search?q=test")

    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test FM"
    assert data[0]["url"] == "http://stream.test/live"


# ── Zones ─────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_zones_empty(client):
    r = await client.get("/api/zones")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.anyio
async def test_zone_create_and_delete(client):
    import os, aiosqlite
    async with aiosqlite.connect(os.environ["STOC_DB_PATH"]) as db:
        await db.execute(
            "INSERT OR IGNORE INTO devices (id, name, ip, mac, model, firmware, last_seen) VALUES (?,?,?,?,?,?,?)",
            ("slave-id", "Slave Speaker", "192.168.1.100", "FF:EE:DD:CC:BB:AA", "SoundTouch 10", "27.0.6", 0)
        )
        await db.commit()

    with patch("soundtouch.client.SoundTouchClient.get_info", new_callable=AsyncMock,
               return_value={"id": "test-id", "name": "Test", "model": "ST10",
                             "mac": "AA:BB:CC:DD:EE:FF", "firmware": "27", "ip": "192.168.1.99"}):
        with patch("soundtouch.client.SoundTouchClient.create_zone", new_callable=AsyncMock):
            r = await client.post("/api/zones", json={
                "name": "Wohnbereich",
                "master_device_id": "test-id",
                "member_device_ids": ["slave-id"],
            })

    assert r.status_code == 200
    zone_id = r.json()["id"]

    # Delete it
    with patch("soundtouch.client.SoundTouchClient.remove_zone", new_callable=AsyncMock):
        r = await client.delete(f"/api/zones/{zone_id}")
    assert r.status_code == 200


# ── SoundTouch Client ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_client_parse_now_playing():
    """Unit test for XML parsing — no network needed."""
    import xml.etree.ElementTree as ET
    from soundtouch.client import SoundTouchClient

    xml = """<nowPlaying source="TUNEIN" sourceAccount="">
      <track>WDR 2</track>
      <artist>Radio</artist>
      <album></album>
      <art>https://example.com/art.jpg</art>
      <playStatus>PLAY_STATE</playStatus>
    </nowPlaying>"""

    client = SoundTouchClient("127.0.0.1")

    # Monkey-patch get to return parsed XML
    async def fake_get(path):
        return ET.fromstring(xml)

    client.get = fake_get
    result = await client.get_now_playing()

    assert result["track"] == "WDR 2"
    assert result["play_status"] == "PLAY_STATE"
    assert result["source"] == "TUNEIN"


@pytest.mark.anyio
async def test_client_volume_clamp():
    """Volume must be clamped to 0-100."""
    from soundtouch.client import SoundTouchClient
    calls = []

    client = SoundTouchClient("127.0.0.1")

    async def fake_post(path, body):
        calls.append(body)
        import xml.etree.ElementTree as ET
        return ET.fromstring("<volume>50</volume>")

    client.post = fake_post

    await client.set_volume(150)  # should clamp to 100
    assert "<volume>100</volume>" in calls[-1]

    await client.set_volume(-10)  # should clamp to 0
    assert "<volume>0</volume>" in calls[-1]
