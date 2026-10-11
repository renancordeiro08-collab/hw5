"""Shared plumbing for every agent: the MCP connection, per-agent tool allowlists,
identity stamping, and the `delegate` tool that gives the team full connectivity."""

import sys
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import CallToolFunc, MCPToolset

from ..config import (
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MCP_SERVER,
    PROMPTS_DIR,
    WORKING_DB,
    build_model,
)
from ..models import AgentName, TeamDeps

# Tools that move money or decide approvals. No agent ever gets these;
# only the human operator (dashboard) can call them.
HUMAN_ONLY_TOOLS = {"approve_request", "reject_request", "list_approval_requests"}

# Arguments that record WHO did something. We overwrite them with the calling agent's
# real name so an agent can never file a request or draft under someone else's name.
IDENTITY_ARGS = ("requested_by", "written_by", "updated_by")

# Which MCP tools each agent may see and call (least privilege).
AGENT_TOOLS: dict[str, set[str]] = {
    "boss": {"list_open_tickets", "get_ticket", "check_cash_position", "update_ticket_status"},
    "inventory": {"get_ticket", "check_stock_and_pricing", "check_vendor_and_invoices"},
    "accounting": {
        "get_ticket", "check_vendor_and_invoices", "check_lease_and_cash", "check_cash_position",
        "check_discount_margin", "request_payment_approval", "request_purchase_order",
    },
    "facilities": {"get_ticket", "check_lease_and_cash", "check_cash_position"},
    "customer_service": {"get_ticket", "check_stock_and_pricing", "save_customer_draft"},
}
assert not any(tools & HUMAN_ONLY_TOOLS for tools in AGENT_TOOLS.values()), "agents must never get human-only tools"


async def _guard_tool_call(ctx: RunContext[TeamDeps], call_tool: CallToolFunc, name: str, args: dict[str, Any]) -> Any:
    """Runs before every MCP call: block anything outside the agent's allowlist and stamp identity."""
    me = ctx.deps.agent_name
    if name in HUMAN_ONLY_TOOLS or name not in AGENT_TOOLS[me]:
        return {"refused": True, "reason": f"{me} is not allowed to call {name}."}
    args = {**args, **{k: me for k in IDENTITY_ARGS if k in args}}
    return await call_tool(name, args)


# One MCP server process (stdio) shared by the whole team; every fact comes from here.
shop_mcp = MCPToolset(
    Client(StdioTransport(command=sys.executable, args=[str(MCP_SERVER)], env={"CAMPUS_DB_PATH": str(WORKING_DB)})),
    process_tool_call=_guard_tool_call,
)


def load_prompt(name: str) -> str:
    team_rules = (PROMPTS_DIR / "team_rules.md").read_text()
    return (PROMPTS_DIR / f"{name}.md").read_text() + "\n\n" + team_rules


async def delegate(ctx: RunContext[TeamDeps], to_agent: AgentName, task: str) -> str:
    """Hand a sub-task to a teammate (boss, inventory, accounting, facilities, or
    customer_service) and wait for their report. Write the task so it stands alone:
    the ticket id, the exact facts you need or the action you want, and why."""
    from .team import run_agent  # late import: team imports the agents

    d = ctx.deps
    if to_agent == d.agent_name:
        return "REFUSED: you cannot delegate to yourself. Do the work with your own tools."
    if to_agent in d.chain:
        return f"REFUSED: {to_agent} is already in this delegation chain {d.chain}. Return what you have instead of looping."
    if d.depth + 1 > MAX_DELEGATION_DEPTH:
        return f"REFUSED: delegation depth limit ({MAX_DELEGATION_DEPTH}) reached. Finish with your own tools and report blockers."
    if d.team.delegations >= MAX_DELEGATIONS_PER_TICKET:
        return f"REFUSED: the team used all {MAX_DELEGATIONS_PER_TICKET} delegations for this ticket. Wrap up."
    d.team.delegations += 1
    report = await run_agent(to_agent, task, team=d.team, parent=d, usage=ctx.usage)
    return report.model_dump_json()


def build_agent(name: str, output_type: type) -> Agent[TeamDeps, Any]:
    allowed = AGENT_TOOLS[name]
    agent = Agent(
        build_model(),
        name=name,
        deps_type=TeamDeps,
        output_type=output_type,
        instructions=load_prompt(name),
        toolsets=[shop_mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)],
        tools=[delegate],
        retries=2,
    )

    @agent.instructions
    def where_am_i(ctx: RunContext[TeamDeps]) -> str:
        d = ctx.deps
        left = MAX_DELEGATIONS_PER_TICKET - d.team.delegations
        return (
            f"You are `{d.agent_name}`. Ticket: {d.team.ticket_id}. Delegation chain so far: {' -> '.join(d.chain)} "
            f"(depth {d.depth} of {MAX_DELEGATION_DEPTH}). Team delegations left for this ticket: {left}. "
            f"Your MCP tools: {', '.join(sorted(allowed))}."
        )

    return agent
