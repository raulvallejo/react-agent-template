# AGENTS.md — ReAct Agent Template

This file is the authoritative guide for AI coding assistants (Claude Code, Cursor, Copilot, etc.)
working on this repository. Read it before touching any code.

---

## Overview

[PLACEHOLDER: 1–3 sentences describing what *your* agent does, who uses it, and why it exists.]

Example: "Market Scout is a ReAct agent that researches financial instruments on demand.
Given a ticker or company name, it searches for recent news, fundamentals, and analyst
sentiment, then synthesises a structured brief for retail investors."

**Template origin:** `github.com/raulvallejo/react-agent-template`
**Real-world example:** `github.com/raulvallejo/market-scout`

---

## Architecture

```
Browser / Client
      │
      ▼
FastAPI  (backend/main.py)
      │
      ├─ GET  /              → health check
      └─ POST /api/research
               │
               ├─ 1. Input guardrail  (Groq, raw SDK)
               │        └─ rejects off-topic / unsafe queries → HTTP 400
               │
               └─ 2. ReAct AgentExecutor  (LangChain + ChatGroq)
                        │
                        ├─ Thought  ──▶  LLM (llama-3.3-70b-versatile)
                        ├─ Action   ──▶  Tool (Tavily web search)
                        └─ Observation ─▶ LLM (repeat until Final Answer)
```

**Key design decisions:**
- Guardrail uses the raw Groq SDK (not LangChain) so it can be replaced or disabled
  without affecting the agent internals.
- `_safe_track` wraps OPIK tracing in a try/except so the service degrades gracefully
  when `OPIK_API_KEY` is missing.
- `return_intermediate_steps=True` is required — removing it breaks the `/api/research`
  response shape.
- `handle_parsing_errors=True` prevents the agent from crashing on malformed LLM output.

---

## Pipeline (step by step)

1. **Request arrives** at `POST /api/research` with `{query, session_id}`.
2. **Guardrail** — `run_guardrail(query)` calls Groq and returns `(allowed, reason)`.
   If `allowed` is `False`, raise HTTP 400 immediately.
3. **Agent** — `run_agent(query, session_id)` calls `agent_executor.ainvoke()`.
   The executor runs the ReAct loop: Thought → Action → Observation, up to
   `max_iterations` times.
4. **Normalise steps** — `intermediate_steps` is a list of `(AgentAction, str)` tuples.
   We convert each into `{thought, action, action_input, observation}`.
5. **Return** `{result, steps, session_id}`.

---

## LLM setup

| Setting       | Value                        | Where to change |
|---------------|------------------------------|-----------------|
| Agent model   | `llama-3.3-70b-versatile`    | `AGENT_MODEL` constant in `main.py` |
| Guardrail model | `llama-3.3-70b-versatile`  | `GUARD_MODEL` constant in `main.py` |
| Temperature   | `0` (deterministic)          | `ChatGroq(temperature=...)` |
| Max iterations | `10`                        | `AgentExecutor(max_iterations=...)` |

[PLACEHOLDER: Note any model constraints specific to your deployment, e.g. rate limits,
token budgets, or reasons you chose a particular model.]

---

## OPIK instrumentation

Two functions are traced as separate spans:

| Span name     | Function          | What it captures |
|---------------|-------------------|------------------|
| `guardrail`   | `run_guardrail()` | Raw prompt, verdict, latency |
| `react_agent` | `run_agent()`     | Full ReAct loop, tool calls, final output |

The `_safe_track` decorator factory handles the case where OPIK is not configured —
it logs a warning and returns the unwrapped function. This means **you can develop
locally without setting `OPIK_API_KEY`**.

OPIK project name is controlled by the `OPIK_PROJECT_NAME` env var
(default: `"react-agent-template"`).

[PLACEHOLDER: Add a link to your OPIK dashboard once the project is running.]

---

## Guardrails

The input guardrail (`run_guardrail`) is intentionally simple: one Groq call that
returns `{"allowed": true}` or `{"allowed": false, "reason": "..."}`.

**When to update it:**
- When you add a new domain focus (e.g. only allow financial queries).
- When you observe false positives / negatives in production.
- When you want to add output guardrails (post-process the agent's final answer).

**Current rejection criteria** (see `GUARDRAIL_SYSTEM` in `main.py`):
- Requests for illegal content
- Purely conversational inputs
- Queries unrelated to research

[PLACEHOLDER: Document your project-specific rejection rules here once you've
customised `GUARDRAIL_SYSTEM`.]

---

## Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `TavilySearchResults` | `langchain-community` | Real-time web search |

[PLACEHOLDER: Add rows as you add tools. Include: tool name, source package,
purpose, and any configuration (e.g. `max_results`, auth method).]

**To add a tool:**
1. Import or implement it so it inherits from `langchain_core.tools.BaseTool`
   (or use `@tool` decorator).
2. Append it to the `tools = [...]` list in `main.py`.
3. Document it in this table.

---

## Deployment (Render)

The `Procfile` tells Render how to start the service:

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Environment variables required in Render dashboard:**

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq API key |
| `TAVILY_API_KEY` | Tavily search API key |
| `OPIK_API_KEY` | Comet OPIK API key |
| `OPIK_WORKSPACE` | OPIK workspace slug |
| `OPIK_PROJECT_NAME` | OPIK project name (optional, defaults to `react-agent-template`) |

**Root directory:** set to `backend/` in the Render service settings.

[PLACEHOLDER: Add any additional env vars your customised agent requires.]

---

## Environment variables (local)

Create `backend/.env` (never commit this file):

```
GROQ_API_KEY=gsk_...
TAVILY_API_KEY=tvly-...
OPIK_API_KEY=...
OPIK_WORKSPACE=your-workspace
OPIK_PROJECT_NAME=react-agent-template
```

---

## Critical rules for AI assistants

1. **Do not remove `return_intermediate_steps=True`** from `AgentExecutor`.
   The `/api/research` response schema depends on it.

2. **Do not mock the guardrail** when writing tests — the guardrail is a thin Groq
   call and should be tested with real (or VCR-cassette) HTTP responses.

3. **The ReAct prompt template must contain all four variables:**
   `{tools}`, `{tool_names}`, `{input}`, `{agent_scratchpad}`.
   Removing any of them breaks `create_react_agent`.

4. **`_safe_track` is not a no-op** — it wraps async functions with OPIK tracing.
   Do not replace it with `@opik.track(...)` directly unless you also add the
   try/except fallback.

5. **CORS is wide open** (`allow_origins=["*"]`). Tighten this before shipping
   to production by setting the allowed origin to your frontend domain.

6. **Never commit `.env`** — add it to `.gitignore` if not already there.

---

## Known gotchas

- **`handle_parsing_errors=True`** silently retries when the LLM produces malformed
  output. If the agent loops without progressing, check whether the LLM is
  consistently failing to follow the ReAct format and adjust the prompt.

- **Tavily `max_results`** affects both quality and token cost. At 5 results,
  a single search can consume ~2 k tokens. Reduce to 3 for cost-sensitive workloads.

- **Groq rate limits** — the free tier has strict RPM limits. Add retry logic
  (e.g. `tenacity`) if you see `429` errors under load.

- **OPIK `configure(use_local=False)`** assumes cloud OPIK. If you are running
  OPIK locally, set `use_local=True` or remove the call entirely.

- **`session_id` is passed to LangChain config but not used for memory** in this
  template. To add conversation memory, wire in a `ConversationBufferMemory`
  keyed by `session_id`.

[PLACEHOLDER: Add project-specific gotchas as you discover them.]
