# Homework 5, Problem 1: AI Prompts

This is the log of prompts I typed into Claude Code (Opus 5.5, desktop app) to build Campus Customs Multi-Agent Operations: an MCP server, a FastAPI backend with a multi-agent team, and a React dashboard. The prompts are copied exactly as I typed them. I update this file as I work.

## Prompt 1: kickoff

> Are you ready to rock another AI Homeowrk!!??

Claude confirmed the course defaults (Portkey, `.env` keys, a local `.venv`, the Miami Vice design style) and asked for the assignment.

## Prompt 2: the assignment + this log

> @"/Users/augustoreis/Downloads/data-2/"
> awesome! love u!
>
> PROBLEM 1: CREATE A AI_PROMPT.MD and update it as i work on it

I attached two screenshots of the assignment:
- **Scenario.** Campus Customs Multi-Agent Operations runs the shop. Open tickets (customer orders, rent, unpaid bills, discount requests) land on a board. Build three connected pieces: an **MCP server**, a **FastAPI backend** with a multi-agent team, and a **React dashboard** where a human watches the agents and approves requests. The team has full connectivity (any agent can delegate to any other). The agents are **Boss**, **Inventory**, **Accounting**, **Facilities**, and **Customer Service**.
- **Data.** `data/campus_customs.db` has the tables `desk`, `tickets`, `inventory`, `pricing`, `vendors`, `leases`, `cash_accounts`, `payments`, and `invoices`. The tools work on a copy, `data/campus_customs_new.db`, and the original stays untouched so it can be reset.
- **Rules of this shop.** `desk.date_today` is "today". Vendor lead times come from `vendors`. A vendor won't ship while it has an open unpaid invoice. **Every payment needs human approval** and must update the relevant table. The pay tool must refuse if there isn't enough cash (no negative balances). Cash only goes out. Reset the database before a full run. Never email customers or call real vendors; drafts stay on the board. Use **only `gpt-6-luna`** through Portkey for every agent.

What Claude did with this prompt:
- Created `homework_05/` as the project folder and this `AI_prompts.md` log.
- Copied the database to `data/campus_customs.db` (the original) and `data/campus_customs_new.db` (the working copy).
- Checked the data: `desk.date_today` = **2026-08-31**, and there are 3 open tickets:
  - **101** `customer_order`: Tauhid Zaman needs a Bulldog tee (`CC-TEE-WHITE`), size S, qty 1.
  - **102** `rent_notice`: Elm City Properties says shop rent is due in 2 days.
  - **103** `price_override`: Yale AI Club wants 20 navy hoodies (`CC-HOOD-NAVY`), size M, at a bulk discount.
- Model note: the assignment requires `gpt-6-luna`, which overrides the workspace's default model. Every agent will use `gpt-6-luna` only.

## Prompt 3: clarification

> this is homework 5 btw!!

Claude confirmed the work is already in the `homework_05/` folder and added "Homework 5" to this file's title.

## Prompt 4: Problem 2, set up the working DB and study the tickets

> open the data/campus_custom.db and copy original file to campus_customs_new;.db --- we'll be working on it on later problems...
>
> study the three open tickets so you see how they link to other tables
> also start out harness.md just like we did the other prboelmas... list the fields and one short line on why were adding that and why they matter for the agents

What Claude did with this prompt:
- Copied `data/campus_customs.db` over `data/campus_customs_new.db` again (a fresh reset) and checked that the two files are byte-identical.
- Read the full schema and every row (the database is small: 3 tickets, 10 inventory rows, 4 prices, 3 vendors, 1 lease, 1 cash account, 0 payments, 1 invoice).
- Started `output/harness.md`, the same style as hw4. It has a table map, every field with one line on why it matters for the agents, and how each ticket links across tables.
- Key findings:
  - **101:** the white tee in size S is sold out (0). It's linked to **invoice 501**: $840 to Bulldog Print Co, **3 days overdue**. That vendor won't ship until it's paid. With a 5-day lead time, the earliest arrival is about 09-05.
  - **102:** rent of $2,400 on lease 1 is due 09-02.
  - **103:** 20 navy hoodies in size M are wanted, but only 8 are in stock, a 12-unit shortfall. The restock comes from the **same blocked vendor**. Cost is $22 and list is $58, so the discount must stay above cost.
  - **Cash trap:** $3,400 − $840 − $2,400 = **$160**, which can't cover the $264 restock. The pay tool must refuse it, and the Boss must choose.

