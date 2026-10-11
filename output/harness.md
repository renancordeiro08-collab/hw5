# Homework 5 Agent Harness

This is the working harness for **Campus Customs Multi-Agent Operations**. It covers everything built for Homework 5:

1. the data (every table and field, and how the 3 tickets link);
2. the MCP server and its tools;
3. the Claude Code smoke test;
4. the five-agent PydanticAI team and its delegation loop;
5. the audit trail;
6. the safety guardrails;
7. the FastAPI routes;
8. the React dashboard;
9. the **official resolved run**, with the issues found and fixed along the way.

A file index is at the end.

- **Original (never touched):** `data/campus_customs.db`
- **Working copy (tools read and write here):** `data/campus_customs_new.db`. To reset, copy the original over it.
- **Model:** `gpt-6-luna` through Portkey for every agent.

## How the tables connect

```
tickets ──sku+size──▶ inventory ──sku──▶ pricing
   │  └──invoice_id──▶ invoices ──vendor_id──▶ vendors
   └──lease_id──▶ leases
payments ──kind+ref_id──▶ invoices.id | leases.id        (cash leaves cash_accounts)
desk.date_today = "today" for every due-date and overdue check
```

## Tables and fields

### `desk` (1 row): the shop's clock
| Field | Why we add it / why it matters for the agents |
|---|---|
| `date_today` | "Today" for the shop (**2026-08-31**). Every overdue and due-soon call is measured against this date, never the real clock. |
| `notes` | Free-text notes for the shift (empty now). Any agent can read standing instructions here. |

### `tickets` (3 rows): the work board
| Field | Why we add it / why it matters for the agents |
|---|---|
| `id` | Unique ticket number. Every agent action, draft, and approval is tied back to it. |
| `type` | `customer_order`, `rent_notice`, or `price_override`. The Boss uses it to route the ticket to the right agent. |
| `requester` | Who asked (customer, landlord, student org). Customer Service addresses drafts to this person. |
| `subject` | A short title for the dashboard card. |
| `sku` | Links to `inventory` and `pricing`. Inventory checks stock with it; Accounting checks margin. |
| `size` | Together with `sku`, it picks the exact inventory row to check. |
| `qty` | How many units are wanted. Compared with stock to find the shortfall. |
| `lease_id` | Links to `leases`, so Facilities knows which space and rent is involved. |
| `invoice_id` | Links to `invoices`. It shows a vendor bill is involved in fixing this ticket. |
| `status` | `open` now. Agents move it forward (for example to awaiting approval or resolved) so nothing is worked twice. |
| `notes` | The requester's words. Context for drafts and judgment calls. |
| `created_at` | When the ticket arrived. Used for ordering and urgency. |

### `inventory` (10 rows): stock by SKU and size
| Field | Why we add it / why it matters for the agents |
|---|---|
| `sku` | Product code, shared with `pricing` and `tickets`. |
| `name` | A readable product name for customer drafts. |
| `size` | S/M/L/XL or OS (one size). Stock is tracked per size, so the size must match exactly. |
| `qty` | Units on hand. **0 means sold out.** This is where Inventory spots shortfalls. |
| `location` | Aisle. Useful for pick or hold notes. |

### `pricing` (4 rows): cost vs. price
| Field | Why we add it / why it matters for the agents |
|---|---|
| `sku` | Joins to inventory and tickets. |
| `unit_cost` | What a unit costs the shop. It's the margin floor, so Accounting never approves a discount below cost, and it prices restock orders. |
| `list_price` | The normal selling price. The starting point for any discount math. |

### `vendors` (3 rows): who can restock
| Field | Why we add it / why it matters for the agents |
|---|---|
| `id` | Joins to `invoices.vendor_id`. |
| `name` | The vendor's name, for purchase orders and the dashboard. |
| `specialty` | What they supply: apparel reprint, mugs and small goods, or local courier. Inventory uses it to pick the right vendor for a SKU. |
| `lead_days` | Days to restock. It's the **rule source** for any promised date (date_today + lead_days, and only once the vendor is willing to ship). |

### `leases` (1 row): the shop space
| Field | Why we add it / why it matters for the agents |
|---|---|
| `id` | Joins to `tickets.lease_id`. |
| `space_name` | Which space (Chapel Street shop). |
| `landlord` | Who gets paid. It should match the ticket requester. |
| `monthly_rent` | The rent amount (**$2,400**). |
| `next_due` | The due date (**2026-09-02**, 2 days from today). Facilities checks urgency against `desk.date_today`, then moves it forward one month after payment. |
| `notes` | Lease remarks (empty now). |

