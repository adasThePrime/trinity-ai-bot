from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.config import MAX_TIMEZONES_PER_CALL

logger = logging.getLogger(__name__)

_TZ_ALIASES = {
    "UTC": "UTC", "GMT": "Europe/London",
    "EST": "America/New_York", "EDT": "America/New_York", "ET": "America/New_York",
    "CST": "America/Chicago", "CDT": "America/Chicago", "CT": "America/Chicago",
    "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles", "PT": "America/Los_Angeles",
    "MST": "America/Denver", "MDT": "America/Denver", "MT": "America/Denver",
    "AST": "America/Halifax", "ADT": "America/Halifax",
    "HST": "Pacific/Honolulu",
    "AKST": "America/Anchorage", "AKDT": "America/Anchorage",
    "BST": "Europe/London",
    "EET": "Europe/Bucharest", "EEST": "Europe/Bucharest",
    "WET": "Europe/Lisbon", "WEST": "Europe/Lisbon",
    "MSK": "Europe/Moscow", "TRT": "Europe/Istanbul",
    "IST": "Asia/Kolkata", "PKT": "Asia/Karachi", "BDT": "Asia/Dhaka",
    "NPT": "Asia/Kathmandu", "SLST": "Asia/Colombo", "AFT": "Asia/Kabul",
    "IRST": "Asia/Tehran", "IDT": "Asia/Jerusalem",
    "AST_ARAB": "Asia/Riyadh", "GST": "Asia/Dubai",
    "JST": "Asia/Tokyo", "KST": "Asia/Seoul",
    "CST_CN": "Asia/Shanghai", "HKT": "Asia/Hong_Kong",
    "SGT": "Asia/Singapore", "PHT": "Asia/Manila",
    "ICT": "Asia/Bangkok", "WIB": "Asia/Jakarta",
    "WITA": "Asia/Makassar", "WIT": "Asia/Jayapura", "MMT": "Asia/Yangon",
    "AEST": "Australia/Sydney", "AEDT": "Australia/Sydney",
    "ACST": "Australia/Adelaide", "ACDT": "Australia/Adelaide",
    "AWST": "Australia/Perth",
    "NZST": "Pacific/Auckland", "NZDT": "Pacific/Auckland",
    "SAST": "Africa/Johannesburg", "EAT": "Africa/Nairobi",
    "WAT": "Africa/Lagos", "CAT": "Africa/Harare",
    "BRT": "America/Sao_Paulo",
    "ART": "America/Argentina/Buenos_Aires",
    "CLT": "America/Santiago"
}


def _resolve_tz(name: str) -> str:
    upper = name.strip().upper()
    return _TZ_ALIASES.get(upper, name.strip())


def get_current_time(timezones: list[str] | None = None) -> dict:
    if not timezones:
        timezones = ["UTC"]
    
    logger.info(f"Time lookup: {timezones}")
    timezones = timezones[:MAX_TIMEZONES_PER_CALL]
    results = {}

    for tz_name in timezones:
        iana = _resolve_tz(tz_name)
        if iana != tz_name.strip():
            logger.debug(f"Resolved {tz_name} -> {iana}")
        
        try:
            tz_obj = timezone.utc if iana == "UTC" else ZoneInfo(iana)
            now = datetime.now(tz_obj)
            formatted = now.strftime("%A, %B %d, %Y %I:%M %p %Z (UTC%z)")
            results[tz_name] = formatted
            logger.debug(f"  {tz_name} -> {formatted}")
        except (ZoneInfoNotFoundError, KeyError):
            results[tz_name] = (
                f"Unknown timezone '{tz_name}'. Use IANA names like "
                f"'Asia/Kolkata', 'America/New_York', or abbreviations like IST, EST, PST."
            )
            logger.warning(f"Invalid timezone: {tz_name} (resolved to: {iana})")
    
    logger.info(f"Time lookup complete — {len(results)} timezone(s)")
    return results