## Prompt 5: Problem 3, build the MCP server

> yea problem 3 is build the mcp server...
>
> you should write an mcp serrver in mcp_server using FASTMCP... it will converse with the campus customs new db. dont connect or run it in this problem yet...
>
> every agent uses the tools in the mcp servers, were gonna add more tools to it later.. just write them now... have good and clear neames for them
>
> in harness list each of the three mcp tools.... iclu what table it reads, what tickets it helps unlock and 1 sentence why that tool is the righ one for the ticket.... tie too to ticket... also add a short read md that explains what the mcp server is for and other necessary explantions

What Claude did with this prompt:
- Created a local `.venv` and installed `fastmcp` 4.1.0 and `python-dotenv` (listed in `requirements.txt`). Added `.env.example` with placeholders and `gpt-6-luna`, plus a `.gitignore`.
- Wrote `mcp_server/server.py` with 3 read-only FastMCP tools. They point at `data/campus_customs_new.db` and open it in read-only mode:
  - `check_stock_and_pricing(sku, size, qty_needed)` covers tickets 101 and 103.
  - `check_vendor_and_invoices(vendor_id | invoice_id)` covers ticket 101, which also unblocks 103.
  - `check_lease_and_cash(lease_id)` covers ticket 102.
- The shop rules are built into the tools: "today" = `desk.date_today`, days overdue, `can_ship_now = false` while the vendor has an open invoice, the earliest arrival (today + lead_days), and whether cash covers the rent.
- Did **not** start or connect the server, as asked. To check the code, Claude imported it and called each function directly. Results: tee S = 0 and the vendor is blocked by invoice 501 ($840, 3 days overdue, arrival about 09-05). Hoodie M has a shortfall of 12 with a $264 restock. Rent is $2,400, due in 2 days, and cash covers it. The working database was byte-identical afterwards.
- Added an "MCP tools" table to `output/harness.md` (tables read, tickets unlocked, why each tool fits) and wrote `mcp_server/README.md` (purpose, data files, tools, the vendor-mapping assumption, how to run it later, next tools).

## Prompt 6: Problem 4, add the MCP server to the vibe coder and smoke-test it

> problem 4 is to add the mcp to the vibe coder and test each tool... for each tool include inclusde the prompted i asked the bibe coder the tool name and the tool output... al this in a mcp_smoke.json

What Claude did with this prompt:
- Registered the server with Claude Code by adding `.mcp.json` at the workspace root. It defines the `campus-customs` server over stdio, using the project's `.venv` Python and `homework_05/mcp_server/server.py`.
- Ran a real MCP handshake over stdio with the FastMCP client. All 3 tools were listed, `check_lease_and_cash(1)` returned the lease, and the database was unchanged afterwards.
- Claude Code only loads MCP servers when a session starts, so Claude asked me to restart the session, approve the `campus-customs` server, and then ask it one prompt per tool. The answers go into `output/mcp_smoke.json`.

## Prompt 7: Problem 4 smoke test, tool 1

(I restarted the session so Claude Code loaded the `campus-customs` MCP server.)

> Use the MCP to check if we have the Bulldog tee CC-TEE-WHITE in size S for ticket 101