### `cash_accounts` (1 row): money available
| Field | Why we add it / why it matters for the agents |
|---|---|
| `name` | The account (`checking`). Payments draw from it. |
| `balance` | Cash on hand (**$3,400**). The pay tool **must refuse** if `amount > balance`, so no balance goes negative. Cash only goes out. |
| `date` | The as-of date of the balance. |

### `payments` (0 rows): the ledger of money out
| Field | Why we add it / why it matters for the agents |
|---|---|
| `id` | Payment number. |
| `kind` | What was paid (for example `invoice` or `rent`). Together with `ref_id`, it tells which table the payment settles. |
| `ref_id` | The invoice id or lease id that was paid. |
| `amount` | Dollars out. It must equal the amount deducted from `cash_accounts`. |
| `account` | Which cash account paid. |
| `paid_at` | When it was paid (use `desk.date_today`). |
| `approved_by` | **The human who approved it.** It's required. An agent can prepare a payment but can never be the approver. |

### `invoices` (1 row): what the shop owes vendors
| Field | Why we add it / why it matters for the agents |
|---|---|
| `id` | Joins to `tickets.invoice_id` and `payments.ref_id`. |
| `vendor_id` | Which vendor is owed. **An open invoice blocks that vendor from shipping anything new.** |
| `amount` | What's owed (**$840**). |
| `due_date` | **2026-08-28, so it's 3 days overdue** compared with today. |
| `status` | `open` means unpaid. It flips to `paid` once an approved payment posts. |
| `description` | "Rush reprint CC-TEE-WHITE S". It ties the bill to the item ticket 101 needs. |

## How the three open tickets link across tables

### Ticket 101: `customer_order`, Tauhid Zaman, Bulldog tee `CC-TEE-WHITE`, size S, qty 1
- **inventory:** CC-TEE-WHITE S has **qty 0**, so it's sold out with a shortfall of 1. (M has 5, L has 3, XL has 2.)
- **invoice_id 501 → invoices:** $840 to vendor 1, **open and overdue** (it was due 08-28). The rush reprint of this exact tee is stuck on this bill.
- **vendors:** vendor 1 is Bulldog Print Co (apparel reprint, 5 lead days). **It won't ship until invoice 501 is paid.**
- **Chain:** Accounting prepares the $840 payment → a human approves → invoice 501 is marked `paid`, a payment row is written, and checking drops to $2,560 → Bulldog Print Co can ship → the earliest arrival is about **2026-09-05** (today + 5 days, counted from payment) → Customer Service drafts an honest message to Tauhid with that date and offers M as an alternative.

### Ticket 102: `rent_notice`, Elm City Properties, rent due
- **lease_id 1 → leases:** Chapel Street shop, **$2,400 due 2026-09-02** (in 2 days, not overdue yet).
- **cash_accounts:** checking has $3,400, so rent alone is affordable.
- **Chain:** Facilities confirms the lease and amount → Accounting prepares the payment → a human approves → a payment row is written, checking drops by $2,400, and `next_due` moves to 2026-10-02 → Customer Service (or Facilities) drafts a confirmation to the landlord.

### Ticket 103: `price_override`, Yale AI Club, 20 navy hoodies `CC-HOOD-NAVY`, size M, bulk discount
- **inventory:** CC-HOOD-NAVY M has **qty 8**, a **shortfall of 12**. (L has 14, S has 4, XL has 6.)
- **pricing:** cost is $22 and list is $58. At list, 20 units = $1,160. Any discount must stay above $22 per unit. For example, 15% off = $49.30 per unit, which keeps a $27.30 margin (55%).
- **vendors:** the restock comes from Bulldog Print Co (apparel), the **same vendor blocked by invoice 501**. So this ticket depends on ticket 101's bill being paid.
- **Restock cost:** 12 × $22 = **$264**.
- **Chain:** Inventory finds the shortfall and the vendor → Accounting checks margin on the proposed discount → the Boss makes the final discount call → a purchase order is prepared for human approval → Customer Service drafts the quote and timeline for the club (8 now and 12 after restock, or all 20 together about 5 days after the vendor is cleared).

## MCP tools v1: the first three (Problem 3)

