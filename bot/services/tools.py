from __future__ import annotations

import json
import logging

from bot.services.currency import CurrencyError, currency_exchange
from bot.services.search import (
    SearchError,
    image_search,
    news_search,
    video_search,
    web_search
)
from bot.services.time import get_current_time

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for real-time text info (events, facts, docs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "backend": {
                        "type": "string",
                        "description": "brave|duckduckgo|google|grokipedia|mojeek|wikipedia|yahoo|yandex|auto",
                        "default": "auto",
                    },
                },
                "required": ["query"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "image_search",
            "description": "Search for images on the web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Image search query."},
                    "backend": {
                        "type": "string",
                        "description": "duckduckgo|auto",
                        "default": "auto"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "news_search",
            "description": "Search for recent news articles and headlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "News search query."},
                    "backend": {
                        "type": "string",
                        "description": "bing|duckduckgo|yahoo|auto",
                        "default": "auto"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "video_search",
            "description": "Search for videos on the web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Video search query."},
                    "backend": {
                        "type": "string",
                        "description": "duckduckgo|auto",
                        "default": "auto"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "Get current date/time in given timezones. Supports IANA names "
                "and abbreviations (EST, EDT, PST, PDT, IST, JST, AEST, AEDT, "
                "NZST, CET, CEST, MSK, AST_ARAB, CST_CN). Defaults to UTC."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "timezones": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Timezone names/abbreviations (max 5). Default: ['UTC'].",
                        "default": ["UTC"]
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "currency_exchange",
            "description": "Get exchange rates, convert amounts, historical/timeseries rates (ECB via Frankfurter).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["latest", "historical", "timeseries", "currencies"],
                        "description": "latest|historical|timeseries|currencies."
                    },
                    "base": {"type": "string", "description": "Base currency code.", "default": "EUR"},
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Target currency codes (max 10)."
                    },
                    "amount": {"type": "number", "description": "Amount to convert."},
                    "date": {"type": "string", "description": "YYYY-MM-DD for historical."},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD start for timeseries."},
                    "end_date": {"type": "string", " description": "YYYY-MM-DD end for timeseries."}
                },
                "required": ["action"]
            }
        }
    }
]

_NO_RESULTS = (
    "No results found across all backends. "
    "Tell the user and suggest rephrasing the query."
)


def _fmt_text(results: list[dict]) -> str:
    return "\n\n".join(
        f"{i}. **{r.get('title','N/A')}**\n   {r.get('body','')}\n   URL: {r.get('href','')}"
        for i, r in enumerate(results, 1)
    )


def _fmt_images(results: list[dict]) -> str:
    return "\n\n".join(
        f"{i}. **{r.get('title','N/A')}**\n   Image: {r.get('image','')}\n   Thumb: {r.get('thumbnail','')}\n   Source: {r.get('url','')}"
        for i, r in enumerate(results, 1)
    )


def _fmt_news(results: list[dict]) -> str:
    return "\n\n".join(
        f"{i}. **{r.get('title','N/A')}**\n   {r.get('body','')}\n   {r.get('source','')} | {r.get('date','')}\n   URL: {r.get('href', r.get('url',''))}"
        for i, r in enumerate(results, 1)
    )


def _fmt_videos(results: list[dict]) -> str:
    return "\n\n".join(
        f"{i}. **{r.get('title','N/A')}**\n   {r.get('description', r.get('body',''))}\n   Duration: {r.get('duration','')}\n   URL: {r.get('embed_url', r.get('href', r.get('url','')))}"
        for i, r in enumerate(results, 1)
    )


_SEARCH_DISPATCH = {
    "web_search":    (web_search,   _fmt_text),
    "image_search":  (image_search, _fmt_images),
    "news_search":   (news_search,  _fmt_news),
    "video_search":  (video_search, _fmt_videos),
}


async def execute_tool(name: str, args: dict) -> str:
    if name in _SEARCH_DISPATCH:
        search_fn, fmt_fn = _SEARCH_DISPATCH[name]
        try:
            results = await search_fn(args.get("query", ""), args.get("backend", "auto"))
        except SearchError as exc:
            return f"Search error: {exc}"
        return fmt_fn(results) if results else _NO_RESULTS
    
    if name == "get_current_time":
        results = get_current_time(args.get("timezones", ["UTC"]))
        return "\n".join(f"• {tz}: {dt}" for tz, dt in results.items())
    
    if name == "currency_exchange":
        try:
            data = await currency_exchange(
                action=args.get("action", "latest"),
                base=args.get("base", "EUR"),
                symbols=args.get("symbols"),
                amount=args.get("amount"),
                date_str=args.get("date"),
                start_date=args.get("start_date"),
                end_date=args.get("end_date")
            )
        except CurrencyError as exc:
            return f"Currency error: {exc}"
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    return f"Unknown tool: {name}"