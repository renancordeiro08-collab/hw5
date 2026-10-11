"""Boss: reads each ticket, decides who works on it, and makes the final call."""

from ..models import BossDecision
from .base import build_agent

NAME = "boss"
agent = build_agent(NAME, BossDecision)
