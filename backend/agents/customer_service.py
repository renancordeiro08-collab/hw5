"""Customer Service: drafts messages for customers, landlords, and vendors (never sends)."""

from ..models import AgentReport
from .base import build_agent

NAME = "customer_service"
agent = build_agent(NAME, AgentReport)
