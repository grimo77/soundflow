"""
Network utility helpers.
"""

import socket
import logging

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """
    Detect the local IP address that other devices on the LAN can reach.
    Uses a UDP trick — no actual packet is sent.
    Falls back to 127.0.0.1 if detection fails.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        logger.warning("Could not detect local IP: %s", e)
        return "127.0.0.1"


def get_local_url(port: int) -> str:
    """Return the full local URL that speakers should point to."""
    return f"http://{get_local_ip()}:{port}"