Claude called `check_stock_and_pricing` through the MCP with `sku = CC-TEE-WHITE`, `size = S`, and `qty_needed = 1`. Size S is **sold out** (0 on hand). M has 5, L has 3, and XL has 2. The restock vendor, Bulldog Print Co, is **blocked** by invoice 501 ($840, 3 days overdue). If that invoice is paid today, the earliest arrival is 2026-09-05. Claude saved the prompt, tool, input, and output to `output/mcp_smoke.json`.

## Prompt 8: Problem 4 smoke test, tool 2

> Use the MCP to check invoice 501, is the vendor blocked from shipping?

Claude called `check_vendor_and_invoices` through the MCP with `invoice_id = 501`. **Yes, the vendor is blocked.** Invoice 501 is $840 to Bulldog Print Co, was due 2026-08-28, and is **3 days overdue**, so `can_ship_now = false`. If it's paid today (with human approval), the earliest arrival is 2026-09-05. Claude added this to `output/mcp_smoke.json`.

## Prompt 9: Problem 4 smoke test, tool 3

> 1. Use the MCP to check lease 1, when is rent due and can we cover it?

Claude called `check_lease_and_cash` through the MCP with `lease_id = 1`. Rent for the Chapel Street shop (Elm City Properties) is **$2,400, due 2026-09-02**, which is in 2 days and not overdue. Checking has $3,400, so **we can cover it**, with $1,000 left. Claude finished `output/mcp_smoke.json`: 3 of 3 tools passed, and the working database was unchanged. It also noted the cross-ticket cash squeeze: after paying the invoice and the rent, $160 is left, which can't cover the $264 hoodie restock.

## Prompt 10: Problem 5, build the agent team and grow the MCP tools

> ojk... problem 5 is to build the agent tteam and grow the mcp tools...
>
> lets build an agentic team for campus costums using pydantic ai: boss inventory accounting facilities and costumer services.
>
> please include propmsts models and agent loops so they can delegate work to each other with a lot of connectivity.
>
> pt the agent prompts in backend prompts one file per agent ... put data types in backend models py, and agent files unders backend.... use only gpt 6 luna so we dotnt go bankrput..
>
> get us detailed prompts for our teams of agents
>
> shop fact come from the mcp server over and only
>
> wirte agents so they append to audit_trail.json
>
> in harness list each agent, and they do and each of their mcp tools.... also add a safety sections we oughta add guardrails a real business would want.
>
> upate the read me as well

What Claude did with this prompt:
- **Grew the MCP server from 3 to 14 tools.**
  - Board and money reads: `list_open_tickets`, `get_ticket`, `check_cash_position`, `check_discount_margin`.
  - Request-only writes: `request_payment_approval`, `request_purchase_order`, `save_customer_draft`, `update_ticket_status`.
  - **Human-only** tools: `list_approval_requests`, `approve_request`, `reject_request`. `approve_request` is the only one that moves money. It re-checks cash and refuses negative balances, writes `payments` with a human `approved_by`, and marks the invoice paid or moves rent forward a month.
  - The working copy gets three new tables: `approval_requests`, `drafts`, and `ticket_updates`.
- **Tested the guardrails on a throwaway database** before using the real working copy. These were all refused: a wrong amount, a duplicate request, an agent approving a payment, a PO to the blocked vendor, the $264 PO with only $160 left, and resolving a ticket while an approval was pending. Human approvals worked: $3,400 → $2,560 → $160.
- **Built the PydanticAI team** in `backend/`. PydanticAI 2.55 connects to the MCP server through `MCPToolset`.
  - `config.py`: the model is hardcoded to `gpt-6-luna` through Portkey, and `OPENAI_MODEL` is ignored. A ping returned "Portkey connection works."
  - `models.py`: `TeamDeps`, `AgentReport`, `BossDecision`, and the related types.
  - `prompts/`: a detailed prompt for each agent, plus `team_rules.md`.
  - `agents/`: one file per agent, plus `base.py` (tool allowlists, identity stamping, the `delegate` tool) and `team.py` (the agent loop).
  - `audit.py` appends one entry per agent run to `output/audit_trail.json`.
