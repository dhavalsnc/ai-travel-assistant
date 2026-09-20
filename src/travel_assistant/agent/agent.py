from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from travel_assistant.agent.prompts import build_system_prompt
from travel_assistant.llm import build_llm
from travel_assistant.mcp_layer.client import MCPLoadResult, describe_availability, load_mcp_tools
from travel_assistant.rag.kb_tool import search_travel_kb
from travel_assistant.rag.vectorstore import prewarm

logger = logging.getLogger(__name__)

RECURSION_LIMIT = 25


@dataclass
class Assistant:
    agent: object
    mcp: MCPLoadResult

    @property
    def tool_names(self) -> list[str]:
        return ["search_travel_kb"] + [tool.name for tool in self.mcp.tools]


async def build_assistant(mcp_result: MCPLoadResult | None = None) -> Assistant:
    prewarm()

    mcp_result = mcp_result if mcp_result is not None else await load_mcp_tools()

    tools = [search_travel_kb, *mcp_result.tools]
    logger.info("Agent tools: %s", [tool.name for tool in tools])

    agent = create_agent(
        build_llm(),
        tools,
        system_prompt=build_system_prompt(describe_availability(mcp_result)),
        checkpointer=MemorySaver(),
    )
    return Assistant(agent=agent, mcp=mcp_result)


def build_assistant_sync(mcp_result: MCPLoadResult | None = None) -> Assistant:
    prewarm()
    return asyncio.run(build_assistant(mcp_result))


async def run_turn(assistant: Assistant, message: str, thread_id: str = "default") -> list[AnyMessage]:
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}

    before = await assistant.agent.aget_state(config)
    seen = len(before.values.get("messages", [])) if before.values else 0

    state = await assistant.agent.ainvoke({"messages": [HumanMessage(content=message)]}, config)
    return state["messages"][seen:]


def run_turn_sync(assistant: Assistant, message: str, thread_id: str = "default") -> list[AnyMessage]:
    return asyncio.run(run_turn(assistant, message, thread_id))
