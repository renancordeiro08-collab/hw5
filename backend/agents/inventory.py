"""Inventory: stock by SKU and size, shortfalls, and which vendor can restock."""

from ..models import AgentReport
from .base import build_agent

NAME = "inventory"
agent = build_agent(NAME, AgentReport)
