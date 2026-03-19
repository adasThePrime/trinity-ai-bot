from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from bot.config import (
    MAX_TOOL_ROUNDS,
    OPENROUTER_BASE_URL,
    OPENROUTER_DEFAULT_MODEL,
    OPENROUTER_MODELS,
    USE_ZAI,
    ZAI_DEFAULT_MODEL,
    ZAI_MODELS
)
from bot.services.cache import cache
from bot.services.db import db
from bot.services.http import openrouter_client
from bot.services.tools import execute_tool, TOOLS
from bot.services.zai import zai_chat_completion, zai_chat_completion_stream

logger = logging.getLogger(__name__)


def _resolve_or_model(model: str | None) -> str:
    if model and any(m["id"] == model for m in OPENROUTER_MODELS):
        return model
    return OPENROUTER_DEFAULT_MODEL


def _resolve_zai_model(model: str | None) -> str:
    if model and any(m["id"] == model for m in ZAI_MODELS):
        return model
    return ZAI_DEFAULT_MODEL


async def _request(client: httpx.AsyncClient, payload: dict) -> dict:
    try:
        resp = await client.post(OPENROUTER_BASE_URL, json=payload)
    except httpx.ConnectError as exc:
        logger.error(f"Connection error to OpenRouter: {exc}")
        raise RuntimeError(f"Connection error: {exc}") from exc
    except httpx.TimeoutException as exc:
        logger.error(f"Request timeout to OpenRouter: {exc}")
        raise RuntimeError(f"Timeout error: {exc}") from exc
    except httpx.HTTPError as exc:
        logger.error(f"HTTP client error: {exc}")
        raise RuntimeError(f"Network error: {exc}") from exc

    if resp.status_code != 200:
        body_snippet = resp.text[:300]
        logger.error(f"OpenRouter HTTP {resp.status_code}: {body_snippet}")
        raise RuntimeError(f"HTTP Error ({resp.status_code}): {body_snippet}")

    data = resp.json()

    if "error" in data:
        err_msg = data["error"].get("message", str(data["error"]))
        logger.error(f"OpenRouter API error: {err_msg}")
        raise RuntimeError(f"OpenRouter error: {err_msg}")

    return data


async def _request_stream(
    client: httpx.AsyncClient,
    payload: dict
) -> AsyncGenerator[str, None]:
    try:
        async with client.stream("POST", OPENROUTER_BASE_URL, json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                logger.error(f"OpenRouter streaming error (HTTP {resp.status_code}): {body.decode()}")
                raise RuntimeError(f"HTTP Error ({resp.status_code}): streaming request failed")

            async for raw_line in resp.aiter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue

                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                delta = (
                    data.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content")
                )
                if delta:
                    yield delta

    except httpx.ConnectError as exc:
        logger.error(f"Connection error during streaming: {exc}")
        raise RuntimeError(f"Connection error: {exc}") from exc
    except httpx.TimeoutException as exc:
        logger.error(f"Timeout during streaming: {exc}")
        raise RuntimeError(f"Timeout error: {exc}") from exc
    except httpx.HTTPError as exc:
        logger.error(f"HTTP streaming error: {exc}")
        raise RuntimeError(f"Network error: {exc}") from exc


def get_models() -> list[dict]:
    return ZAI_MODELS if USE_ZAI else OPENROUTER_MODELS


def get_default_model() -> str:
    return ZAI_DEFAULT_MODEL if USE_ZAI else OPENROUTER_DEFAULT_MODEL


def valid_model_id(model_id: str) -> bool:
    return any(m["id"] == model_id for m in get_models()) 


def model_id_to_alias(model_id: str) -> str:
    for i, m in enumerate(get_models()):
        if m["id"] == model_id:
            return str(i)
    return model_id


def alias_to_model_id(alias: str) -> str | None:
    try:
        idx = int(alias)
    except ValueError:
        return None
    models = get_models()
    if 0 <= idx < len(models):
        return models[idx]["id"]
    return None


async def resolve_user_model(user_id: int | None) -> str | None:
    if user_id is None:
        return None
    return await db.get_user_model(user_id)


async def chat_completion(messages: list[dict], model: str | None = None) -> str:
    if USE_ZAI:
        return await zai_chat_completion(messages, model=_resolve_zai_model(model))

    resolved = _resolve_or_model(model)
    payload = {"model": resolved, "messages": messages}
    payload["tools"] = TOOLS
    payload["tool_choice"] = "auto"

    client = openrouter_client()

    for _ in range(MAX_TOOL_ROUNDS):
        data = await _request(client, payload)
        msg = data["choices"][0]["message"]

        if msg.get("content") and not msg.get("tool_calls"):
            return msg["content"]

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return msg.get("content", "")

        messages.append(msg)

        for tc in tool_calls:
            fn = tc["function"]
            try:
                args = json.loads(fn["arguments"])
            except (json.JSONDecodeError, KeyError):
                args = {}
            result = await execute_tool(fn["name"], args)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        payload["messages"] = messages

    logger.warning(f"Max tool rounds ({MAX_TOOL_ROUNDS}) exhausted, requesting text-only reply")
    try:
        payload.pop("tools", None)
        payload.pop("tool_choice", None)
        data = await _request(client, payload)
        return data["choices"][0]["message"].get("content", "")
    except Exception:
        logger.exception("Final text-only fallback also failed")
        return "I encountered an issue processing your request. Please try again"
    

async def chat_completion_stream(messages: list[dict], model: str | None = None) -> AsyncGenerator[str, None]:
    if USE_ZAI:
        async for chunk in zai_chat_completion_stream(messages, model=_resolve_zai_model(model)):
            yield chunk
        return

    resolved = _resolve_or_model(model)
    payload = {"model": resolved, "messages": messages}
    payload["tools"] = TOOLS
    payload["tool_choice"] = "auto"

    client = openrouter_client()

    for _ in range(MAX_TOOL_ROUNDS):
        data = await _request(client, payload)
        msg = data["choices"][0]["message"]

        if msg.get("content") and not msg.get("tool_calls"):
            yield msg["content"]
            return

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            content = msg.get("content", "")
            if content:
                yield content
            return

        messages.append(msg)

        for tc in tool_calls:
            fn = tc["function"]
            try:
                args = json.loads(fn["arguments"])
            except (json.JSONDecodeError, KeyError):
                args = {}
            result = await execute_tool(fn["name"], args)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        payload["messages"] = messages

    payload.pop("tools", None)
    payload.pop("tool_choice", None)
    payload["stream"] = True

    async for chunk in _request_stream(client, payload):
        yield chunk