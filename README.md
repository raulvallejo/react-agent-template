# ReAct Agent Template

A production-ready starting point for building ReAct (Reasoning + Acting) agents
with FastAPI, LangChain, Groq, Tavily, and OPIK.

**Real-world example built from this template →** [market-scout](https://github.com/raulvallejo/market-scout)

---

## What is a ReAct agent?

ReAct ([Yao et al., 2023](https://arxiv.org/abs/2210.03629)) is a prompting pattern
that interleaves *reasoning* and *acting* in a loop:

```
Thought:      "I need to find the latest funding round for Acme Corp."
Action:       tavily_search_results_json
Action Input: "Acme Corp funding round 2025"
Observation:  [{"title": "...", "url": "...", "content": "..."}]
Thought:      "The result mentions a $40 M Series B. Let me verify the date."
...
Final Answer: "Acme Corp raised a $40 M Series B in March 2025 (source: ...)."
```

The agent keeps looping until it has enough information to produce a final answer,
or until it hits `max_iterations`. This makes it dramatically better at
research tasks than a single-shot LLM call.

---

## Why this template?

| Problem | How this template solves it |
|---|---|
| Boilerplate is tedious | Working FastAPI + LangChain wiring, ready to run |
| Agents go off the rails | Input guardrail blocks bad queries before the agent fires |
| No visibility into reasoning | OPIK traces every span; frontend shows the full chain |
| Hard to deploy | Procfile + Render-ready env var list |
| Hard to customise | Every section marked with `[PLACEHOLDER]` comments |

---

## Stack

| Layer | Technology | Purpose |
|---|---|---|
| API | [FastAPI](https://fastapi.tiangolo.com) | HTTP server, request validation |
| Agent framework | [LangChain](https://python.langchain.com) | `create_react_agent` + `AgentExecutor` |
| LLM | [Groq](https://groq.com) — `llama-3.3-70b-versatile` | Fast inference for both agent and guardrail |
| Web search | [Tavily](https://tavily.com) | Real-time search results |
| Observability | [OPIK](https://www.comet.com/site/products/opik/) | Traces, spans, prompt logging |
| Frontend | Vanilla HTML/CSS/JS | Zero-dependency UI, single file |
| Deployment | [Render](https://render.com) | Procfile-based deployment |

---

## Project structure

```
react-agent-template/
├── backend/
│   ├── main.py          # FastAPI app — all agent logic lives here
│   ├── requirements.txt # Pinned dependencies
│   └── Procfile         # Render start command
├── frontend/
│   └── index.html       # Single-file dark-theme UI
├── AGENTS.md            # Guide for AI coding assistants
└── README.md
```

---

## Quick start

### 1. Clone & install

```bash
git clone https://github.com/raulvallejo/react-agent-template.git
cd react-agent-template/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set environment variables

Create `backend/.env`:

```
GROQ_API_KEY=gsk_...
TAVILY_API_KEY=tvly-...
OPIK_API_KEY=...
OPIK_WORKSPACE=your-workspace
OPIK_PROJECT_NAME=react-agent-template
```

Get your keys:
- Groq → https://console.groq.com/keys
- Tavily → https://app.tavily.com/home
- OPIK → https://www.comet.com/signup

### 3. Run the backend

```bash
cd backend
uvicorn main:app --reload
```

API is live at `http://localhost:8000`. Visit `http://localhost:8000/docs` for
the auto-generated Swagger UI.

### 4. Open the frontend

Open `frontend/index.html` directly in your browser (no build step needed),
or serve it:

```bash
python -m http.server 3000 --directory frontend
```

Then visit `http://localhost:3000`.

---

## What to customise

Every file has `[PLACEHOLDER]` comments marking the exact spots to change.
Here is the short version:

| What | Where | How |
|---|---|---|
| Agent domain / persona | `main.py` → `REACT_TEMPLATE` | Rewrite the system block |
| Guardrail rules | `main.py` → `GUARDRAIL_SYSTEM` | Add / remove rejection criteria |
| LLM model | `main.py` → `AGENT_MODEL`, `GUARD_MODEL` | Swap Groq model slug |
| Tools | `main.py` → `tools = [...]` | Add `BaseTool` subclasses |
| Max search results | `main.py` → `TavilySearchResults(max_results=...)` | Tune cost vs. quality |
| Max reasoning steps | `main.py` → `AgentExecutor(max_iterations=...)` | Increase for deep tasks |
| UI heading & placeholder | `frontend/index.html` | Update `[PLACEHOLDER]` blocks |
| Accent colour | `frontend/index.html` → `:root` → `--accent` | Any CSS hex colour |
| API base URL | `frontend/index.html` → `const API_BASE` | Your Render URL |
| OPIK project name | `.env` → `OPIK_PROJECT_NAME` | Any string |

---

## Deploying to Render

1. Push this repo to GitHub.
2. Create a new **Web Service** on Render, connect your repo.
3. Set **Root Directory** to `backend`.
4. Render auto-detects the Procfile:
   ```
   web: uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
5. Add all five environment variables in the Render dashboard.
6. Update `API_BASE` in `frontend/index.html` to your Render service URL.

---

## API reference

### `GET /`

Health check.

**Response:**
```json
{"status": "ok", "model": "llama-3.3-70b-versatile"}
```

### `POST /api/research`

Run the ReAct agent.

**Request:**
```json
{
  "query": "What are the top open-source LLMs in 2025?",
  "session_id": "user-abc-123"
}
```

**Response:**
```json
{
  "result": "The top open-source LLMs in 2025 are ...",
  "steps": [
    {
      "thought": "I need to search for recent rankings of open-source LLMs.",
      "action": "tavily_search_results_json",
      "action_input": "top open-source LLMs 2025",
      "observation": [{"title": "...", "url": "...", "content": "..."}]
    }
  ],
  "session_id": "user-abc-123"
}
```

**Error (guardrail blocked):**
```json
{"detail": "Query not allowed: purely conversational input"}
```
HTTP status `400`.

---

## Architecture decisions

**Why two separate Groq clients?**
The guardrail uses the raw `groq.Groq` SDK while the agent uses `ChatGroq`
(LangChain's wrapper). Keeping them separate means you can swap the guardrail
to a different provider, a fine-tuned model, or a rule-based classifier without
touching the agent wiring.

**Why `_safe_track` instead of `@opik.track` directly?**
`opik.configure()` raises if the API key is missing. Wrapping in try/except lets
you run locally without any OPIK credentials while still getting full tracing in
production.

**Why `handle_parsing_errors=True`?**
LLMs occasionally produce malformed ReAct output (e.g. missing `Action Input:`).
This flag makes the executor retry rather than crash, which is the right default
for a production service.

**Why a single HTML file for the frontend?**
Templates are meant to be dropped into existing projects. A single file with zero
build tooling is the lowest-friction way to verify the backend works before you
integrate it into your actual frontend stack.

---

## License

MIT — see below.

```
MIT License

Copyright (c) 2025 Raul Vallejo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
