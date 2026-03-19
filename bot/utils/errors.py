from __future__ import annotations


def error_detail(exc: Exception) -> str:
    msg = str(exc)
    for marker in ("HTTP Error", "HTTP ", "Network error", "Connection error", "Timeout"):
        if marker.lower() in msg.lower():
            return f"{msg.split(':')[0].strip()}"
    return "Unknown Error"