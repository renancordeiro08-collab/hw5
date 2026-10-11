"""Settings for the Campus Customs agent team: paths, the ONE allowed model, and loop limits."""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

PROJECT_DIR = Path(__file__).resolve().parent.parent
# Project .env first; fall back to the workspace .env (keys only, never printed).
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PROJECT_DIR.parent / ".env")

# The assignment allows exactly one model. It is not read from OPENAI_MODEL on purpose,
# so a different value in some .env can never leak into a run.
MODEL_NAME = "gpt-6-luna"
if os.getenv("HW5_MODEL", MODEL_NAME) != MODEL_NAME:
    raise RuntimeError(f"HW5 only allows {MODEL_NAME}; refusing to start with HW5_MODEL={os.getenv('HW5_MODEL')}.")

ORIGINAL_DB = PROJECT_DIR / "data" / "campus_customs.db"
WORKING_DB = Path(os.getenv("CAMPUS_DB_PATH", PROJECT_DIR / "data" / "campus_customs_new.db"))
MCP_SERVER = PROJECT_DIR / "mcp_server" / "server.py"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
AUDIT_TRAIL = PROJECT_DIR / "output" / "audit_trail.json"

# Agent-loop guardrails (shared by the whole team for one ticket).
MAX_DELEGATION_DEPTH = 3        # Boss -> A -> B -> C, no deeper
MAX_DELEGATIONS_PER_TICKET = 10
TEAM_REQUEST_LIMIT = 40         # model calls per ticket across all agents
TEAM_TOOL_CALL_LIMIT = 60       # tool calls per ticket across all agents


def build_model() -> OpenAIResponsesModel:
    """gpt-6-luna through Portkey, using the course's proven client pattern."""
    key = os.getenv("PORTKEY_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set (add it to .env).")
    client = AsyncOpenAI(
        api_key=key,
        base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1"),
        default_headers={
            "x-portkey-api-key": key,
            "x-portkey-provider": os.getenv("PORTKEY_PROVIDER", "openai"),
            # Never replay a cached answer: cached Responses items carried fake ids that broke a run,
            # and every official run must reflect what the agents decide now.
            "x-portkey-cache-force-refresh": "true",
        },
    )
    # Responses API: gpt-6-luna only allows tools + reasoning here (Chat Completions rejects that combo).
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