- **Full connectivity:** any agent can delegate to any other. Loops are blocked (no self- or cycle-delegation, depth ≤ 3, ≤ 10 delegations per ticket, a 40-request and 60-tool-call budget per ticket).
- **Ran the real team twice** (`--reset --all`).
  - The first run worked. Claude then fixed two things: `delegated_to` is now taken from the real trace (the Boss had under-reported it), and the Boss prompt now says the discount floor is a limit, not a target (it had offered the maximum 25%).
  - The final run:
    - **101:** awaiting approval. Request #1 is $840 for invoice 501. The PO was refused live because the vendor is blocked. Draft #1 went to Tauhid.
    - **102:** awaiting approval. Request #2 is $2,400 rent. Draft #2 went to the landlord.
    - **103:** blocked. 10% off ($52.20) is within policy. The 12-unit restock is blocked by the vendor and by cash. Draft #3 went to the club.
  - **0 payments were made**, and cash is still $3,400.
- **Docs:** `output/harness.md` now has the ops tables, the 14 tools, each agent with its tools, the delegation loop, the audit-trail fields, a **Safety and guardrails** section (built-in plus what a real business would add), and the run results. Also updated `mcp_server/README.md` and added a project `README.md`.
- Checked the whole project: no model other than `gpt-6-luna` appears anywhere.

## Prompt 11: Problem 6, plan the three tickets

> lets do the problem 6 now...
>
> problem 6 is to plan the three tickets..
>
> before we wire the backwend lets write what we expect the team to do on each open ticket... build a output/desk_tickets.html -- a page where i can double click with one tab per ticket..
>
> also add empty cash and reflection tabs for later problems... on .
>
> tab i will fill an expected section only leaving the actual section for after the agents run

What Claude did with this prompt:
- Built `output/desk_tickets.html`. It's one self-contained file (no server, opens with a double-click) in the Miami Vice style. It has 5 tabs: **Ticket 101**, **Ticket 102**, **Ticket 103**, **Cash** (empty), and **Reflection** (empty). The tabs work with the keyboard too (left and right arrows) and remember the last one opened.
- Each ticket tab has a filled-in **Expected** section:
  - a one-paragraph plan;
  - the facts the tools should return;
  - the expected agent routing;
  - a table of the expected MCP tool calls (agent, tool, input, expected result);
  - the guardrails the ticket should trigger;
  - what changes after the human approves;
  - a success checklist.
- Ticket 103 also lists the **decision options** for the Boss: A) partial fill now at 10–15% off (the expected pick), B) wait for all 20, C) vendor terms, D) no discount.
- Each ticket tab has an empty **Actual** box, to fill after the agents run.
- Expected outcomes:
  - **101:** `awaiting_approval`, with $840 pending for invoice 501 and the PO refused while the vendor is blocked.
  - **102:** `awaiting_approval`, with $2,400 rent pending and $160 left uncommitted.
  - **103:** `blocked`. 8 now at a modest discount, and the 12-unit restock ($264) is blocked by both the vendor and cash.
- Checked in the browser: all 5 tabs switch correctly, and the page doesn't scroll sideways at narrow width.

## Prompt 12: Problem 7, backend routes

> now lets do problem 7 - backend routes
>
> my react fronteand needs a backent to call... in backend/main.py use fast api and add routes that are gonna be doing:
>
> 1. return the 3 tickets and ewheat each is open or resolvers
> 2. take a ticket id and run my agent team on that ricket
> 3. return recent agent events so the board can refreash
> 4. approve a payment or purchase after a human clicks approve
> 5. return the current checking balance from cash accounts
> 6. reser the database to the original values when u want to try a feesh run
>
> it should run with uvicorn main:app --reload --port 8000
> update harness

