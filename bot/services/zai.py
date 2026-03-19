from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator

import httpx

from bot.services.http import generate_chrome_headers, zai_client
from bot.services.tools import execute_tool

logger = logging.getLogger(__name__)

_BASE_URL = "https://chat.z.ai/api/v2/chat/completions"
_AUTH_URL = "https://chat.z.ai/api/v1/auths/"
_HOMEPAGE_URL = "https://chat.z.ai/"
_NEW_CHAT_URL = "https://chat.z.ai/api/v1/chats/new"
_HMAC_STATIC_KEY = b"key-@@@@)))()((9))-xxxx&&&%%%%%"
_MAX_TOOL_ROUNDS = 5
_MAX_RETRIES = 3
_RETRY_BASE_MS = 1000
_RETRYABLE_CODES = {429, 500, 502, 503}
_TOOL_CALL_RE = re.compile(r"<(.*?)(?:/>|</.*?>)", re.DOTALL)

_fe_version = ""
_cached_user_id = ""
_cached_token = ""
_cached_token_exp = 0.0
_version_updater_started = False


async def _fetch_fe_version():
    global _fe_version
    try:
        client = zai_client()
        headers = {
            **generate_chrome_headers(),
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Host": "chat.z.ai",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate"
        }
        resp = await client.get(_HOMEPAGE_URL, headers=headers)
        html = resp.text
        match = re.search(r"prod-fe-[\.\d]+", html)
        if match:
            _fe_version = match.group()
            logger.info(f"FE version updated: {_fe_version}")
        else:
            logger.warning("Could not find FE version in homepage response")
    except Exception:
        logger.exception("FE version fetch failed")


async def _start_version_updater():
    global _version_updater_started
    if _version_updater_started:
        return
    _version_updater_started = True
    await _fetch_fe_version()

    async def _loop():
        while True:
            await asyncio.sleep(3600)
            await _fetch_fe_version()

    asyncio.create_task(_loop())


async def _ensure_version():
    if not _fe_version:
        await _fetch_fe_version()
    return _fe_version


async def _get_token() -> str:
    global _cached_user_id, _cached_token, _cached_token_exp

    now = time.time()
    if _cached_token and now < _cached_token_exp - 60:
        logger.debug("Using cached anonymous token")
        return _cached_user_id, _cached_token

    try:
        client = zai_client()
        headers = {
            **generate_chrome_headers(),
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Host": "chat.z.ai",
            "Pragma": "no-cache",
            "Referer": "https://chat.z.ai/",
            "Sec-Fetch-Mode": "cors"
        }
        del headers["Sec-Fetch-User"]
        del headers["Upgrade-Insecure-Requests"]
        resp = await client.get(_AUTH_URL, headers=headers)
        data = resp.json()
        _cached_user_id = data["id"]
        _cached_token = data["token"]
        _cached_token_exp = now + 86400
        logger.info("Anonymous token acquired")
        return _cached_user_id, _cached_token
    except Exception:
        logger.exception("Failed to acquire anonymous token")
        raise RuntimeError("Failed to acquire ZAI auth token")
    