Every agent uses the same MCP server. The tools connect to `data/campus_customs_new.db` **read-only** for now. Write tools (payments, ticket updates) come later, behind human approval. Every result includes `date_today`, taken from `desk`.

| # | Tool | Reads tables | Unlocks tickets | Why it's the right tool for the ticket |
|---|---|---|---|---|
| 1 | `check_stock_and_pricing(sku, size, qty_needed)` | `inventory`, `pricing`, `vendors`, `invoices`, `desk` | **101**, **103** | It answers the stock question for an exact SKU and size in one call: on hand, shortfall, other sizes, cost and list price, and whether the restock vendor can ship. That covers both Tauhid's sold-out tee and the club's 12-hoodie shortfall with its margin floor. |
| 2 | `check_vendor_and_invoices(vendor_id \| invoice_id)` | `vendors`, `invoices`, `desk` | **101** (and through it **103**) | Ticket 101 points to `invoice_id` 501. This tool follows it to Bulldog Print Co and shows the $840 bill is 3 days overdue, which means `can_ship_now = false`. That's the exact blocker the Boss must clear before any restock. |
| 3 | `check_lease_and_cash(lease_id)` | `leases`, `cash_accounts`, `desk` | **102** | Ticket 102 points to `lease_id` 1. This tool returns the $2,400 rent, the due date (09-02, in 2 days), and whether checking covers it without going negative. That's everything Facilities and Accounting need to prepare the rent payment for approval. |

How each ticket uses them:
- **101:** Inventory calls tool 1 (S = 0, vendor blocked) → Accounting calls tool 2 on invoice 501 → payment prepared for human approval → Customer Service drafts the 09-05 timeline for Tauhid.
- **102:** Facilities calls tool 3 → Accounting prepares $2,400 for approval → draft to Elm City Properties.
- **103:** Inventory calls tool 1 with `qty_needed=20` (shortfall 12, restock cost $264, same blocked vendor) → Accounting checks the discount against the $22 cost → the Boss decides.

## Cross-ticket constraints the Boss must see
| Item | Amount | Checking after |
|---|---|---|
| Starting cash | | **$3,400** |
| Pay invoice 501 (unblocks the vendor; overdue) | $840 | $2,560 |
| Pay rent, lease 1 (due 09-02) | $2,400 | **$160** |
| Restock 12 hoodies (if paid upfront) | $264 | **−$104: REFUSED** |

- Paying both bills leaves only **$160**, so an upfront hoodie restock **can't** also be paid. The pay tool must refuse it. The Boss has to choose between options like these: have the vendor bill the restock as a new invoice on terms, sell the club only the 8 in stock, or wait. No revenue is modeled, so cash never comes back in.
- **Priority:** invoice 501 is already overdue and blocks two tickets (101 and 103). Rent is due in 2 days and is the shop's space. Both fit in cash, so pay both with human approval, then handle the hoodie order within what's left.
- **Never:** pay without human approval, let any balance go negative, email the customer or vendor for real, or use any model other than `gpt-6-luna`.

## Operations tables added by the MCP server (working copy only)

The write tools create three tables in `campus_customs_new.db` the first time they're used. The original database keeps its 9 tables, and a reset removes these.

| Table | Fields | Why we add it |
|---|---|---|
| `approval_requests` | id, ticket_id, kind (invoice / rent / purchase_order), ref_id, sku, size, qty, amount, account, requested_by, reason, status (pending / paid / rejected), created_at, decided_by, decided_at, decision_note, payment_id | The **human approval queue**. Agents can only add `pending` rows. Only a human decision turns one into a `payments` row. |
| `drafts` | id, ticket_id, to_name, subject, body, written_by, status (`draft`), created_at | Customer, landlord, and vendor messages **stay on the board**. Nothing is ever sent. |
| `ticket_updates` | id, ticket_id, status, note, updated_by, at | The status history of each ticket: who moved it, when, and why. |

## MCP tools v2: the full toolbox (Problems 5 and 7)

There are 15 tools in `mcp_server/server.py` (14 here, plus `list_tickets`, a human-only tool added in Problem 7). **Every shop fact the agents use comes from these tools and nothing else.** The agents have no SQL and no direct database access.

