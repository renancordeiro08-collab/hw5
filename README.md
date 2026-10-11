# Homework 5: Campus Customs Multi-Agent Operations

An AI operations team for the Campus Customs shop. Tickets on a board (customer orders, rent, unpaid bills, discount requests) are worked by five PydanticAI agents. The agents get every fact from a FastMCP server, and a human approves anything that spends money.

```
React dashboard (frontend)  ─▶  FastAPI backend (backend/main.py)  ─▶  agent team (backend/agents)  ─▶  MCP server (mcp_server)  ─▶  data/campus_customs_new.db
                                                         Boss ⇄ Inventory ⇄ Accounting ⇄ Facilities ⇄ Customer Service
```

## Layout

| Path | What's there |
|---|---|
| `data/campus_customs.db` | Original database. **Never modified.** |
| `data/campus_customs_new.db` | Working copy the tools read and write. Reset by copying the original over it. |
| `mcp_server/server.py` | FastMCP server with 15 tools: reads, requests and drafts, and human-only approvals ([README](mcp_server/README.md)). |
| `backend/config.py` | Paths, the **only** model (`gpt-6-luna`), the Portkey client, and loop limits. |
| `backend/models.py` | Data types: `AgentName`, `TeamDeps`, `AgentReport`, `BossDecision`, … |
| `backend/prompts/*.md` | One detailed prompt per agent, plus the shared `team_rules.md`. |
| `backend/agents/` | `boss.py`, `inventory.py`, `accounting.py`, `facilities.py`, `customer_service.py`, plus `base.py` (MCP connection, allowlists, `delegate` tool) and `team.py` (agent loop and audit). |
| `backend/audit.py` | Appends every agent run to `output/audit_trail.json`. |
| `backend/run_team.py` | Command-line runner. |
| `backend/main.py` | FastAPI routes for the dashboard: tickets, run, events, approvals, cash, reset. |
| `frontend/` | React + Vite + TS ops board: live agents, approvals, checking balance. |
| `output/design.md` | Dashboard aesthetic: Miami Vice after dark. |
| `output/desk_tickets.html` | Problems 6, 9 and 10: Expected vs. Actual per ticket, plus the Reflection answers. |
| `output/harness.md` | Tables and fields, ticket links, tools, agents, audit format, and **safety guardrails**. |
| `output/mcp_smoke.json` | Problem 4: live MCP tool tests from Claude Code. |
| `output/audit_trail.json` | Every event from the official run: agent steps, agent reports, human decisions, and failed attempts. |
| `output/resolved_tickets.json` | Problem 9: final status, outcome, each agent's contribution, and approvals per ticket. |
| `output/resolved_board.html` | Problem 9: double-click page with a board screenshot for each resolved ticket. |
| `output/screenshots/` | Full-size dashboard captures (`/?ticket=<id>`). |
| `AI_prompts.md` | Log of every prompt I gave the vibe coder. |
| `.mcp.json` | Registers the MCP server with Claude Code (relative paths). |
| `output/github_url.txt` | Link to this repository. |

## How to run it (from the repo root)

**0. One-time setup**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # add your PORTKEY_API_KEY. Never commit .env.
(cd frontend && npm install)
```

The model is hardcoded to **`gpt-6-luna`** through Portkey. `OPENAI_MODEL` is ignored on purpose, and setting `HW5_MODEL` to anything else stops startup.

**1. Copy the original database to the working copy (whenever you need a clean run)**

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

`campus_customs.db` is never modified. Every tool reads and writes `campus_customs_new.db`.

**2. Start the MCP server**

```bash
.venv/bin/python mcp_server/server.py
```

You rarely need to run it by hand:
- **Claude Code** starts it from `.mcp.json` (server `campus-customs`).
- The **backend** starts its own stdio copy for each agent run, and loads it in-process for the dashboard's reads and approvals.

Running it by hand is just a quick check that it boots.

**3. Start the FastAPI backend** (http://localhost:8000; interactive docs at `/docs`)

```bash
cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000
```

**4. Start the React board** (http://localhost:5173), in a second terminal

```bash
cd frontend && npm run dev
```

**5. Reset the database before a full run**

Click **Reset database** on the board, run `curl -X POST localhost:8000/api/reset`, or run `.venv/bin/python -m backend.run_team --reset`. Then, on the board:
1. Pick a ticket and click **Start agent team**. Agents light up live as they work.
2. Approve or reject payments and purchase orders on the right. The checking balance drops when you approve.
3. Repeat for each ticket. A ticket resolves when its run finishes and nothing is waiting for approval.

**Without the board** (command line):

```bash
.venv/bin/python -m backend.run_team --reset --all     # fresh DB, work every open ticket
.venv/bin/python -m backend.run_team --ticket 103      # one ticket
```

Each ticket goes to the **Boss**, who delegates to specialists. Any agent can delegate to any other, so you get chains like Boss → Inventory → Accounting. Every step is appended to `output/audit_trail.json`.

## Shop rules the code enforces
- "Today" = `desk.date_today` (2026-08-31). Overdue is measured against it.
- Vendor lead times come from `vendors`. A vendor with an open unpaid invoice won't ship, and POs to them are refused.
- **Every payment needs human approval.** Agents can only file pending requests. `approve_request` (human only) writes `payments`, lowers cash, and marks the invoice paid or moves rent forward.
- The pay tool refuses if cash is short, so there are no negative balances. Cash only goes out.
- Nothing is emailed or called. Drafts stay on the board.
- Only `gpt-6-luna`, with per-ticket caps on requests, tool calls, and delegations.

See [output/harness.md](output/harness.md) for the full agent, tool, and guardrail reference.
