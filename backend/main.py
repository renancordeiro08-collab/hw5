"""Campus Customs backend: the API the React dashboard calls.

Run from the backend folder:
    cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000

Every shop read and every approval goes through the MCP server (the same tools and
guardrails the agents use). Agent runs happen in the background so the board can poll
/api/events while the team works.
"""

import asyncio
import importlib.util
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:  # lets `uvicorn main:app` run from inside backend/
    sys.path.insert(0, str(PROJECT_DIR))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastmcp import Client  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend import audit  # noqa: E402
from backend.agents.team import run_ticket  # noqa: E402
from backend.config import MCP_SERVER, MODEL_NAME, ORIGINAL_DB, WORKING_DB  # noqa: E402

# Load the MCP server in-process: same tools and rules as the agents' stdio connection, no subprocess per request.
_spec = importlib.util.spec_from_file_location("campus_mcp_server", MCP_SERVER)
shop_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shop_server)

app = FastAPI(title="Campus Customs Multi-Agent Operations", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One team run at a time, so every cash check sees the requests filed before it.
_run_lock = asyncio.Lock()
_current_run: dict[str, Any] = {"ticket_id": None, "started_at": None}
_last_results: dict[int, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def mcp_call(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    async with Client(shop_server.mcp) as client:
        result = await client.call_tool(tool, args or {}, raise_on_error=False)
    if result.is_error:
        raise HTTPException(502, f"MCP tool {tool} failed: {result.content[0].text if result.content else 'unknown error'}")
    return result.data


# ---------------------------------------------------------------- request bodies

class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=2, description="Name of the human approving, e.g. 'Augusto Reis'.")


class RejectBody(BaseModel):
    rejected_by: str = Field(min_length=2)
    reason: str = Field(min_length=3)


# ---------------------------------------------------------------- routes

@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "model": MODEL_NAME, "database": WORKING_DB.name, "running_ticket": _current_run["ticket_id"]}


@app.get("/api/tickets")
async def list_tickets() -> dict[str, Any]:
    """1. Every ticket with its status and whether it is open or resolved."""
    board = await mcp_call("list_tickets")
    for t in board["tickets"]:
        t["running"] = t["id"] == _current_run["ticket_id"]
        t["last_decision"] = _last_results.get(t["id"])
    return board


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int) -> dict[str, Any]:
    """One ticket with history, approval requests, drafts, and the Boss's last decision."""
    detail = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if "error" in detail:
        raise HTTPException(404, detail["error"])
    detail["last_decision"] = _last_results.get(ticket_id)
    return detail


async def _resolve_if_clear(ticket_id: int, by: str, note: str) -> bool:
    """Mark a ticket resolved once nothing on it waits for a human. The MCP tool refuses while approvals are pending."""
    result = await mcp_call("update_ticket_status", {"ticket_id": ticket_id, "status": "resolved", "note": note, "updated_by": by})
    if not result.get("refused"):
        audit.append({"type": "ticket_resolved", "ticket_id": ticket_id, "by": by, "note": note})
        return True
    return False


async def _run_and_record(ticket_id: int) -> dict[str, Any]:
    _current_run.update(ticket_id=ticket_id, started_at=_now())
    audit.append({"type": "run_started", "ticket_id": ticket_id, "model": MODEL_NAME})
    try:
        result = await run_ticket(ticket_id)
        decision = result.model_dump()
        decision["run_ok"] = result._team_run_ok
        if not decision["run_ok"]:  # a crashed or limit-stopped run never resolves a ticket
            audit.append({"type": "run_failed", "ticket_id": ticket_id, "error": decision["decision"][:500]})
            decision["resolved"] = False
            _last_results[ticket_id] = decision
            return decision
        # Run finished: resolve now unless a payment/PO still waits for a human (then approval resolves it).
        decision["resolved"] = await _resolve_if_clear(
            ticket_id, "operations-desk",
            f"Team run finished. Boss reported {decision['final_status']}: {decision['decision'][:300]}",
        )
        _last_results[ticket_id] = decision
        return decision
    except Exception as e:
        audit.append({"type": "run_failed", "ticket_id": ticket_id, "error": f"{type(e).__name__}: {e}"})
        raise
    finally:
        _current_run.update(ticket_id=None, started_at=None)
        _run_lock.release()


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_team_on_ticket(ticket_id: int, wait: bool = Query(False, description="Block until the team finishes.")) -> dict[str, Any]:
    """2. Run the agent team on one ticket. Returns at once (poll /api/events) unless wait=true."""
    detail = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if "error" in detail:
        raise HTTPException(404, detail["error"])
    if _run_lock.locked():
        raise HTTPException(409, f"The team is already working ticket {_current_run['ticket_id']}. Try again when it finishes.")
    await _run_lock.acquire()  # released in _run_and_record
    if wait:
        return {"ticket_id": ticket_id, "status": "finished", "decision": await _run_and_record(ticket_id)}
    asyncio.create_task(_run_and_record(ticket_id))
    return {"ticket_id": ticket_id, "status": "started", "poll": "/api/events"}


