"""Data types shared by the agent team: who the agents are, what they pass around, and what they return."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["in_progress", "awaiting_approval", "blocked", "resolved"]


# ---------------------------------------------------------------- run state (not sent to the model)

@dataclass
class TeamState:
    """Shared by every agent working on one ticket."""
    run_id: str
    ticket_id: int | None
    delegations: int = 0
    boss_ok: bool = False  # True only if the Boss's run finished without an error or limit stop


@dataclass
class TeamDeps:
    """What each agent run knows about itself and its place in the delegation chain."""
    team: TeamState
    agent_name: AgentName
    agent_run_id: str
    chain: list[str] = field(default_factory=list)  # e.g. ["boss", "inventory"]
    parent_agent_run_id: str | None = None

    @property
    def depth(self) -> int:
        return len(self.chain) - 1


# ---------------------------------------------------------------- structured outputs (what the model must return)

class AgentReport(BaseModel):
    """What a specialist returns to whoever delegated to it."""
    agent: AgentName
    summary: str = Field(description="Two or three sentences: what you found and what you did.")
    facts: list[str] = Field(default_factory=list, description="Each fact with the MCP tool it came from, e.g. 'S on hand = 0 (check_stock_and_pricing)'.")
    actions_taken: list[str] = Field(default_factory=list, description="Writes you made: requests filed, drafts saved, statuses changed.")
    approval_request_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list, description="Anything that stops the ticket from being finished.")
    needs_human: bool = Field(default=False, description="True if a person must approve or decide something.")
    recommendation: str = Field(description="What you recommend the Boss do next.")


class BossDecision(BaseModel):
    """The Boss's final call on one ticket, shown on the dashboard."""
    ticket_id: int
    final_status: TicketStatus
    decision: str = Field(description="The final call in plain language.")
    delegated_to: list[AgentName] = Field(default_factory=list)
    approval_request_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    human_actions_needed: list[str] = Field(default_factory=list, description="Exactly what the human must approve or decide.")
    risks: list[str] = Field(default_factory=list)
    rationale: str
    _team_run_ok: bool = PrivateAttr(default=False)  # set by the loop, never by the model
