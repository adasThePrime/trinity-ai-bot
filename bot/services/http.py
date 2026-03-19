from __future__ import annotations

import logging
import random

import httpx

from bot.config import (
    OPENROUTER_API_KEY,
    HTTPX_PROXY_URL,
    OPENROUTER_TIMEOUT,
    ZAI_TIMEOUT
)

logger = logging.getLogger(__name__)

_proxy: str = HTTPX_PROXY_URL or None

_openrouter: httpx.AsyncClient | None = None
_zai: httpx.AsyncClient | None = None
_default: httpx.AsyncClient | None = None


def generate_chrome_headers() -> dict[str, str]:
    ver = random.randint(130, 145)
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": f'"Not:A-Brand";v="99", "Google Chrome";v="{ver}", "Chromium";v="{ver}"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{ver}.0.0.0 Safari/537.36"
        )
    }


def openrouter_client() -> httpx.AsyncClient:
    global _openrouter
    if _openrouter is None or _openrouter.is_closed:
        _openrouter = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(OPENROUTER_TIMEOUT),
            proxy=_proxy
        )
    return _openrouter


def zai_client() -> httpx.AsyncClient:
    global _zai
    if _zai is None or _zai.is_closed:
        _zai = httpx.AsyncClient(
            headers=generate_chrome_headers(),
            timeout=httpx.Timeout(ZAI_TIMEOUT),
            proxy=_proxy
        )
    return _zai


def default_client() -> httpx.AsyncClient:
    global _default
    if _default is None or _default.is_closed:
        _default = httpx.AsyncClient(timeout=httpx.Timeout(15.0), proxy=_proxy)
    return _default


async def close_all_http_clients():
    for name, client in [("openrouter", _openrouter), ("zai", _zai), ("default", _default)]:
        if client and not client.is_closed:
            await client.aclose()
            logger.info(f"Closed {name} httpx client")