async def _create_new_chat(token: str) -> str:
    try:
        client = zai_client()
        headers = {
            **generate_chrome_headers(),
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "Origin": "https://chat.z.ai",
            "Referer": "https://chat.z.ai/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }
        del headers["Sec-Fetch-User"]
        del headers["Upgrade-Insecure-Requests"]
        resp = await client.post(_NEW_CHAT_URL, headers=headers, json={"chat": {}})
        if resp.status_code != 200:
            logger.error(
                f"Failed to create new chat: HTTP {resp.status_code} - {resp.text[:500]}"
            )
            raise RuntimeError("Failed to create chat")
        data = resp.json()
        chat_id = data.get("id")
        if not chat_id:
            logger.error(f"No 'id' in new chat response: {resp.text[:500]}")
            raise RuntimeError("Failed to create chat")
        logger.debug(f"New chat created: {chat_id}")
        return chat_id
    except RuntimeError:
        raise
    except Exception:
        logger.exception("Failed to create new chat")
        raise RuntimeError("Failed to create chat")


def _hmac_sha256_hex(key: bytes, data: str) -> str:
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()


def _generate_signature(
    user_id: str, 
    request_id: str,
    user_content: str,
    timestamp_ms: int
) -> str:
    request_info = f"requestId,{request_id},timestamp,{timestamp_ms},user_id,{user_id}"
    content_b64 = base64.b64encode(user_content.encode()).decode()
    sign_data = f"{request_info}|{content_b64}|{timestamp_ms}"

    period = timestamp_ms // (5 * 60 * 1000)
    first_hmac = _hmac_sha256_hex(_HMAC_STATIC_KEY, str(period))
    return _hmac_sha256_hex(first_hmac.encode(), sign_data)


def _parse_inner_tool_call(inner: str) -> tuple[str, dict]:
    s = inner.strip()
    i = 0

    while i < len(s) and s[i] in (' ', '\t', '\n', '\r'):
        i += 1

    start = i
    while i < len(s) and s[i] not in (' ', '\t', '\n', '\r', '>'):
        i += 1
    func_name = s[start:i]

    kv = {}
    while i < len(s) and s[i] != '>':
        while i < len(s) and s[i] in (' ', '\t', '\n', '\r'):
            i += 1
        if i >= len(s) or s[i] == '>':
            break

        k_start = i
        while i < len(s) and s[i] not in ('=', ' ', '\t', '\n', '\r', '>'):
            i += 1
        key = s[k_start:i]
        if not key:
            i += 1
            continue

        while i < len(s) and s[i] in (' ', '\t', '\n', '\r'):
            i += 1
        if i >= len(s) or s[i] == '>':
            break

        if s[i] == '=':
            i += 1
            while i < len(s) and s[i] in (' ', '\t', '\n', '\r'):
                i += 1
            if i < len(s) and s[i] == '"':
                i += 1
                val_parts = []
                while i < len(s):
                    if s[i] == '\\' and i + 1 < len(s) and s[i + 1] == '"':
                        val_parts.append('"')
                        i += 2
                    elif s[i] == '"':
                        i += 1
                        break
                    else:
                        val_parts.append(s[i])
                        i += 1
                kv[key] = "".join(val_parts)

    return func_name, kv


def _is_valid_tool_call(name: str, attrs: dict) -> bool:
    if not name or len(name) > 100:
        return False
    if not re.match(r'^[a-zA-Z_]\w*$', name):
        return False
    if len(attrs) > 50:
        return False
    return True


def _parse_tool_calls(text: str):
    calls = []
    for m in _TOOL_CALL_RE.finditer(text):
        inner = m.group(1).strip()
        if len(inner) > 800000:
            continue
        func_name, kv = _parse_inner_tool_call(inner)
        if not _is_valid_tool_call(func_name, kv):
            continue
        calls.append({"name": func_name, "arguments": kv})
    logger.debug(f"Parsed {len(calls)} tool calls from response")
    return calls


def _convert_messages(messages: list[dict]) -> list[dict]:
    converted = []
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            if i == 0:
                converted.append({
                    "role": "user",
                    "content": (
                        "[SYSTEM INSTRUCTIONS — follow these exactly "
                        "for the entire conversation]\n" + m["content"]
                    )
                })
                converted.append({
                    "role": "assistant",
                    "content": "Understood. I will follow these instructions exactly."
                })
            continue
        converted.append({"role": m["role"], "content": m["content"]})
    return converted


def _strip_tool_calls(text: str) -> str:
    return _TOOL_CALL_RE.sub("", text).strip()


async def _send_zai_request(
    client: httpx.AsyncClient,
    messages: list[dict],
    model: str
) -> httpx.Response:
    user_id, token = await _get_token()
    fe_version = await _ensure_version()

    timestamp_ms = int(time.time() * 1000)
    request_id = str(uuid.uuid4())
    chat_id = await _create_new_chat(token)
    msg_id = str(uuid.uuid4())

    user_content = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_content = m.get("content", "")
            break

    signature = _generate_signature(user_id, request_id, user_content, timestamp_ms)

    enable_thinking = "-thinking" in model
    base_model = model.replace("-thinking", "").replace("-search", "")

    url = (
        f"{_BASE_URL}?"
        f"timestamp={timestamp_ms}"
        f"&requestId={request_id}"
        f"&user_id={user_id}"
        f"&version=0.0.1"
        f"&platform=web"
        f"&token={token}"
        f"&current_url=https://chat.z.ai/c/{chat_id}"
        f"&pathname=/c/{chat_id}"
        f"&signature_timestamp={timestamp_ms}"
    )

    headers = {
        **generate_chrome_headers(),
        "Accept": "*/*",
        "Authorization": f"Bearer {token}",
        "Connection": "keep-alive",
        "X-FE-Version": fe_version,
        "X-Signature": signature,
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "Origin": "https://chat.z.ai",
        "Referer": f"https://chat.z.ai/c/{chat_id}",
        "Accept": "text/event-stream",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    del headers["Sec-Fetch-User"]
    del headers["Upgrade-Insecure-Requests"]

    body = {
        "stream": True,
        "model": base_model,
        "messages": _convert_messages(messages),
        "signature_prompt": user_content,
        "params": {},
        "features": {
            "image_generation": False,
            "web_search": False,
            "auto_web_search": False,
            "preview_mode": True,
            "enable_thinking": enable_thinking
        },
        "chat_id": chat_id,
        "id": str(uuid.uuid4()),
        "current_user_message_id": msg_id,
        "files": []
    }

    logger.debug(f"ZAI request -> model={base_model} thinking={enable_thinking}")
    resp = await client.post(url, headers=headers, json=body)
    logger.debug(f"ZAI response status: {resp.status_code}")
    return resp


def _get_edit_content(data: dict) -> str:
    ec = data.get("edit_content", "")
    if not ec:
        return ""
    if len(ec) > 0 and ec[0] == '"':
        try:
            unescaped = json.loads(ec)
            if isinstance(unescaped, str):
                return unescaped
        except (json.JSONDecodeError, ValueError):
            pass
    return ec


def _parse_sse_event(line: str) -> dict | None:
    if not line.startswith("data: "):
        return None
    payload = line[len("data: "):]
    if payload == "[DONE]":
        return None
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    return data


def _should_skip_content(ec: str) -> bool:
    return ec and ('"search_result"' in ec or '"search_image"' in ec or '"mcp"' in ec)


def _extract_answer_delta(data: dict, ec: str) -> str:
    delta = data.get("delta_content", "")
    if delta:
        return delta
    if ec and "</details>" in ec:
        idx = ec.index("</details>")
        after = ec[idx + len("</details>"):]
        if after.startswith("\\n"):
            after = after[2:]
        elif after.startswith("\n"):
            after = after[1:]
        return after
    return ""


async def _collect_sse_text(resp: httpx.Response) -> str:
    chunks = []
    total_output_len = 0

    for line in resp.text.splitlines():
        line = line.strip()
        data = _parse_sse_event(line)
        if data is None:
            continue

        phase = data.get("phase", "")
        if phase == "done":
            break
        if phase == "thinking":
            continue

        ec = _get_edit_content(data)
        if _should_skip_content(ec):
            continue

        if phase == "answer":
            delta = _extract_answer_delta(data, ec)
            if delta:
                chunks.append(delta)
        elif phase in ("other", "tool_call"):
            if ec:
                chars = list(ec)
                if len(chars) > total_output_len:
                    chunks.append("".join(chars[total_output_len:]))
                    total_output_len = len(chars)

    result = "".join(chunks).strip()
    logger.debug(f"Collected SSE text: {len(result)} chars")
    return result


async def _stream_sse_text(resp: httpx.Response) -> AsyncGenerator[str, None]:
    total_output_len = 0

    async for raw_line in resp.aiter_lines():
        line = raw_line.strip()
        data = _parse_sse_event(line)
        if data is None:
            continue

        phase = data.get("phase", "")
        if phase == "done":
            break
        if phase == "thinking":
            continue

        ec = _get_edit_content(data)
        if _should_skip_content(ec):
            continue

        if phase == "answer":
            delta = _extract_answer_delta(data, ec)
            if delta:
                yield delta
        elif phase in ("other", "tool_call"):
            if ec:
                chars = list(ec)
                if len(chars) > total_output_len:
                    yield "".join(chars[total_output_len:])
                    total_output_len = len(chars)


async def _request_with_retry(
    client: httpx.AsyncClient,
    messages: list,
    model: str,
    collect: bool = True
) -> str | httpx.Response:
    last_err = None
    for attempt in range(_MAX_RETRIES):
        if attempt > 0:
            delay_ms = _RETRY_BASE_MS * (1 << (attempt - 1))
            logger.info(f"Retrying ZAI request in {delay_ms}ms (attempt {attempt + 1})")
            await asyncio.sleep(delay_ms / 1000)
        try:
            resp = await _send_zai_request(client, messages, model)
            if resp.status_code != 200:
                body_snippet = resp.text[:500]
                if resp.status_code in _RETRYABLE_CODES:
                    logger.warning(
                        f"Retryable HTTP {resp.status_code} (attempt {attempt + 1}): {body_snippet}"
                    )
                    if resp.status_code == 401:
                        global _cached_token, _cached_token_exp
                        _cached_token = ""
                        _cached_token_exp = 0.0
                    last_err = RuntimeError(f"ZAI HTTP {resp.status_code}: {body_snippet}")
                    continue
                raise RuntimeError(f"ZAI HTTP {resp.status_code}: {body_snippet}")

            if collect:
                return await _collect_sse_text(resp)
            return resp

        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            logger.warning(f"Network error (attempt {attempt + 1}): {exc}")
            last_err = exc

    raise RuntimeError(f"ZAI request failed after {_MAX_RETRIES} retries") from last_err


def _prepare_tool_args(name: str, args: dict) -> dict:
    out = dict(args)
    if name == "get_current_time" and "timezones" in out:
        out["timezones"] = [tz.strip() for tz in out["timezones"].split(",") if tz.strip()]
    if name == "currency_exchange" and "symbols" in out:
        out["symbols"] = [s.strip() for s in out["symbols"].split(",") if s.strip()]
    return out


async def zai_chat_completion(messages: list, model: str = "glm-5-thinking") -> str:
    await _start_version_updater()
    client = zai_client()
    
    for _ in range(_MAX_TOOL_ROUNDS):
        text = await _request_with_retry(client, messages, model, collect=True)

        tool_calls = _parse_tool_calls(text)
        if not tool_calls:
            return _strip_tool_calls(text) if text else ""

        clean_text = _strip_tool_calls(text)
        if clean_text:
            messages.append({"role": "assistant", "content": clean_text})

        for tc in tool_calls:
            name = tc.get("name", "")
            raw_args = tc.get("arguments", {})
            args = _prepare_tool_args(name, raw_args)
            logger.info(f"Tool call: {name}({json.dumps(raw_args)})")
            result_str = await execute_tool(name, args)
            messages.append({
                "role": "user",
                "content": f"[Tool result: {name}]\n{result_str}\n\nContinue."
            })

    logger.warning(f"Max tool rounds ({_MAX_TOOL_ROUNDS}) exhausted")
    text = await _request_with_retry(client, messages, model, collect=True)
    return _strip_tool_calls(text) if text else ""


async def zai_chat_completion_stream(
    messages: list,
    model: str = "glm-5-thinking"
) -> AsyncGenerator[str, None]:
    await _start_version_updater()

    client = zai_client()
    for _ in range(_MAX_TOOL_ROUNDS):
        text = await _request_with_retry(client, messages, model, collect=True)
        tool_calls = _parse_tool_calls(text)
        if not tool_calls:
            clean = _strip_tool_calls(text) if text else ""
            if clean:
                yield clean
            return

        clean_text = _strip_tool_calls(text)
        if clean_text:
            messages.append({"role": "assistant", "content": clean_text})

        for tc in tool_calls:
            name = tc.get("name", "")
            raw_args = tc.get("arguments", {})
            args = _prepare_tool_args(name, raw_args)
            logger.info(f"Tool call (stream): {name}({json.dumps(raw_args)})")
            result_str = await execute_tool(name, args)
            messages.append({
                "role": "user",
                "content": f"[Tool result: {name}]\n{result_str}\n\nContinue."
            })

    resp = await _request_with_retry(client, messages, model, collect=False)
    async for chunk in _stream_sse_text(resp):
        yield chunk