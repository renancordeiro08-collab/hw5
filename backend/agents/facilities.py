"""Facilities: the shop space (leases, rent, due dates)."""

from ..models import AgentReport
from .base import build_agent

NAME = "facilities"
agent = build_agent(NAME, AgentReport)