What Claude did with this prompt:
- Wrote `backend/main.py` (FastAPI). The six required routes are:
  1. `GET /api/tickets`
  2. `POST /api/tickets/{id}/run`, which runs in the background (`?wait=true` to block) and returns 409 if the team is busy
  3. `GET /api/events?since=`
  4. `POST /api/approvals/{id}/approve`
  5. `GET /api/cash`
  6. `POST /api/reset`
- Extra routes: ticket detail, reject, the approvals list, a manual resolve, and health.
- Shop reads and approvals go through the **MCP server in-process**, so the dashboard uses the same guardrails as the agents.
- Added two MCP changes: a `list_tickets` tool (human only), and approving a purchase order is now refused while the vendor still has an open invoice.
- The app's preview launcher couldn't open the Desktop folder ("Operation not permitted"), so Claude started uvicorn from the shell with the exact command. Results:
  - All routes responded. Reset worked, and the 3 tickets came back open.
  - Cash showed $3,400. A bad request id returned 409, and an unknown ticket returned 404.
  - CORS allows `http://localhost:5173`.

## Prompt 13: Problem 8, the agent dashboard

> now lets make our agent dashboard
> frontednd with reac vite and typescript
>
> the ;age should call routes we built in backend list all 3 tickets
> let me pick 1 ticket and start the agent team on it
> show each agent and see what theyre saying and doing while the ticket rruns
> mark a ticket as resolved when the run finishes
> show a short summary of what each agent did
> let a human approve a pay or purchase
>
> show the checking baalance (it obvsly should drop if we approve payment)
>
> tell the front end to talk to my backend end at local host 8000... on the backend allow the vite page so browser is allowed to call those routs
> start the board with
> npm run dev
> write my output/design.md with my aesthetic preferences for the dashboard

What Claude did with this prompt:
- **Live agent events:** the agent loop now sends PydanticAI's `event_stream_handler` events (started, tool_call, tool_result) to the audit trail as `agent_step` events, so the board can show what each agent is doing *while* it runs.
- **Resolved on finish:** when a run finishes, the ticket is marked resolved if nothing waits for a human. If a payment is pending, it resolves automatically once the human approves or rejects the last request. The MCP rule "can't resolve with pending approvals" is kept.
- **Built `frontend/`** (React 19 + Vite 6 + TypeScript):
  - a ticket board;
  - a Start button;
  - 5 live agent cards (working, waiting on a teammate, done; the current action; what they were asked);
  - a "what they're saying & doing" feed, with guardrail refusals in red;
  - never-sent drafts;
  - per-agent summaries plus the Boss's final call;
  - an approvals queue (Approve & pay or Reject, approver name required);
  - an animated checking balance;
  - a payments ledger and a Reset button.
- `frontend/.env.development` points at `http://localhost:8000`. The backend CORS allows `http://localhost:5173`. Started with `npm run dev`.
- Wrote `output/design.md` ("Miami Vice after dark": palette, one color per agent, typography, layout, motion, voice, accessibility).
- **Tested in the browser:**
  - Started the team on #101 and watched the agents go live.
  - The run finished `awaiting_approval` with request #1 ($840).
  - Approved as "Dashboard Test". **Checking went $3,400 → $2,560**, and #101 flipped to **Resolved**.
  - Fixed a cramped feed layout at narrow widths along the way.
- Updated `output/harness.md` (backend routes, the dashboard, how tickets resolve) and `README.md`.

## Prompt 14: Problem 9, reset, run, and record the resolved board

> problem 9 - reset and run the database again
>
> open the outpu/desk_tickets html from problem 6 and fill the actual resolt which agents worked and the tools they used
>
> also save output/resolved_tickets.json for each ticket, id fina status, short outcome, what each agent contributed and any human approvals
> also
> output/resolverd_board.html - a page u can double click with a screen short of y reach board for each the resolved ticket
>
> append real runs to audit.trail.json finish the out/haarnessss so it covers everything we did here

Follow-up (Claude asked who should click Approve; I picked "I'll click them myself"), then:

> Done

