from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from travel_assistant.mcp_layer.registry import MCP_SERVERS

logger = logging.getLogger(__name__)

STARTUP_TIMEOUT = 45.0


@dataclass
class MCPLoadResult:
    tools: list[BaseTool] = field(default_factory=list)
    connected: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)

    @property
    def all_connected(self) -> bool:
        return not self.failures


async def load_mcp_tools(servers: dict[str, dict] | None = None) -> MCPLoadResult:
    servers = servers if servers is not None else MCP_SERVERS
    result = MCPLoadResult()

    for name, config in servers.items():
        try:
            client = MultiServerMCPClient({name: config})
            tools = await asyncio.wait_for(client.get_tools(), timeout=STARTUP_TIMEOUT)
        except TimeoutError:
            message = f"did not start within {STARTUP_TIMEOUT:.0f}s"
            logger.error("MCP server %r %s", name, message)
            result.failures[name] = message
            continue
        except Exception as exc:  # noqa: BLE001
            logger.error("MCP server %r failed to load: %s", name, exc)
            result.failures[name] = str(exc)
            continue

        logger.info("MCP server %r: %d tool(s) — %s", name, len(tools), [t.name for t in tools])
        result.tools.extend(tools)
        result.connected.append(name)

    return result


def describe_availability(result: MCPLoadResult) -> str:
    if result.all_connected:
        return "All MCP tools are connected and available."

    lines = [
        "MCP TOOL AVAILABILITY WARNING — the following live-data servers failed to start:"
    ]
    for name, reason in result.failures.items():
        lines.append(f"  - {name}: {reason}")
    lines.append(
        "If the user asks for data from an unavailable server, state plainly that the "
        "live service could not be reached. Never substitute remembered values."
    )
    return "\n".join(lines)
