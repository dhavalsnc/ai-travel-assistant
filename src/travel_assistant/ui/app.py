from __future__ import annotations

import logging
import uuid

import streamlit as st

from travel_assistant.agent.agent import Assistant, build_assistant_sync, run_turn_sync
from travel_assistant.agent.trace import TurnTrace, extract_trace
from travel_assistant.config import DESTINATION
from travel_assistant.llm import MissingAPIKeyError, explain_llm_error
from travel_assistant.rag.vectorstore import VectorStoreMissingError, load_store, store_stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title=f"{DESTINATION} Travel Assistant", page_icon="🌏", layout="wide")


@st.cache_resource(show_spinner="Starting MCP servers and loading the knowledge base…")
def get_assistant() -> Assistant:
    return build_assistant_sync()


def render_sidebar(assistant: Assistant | None) -> None:
    with st.sidebar:
        st.header("Status")

        try:
            st.success(f"Knowledge base: {store_stats(load_store())['chunks']} chunks")
        except VectorStoreMissingError as exc:
            st.error(str(exc))

        if assistant is not None:
            for name in assistant.mcp.connected:
                st.success(f"MCP `{name}` connected")
            for name, reason in assistant.mcp.failures.items():
                st.error(f"MCP `{name}` unavailable — {reason}")
            st.caption("Tools: " + ", ".join(f"`{name}`" for name in assistant.tool_names))

        st.divider()
        if st.button("Reset conversation", use_container_width=True):
            st.session_state.history = []
            st.session_state.thread_id = str(uuid.uuid4())
            st.rerun()


def render_sources(trace: TurnTrace) -> None:
    if not trace.citations:
        return

    with st.expander(f"Sources — {len(trace.citations)} cited"):
        for citation in trace.citations:
            section = f" — {citation['section']}" if citation.get("section") else ""
            url = citation.get("url")
            title = f"[{citation['title']}]({url})" if url else citation["title"]
            st.markdown(f"- {title}{section}  ·  relevance {citation.get('score', 0):.2f}")


def main() -> None:
    st.title(f"🌏 {DESTINATION} Travel Planning Assistant")
    st.caption(
        "Destination knowledge from a curated knowledge base (RAG) · "
        "live weather and currency from MCP tools"
    )

    st.session_state.setdefault("history", [])
    st.session_state.setdefault("thread_id", str(uuid.uuid4()))

    try:
        assistant = get_assistant()
    except MissingAPIKeyError as exc:
        render_sidebar(None)
        st.error(str(exc))
        st.stop()

    render_sidebar(assistant)

    for entry in st.session_state.history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            if entry.get("trace"):
                render_sources(entry["trace"])

    prompt = st.chat_input(f"Ask about {DESTINATION}…")
    if not prompt:
        return

    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving and calling tools…"):
            try:
                messages = run_turn_sync(assistant, prompt, st.session_state.thread_id)
                trace = extract_trace(messages)
            except Exception as exc:
                logger.exception("Turn failed")
                st.error(explain_llm_error(exc) or f"Something went wrong: {exc}")
                st.session_state.history.pop()
                return

        answer = trace.answer or "_The assistant returned no text for this turn._"
        st.markdown(answer)
        render_sources(trace)

    st.session_state.history.append({"role": "assistant", "content": answer, "trace": trace})


main()