What Claude did with these prompts:
- **Reset** with `POST /api/reset`. The working database was byte-identical to the original.
- **Ran #101.** The first attempt crashed: Portkey replayed a *cached* Responses answer with fake item ids. That exposed a bug: the crashed run still auto-resolved the ticket. Claude fixed both problems:
  - every request now bypasses Portkey's cache;
  - a failed run never resolves a ticket.
- A second attempt with Chat Completions failed, because `gpt-6-luna` only supports tools + reasoning on the Responses API. Claude reverted to the Responses API, reset again (keeping the audit trail), and the **third attempt succeeded**: request #1 ($840) was filed and draft #1 was saved.
- **Ran #102:** request #2 ($2,400 rent) and draft #2.
- **I approved both** in the dashboard as **Augusto**. Checking went $3,400 → $2,560 → **$160**, invoice 501 is paid, rent is next due 2026-10-02, and #101 and #102 auto-resolved.
- **Ran #103.** The Boss chose **10% off ($52.20)**. 8 hoodies are offered now ($417.60), and the 12-unit restock ($264) wasn't filed because only $160 remained. It resolved on finish with no human approval needed. Accounting delegated back to Inventory (Boss → Accounting → Inventory).
- **Screenshots:** added a `/?ticket=<id>` deep link to the board and captured 1440×2200 screenshots with headless Chrome into `output/screenshots/`.
- **Deliverables:**
  - `output/desk_tickets.html`: filled the **Actual** section for each ticket (real delegation chains, each agent's MCP tools and what it did, the human approval, plan vs. actual). Cash and Reflection stay empty for later problems.
  - `output/resolved_tickets.json`: generated from the audit trail and database. For each ticket it has the id, final status, outcome, each agent's tools and contribution, human approvals, draft, status history, and usage.
  - `output/resolved_board.html`: a double-click page with summary stats and one board screenshot per resolved ticket. Claude checked it in headless Chrome.
  - `output/audit_trail.json`: holds every real event, including the 2 failed attempts.
  - `output/harness.md`: added the official run, the issues and fixes, lessons learned, and a **deliverables index** for Problems 1–9.

## Prompt 15: Reflection

I attached the five reflection questions and gave my answers:

> open desk_tickets.html and lets reflect on
>
> 1. the agents were thorough, and inventory played a good. i just dont think the customer service wrote good emails that could be used in real life
> 2. they were similar enough, the conditions were controlled and agents acted as expected
> 3. probably the accounting and facilityies could be merged as one agent that takes care of every expense and cost... this separationmade things only more complicated
> 4. we could solve all problems related to payment of utilities, our agents could fill in orders from online sells, and also we could also build income statements with the our agents
> 5. problems that it can face could be defects and returns that should be made, we have no capabilities of returns. i think the payment of taxes could be another issue we dont have the capabilities of solving. payment of employees / accompanying their schedules is also not encompassed in our

What Claude did with this prompt:
- Filled the **Reflection** tab of `output/desk_tickets.html`. Each of my five answers is kept as the headline, with evidence from the official run underneath:
  1. A per-ticket scorecard (correct decision, followed the rules, efficiency, customer message), with the exact draft phrases that wouldn't work in real life: "overdue invoice", "pending human approval", "pending funding".
  2. Plan vs. actual for each ticket, including how approving invoice 501 before #103 changed the agents' reasoning.
  3. The audit trail backs up merging Accounting and Facilities: on #102, the lease was checked 3× and cash 4× across 5 agent runs, and Facilities' tools were a subset of Accounting's.
  4. Utilities, online orders, and income statements, each mapped to the existing tools, with honest notes: shipping needs an inventory-decrement tool, and income statements need revenue data.
  5. Returns, taxes, and payroll, each with the new tools and the new agent it would need, keeping the rule that only a human moves money.
- Checked the page in headless Chrome and fixed a style bug where bold labels in the Q5 cards rendered oversized.
