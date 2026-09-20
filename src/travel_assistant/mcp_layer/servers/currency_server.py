from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = "https://api.frankfurter.dev/v1"
TIMEOUT = 15.0

mcp = FastMCP("currency")


def _error(message: str, detail: str = "") -> dict[str, Any]:
    return {
        "status": "error",
        "tool_source": "MCP currency server (Frankfurter / ECB)",
        "error": message,
        "detail": detail,
        "guidance": (
            "Conversion is unavailable. Say so explicitly and give the budget in the "
            "original currency. Do not quote an exchange rate from memory."
        ),
    }


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            response = client.get(f"{API_BASE}{path}", params=params or {})
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        return _error("Currency service timed out", f"No response within {TIMEOUT}s")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return _error(
                "Unsupported currency pair",
                "Frankfurter only tracks ECB reference currencies.",
            )
        return _error("Currency service returned an error", f"HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        return _error("Could not reach the currency service", str(exc))
    except ValueError as exc:
        return _error("Currency service returned malformed data", str(exc))


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict[str, Any]:
    """Convert an amount between two currencies at the current exchange rate.

    Use for any question involving money in a different currency: travel budgets,
    "how much is X in Y", or showing costs in Singapore dollars.

    Args:
        amount: The amount to convert, e.g. 50000. Must be positive.
        from_currency: Three-letter ISO code of the source currency, e.g. "INR".
        to_currency: Three-letter ISO code of the target currency, e.g. "SGD".
    """
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return _error("Invalid `amount`", f"Expected a number, got {amount!r}")

    if amount <= 0:
        return _error("Invalid `amount`", "Amount must be greater than zero.")

    source = str(from_currency).strip().upper()
    target = str(to_currency).strip().upper()

    for label, code in (("from_currency", source), ("to_currency", target)):
        if len(code) != 3 or not code.isalpha():
            return _error(f"Invalid `{label}`", f"Expected a 3-letter ISO code, got {code!r}")

    if source == target:
        return {
            "status": "ok",
            "tool_source": "MCP currency server (Frankfurter / ECB)",
            "amount": amount,
            "from_currency": source,
            "to_currency": target,
            "rate": 1.0,
            "converted_amount": round(amount, 2),
            "rate_date": None,
            "note": "Source and target currencies are identical; no conversion applied.",
        }

    payload = _get("/latest", {"amount": amount, "from": source, "to": target})
    if payload.get("status") == "error":
        return payload

    rates = payload.get("rates", {})
    if target not in rates:
        return _error(
            "Conversion rate not returned",
            f"{source}->{target} is not published by the ECB reference set.",
        )

    converted = rates[target]
    return {
        "status": "ok",
        "tool_source": "MCP currency server (Frankfurter / ECB)",
        "amount": amount,
        "from_currency": source,
        "to_currency": target,
        "rate": round(converted / amount, 6),
        "converted_amount": round(converted, 2),
        "rate_date": payload.get("date"),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
