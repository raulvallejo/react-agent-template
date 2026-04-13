"""
ReAct Agent — FastAPI backend template
=======================================
Architecture: FastAPI → Guardrail (Groq) → ReAct Agent (LangChain + Groq) → Tools (Tavily)
Observability: OPIK via _safe_track decorator
Deployment: Render (see Procfile)

[PLACEHOLDER] Replace the research domain, tools, and system prompt to fit your use case.
"""

import json
import logging
import os
from typing import Any

import opik
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from langchain.agents import AgentExecutor, create_react_agent
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OPIK — observability
# Configure the OPIK project name to match your project.
# [PLACEHOLDER] Change "react-agent-template" to your project name.
# ---------------------------------------------------------------------------

opik.configure(use_local=False)   # uses OPIK_API_KEY + OPIK_WORKSPACE from env

OPIK_PROJECT = os.getenv("OPIK_PROJECT_NAME", "react-agent-template")


def _safe_track(name: str):
    """
    Decorator factory that wraps a coroutine with opik.track for tracing.
    Falls back to the bare function if OPIK is misconfigured, so the agent
    still runs in environments where tracing is not set up.
    """
    def decorator(fn):
        try:
            return opik.track(name=name, project_name=OPIK_PROJECT)(fn)
        except Exception:
            log.warning("OPIK tracking unavailable — running without tracing.")
            return fn
    return decorator


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ReAct Agent API",
    description="LangChain ReAct agent with Groq + Tavily",
    version="1.0.0",
)

# [PLACEHOLDER] Tighten origins before going to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Groq clients
# Two separate clients:
#   1. groq_client  — raw Groq SDK, used only for the input guardrail check.
#   2. ChatGroq     — LangChain wrapper, used inside the ReAct agent.
# Keeping them separate makes it easy to swap the guardrail model independently.
# ---------------------------------------------------------------------------

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

# [PLACEHOLDER] Swap model slugs here if Groq releases newer versions.
AGENT_MODEL = "llama-3.3-70b-versatile"
GUARD_MODEL = "llama-3.3-70b-versatile"

llm = ChatGroq(
    model=AGENT_MODEL,
    temperature=0,          # deterministic reasoning
    api_key=os.environ["GROQ_API_KEY"],
)

# ---------------------------------------------------------------------------
# Tools
# [PLACEHOLDER] Add, remove, or replace tools here.
# Each tool must have a `.name`, `.description`, and be callable.
# LangChain's TavilySearchResults already satisfies that contract.
# ---------------------------------------------------------------------------

search_tool = TavilySearchResults(
    max_results=5,          # [PLACEHOLDER] Tune result count vs. token cost.
    api_key=os.environ["TAVILY_API_KEY"],
)

tools = [search_tool]

# ---------------------------------------------------------------------------
# ReAct prompt
# LangChain's create_react_agent requires these exact variables:
#   {tools}, {tool_names}, {input}, {agent_scratchpad}
# The system block is where you inject domain expertise.
# [PLACEHOLDER] Rewrite the system block for your domain.
# ---------------------------------------------------------------------------

REACT_TEMPLATE = """You are a rigorous research assistant. Your job is to answer
the user's question accurately using web search. Follow the ReAct pattern strictly:
think step-by-step, search when you need evidence, and synthesise a final answer
only when you have enough information.

Rules:
- Always prefer recent, authoritative sources.
- If a search returns irrelevant results, reformulate and try again.
- Never fabricate URLs or statistics.
- Keep your final answer concise and well-structured.

[PLACEHOLDER] Add domain-specific rules here (e.g. "Focus only on financial data",
"Always cite sources in APA format", etc.)

Available tools:
{tools}

Use the following format — do not deviate:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

react_prompt = PromptTemplate.from_template(REACT_TEMPLATE)

# Build the ReAct agent + executor once at startup (thread-safe; stateless per call).
agent = create_react_agent(llm=llm, tools=tools, prompt=react_prompt)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,           # logs Thought/Action/Observation to stdout
    handle_parsing_errors=True,  # recovers from malformed LLM output
    max_iterations=10,      # [PLACEHOLDER] Increase for deeper research tasks.
    return_intermediate_steps=True,  # required so we can return reasoning trace
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    query: str
    session_id: str = "default"


class ResearchResponse(BaseModel):
    result: str
    steps: list[dict[str, Any]]
    session_id: str


# ---------------------------------------------------------------------------
# Input guardrail
# Runs *before* the agent to reject off-topic or unsafe queries.
# Using a fast, separate LLM call keeps latency low.
# [PLACEHOLDER] Rewrite the guardrail prompt for your domain / safety policy.
# ---------------------------------------------------------------------------

GUARDRAIL_SYSTEM = """You are a query classifier. Your only job is to decide
whether a user query is appropriate for a research assistant that answers
questions by searching the web.

