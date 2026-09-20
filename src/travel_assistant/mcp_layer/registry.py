from __future__ import annotations

import sys

MCP_SERVERS: dict[str, dict] = {
    "weather": {
        "command": sys.executable,
        "args": ["-m", "travel_assistant.mcp_layer.servers.weather_server"],
        "transport": "stdio",
    },
    "currency": {
        "command": sys.executable,
        "args": ["-m", "travel_assistant.mcp_layer.servers.currency_server"],
        "transport": "stdio",
    },
}
