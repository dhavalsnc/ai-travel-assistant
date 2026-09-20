# AI Travel Planning Assistant — Singapore

GitHub: https://github.com/dhavalsnc/ai-travel-assistant

Demo: https://nagarro-my.sharepoint.com/:v:/p/dhaval_chandnani/IQCU4kgZxZW8TJOo3byZGIt9AWdBZzl9fTdBsl_c2h_gkK8?e=0Nizza

A travel assistant that answers destination questions from a curated knowledge base
(RAG) and fetches live weather and exchange rates through MCP tools, combining both
when a question needs them.

Every answer labels where its information came from: **📚 knowledge base**,
**🌐 live MCP data**, or **💡 the model's own suggestion**.

---

## Quick start

Requires **Python 3.10+** (3.11 recommended — the repo pins 3.11.8 via `.python-version`).

```bash
make setup                      # venv + dependencies
cp .env.example .env            # then add your GOOGLE_API_KEY
make ingest                     # build the knowledge base (~2 min first run)
make run                        # open the Streamlit UI
```

`make ingest` downloads nine Wikivoyage pages and a ~130 MB embedding model on first
run. The resulting FAISS index is committed, so this step is reproducible rather than
required. The only secret needed is `GOOGLE_API_KEY` — the weather and currency
services are free and key-less.

---

## Architecture

Two pipelines: one offline, one per request.

**Offline — `make ingest`**

```
data/sources.yaml → fetch (MediaWiki API) → clean to Markdown → heading-aware chunk
                  → embed (bge-small) → FAISS index + citation metadata
```

**Runtime**

```
Streamlit chat
      │
      ▼
LangGraph ReAct agent ── system prompt (provenance contract)
      │                ── MemorySaver checkpointer (multi-turn memory)
      ├── search_travel_kb(query)        → FAISS retrieval + citations
      ├── get_current_weather()          ─┐
      ├── get_weather_forecast(days)     ─┤ MCP servers over stdio
      └── convert_currency(...)          ─┘ (subprocesses of the app)
      │
      ▼
Answer labelled 📚 / 🌐 / 💡  +  Sources list
```

The knowledge base is registered as a **tool** alongside the MCP tools rather than being
retrieved before every turn. That is what lets the model pick the knowledge base, an MCP
tool, or both from the tool descriptions, with no hand-written router — and it is why
destination facts have exactly one entry point, so MCP cannot answer them.

| Layer         | Choice                                     | Notes                                                      |
| ------------- | ------------------------------------------ | ---------------------------------------------------------- |
| Orchestration | LangChain                                  | `create_agent` + `MemorySaver`                             |
| LLM           | `gemini-*-flash`                           | via `langchain-google-genai`; override with `TRAVEL_MODEL` |
| Embeddings    | `BAAI/bge-small-en-v1.5`                   | local, 384-dim, no API key                                 |
| Vector store  | FAISS                                      | cosine distance, committed to the repo                     |
| MCP           | `mcp` (FastMCP) + `langchain-mcp-adapters` | two local stdio servers                                    |
| UI            | Streamlit                                  | chat + per-answer sources panel                            |

---

## Knowledge-base sources

Nine Wikivoyage pages, all **CC BY-SA 4.0** — which permits redistribution with
attribution, so the extracted content is committed under `data/processed/`.

| Source                   | Covers                                                   |
| ------------------------ | -------------------------------------------------------- |
| Wikivoyage: Singapore    | overview, transport, culture, food, climate, itineraries |
| Singapore/Riverside      | museums, indoor attractions                              |
| Singapore/Marina Bay     | gardens, indoor and outdoor attractions                  |
| Singapore/Chinatown      | culture, temples, food                                   |
| Singapore/Bugis          | culture, Kampong Glam, shopping                          |
| Singapore/Orchard        | shopping, indoor options                                 |
| Singapore/Sentosa        | family attractions, beaches                              |
| Singapore/East Coast     | food, outdoor, beaches                                   |
| Singapore/North and West | zoo, nature, family                                      |

The brief also suggests Visit Singapore pages. Those are © Singapore Tourism Board with
no general reuse grant, so they are not redistributed here.

Every chunk carries `source_title`, `source_url`, `license` and `section`, so citations
are real metadata rather than something the model reconstructs.

---

## RAG workflow

1. **Load** — MediaWiki `parse` API returns article body HTML (no site chrome).
2. **Clean** — strip navigation, edit links, footnotes, infoboxes → Markdown.
3. **Chunk** — split on Markdown headings first so a chunk never straddles two topics,
   then on size (1000 chars, 150 overlap). Each chunk is prefixed with its heading path
   (`Singapore > Get around > MRT`) before embedding, because sections are written
   elliptically — "Fares start at $1.09" embeds against nothing useful without it.