Respond with exactly one JSON object and nothing else:
{"allowed": true}   — if the query is a legitimate research question
{"allowed": false, "reason": "<short explanation>"}  — if it should be blocked

Block queries that:
- Ask for illegal content or instructions
- Are purely conversational (e.g., "hi", "how are you")
- Are completely unrelated to research or information-gathering
- [PLACEHOLDER] Add domain-specific rejection criteria here

Do NOT be overly restrictive. When in doubt, allow."""


@_safe_track(name="guardrail")
async def run_guardrail(query: str) -> tuple[bool, str]:
    """
    Returns (is_allowed, rejection_reason).
    If OPIK tracing is active this call is recorded as its own span.
    """
    response = groq_client.chat.completions.create(
        model=GUARD_MODEL,
        messages=[
            {"role": "system", "content": GUARDRAIL_SYSTEM},
            {"role": "user", "content": query},
        ],
        temperature=0,
        max_tokens=128,
    )
    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if the model wraps the JSON.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError:
        # If parsing fails, be permissive — don't block legitimate queries.
        log.warning("Guardrail returned non-JSON: %s", raw)
        return True, ""

    allowed = verdict.get("allowed", True)
    reason = verdict.get("reason", "")
    return allowed, reason


# ---------------------------------------------------------------------------
# Core agent runner
# Isolated in its own function so OPIK can trace it as a separate span.
# ---------------------------------------------------------------------------

@_safe_track(name="react_agent")
async def run_agent(query: str, session_id: str) -> dict[str, Any]:
    """
    Invokes the AgentExecutor and normalises the intermediate steps into a
    list of dicts that the frontend can render as Thought/Action/Observation cards.
    """
    raw = await agent_executor.ainvoke(
        {"input": query},
        config={"configurable": {"session_id": session_id}},
    )

    steps: list[dict[str, Any]] = []
    for action, observation in raw.get("intermediate_steps", []):
        steps.append(
            {
                "thought": action.log.split("Action:")[0].replace("Thought:", "").strip(),
                "action": action.tool,
                "action_input": action.tool_input,
                # observation may be a list of dicts (Tavily) or a plain string
                "observation": observation,
            }
        )

    return {"result": raw["output"], "steps": steps}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"])
async def health():
    """Liveness check — used by Render to confirm the service is up."""
    return {"status": "ok", "model": AGENT_MODEL}


@app.post("/api/research", response_model=ResearchResponse, tags=["agent"])
async def research(req: ResearchRequest):
    """
    Main endpoint. Flow:
      1. Guardrail — reject bad queries early.
      2. ReAct agent — searches the web and synthesises an answer.
      3. Return result + reasoning trace.
    """
    log.info("Received query | session=%s | query=%.80s", req.session_id, req.query)

    # --- Step 1: guardrail ---
    allowed, reason = await run_guardrail(req.query)
    if not allowed:
        log.warning("Query blocked | session=%s | reason=%s", req.session_id, reason)
        raise HTTPException(status_code=400, detail=f"Query not allowed: {reason}")

    # --- Step 2: agent ---
    try:
        result = await run_agent(req.query, req.session_id)
    except Exception as exc:
        log.exception("Agent failed | session=%s", req.session_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    log.info("Query complete | session=%s | steps=%d", req.session_id, len(result["steps"]))

    return ResearchResponse(
        result=result["result"],
        steps=result["steps"],
        session_id=req.session_id,
    )
