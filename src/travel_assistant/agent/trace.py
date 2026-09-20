from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

KB_TOOL = "search_travel_kb"


@dataclass
class ToolCallTrace:
    name: str
    args: dict
    artifact: dict | None = None

    @property
    def is_kb(self) -> bool:
        return self.name == KB_TOOL


@dataclass
class TurnTrace:
    answer: str = ""
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)

    @property
    def kb_calls(self) -> list[ToolCallTrace]:
        return [call for call in self.tool_calls if call.is_kb]

    @property
    def mcp_calls(self) -> list[ToolCallTrace]:
        return [call for call in self.tool_calls if not call.is_kb]


def extract_trace(messages: list[AnyMessage]) -> TurnTrace:
    trace = TurnTrace()
    pending: dict[str, ToolCallTrace] = {}

    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                entry = ToolCallTrace(name=call["name"], args=call.get("args", {}))
                pending[call["id"]] = entry
                trace.tool_calls.append(entry)

            text = _text_of(message)
            if text:
                trace.answer = text

        elif isinstance(message, ToolMessage):
            entry = pending.get(message.tool_call_id)
            if entry is None:
                continue
            entry.artifact = message.artifact if isinstance(message.artifact, dict) else None

    trace.citations = _collect_citations(trace)
    return trace


def _text_of(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content.strip()

    parts = [
        block.get("text", "")
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(part for part in parts if part).strip()


def _collect_citations(trace: TurnTrace) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    citations: list[dict] = []

    for call in trace.kb_calls:
        if not call.artifact or call.artifact.get("status") != "ok":
            continue
        for citation in call.artifact.get("citations", []):
            key = (citation.get("title", ""), citation.get("section", ""))
            if key in seen:
                continue
            seen.add(key)
            citations.append(citation)

    return citations