4. **Embed & store** — `bge-small-en-v1.5`, unit-normalised, into FAISS.
5. **Retrieve** — top-20 by cosine similarity, capped at 3 chunks per source so one page
   cannot monopolise the context, trimmed to 6.
6. **Ground** — coverage is scored as the **mean of the top-5 similarities**, not the
   single best, because one accidental strong chunk can outscore a genuinely covered
   question. Below the 0.20 threshold the tool returns `NO_RELEVANT_CONTENT` and the
   assistant says the topic is not covered instead of improvising.
7. **Cite** — the tool returns citations as structured data, rendered in the UI.

This gate catches *off-topic* questions but not *wrong-place* ones — "visa requirements
for Japan" scores highly because the knowledge base really does discuss visas, for
Singapore. Scope mismatch is handled by an explicit prompt rule instead.

---

## MCP tools

Both servers are implemented in this repo (`src/travel_assistant/mcp_layer/servers/`)
and run as **stdio subprocesses** of the app.

| Server     | Tools                                               | Upstream          | Key  |
| ---------- | --------------------------------------------------- | ----------------- | ---- |
| `weather`  | `get_current_weather`, `get_weather_forecast(days)` | Open-Meteo        | none |
| `currency` | `convert_currency(amount, from, to)`                | Frankfurter (ECB) | none |

**Failure contract.** No tool raises. Every result is a dict with a `status` field, and
failures return `{"status": "error", "error": ..., "guidance": ...}` where `guidance`
tells the model what to do — report the failure, never substitute a remembered value.
Failures are data the agent can reason about, not exceptions that abort the turn.

Servers are loaded through separate clients, so one failing server degrades the app to
the tools that did load. What failed is injected into the system prompt and shown in the
sidebar.

The weather tool also returns an `outdoor_friendly` flag per day (derived from the WMO
code and rain probability), which is what the agent keys indoor alternatives off.

---

## Prompt and context strategy

- **Three named sources.** The prompt states that the knowledge base, the MCP tools and
  the model's own reasoning are not interchangeable, with an explicit "you do not know
  these facts independently" for destination content.
- **The provenance contract** (📚 / 🌐 / 💡) gets the most prompt real estate, because it
  is the one thing the architecture cannot enforce structurally. Tool selection is driven
  by tool descriptions; the coverage gate is decided by the retriever; failure guidance
  travels in the tool result. The prompt handles only what code cannot.
- **Failures are enumerated per mode**, because "don't hallucinate" is not actionable —
  "an MCP `status: error` means report the failure and continue without weather
  adjustment" is.
- **Scope checking** covers the retrieval gate's blind spot: retrieval returning chunks
  does not by itself mean the question was answered.
- **Preferences** (trip length, budget, companions, interests) carry forward for the
  session via the LangGraph checkpointer, keyed by `thread_id`; newer statements win.

---

## Project layout

```
data/sources.yaml            citation registry — titles, URLs, licences
data/processed/              cleaned Markdown with frontmatter (committed)
vectorstore/singapore/       FAISS index (committed)
src/travel_assistant/
  config.py                  all tunables
  llm.py                     ChatGoogleGenerativeAI factory
  ingestion/                 fetch → clean → chunk → build_index
  rag/                       vectorstore, retriever (grounding gate), kb_tool
  mcp_layer/servers/         weather + currency MCP servers
  mcp_layer/client.py        per-server loading, failure isolation
  agent/                     prompts, agent graph, trace extraction
  ui/app.py                  Streamlit
"Sample Questions and their Responses.pdf"   sample questions and captured responses
```

---

## Acceptance criteria

| Criterion                               | Where                                                  |
| --------------------------------------- | ------------------------------------------------------ |
| Knowledge base from ≥3 resources        | 9 Wikivoyage sources, `data/sources.yaml`              |
| Embedding-based semantic retrieval      | `rag/vectorstore.py`, `rag/retriever.py`               |
| Grounded answers with source references | `rag/kb_tool.py` artifact → UI sources panel           |
| Weather via MCP                         | `mcp_layer/servers/weather_server.py`                  |
| Currency conversion via MCP             | `mcp_layer/servers/currency_server.py`                 |
| Combined RAG + MCP response             | ReAct agent calling `search_travel_kb` + an MCP tool in one turn |
| Multi-turn context                      | `MemorySaver` checkpointer, keyed by `thread_id`       |
| Tool selection by intent                | ReAct agent + tool descriptions                        |
| Missing knowledge / tool failures       | coverage gate + `status: error` contract               |
| Simple usable interface                 | `ui/app.py`                                            |