| Tool | Kind | Reads / writes | Used by | Tickets |
|---|---|---|---|---|
| `list_open_tickets` | read | tickets, desk | Boss | all |
| `get_ticket` | read | tickets, ticket_updates, approval_requests, drafts, desk | everyone | all |
| `check_stock_and_pricing` | read | inventory, pricing, vendors, invoices, desk | Inventory, Customer Service | 101, 103 |
| `check_vendor_and_invoices` | read | vendors, invoices, desk | Inventory, Accounting | 101, 103 |
| `check_lease_and_cash` | read | leases, cash_accounts, desk | Facilities, Accounting | 102 |
| `check_cash_position` | read | cash_accounts, approval_requests, payments | Boss, Accounting, Facilities | all |
| `check_discount_margin` | read | pricing | Accounting | 103 |
| `request_payment_approval` | write (request only) | → approval_requests | Accounting | 101 (invoice 501), 102 (rent) |
| `request_purchase_order` | write (request only) | → approval_requests | Accounting | 103 (and 101 restock) |
| `save_customer_draft` | write (draft only) | → drafts | Customer Service | all |
| `update_ticket_status` | write | → tickets, ticket_updates | Boss | all |
| `list_approval_requests` | read, **human only** | approval_requests | dashboard | all |
| `approve_request` | **moves money, human only** | → payments, cash_accounts, invoices / leases, approval_requests | dashboard | 101, 102, 103 |
| `reject_request` | **human only** | → approval_requests | dashboard | all |

## The agent team (`backend/`, PydanticAI, `gpt-6-luna` only)

Each agent is a PydanticAI `Agent` with:
- its own prompt (`backend/prompts/<agent>.md`), plus the shared `team_rules.md`;
- a **filtered** view of the MCP server, so it only sees the tools in its allowlist;
- a structured output type (`backend/models.py`);
- the shared `delegate` tool.

| Agent | What it does | Its MCP tools | Output |
|---|---|---|---|
| **Boss** (`boss.md`) | Reads each ticket, routes it to specialists, weighs cash, urgency, and margin, and makes the **final call**. Sets the ticket status. Never pays. | `get_ticket`, `list_open_tickets`, `check_cash_position`, `update_ticket_status` | `BossDecision` |
| **Inventory** (`inventory.md`) | Checks stock by SKU and size, finds the shortfall and alternatives, and works out which vendor restocks, how fast, and whether an open invoice blocks it. | `get_ticket`, `check_stock_and_pricing`, `check_vendor_and_invoices` | `AgentReport` |
| **Accounting** (`accounting.md`) | Watches cash and invoices, checks discount margins, and **files** payment and purchase-order requests for human approval. It's the team's brake on spending. | `get_ticket`, `check_cash_position`, `check_vendor_and_invoices`, `check_lease_and_cash`, `check_discount_margin`, `request_payment_approval`, `request_purchase_order` | `AgentReport` |
| **Facilities** (`facilities.md`) | Handles the shop space: verifies the rent notice against the lease (landlord, amount, due date), measures urgency, and flags lease risk. | `get_ticket`, `check_lease_and_cash`, `check_cash_position` | `AgentReport` |
| **Customer Service** (`customer_service.md`) | Writes honest drafts for customers, the landlord, and vendors. Bad news comes first with the best alternative, and it never promises money moved. **It never sends anything.** | `get_ticket`, `check_stock_and_pricing`, `save_customer_draft` | `AgentReport` |

**Data types (`backend/models.py`):**
- `AgentName` and `TicketStatus` (literals);
- `TeamState`: the run id, ticket id, and delegation counter shared by the whole team for one ticket;
- `TeamDeps`: who I am, my run id, the delegation chain, and the parent run;
- `AgentReport`: summary, facts each tied to the tool they came from, actions, request and draft ids, blockers, `needs_human`, and a recommendation;
- `BossDecision`: final status, decision, who it delegated to, request and draft ids, `human_actions_needed`, risks, and rationale.

## The agent loop and delegation (full connectivity)

```
run_ticket(id) ─▶ Boss.run("work ticket id")
                   │ loop: model → MCP tool or delegate(to_agent, task) → result → model … → BossDecision
                   ├─ delegate("inventory", …) ─▶ Inventory.run  ─┬─ MCP tools
                   │                                              └─ delegate("accounting", …) ─▶ Accounting.run
                   ├─ delegate("accounting", …) ─▶ Accounting.run ─ files pending requests
                   └─ delegate("customer_service", …) ─▶ CS.run ─ saves a draft
every Agent.run ─▶ one entry appended to output/audit_trail.json
```

