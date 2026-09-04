import logging
from fastapi import APIRouter
import httpx
from soundtouch.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

APP_VERSION = "1.0.0"


@router.get("/version")
async def get_version():
    return {"version": APP_VERSION}


@router.get("/update_check")
async def check_update():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"https://api.github.com/repos/{settings.github_repo}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            r.raise_for_status()
            data = r.json()
            latest = data.get("tag_name", "").lstrip("v")
            url = data.get("html_url", "")
            has_update = latest != APP_VERSION and latest != ""
            return {
                "current": APP_VERSION,
                "latest": latest,
                "has_update": has_update,
                "url": url,
            }
    except Exception as e:
        logger.warning("Update check failed: %s", e)
        return {"current": APP_VERSION, "latest": None, "has_update": False, "url": ""}
