"""Accounting: cash, invoices, margins, and payment / purchase-order requests for human approval."""

from ..models import AgentReport
from .base import build_agent

NAME = "accounting"
agent = build_agent(NAME, AgentReport)
