from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from bot.config import FRANKFURTER_BASE_URL, MAX_CURRENCY_SYMBOLS
from bot.services.http import default_client

logger = logging.getLogger(__name__)


class CurrencyError(Exception):
    pass


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _validate_date(d: str, label: str = "date") -> str:
    try:
        parsed = date.fromisoformat(d)
    except (ValueError, TypeError) as exc:
        raise CurrencyError(f"Invalid {label} '{d}'. Use YYYY-MM-DD format.") from exc
    if parsed > date.today():
        raise CurrencyError(f"The {label} '{d}' is in the future.")
    return d


async def _get(url: str, params: dict | None = None) -> dict:
    logger.info(f"Frankfurter GET {url} params={params}")
    client = default_client()
    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        text = resp.text
        logger.error(f"Frankfurter HTTP {resp.status_code}: {text[:300]}")
        raise CurrencyError(f"Frankfurter API error (HTTP {resp.status_code}): {text}")
    data = resp.json()
    logger.debug(f"Frankfurter response: {str(data)[:300]}")
    return data


async def currency_exchange(
    action: str,
    base: str = "EUR",
    symbols: list | None = None,
    amount: float | None = None,
    date_str: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None
) -> dict:
    action = action.strip().lower()

    if action == "currencies":
        return await _get(f"{FRANKFURTER_BASE_URL}/currencies")

    params = {"base": base.upper()}

    if symbols:
        symbols = [s.upper() for s in symbols[:MAX_CURRENCY_SYMBOLS]]
        params["symbols"] = ",".join(symbols)

    if amount is not None:
        params["amount"] = str(amount)

    if action == "latest":
        return await _get(f"{FRANKFURTER_BASE_URL}/latest", params)

    if action == "historical":
        if not date_str:
            raise CurrencyError("A 'date' is required for historical lookups.")
        _validate_date(date_str, "date")
        return await _get(f"{FRANKFURTER_BASE_URL}/{date_str}", params)

    if action == "timeseries":
        if not start_date:
            raise CurrencyError("A 'start_date' is required for time-series queries.")
        _validate_date(start_date, "start_date")
        end = end_date if end_date and _validate_date(end_date, "end_date") else _today_str()
        return await _get(f"{FRANKFURTER_BASE_URL}/{start_date}..{end}", params)

    raise CurrencyError(f"Unknown action '{action}'. Use: latest, historical, timeseries, currencies.")