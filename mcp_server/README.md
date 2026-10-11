# Campus Customs MCP Server

## What it's for

This MCP (Model Context Protocol) server is the **shared toolbox for the whole agent team**. Boss, Inventory, Accounting, Facilities, and Customer Service don't write SQL or touch the database themselves. When they need a fact (stock, a vendor's bills, rent due) or want to act (file a payment request, save a draft), they call a tool here and get back clean JSON.

Why an MCP server instead of putting the tools inside each agent:
- **One source of truth.** Every agent calls the same tools, so they see the same numbers and the same shop rules. Shop facts come from here and only from here.
- **The rules are enforced in code, not in prompts.** "Today" comes from `desk.date_today`, a vendor with an open invoice can't get a PO, a payment must match the bill, and no balance can go negative. The model can't skip any of these.
- **Safe by design.** Read tools open the database read-only. Agent write tools can only create *requests*, drafts, and status updates. Money moves only through the **human-only** tools.
- **Works with any client.** The same server is used by Claude Code (through `.mcp.json`, for the Problem 4 smoke test) and by the PydanticAI team (through `MCPToolset`).

Built with [FastMCP](https://gofastmcp.com) (`fastmcp` 4.x).

## Data it uses

| File | Role |
|---|---|
| `data/campus_customs.db` | The **original**. The server never opens it. |
| `data/campus_customs_new.db` | The **working copy**. All tools read and write here. |

To reset before a full run:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

`backend.run_team --reset` does the same thing. You can point the server at a different file with `CAMPUS_DB_PATH`.

The write tools add three tables to the working copy: `approval_requests`, `drafts`, and `ticket_updates`. A reset removes them.

## Tools (15)

| Tool | Kind | What it does |
|---|---|---|
| `list_open_tickets` | read | The board: every unresolved ticket, oldest first |
| `get_ticket(ticket_id)` | read | One ticket, plus its history, approval requests, and drafts |
| `check_stock_and_pricing(sku, size, qty_needed)` | read | On hand, shortfall, other sizes, cost and list price, restock vendor and whether it's blocked |
| `check_vendor_and_invoices(vendor_id \| invoice_id)` | read | Lead time, open invoices with days overdue, `can_ship_now` |
| `check_lease_and_cash(lease_id)` | read | Rent, due date, days until due, whether cash covers it |
| `check_cash_position()` | read | Cash on hand, pending request total, available for new requests, payments so far |
| `check_discount_margin(sku, qty, discount_pct \| proposed_unit_price)` | read | Margin, and whether the price is within policy (never below cost, margin ≥ 30%, discount ≤ 25%) |
| `request_payment_approval(ticket_id, kind, ref_id, amount, requested_by, reason)` | agent write | Files a **pending** invoice or rent payment. The amount must match the bill, there are no duplicates, and it must fit uncommitted cash. |
| `request_purchase_order(ticket_id, sku, size, qty, requested_by, reason)` | agent write | Files a **pending** restock PO. Refused if the vendor is blocked or cash is short. |
| `save_customer_draft(ticket_id, to_name, subject, body, written_by)` | agent write | Saves a draft. **Never sent.** |
| `update_ticket_status(ticket_id, status, note, updated_by)` | agent write | Moves a ticket forward. Can't be set to `resolved` while approvals are pending. |
| `list_tickets()` | **human only** | The whole board for the dashboard (open and resolved) |
| `list_approval_requests(status)` | **human only** | The approval queue |
| `approve_request(request_id, approved_by)` | **human only, moves money** | Re-checks cash, writes `payments` (with `approved_by` = a person), lowers the balance, marks the invoice paid or moves rent `next_due` forward a month |
| `reject_request(request_id, rejected_by, reason)` | **human only** | Rejects a request. No money moves. |

Every read response includes `date_today`, so agents reason from the shop's date, not the real calendar.

**Assumption:** the `vendors` table has no SKU column, so the server matches the product line to the vendor's specialty: hoodies, tees, and hats go to apparel (Bulldog Print Co), and mugs go to mugs (Elm City Gifts). This mapping is in `SKU_PREFIX_TO_SPECIALTY`.

**Policy settings** (env vars): `MIN_MARGIN_PCT` (default 30) and `MAX_DISCOUNT_PCT` (default 25).

## How the human-only tools stay human-only
1. They're tagged `human_only` on the server.
2. The backend gives each agent an **allowlist** of tools (`backend/agents/base.py → AGENT_TOOLS`), and none of the allowlists include them.
3. `_guard_tool_call` blocks them again on every call, and stamps the real agent name into `requested_by`, `written_by`, and `updated_by`.
4. `approve_request` itself refuses an approver that's blank, an agent name, or contains "agent".

## Running it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python mcp_server/server.py          # stdio
```

You normally don't start it by hand. Claude Code starts it from `.mcp.json`, and the backend team starts it as a stdio subprocess for each run.
