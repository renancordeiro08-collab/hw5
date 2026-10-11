"""Append-only audit trail: one JSON object per agent run in output/audit_trail.json."""

import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart

from .config import AUDIT_TRAIL

_lock = threading.Lock()
_SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|pk-[A-Za-z0-9_\-]{8,}|[Bb]earer\s+\S+)")
_MAX_RESULT_CHARS = 1500


def redact(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)


def tool_trace(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Pair each tool call with its result, in the order the agent made them."""
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ToolCallPart) and isinstance(msg, ModelResponse):
                calls[part.tool_call_id] = {"tool": part.tool_name, "args": part.args_as_dict(), "result": None}
                order.append(part.tool_call_id)
            elif isinstance(part, ToolReturnPart) and part.tool_call_id in calls:
                content = part.content if isinstance(part.content, str) else json.dumps(part.content, default=str)
                calls[part.tool_call_id]["result"] = redact(content)[:_MAX_RESULT_CHARS]
    return [calls[i] for i in order if calls[i]["tool"] != "final_result"]


def read() -> list[dict[str, Any]]:
    with _lock:
        try:
            return json.loads(AUDIT_TRAIL.read_text()) if AUDIT_TRAIL.exists() else []
        except json.JSONDecodeError:
            return []


def clear() -> None:
    with _lock:
        AUDIT_TRAIL.unlink(missing_ok=True)


def append(entry: dict[str, Any]) -> None:
    """Add one entry; rewrite the file atomically so a crash never leaves broken JSON."""
    entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with _lock:
        AUDIT_TRAIL.parent.mkdir(parents=True, exist_ok=True)
        try:
            trail = json.loads(AUDIT_TRAIL.read_text()) if AUDIT_TRAIL.exists() else []
        except json.JSONDecodeError:
            trail = []
        trail.append(json.loads(redact(json.dumps(entry, default=str))))
        tmp = AUDIT_TRAIL.with_suffix(".tmp")
        tmp.write_text(json.dumps(trail, indent=2))
        os.replace(tmp, AUDIT_TRAIL)