@app.get("/api/events")
async def recent_events(
    since: int = Query(-1, description="Return events with id greater than this (use the last id you saw)."),
    limit: int = Query(50, ge=1, le=500),
    ticket_id: int | None = None,
    full: bool = Query(False, description="Include full tool results and outputs."),
) -> dict[str, Any]:
    """3. Recent agent events from the audit trail, newest last, so the board can refresh."""
    trail = audit.read()
    events = []
    for i, e in enumerate(trail):
        if i <= since or (ticket_id is not None and e.get("ticket_id") != ticket_id):
            continue
        if not full and e.get("type") == "agent_run":
            out = e.get("output") or {}
            e = {
                **{k: e.get(k) for k in ("time", "type", "run_id", "ticket_id", "agent", "agent_run_id",
                                          "parent_agent_run_id", "chain", "depth", "model", "status", "delegated_to")},
                "task": (e.get("task") or "")[:300],
                "tools": [c["tool"] for c in e.get("tool_calls", [])],
                "summary": out.get("summary") or out.get("decision"),
                "needs_human": out.get("needs_human") or bool(out.get("human_actions_needed")),
            }
        events.append({"id": i, **e})
    events = events[-limit:]
    return {
        "events": events,
        "last_id": len(trail) - 1,
        "running_ticket": _current_run["ticket_id"],
        "running_since": _current_run["started_at"],
    }


@app.get("/api/approvals")
async def list_approvals(status: str = Query("pending", pattern="^(pending|paid|rejected|all)$")) -> dict[str, Any]:
    """The approval queue the human works through."""
    return await mcp_call("list_approval_requests", {"status": status})


@app.post("/api/approvals/{request_id}/approve")
async def approve(request_id: int, body: ApproveBody) -> dict[str, Any]:
    """4. A human clicked Approve: pay the invoice / rent / purchase order. Refused if cash would go negative."""
    result = await mcp_call("approve_request", {"request_id": request_id, "approved_by": body.approved_by})
    audit.append({"type": "human_decision", "decision": "approve", "request_id": request_id,
                  "by": body.approved_by, "result": result})
    if result.get("refused"):
        raise HTTPException(409, result["reason"])
    result["ticket_resolved"] = await _after_decision(request_id, body.approved_by)
    return result


@app.post("/api/approvals/{request_id}/reject")
async def reject(request_id: int, body: RejectBody) -> dict[str, Any]:
    """A human clicked Reject: no money moves."""
    result = await mcp_call("reject_request", {"request_id": request_id, "rejected_by": body.rejected_by, "reason": body.reason})
    audit.append({"type": "human_decision", "decision": "reject", "request_id": request_id,
                  "by": body.rejected_by, "reason": body.reason, "result": result})
    if result.get("refused"):
        raise HTTPException(409, result["reason"])
    result["ticket_resolved"] = await _after_decision(request_id, body.rejected_by)
    return result


async def _after_decision(request_id: int, human: str) -> bool:
    """After a human decides, resolve the ticket if its team run is done and nothing else is pending."""
    reqs = (await mcp_call("list_approval_requests", {"status": "all"}))["requests"]
    ticket_id = next((r["ticket_id"] for r in reqs if r["id"] == request_id), None)
    if ticket_id is None or ticket_id == _current_run["ticket_id"]:
        return False
    return await _resolve_if_clear(ticket_id, f"human:{human}", f"All approval requests decided (last: #{request_id}).")


@app.post("/api/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int, body: ApproveBody) -> dict[str, Any]:
    """Human override: mark a ticket resolved (still refused while approvals are pending)."""
    if await _resolve_if_clear(ticket_id, f"human:{body.approved_by}", "Marked resolved by a human on the dashboard."):
        return {"ticket_id": ticket_id, "status": "resolved"}
    raise HTTPException(409, "Ticket still has pending approval requests. Approve or reject them first.")


@app.get("/api/cash")
async def cash() -> dict[str, Any]:
    """5. Current checking balance, plus what is already promised to pending approvals."""
    pos = await mcp_call("check_cash_position")
    checking = next((a for a in pos["cash_accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(500, "No checking account found.")
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "date_today": pos["date_today"],
        "pending_approval_total": pos["pending_approval_total"],
        "available_for_new_requests": pos["available_for_new_requests"],
        "payments_made": pos["payments_made"],
    }


@app.post("/api/reset")
async def reset(clear_events: bool = Query(True, description="Also clear the audit trail for a clean run.")) -> dict[str, Any]:
    """6. Copy the original database over the working copy for a fresh run."""
    if _run_lock.locked():
        raise HTTPException(409, f"Can't reset while the team is working ticket {_current_run['ticket_id']}.")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    _last_results.clear()
    if clear_events:
        audit.clear()
    audit.append({"type": "reset", "from": ORIGINAL_DB.name, "to": WORKING_DB.name})
    return {"reset": True, "database": WORKING_DB.name, "events_cleared": clear_events}
