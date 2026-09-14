"""Investigation Layer (design-doc §5.8) + LLM Reasoning (§5.10).

Runs a manual tool-calling loop against Gemini where the *only* tools
available are the six MCP tools (§5.9) — the model never touches Postgres,
Prometheus, or an embedding endpoint directly, only what those tools hand
back through the MCP client session below.

The loop is manual (not the SDK's "automatic function calling" convenience
path) because that path only supports plain sync Python callables, and the
MCP client here is inherently async. Manually appending each turn's
`candidate.content` back into `contents` relies on the installed
`google-genai` SDK actually modeling Gemini 3's `thought_signature` field on
`Part` — an opaque token the model attaches to function-call turns that
must be echoed back unmodified on the next turn. `google-genai==1.30.0`
does not (`Part` has no such field), so a byte-perfect round-trip of
`candidate.content` still silently dropped it and the API rejected the next
turn ("missing thought_signature"); pinning `google-genai>=2.20` fixed it.

Once the model stops calling tools, one final call — with no tools attached
— forces the synthesis into the InvestigationResult schema
(backend/app/schemas/investigation.py), which has no "root_cause" field for
the model to fill in.
"""
import json
import os

from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.schemas.investigation import InvestigationResult

MCP_URL = os.environ.get("MCP_URL", "http://mcp-server:8100/mcp")
# Configurable because Gemini's free tier caps each *model* at a low daily
# request quota (20/day at time of writing) — switching models via env var
# gives a fresh quota bucket without a code change, which matters a lot for
# a live demo/interview after burning quota during development.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
MAX_TOOL_ROUNDS = 6

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


# Hand-mirrored from mcp-server/server.py's @mcp.tool() signatures. Gemini's
# function-calling schema (an OpenAPI 3.0 subset) doesn't cleanly accept the
# `anyOf`/`null` shapes MCP's auto-generated JSON Schema produces for
# optional Python args, so these are declared explicitly here rather than
# converted dynamically from MCP's introspection. MCP itself stays the
# single source of truth for what the tools actually *do*; this is just a
# static mirror of their shape for Gemini's benefit.
_TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_change_details",
        description=(
            "Git diff metadata (commit SHA, author, changed files) for a "
            "service's most recent deployment."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={"service": types.Schema(type="STRING")},
            required=["service"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_dependency_graph",
        description=(
            'Service dependency graph. Pass a service name for just its direct '
            'dependencies/dependents, or "all" for the full graph.'
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={"service": types.Schema(type="STRING")},
            required=["service"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_blast_radius",
        description=(
            "Services potentially impacted downstream of a change to "
            "`service`, ranked by dependency distance."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={"service": types.Schema(type="STRING")},
            required=["service"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_service_telemetry",
        description=(
            "Current latency, error rate, request rate, CPU, and memory "
            "for a service, live from Prometheus."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={"service": types.Schema(type="STRING")},
            required=["service"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_anomalies",
        description="Which demo mesh services are currently behaving anomalously, and on which metric.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="search_historical_incidents",
        description="Semantically similar past incidents for a free-text description of current evidence.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "query": types.Schema(type="STRING"),
                "limit": types.Schema(type="INTEGER"),
            },
            required=["query", "limit"],
        ),
    ),
]

_GEMINI_TOOLS = [types.Tool(function_declarations=_TOOL_DECLARATIONS)]

_SYSTEM_PROMPT = """You are an investigation assistant for a distributed \
systems observability platform. A change was just deployed to the service \
"{service}". Gather evidence using the available tools to help an engineer \
understand what changed, what could be affected, and what evidence exists.

Rules:
- Only state facts you obtained via tool calls. Never invent evidence.
- Call get_change_details first to see what changed.
- Then call get_dependency_graph and get_blast_radius to see what's \
potentially impacted.
- Then call get_service_telemetry for "{service}" and for at least one \
potentially impacted service, and get_anomalies to see what's currently \
unusual across the mesh.
- Then call search_historical_incidents with a short free-text summary of \
what you've found so far, to check whether something similar happened \
before.
- Once you've called all six tool types (or confirmed a tool has nothing \
relevant), stop calling tools and wait for the synthesis instruction.
- Never claim to know "the root cause." Never claim the deployment \
"caused" anything downstream — only that it "preceded" observed signals. \
Say "potentially impacted", never "affected" or "broken".
"""

_SYNTHESIS_PROMPT = """Using only the evidence gathered above, produce the \
structured investigation result now. Every hypothesis must cite \
supporting_evidence drawn from what you retrieved, and every hypothesis \
must state limitations — what this evidence does not prove (for example, \
that it does not establish causation, or that a historical-incident match \
is similar but not confirmed identical). Do not state a single root cause; \
if the evidence supports more than one plausible hypothesis, include more \
than one."""


async def _call_mcp_tool(mcp_session: ClientSession, name: str, args: dict) -> dict:
    result = await mcp_session.call_tool(name, args)
    if not result.content:
        return {}
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"raw": text}


async def run_investigation(service: str) -> InvestigationResult:
    client = _get_client()

    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()

            contents: list[types.Content] = [
                types.Content(
                    role="user",
                    parts=[types.Part(text=_SYSTEM_PROMPT.format(service=service))],
                )
            ]

            for _ in range(MAX_TOOL_ROUNDS):
                response = await client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(tools=_GEMINI_TOOLS),
                )
                candidate = response.candidates[0]
                contents.append(candidate.content)

                function_calls = [
                    part.function_call for part in candidate.content.parts if part.function_call
                ]
                if not function_calls:
                    break

                response_parts = []
                for call in function_calls:
                    tool_result = await _call_mcp_tool(mcp_session, call.name, dict(call.args or {}))
                    response_parts.append(
                        types.Part.from_function_response(name=call.name, response=tool_result)
                    )
                contents.append(types.Content(role="user", parts=response_parts))

            contents.append(types.Content(role="user", parts=[types.Part(text=_SYNTHESIS_PROMPT)]))
            final = await client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=InvestigationResult,
                ),
            )
            return InvestigationResult.model_validate_json(final.text)
