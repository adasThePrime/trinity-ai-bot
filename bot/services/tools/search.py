from __future__ import annotations

import logging
import asyncio

import httpx

from bot.config import (
    DDGS_API_URL,
    MAX_SEARCH_RESULTS,
    SEARCH_ENGINES,
    DDGS_TIMEOUT,
    DDGS_MAX_RETRIES,
    DDGS_RETRY_DELAY
)

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


class SearchError(Exception):
    pass


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=DDGS_API_URL,
            timeout=httpx.Timeout(DDGS_TIMEOUT)
        )
    return _client


async def _search(
    category: str,
    query: str,
    backend: str = "auto",
    max_results: int = MAX_SEARCH_RESULTS,
    page: int = 1,
    **kwargs
) -> list[dict]:
    payload = {"query": query, "backend": backend, "max_results": max_results, **kwargs}
    if page > 0:
        payload["page"] = page

    last_error = None
    for attempt in range(1, DDGS_MAX_RETRIES + 1):
        try:
            resp = await _get_client().post(f"/search/{category}", json=payload)
            resp.raise_for_status()
            results = resp.json().get("results", resp.json())
            if isinstance(results, dict):
                results = results.get("results", [])
            logger.info(
                f"Search [{category}] query={query!r} backend={backend} page={page} -> {len(results)} results (attempt {attempt})"
            )
            return results
        
        except httpx.TimeoutException as exc:
            last_error = exc
            logger.warning(
                f"Timeout attempt {attempt}/{DDGS_MAX_RETRIES} [{category}] query={query!r}: {exc}",
            )
            if attempt < DDGS_MAX_RETRIES:
                await asyncio.sleep(DDGS_RETRY_DELAY)
        
        except httpx.HTTPStatusError as exc:
            last_error = exc
            logger.error(
                f"HTTP {exc.response.status_code} [{category}] query={query!r} backend={backend} page={page}: {exc}"
            )
            break

        except Exception as exc:
            last_error = exc
            logger.error(
                f"Unexpected error [{category}] query={query!r} backend={backend} page={page}: {exc}",
                exc_info=True
            )
            break

    logger.error(f"Search failed [{category}] query={query!r} (last error: {last_error!r})")
    return []


def _validate_backend(category: str, backend: str) -> str:
    if backend == "auto":
        return backend
    allowed = SEARCH_ENGINES.get(category, set())
    if backend not in allowed:
        pretty = ", ".join(sorted(allowed)) or "(none)"
        raise SearchError(f"Backend '{backend}' is not available for {category} search. Permitted: {pretty}")
    return backend


async def web_search(
    query: str,
    backend: str = "auto",
    max_results: int = MAX_SEARCH_RESULTS,
    page: int = 1
) -> list[dict]:
    backend = _validate_backend("text", backend)
    return await _search("text", query, backend, max_results, page)


async def image_search(
    query: str,
    backend: str = "auto",
    max_results: int = MAX_SEARCH_RESULTS,
    page: int = 1
) -> list[dict]:
    backend = _validate_backend("images", backend)
    return await _search("images", query, backend, max_results, page)


async def news_search(
    query: str,
    backend: str = "auto",
    max_results: int = MAX_SEARCH_RESULTS,
    page: int = 1
) -> list[dict]:
    backend = _validate_backend("news", backend)
    return await _search("news", query, backend, max_results, page)


async def video_search(
    query: str,
    backend: str = "auto",
    max_results: int = MAX_SEARCH_RESULTS,
    page: int = 1
) -> list[dict]:
    backend = _validate_backend("videos", backend)
    return await _search("videos", query, backend, max_results, page)