"""The agent loop: run one agent (with audit), run a ticket through the Boss, run the board."""

import json
import uuid
from collections.abc import AsyncIterable
from typing import Any

from pydantic_ai import FunctionToolCallEvent, FunctionToolResultEvent, RunContext, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import RunUsage

from .. import audit
from ..config import MODEL_NAME, TEAM_REQUEST_LIMIT, TEAM_TOOL_CALL_LIMIT
from ..models import AgentReport, BossDecision, TeamDeps, TeamState
from . import accounting, boss, customer_service, facilities, inventory
from .base import shop_mcp

AGENTS = {m.NAME: m.agent for m in (boss, inventory, accounting, facilities, customer_service)}
LIMITS = UsageLimits(request_limit=TEAM_REQUEST_LIMIT, tool_calls_limit=TEAM_TOOL_CALL_LIMIT)


def _step(deps: TeamDeps, kind: str, **data: Any) -> None:
    """A live 'what is this agent doing right now' event for the dashboard (also kept in the audit trail)."""
    audit.append({"type": "agent_step", "step": kind, "run_id": deps.team.run_id, "ticket_id": deps.team.ticket_id,
                  "agent": deps.agent_name, "agent_run_id": deps.agent_run_id, "chain": deps.chain, **data})


async def _stream_steps(ctx: RunContext[TeamDeps], events: AsyncIterable[Any]) -> None:
    async for event in events:
        if isinstance(event, FunctionToolCallEvent) and event.part.tool_name != "final_result":
            _step(ctx.deps, "tool_call", tool=event.part.tool_name, args=event.part.args_as_dict())
        elif isinstance(event, FunctionToolResultEvent) and getattr(event.part, "tool_name", "") != "final_result":
            content = getattr(event.part, "content", "")
            text = content if isinstance(content, str) else json.dumps(content, default=str)
            _step(ctx.deps, "tool_result", tool=getattr(event.part, "tool_name", None), result=audit.redact(text)[:400])


def _fallback(name: str, ticket_id: int | None, reason: str) -> AgentReport | BossDecision:
    if name == "boss":
        return BossDecision(ticket_id=ticket_id or 0, final_status="blocked", decision=f"Run stopped: {reason}",
                            human_actions_needed=["Review this ticket manually."], rationale=reason)
    return AgentReport(agent=name, summary=f"Stopped: {reason}", blockers=[reason], needs_human=True,
                       recommendation="Escalate to a human.")


async def run_agent(name: str, task: str, *, team: TeamState, parent: TeamDeps | None = None,
                    usage: RunUsage | None = None) -> Any:
    """One agent loop: the model thinks, calls MCP tools or delegates, and repeats until it
    returns its structured output. Every run is appended to output/audit_trail.json."""
    deps = TeamDeps(
        team=team,
        agent_name=name,
        agent_run_id=uuid.uuid4().hex[:8],
        chain=(parent.chain if parent else []) + [name],
        parent_agent_run_id=parent.agent_run_id if parent else None,
    )
    messages, status, error = [], "ok", None
    _step(deps, "started", task=task[:600], parent_agent_run_id=deps.parent_agent_run_id)
    try:
        result = await AGENTS[name].run(task, deps=deps, usage=usage, usage_limits=LIMITS,
                                        event_stream_handler=_stream_steps)
        output, messages = result.output, result.new_messages()
    except UsageLimitExceeded as e:
        status, error = "stopped_usage_limit", str(e)
        output = _fallback(name, team.ticket_id, f"usage limit hit ({e})")
    except Exception as e:  # keep the team alive; the audit shows what broke
        status, error = "error", f"{type(e).__name__}: {e}"
        output = _fallback(name, team.ticket_id, error)

    trace = audit.tool_trace(messages)
    if name == "boss" and parent is None:
        team.boss_ok = status == "ok"
    if name == "boss" and status == "ok":
        # Record who the Boss really delegated to (from the trace), not what the model claims.
        output.delegated_to = list(dict.fromkeys(c["args"]["to_agent"] for c in trace if c["tool"] == "delegate"))
    audit.append({
        "type": "agent_run",
        "run_id": team.run_id,
        "ticket_id": team.ticket_id,
        "agent": name,
        "agent_run_id": deps.agent_run_id,
        "parent_agent_run_id": deps.parent_agent_run_id,
        "chain": deps.chain,
        "depth": deps.depth,
        "model": MODEL_NAME,
        "task": task,
        "tool_calls": trace,
        "delegated_to": [c["args"].get("to_agent") for c in trace if c["tool"] == "delegate"],
        "output": output.model_dump(),
        "status": status,
        "error": error,
        "team_usage_so_far": {"requests": usage.requests, "input_tokens": usage.input_tokens,
                              "output_tokens": usage.output_tokens} if usage else None,
    })
    return output


async def run_ticket(ticket_id: int) -> BossDecision:
    """The Boss owns the ticket from start to final call; specialists join via delegate.
    Sets `team_run_ok` on the result so callers never treat a crashed run as finished work."""
    team = TeamState(run_id=uuid.uuid4().hex[:8], ticket_id=ticket_id)
    usage = RunUsage()
    async with shop_mcp:  # start the MCP server once for the whole team
        decision = await run_agent(
            "boss",
            f"Work ticket {ticket_id} from the board to a final call. Start with get_ticket({ticket_id}).",
            team=team, usage=usage,
        )
    audit.append({
        "type": "ticket_done", "run_id": team.run_id, "ticket_id": ticket_id, "model": MODEL_NAME,
        "decision": decision.model_dump(), "delegations": team.delegations, "run_ok": team.boss_ok,
        "team_usage": {"requests": usage.requests, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
    })
    decision._team_run_ok = team.boss_ok
    return decision


async def run_board() -> list[BossDecision]:
    """Work every open ticket, oldest first (one at a time so cash checks stay honest)."""
    async with shop_mcp:
        board = await shop_mcp.direct_call_tool("list_open_tickets", {})
        ticket_ids = [t["id"] for t in board["open_tickets"]]
        return [await run_ticket(tid) for tid in ticket_ids]