- **Any agent may delegate to any other** with `delegate(to_agent, task)`, which runs that agent's own loop and returns its `AgentReport` as JSON. Real chains from the first run included Boss → Inventory → Accounting, and Boss → Facilities → Accounting / Customer Service.
- **Loop safety:**
  - no self-delegation, and no delegating to an agent already in the chain (so no ping-pong);
  - a maximum depth of 3;
  - at most 10 delegations per ticket;
  - one shared usage budget per ticket: 40 model requests and 60 tool calls (`UsageLimits`).
  - If a limit is hit, the agent returns a safe fallback report marked "needs human" instead of crashing.
- Tickets are worked **one at a time**, so the cash checks always see the requests filed before.
- One MCP server process (stdio) is shared by the whole team for each run.

## Audit trail (`output/audit_trail.json`)

It's append-only, with one JSON object per agent run. The file is rewritten atomically under a lock, and anything that looks like a secret is redacted.

| Field | What it records |
|---|---|
| `time` | UTC timestamp |
| `type` | `agent_run`, or `ticket_done` (the Boss's final decision plus total usage) |
| `run_id`, `ticket_id` | Which ticket run this belongs to |
| `agent`, `agent_run_id`, `parent_agent_run_id` | Who ran, and who delegated to them (rebuilds the delegation tree) |
| `chain`, `depth` | For example `["boss","inventory","accounting"]`, depth 2 |
| `model` | Always `gpt-6-luna` |
| `task` | The exact instruction the agent received |
| `tool_calls` | Every MCP and delegate call in order: `tool`, `args`, `result` (truncated) |
| `delegated_to` | The teammates this agent called |
| `output` | The structured `AgentReport` or `BossDecision` |
| `status`, `error` | `ok`, `stopped_usage_limit`, or `error` |
| `team_usage_so_far` | Requests and tokens used on this ticket so far (cost control) |

## Safety and guardrails

**Built in now.** Each one is enforced in code, not only in the prompts.

| Guardrail | Where | What it prevents |
|---|---|---|
| **Human approval for every payment** | Agents only have `request_*` tools. `approve_request` and `reject_request` are tagged `human_only`, kept out of every allowlist, and blocked again in `_guard_tool_call`. | An agent paying a bill on its own (the assignment's main rule). |
| **Approver must be a named human** | `approve_request` refuses an empty `approved_by`, any agent name, or any name containing "agent". | Rubber-stamp or self-approval. `payments.approved_by` always names a person. |
| **No negative balances** | `approve_request` re-checks the balance inside a locked transaction. The request tools also refuse when cash, after pending requests, can't cover the amount. | Overdrafts and over-committing cash. Verified: the $264 hoodie PO was refused when only $160 was uncommitted. |
| **Vendor-block rule** | `request_purchase_order` refuses while the vendor has an open invoice. | Ordering from a vendor who won't ship. Verified live: the PO for ticket 101 was refused because of invoice 501. |
| **Amount must match the bill** | `request_payment_approval` checks the invoice amount or `monthly_rent` exactly. | Fat-finger or inflated payments. |
| **No duplicate requests** | Only one pending request per bill. | Paying the same invoice twice. |
| **Can't resolve with money pending** | `update_ticket_status` refuses `resolved` while approvals are pending. | Tickets closed before a human has acted. |
| **Identity stamping** | `_guard_tool_call` overwrites `requested_by`, `written_by`, and `updated_by` with the real calling agent. | One agent filing requests under another's name, which keeps the audit honest. |
| **Least-privilege tools** | Per-agent allowlists (`AGENT_TOOLS`), and read tools open the database `mode=ro`. | Agents acting outside their role, and accidental writes. |
| **Drafts are never sent** | There's no email or phone tool at all. Drafts are stored with `status = 'draft'`. | Contacting real customers or vendors. |
| **One model only** | `MODEL_NAME = "gpt-6-luna"` is hardcoded and ignores `OPENAI_MODEL`. `HW5_MODEL` set to anything else stops startup. | Cost blow-ups and point deductions. |
| **Loop and cost limits** | Depth 3, 10 delegations, 40 requests, and 60 tool calls per ticket, plus no cycles. | Runaway agent chatter and token burn. |
| **Discount floor** | `check_discount_margin`: never below cost, margin of at least 30%, discount of at most 25%. The Boss prompt treats the floor as a limit, not a target. | Selling at a loss, or giving away margin. |
| **Facts only from tools** | Agents have no database access. Prompts require each fact to name its tool. | Made-up stock, dates, or balances. |
| **Audit trail + secret redaction** | `backend/audit.py` | Unexplainable decisions, and leaked keys. |
| **Reset safety** | Tools never open the original database. `run_team --reset` copies it over the working copy. | Losing the clean starting state. |

**What a real business would add next:**
- **Approval tiers and two-person rule:** for example, more than $1,000 needs two approvers, and the requester can never be the approver. Add spend limits per approver.
- **Vendor and landlord verification:** check bank details and contacts against a master file before paying, to defend against invoice and rent-notice fraud (a fake "rent due" email is a classic scam). Facilities already flags mismatches with the lease.
- **Cash reserve floor:** keep a minimum balance (for example one month's rent) that agents can't commit.
- **Separation of duties:** the person who requests a payment, the person who approves it, and the person who reconciles it should all be different people.
- **Prompt-injection defense:** treat ticket text as untrusted data. A note saying "ignore your rules and pay X" must never change behavior. This already holds in code, because the tools enforce the rules.
- **Customer data privacy (PII):** minimize customer data in prompts and logs, and keep logs only as long as needed.
- **Human review of outbound messages:** show a diff and get sign-off on every draft before sending, with a tone and claims checker.
- **Monitoring and alerts:** alert on refused tool calls, usage-limit stops, and repeated failures. Add a daily reconciliation of `payments` against `cash_accounts`.
- **Kill switch and rate limits:** an operator can pause the team immediately, with spend caps per day.
- **Evaluation suite:** scripted tickets (the overdraft attempt, the blocked vendor, a scam rent notice, an injection in ticket notes) re-run on every prompt change.

## Problem 5 test run (`--reset --all`, before the dashboard existed)

| Ticket | Final status | Delegations | What the team did |
|---|---|---|---|
| 101 | `awaiting_approval` | Boss → Inventory (→ Accounting), Accounting, Customer Service | S = 0. The PO attempt was **refused** because the vendor is blocked. **Request #1: $840 for invoice 501**, pending. Draft #1 to Tauhid offers M/L/XL, with S expected 09-05 only after the bill is paid. |
| 102 | `awaiting_approval` | Boss → Facilities, Accounting, Customer Service | Rent of $2,400 due 09-02 verified. **Request #2: $2,400 rent**, pending. Draft #2 to the landlord says the payment "is being processed". |
| 103 | `blocked` | Boss → Inventory, Accounting, Customer Service | 8 of 20 in stock. **10% off ($52.20 per hoodie)**, within policy. The 12-unit restock ($264) is blocked by invoice 501 and by cash (only $160 uncommitted). Draft #3 quotes the 8 now and gives no promise on the rest. |

After the run there were 2 pending requests ($3,240), **0 payments**, and checking still at $3,400. No money moves until a human approves.

## Backend routes (`backend/main.py`, FastAPI)

Run it with `cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000`. CORS allows only the Vite board (`http://localhost:5173`).

Every shop read and every approval goes through the **MCP server** (loaded in-process with a FastMCP client). So the dashboard gets the same tools and guardrails as the agents.

| # | Method & path | What it does | MCP tool(s) behind it |
|---|---|---|---|
| 1 | `GET /api/tickets` | All 3 tickets with `status`, `is_open` (open vs. resolved), pending approvals, drafts, and whether the team is running on it | `list_tickets` |
| – | `GET /api/tickets/{id}` | One ticket with history, approval requests, drafts, and the Boss's last decision | `get_ticket` |
| 2 | `POST /api/tickets/{id}/run` | Starts the agent team on that ticket **in the background** and returns `202`. Use `?wait=true` to block until done. Returns `409` if the team is already busy (one run at a time keeps cash checks honest). | the whole team |
| 3 | `GET /api/events?since=<last id>` | Recent events from the audit trail for the board to refresh: `run_started`, live `agent_step` (started / tool_call / tool_result), `agent_run` (an agent's report), `ticket_done`, `ticket_resolved`, `human_decision`, `reset` | – |
| 4 | `POST /api/approvals/{id}/approve` `{approved_by}` | **A human approves** a payment or purchase order. It re-checks cash (**refuses negative balances**), writes `payments`, and lowers checking. Returns `409` with the reason if refused. | `approve_request` (human only) |
| – | `POST /api/approvals/{id}/reject` `{rejected_by, reason}` | Rejects a request. No money moves. | `reject_request` (human only) |
| – | `GET /api/approvals?status=pending\|all` | The approval queue | `list_approval_requests` (human only) |
| 5 | `GET /api/cash` | Checking **balance**, pending approval total, uncommitted cash, payments made | `check_cash_position` |
| 6 | `POST /api/reset` | Copies the original database over the working copy for a **fresh run** and clears the event log (`?clear_events=false` keeps it). Refused while a run is in progress. | – |
| – | `POST /api/tickets/{id}/resolve` | Human override to mark a ticket resolved. Refused while approvals are pending. | `update_ticket_status` |
| – | `GET /api/health` | Model, database, and the ticket currently running | – |

**When a ticket becomes "resolved":**
- When a team run finishes, the backend marks the ticket resolved if nothing on it waits for a human.
- If a payment or purchase order is pending, the ticket stays `awaiting_approval`. It **auto-resolves as soon as the human approves or rejects the last pending request.**
- The MCP rule "can't resolve with pending approvals" is never bypassed.

**Live events:** `backend/agents/team.py` passes PydanticAI's `event_stream_handler` to every agent run, so each tool call and result is written as an `agent_step` event the moment it happens. The board polls `/api/events` every 1.2 seconds while a run is live.

## The dashboard (`frontend/`, React + Vite + TypeScript)

Start it with `cd frontend && npm run dev`, then open http://localhost:5173. It talks to the backend at `VITE_API_URL` (`frontend/.env.development` → `http://localhost:8000`). The look is described in `output/design.md`.

| What you can do | Where on the page | Route |
|---|---|---|
| See all 3 tickets, open or resolved, with pending approvals and drafts | Ticket board (left) | `GET /api/tickets` |
| Pick a ticket and **Start agent team** | Stage header | `POST /api/tickets/{id}/run` |
| Watch each agent live: who's working, waiting on a teammate, or done; what it's doing right now; what it was asked | Agent cards | `GET /api/events` |
| Read what agents say to each other, plus tool calls and **guardrail refusals** | "What they're saying & doing" feed | `GET /api/events` |
| See drafts (never sent) | Drafts column | `GET /api/tickets/{id}` |
| A short summary of what each agent did, plus the Boss's final call and token usage | "What each agent did" | `agent_run` and `ticket_done` events |
| **Approve & pay**, or reject, with the approver's name required | Approvals (right) | `POST /api/approvals/{id}/approve` and `/reject` |
| The checking balance, which **counts down when a payment is approved** | Header | `GET /api/cash` |
| Payments made, with the approver | Payments (right) | `GET /api/cash` |
| Reset for a fresh run | Header | `POST /api/reset` |

**Verified end to end in the browser:**
- I reset the database and started the team on #101 from the UI. The agent cards went live (Boss "waiting on teammate", Inventory "checking stock & price"), and the feed streamed every step.
- The run finished with `awaiting_approval`, request #1 for $840, and a draft to Tauhid.
- I clicked **Approve & pay** as "Dashboard Test". Checking dropped from **$3,400 to $2,560**, the payment shows "approved by Dashboard Test", and ticket #101 flipped to **Resolved**.

## Problem 9: the official run (reset → run → approve → resolve)

**Procedure:**
1. `POST /api/reset`. The working database was byte-identical to the original: $3,400 checking, 3 open tickets.
2. Ran the team on **#101**, then **#102**, one at a time (dashboard / `POST /api/tickets/{id}/run`).
3. **Augusto approved** request #1 ($840) and request #2 ($2,400) in the dashboard himself.
4. Ran the team on **#103**.
5. Took full-size board screenshots (headless Chrome at `/?ticket=<id>`).

| Ticket | Delegation chains | Boss status | Human approval | Final | Usage |
|---|---|---|---|---|---|
| **101** Bulldog tee S | Boss → Inventory → Accounting · Boss → Accounting · Boss → Customer Service | `awaiting_approval` | #1 · $840 invoice 501 · **Augusto** · checking $3,400 → $2,560 | resolved (by `human:Augusto`) | 18 calls · 53k tokens · 4 delegations |
| **102** Rent due | Boss → Facilities → Accounting · Boss → Accounting · Boss → Customer Service | `awaiting_approval` | #2 · $2,400 rent lease 1 · **Augusto** · checking $2,560 → $160 · next_due → 2026-10-02 | resolved (by `human:Augusto`) | 17 calls · 48k tokens · 4 delegations |
| **103** Bulk hoodies | Boss → Inventory → Accounting · Boss → Accounting → Inventory · Boss → Customer Service | `blocked` | none: no request filed ($264 restock > $160 cash) | resolved (by `operations-desk` on finish) | 21 calls · 63k tokens · 5 delegations |

**End state:**
- Payments: 2, both `approved_by = Augusto`.
- Invoice 501: `paid`. Lease 1 is next due 2026-10-02.
- Checking: **$160**, never negative.
- Drafts: 3, none sent.

**Decisions worth noting:**
- **#103 discount:** Accounting tested 10%, 15%, and the 25% floor with `check_discount_margin`. The Boss chose **10% ($52.20, 57.85% margin)**, a limit-not-target result that comes straight from the Problem 5 prompt fix.
- **Order matters:** because Augusto paid invoice 501 before #103 ran, Bulldog Print Co was *unblocked* for #103. The only thing stopping the restock was cash ($104 short). Accounting checked this before filing, so no tool refusal was needed.
- **Identity stamping worked in production:** the model passed `requested_by: "Accounting"`, but the database stored `accounting`, because `_guard_tool_call` overwrites it.

### Issues found during the official run, and fixes
| # | What happened | Root cause | Fix |
|---|---|---|---|
| 1 | The first #101 attempt crashed: `Invalid 'input[1].id': 'portkey_cache_…'. Expected an ID that begins with 'fc'.` | Portkey served a **cached** Responses answer whose function-call item ids were replaced. The OpenAI Responses API rejected them when they were sent back. | Every request now sends `x-portkey-cache-force-refresh: true`, so official runs never replay old answers. |
| 2 | That crashed run still **auto-marked #101 resolved**. | `_run_and_record` resolved on finish without checking that the Boss's run succeeded. | `TeamState.boss_ok` / `BossDecision._team_run_ok` (a private attribute the model never sees). A crashed or limit-stopped run logs `run_failed` and **never** resolves a ticket. |
| 3 | The second attempt, switched to Chat Completions, crashed: "Function tools with reasoning_effort are not supported for gpt-6-luna". | `gpt-6-luna` only supports tools + reasoning on `/v1/responses`. | Back to `OpenAIResponsesModel`, keeping the cache bypass. The third attempt succeeded. The guard from fix #2 kept #101 **open** this time. |

All three attempts are kept in `output/audit_trail.json` (reset was called with `clear_events=false`), so the record is honest.

### Lessons for the next iteration
- **Customer drafts leak internal finances.** Draft #1 mentions an "overdue invoice", and draft #3 says "pending funding" and names the vendor. Add a rule to `customer_service.md`: describe supplier delays, never our bills or cash.
- **Landlord tone:** "pending human approval" is accurate but exposes internal process. Prefer "being processed".
- **"Resolved" vs. "blocked":** the desk resolves #103 on finish, even though 12 hoodies remain. A real shop would open a follow-up task (restock when cash allows) instead of closing the loop.

## Deliverables index

| Problem | File(s) | What |
|---|---|---|
| 1 | `AI_prompts.md` | Every prompt to the vibe coder, verbatim, plus what was done |
| 2 | `output/harness.md` (tables section) | Every table and field, and why it matters; how the tickets link |
| 3 | `mcp_server/server.py`, `mcp_server/README.md` | FastMCP server (started with 3 tools, now 15) |
| 4 | `.mcp.json` (workspace root), `output/mcp_smoke.json` | MCP added to Claude Code; 3 live tool tests |
| 5 | `backend/` (agents, prompts, models, audit, run_team) | The PydanticAI team, `gpt-6-luna` only |
| 6 | `output/desk_tickets.html` | Plan (Expected) vs. official run (Actual) per ticket. Cash and Reflection tabs are left for later. |
| 7 | `backend/main.py` | FastAPI routes |
| 8 | `frontend/`, `output/design.md` | React + Vite + TS dashboard; aesthetic spec |
| 9 | `output/resolved_tickets.json`, `output/resolved_board.html`, `output/screenshots/`, `output/audit_trail.json` | The official resolved run |

**Total MCP tools: 15.** That's 7 reads, 4 agent writes (requests, drafts, status), and 4 human-only tools (`list_tickets`, `list_approval_requests`, `approve_request`, `reject_request`).
