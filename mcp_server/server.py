"""Campus Customs MCP server: the shared toolbox every agent uses.

Built with FastMCP. Every tool talks to the WORKING copy of the database
(data/campus_customs_new.db); the original campus_customs.db is never touched.
Read tools open the database read-only. Agent write tools can only create
REQUESTS, drafts, and ticket updates; money moves only through the human-only
tools (approve_request / reject_request), which no agent is given.
"""

import os
import calendar
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")

DB_PATH = Path(os.getenv("CAMPUS_DB_PATH", PROJECT_DIR / "data" / "campus_customs_new.db"))

# Which vendor specialty restocks which product line (SKU prefix).
# The vendors table has no SKU column, so we match on specialty.
AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
TICKET_STATUSES = {"open", "in_progress", "awaiting_approval", "blocked", "resolved"}
MIN_MARGIN_PCT = float(os.getenv("MIN_MARGIN_PCT", "30"))  # discount floor: margin must stay at or above this
MAX_DISCOUNT_PCT = float(os.getenv("MAX_DISCOUNT_PCT", "25"))  # bigger discounts need a human

SKU_PREFIX_TO_SPECIALTY = {
    "CC-HOOD": "apparel",
    "CC-TEE": "apparel",
    "CC-HAT": "apparel",
    "CC-MUG": "mugs",
}

mcp = FastMCP(
    "campus-customs",
    instructions=(
        "Tools for the Campus Customs operations team. 'Today' is always desk.date_today, "
        "never the real clock. Agents may read, request approvals, save drafts and update "
        "tickets. No agent may approve or execute a payment: approve_request and "
        "reject_request are for the human operator only."
    ),
)


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH.name}. Copy campus_customs.db to it first.")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_rw() -> sqlite3.Connection:
    """Write connection with manual transactions; creates the ops tables if missing."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH.name}. Copy campus_customs.db to it first.")
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(OPS_TABLES_SQL)
    return conn


# Operations tables added to the WORKING copy only (the original DB keeps its 9 tables).
OPS_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    kind TEXT NOT NULL,            -- invoice | rent | purchase_order
    ref_id INTEGER,                -- invoice id, lease id, or vendor id (purchase_order)
    sku TEXT, size TEXT, qty INTEGER,
    amount REAL NOT NULL,
    account TEXT NOT NULL DEFAULT 'checking',
    requested_by TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | paid | rejected
    created_at TEXT NOT NULL,
    decided_by TEXT, decided_at TEXT, decision_note TEXT, payment_id INTEGER
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    to_name TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    written_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',      -- drafts are never sent by the system
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_updates (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    updated_by TEXT NOT NULL,
    at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _pending_total(conn: sqlite3.Connection, exclude_id: int | None = None) -> float:
    if not _has_table(conn, "approval_requests"):
        return 0.0
    row = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM approval_requests WHERE status='pending' AND id IS NOT ?", (exclude_id,)
    ).fetchone()
    return round(row["s"], 2)


def _add_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _today(conn: sqlite3.Connection) -> date:
    return date.fromisoformat(conn.execute("SELECT date_today FROM desk").fetchone()["date_today"])


def _restock_vendor(conn: sqlite3.Connection, sku: str) -> sqlite3.Row | None:
    specialty = next((s for p, s in SKU_PREFIX_TO_SPECIALTY.items() if sku.upper().startswith(p)), None)
    if specialty is None:
        return None
    return conn.execute(
        "SELECT * FROM vendors WHERE specialty LIKE ? ORDER BY lead_days LIMIT 1", (f"%{specialty}%",)
    ).fetchone()


def _vendor_report(conn: sqlite3.Connection, vendor: sqlite3.Row, today: date) -> dict:
    open_invoices = conn.execute(
        "SELECT id, amount, due_date, description FROM invoices WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
        (vendor["id"],),
    ).fetchall()
    invoices = []
    for inv in open_invoices:
        days_late = (today - date.fromisoformat(inv["due_date"])).days
        invoices.append({
            "invoice_id": inv["id"],
            "amount": inv["amount"],
            "due_date": inv["due_date"],
            "days_overdue": max(days_late, 0),
            "overdue": days_late > 0,
            "description": inv["description"],
        })
    can_ship = not invoices
    return {
        "vendor_id": vendor["id"],
        "name": vendor["name"],
        "specialty": vendor["specialty"],
        "lead_days": vendor["lead_days"],
        "open_unpaid_invoices": invoices,
        "amount_owed": round(sum(i["amount"] for i in invoices), 2),
        "can_ship_now": can_ship,
        "earliest_arrival_if_ordered_today": (today + timedelta(days=vendor["lead_days"])).isoformat() if can_ship else None,
        "earliest_arrival_once_invoices_paid_today": (today + timedelta(days=vendor["lead_days"])).isoformat(),
        "rule": "A vendor will not ship new product while it has an open unpaid invoice.",
    }


@mcp.tool(annotations={"readOnlyHint": True})
def check_stock_and_pricing(sku: str, size: str, qty_needed: int = 1) -> dict:
    """Check how many units of a SKU are on hand in one size, the shortfall for a
    requested quantity, other sizes in stock, unit cost and list price, and which
    vendor restocks this item. Use for customer orders and bulk/discount requests."""
    with _connect() as conn:
        today = _today(conn)
        rows = conn.execute("SELECT * FROM inventory WHERE sku = ? ORDER BY rowid", (sku.upper(),)).fetchall()
        if not rows:
            return {"error": f"Unknown SKU '{sku}'."}
        by_size = {r["size"]: r["qty"] for r in rows}
        size = size.upper()
        if size not in by_size:
            return {"error": f"SKU {sku} has no size '{size}'. Sizes: {list(by_size)}."}
        on_hand = by_size[size]
        price = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku.upper(),)).fetchone()
        vendor = _restock_vendor(conn, sku)
        shortfall = max(qty_needed - on_hand, 0)
        result = {
            "date_today": today.isoformat(),
            "sku": rows[0]["sku"],
            "name": rows[0]["name"],
            "size": size,
            "location": rows[0]["location"],
            "qty_needed": qty_needed,
            "on_hand": on_hand,
            "shortfall": shortfall,
            "can_fill_from_stock": shortfall == 0,
            "other_sizes_on_hand": {s: q for s, q in by_size.items() if s != size and q > 0},
            "unit_cost": price["unit_cost"] if price else None,
            "list_price": price["list_price"] if price else None,
            "restock_cost_for_shortfall": round(shortfall * price["unit_cost"], 2) if price else None,
            "restock_vendor": _vendor_report(conn, vendor, today) if vendor else None,
        }
        return result


@mcp.tool(annotations={"readOnlyHint": True})
def check_vendor_and_invoices(vendor_id: int | None = None, invoice_id: int | None = None) -> dict:
    """Look up a vendor (by vendor_id, or by one of its invoice_id values): lead time,
    every open unpaid invoice with days overdue versus desk.date_today, total owed,
    and whether the vendor will ship new product right now."""
    if vendor_id is None and invoice_id is None:
        return {"error": "Pass vendor_id or invoice_id."}
    with _connect() as conn:
        today = _today(conn)
        if invoice_id is not None:
            inv = conn.execute("SELECT vendor_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            if inv is None:
                return {"error": f"Unknown invoice {invoice_id}."}
            vendor_id = inv["vendor_id"]
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return {"error": f"Unknown vendor {vendor_id}."}
        return {"date_today": today.isoformat(), **_vendor_report(conn, vendor, today)}


@mcp.tool(annotations={"readOnlyHint": True})
def check_lease_and_cash(lease_id: int) -> dict:
    """Look up a lease: space, landlord, monthly rent, next due date and days until
    due (or overdue) versus desk.date_today, plus the cash balance and whether it
    covers the rent without going negative."""
    with _connect() as conn:
        today = _today(conn)
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if lease is None:
            return {"error": f"Unknown lease {lease_id}."}
        accounts = conn.execute("SELECT name, balance, date FROM cash_accounts").fetchall()
        days_until_due = (date.fromisoformat(lease["next_due"]) - today).days
        total_cash = round(sum(a["balance"] for a in accounts), 2)
        return {
            "date_today": today.isoformat(),
            "lease_id": lease["id"],
            "space_name": lease["space_name"],
            "landlord": lease["landlord"],
            "monthly_rent": lease["monthly_rent"],
            "next_due": lease["next_due"],
            "days_until_due": days_until_due,
            "overdue": days_until_due < 0,
            "notes": lease["notes"],
            "cash_accounts": [dict(a) for a in accounts],
            "cash_after_rent": round(total_cash - lease["monthly_rent"], 2),
            "cash_covers_rent": total_cash >= lease["monthly_rent"],
            "rule": "Any payment needs human approval; no balance may go negative.",
        }


# ---------------------------------------------------------------- board (read)

@mcp.tool(annotations={"readOnlyHint": True})
def list_open_tickets() -> dict:
    """List every ticket on the board that is not resolved, oldest first, with
    desk.date_today. The Boss starts here."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, type, requester, subject, status, created_at FROM tickets WHERE status != 'resolved' ORDER BY created_at"
        ).fetchall()
        return {"date_today": _today(conn).isoformat(), "open_tickets": [dict(r) for r in rows]}


@mcp.tool(annotations={"readOnlyHint": True})
def get_ticket(ticket_id: int) -> dict:
    """Read one ticket in full, plus everything already done on it: status
    history, approval requests, and customer drafts."""
    with _connect() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"error": f"Unknown ticket {ticket_id}."}
        out = {"date_today": _today(conn).isoformat(), "ticket": dict(t)}
        for table, key in (("ticket_updates", "history"), ("approval_requests", "approval_requests"), ("drafts", "drafts")):
            out[key] = (
                [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE ticket_id = ? ORDER BY id", (ticket_id,))]
                if _has_table(conn, table) else []
            )
        return out


# ---------------------------------------------------------------- money (read)

@mcp.tool(annotations={"readOnlyHint": True})
def check_cash_position() -> dict:
    """Cash on hand, money already committed to pending approval requests, cash
    still available for new requests, and every payment made so far."""
    with _connect() as conn:
        accounts = [dict(a) for a in conn.execute("SELECT name, balance, date FROM cash_accounts")]
        total = round(sum(a["balance"] for a in accounts), 2)
        pending = _pending_total(conn)
        pending_rows = (
            [dict(r) for r in conn.execute("SELECT id, ticket_id, kind, ref_id, amount, requested_by FROM approval_requests WHERE status='pending'")]
            if _has_table(conn, "approval_requests") else []
        )
        return {
            "date_today": _today(conn).isoformat(),
            "cash_accounts": accounts,
            "cash_on_hand": total,
            "pending_approval_total": pending,
            "pending_requests": pending_rows,
            "available_for_new_requests": round(total - pending, 2),
            "payments_made": [dict(r) for r in conn.execute("SELECT * FROM payments ORDER BY id")],
            "rule": "Cash only goes out (no revenue is modeled). No payment may make a balance negative.",
        }


@mcp.tool(annotations={"readOnlyHint": True})
def check_discount_margin(sku: str, qty: int, discount_pct: float | None = None, proposed_unit_price: float | None = None) -> dict:
    """Test a proposed discount (as discount_pct off list, or a proposed_unit_price)
    against unit cost: margin per unit and in total, and whether it passes the shop's
    floor (never below cost, margin >= MIN_MARGIN_PCT, discount <= MAX_DISCOUNT_PCT)."""
    with _connect() as conn:
        p = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku.upper(),)).fetchone()
        if p is None:
            return {"error": f"No pricing for SKU '{sku}'."}
        cost, list_price = p["unit_cost"], p["list_price"]
        if proposed_unit_price is None:
            proposed_unit_price = round(list_price * (1 - (discount_pct or 0) / 100), 2)
        discount = round((1 - proposed_unit_price / list_price) * 100, 2)
        margin = round(proposed_unit_price - cost, 2)
        margin_pct = round(margin / proposed_unit_price * 100, 2) if proposed_unit_price else -100.0
        floor_price = round(cost / (1 - MIN_MARGIN_PCT / 100), 2)
        problems = []
        if proposed_unit_price < cost:
            problems.append("below unit cost")
        if margin_pct < MIN_MARGIN_PCT:
            problems.append(f"margin under {MIN_MARGIN_PCT:.0f}%")
        if discount > MAX_DISCOUNT_PCT:
            problems.append(f"discount over {MAX_DISCOUNT_PCT:.0f}% needs a human manager")
        return {
            "sku": sku.upper(), "qty": qty, "unit_cost": cost, "list_price": list_price,
            "proposed_unit_price": proposed_unit_price, "discount_pct": discount,
            "margin_per_unit": margin, "margin_pct": margin_pct,
            "total_at_list": round(list_price * qty, 2), "total_at_proposed": round(proposed_unit_price * qty, 2),
            "total_margin": round(margin * qty, 2),
            "lowest_price_within_policy": max(floor_price, round(list_price * (1 - MAX_DISCOUNT_PCT / 100), 2)),
            "within_policy": not problems, "problems": problems,
        }


# ---------------------------------------------------------------- agent writes (no money moves)

@mcp.tool(annotations={"destructiveHint": False})
def request_payment_approval(ticket_id: int, kind: str, ref_id: int, amount: float, requested_by: str, reason: str) -> dict:
    """Ask the human operator to approve a payment. kind is 'invoice' (ref_id =
    invoice id) or 'rent' (ref_id = lease id). The amount must match the bill.
    This does NOT pay anything; it puts a pending request on the approval queue."""
    kind = kind.lower().strip()
    if kind not in {"invoice", "rent"}:
        return {"refused": True, "reason": "kind must be 'invoice' or 'rent' (use request_purchase_order for restock)."}
    conn = _connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if kind == "invoice":
            bill = conn.execute("SELECT amount, status FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if bill is None or bill["status"] != "open":
                conn.execute("ROLLBACK")
                return {"refused": True, "reason": f"Invoice {ref_id} is not an open invoice."}
            expected = bill["amount"]
        else:
            lease = conn.execute("SELECT monthly_rent FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                conn.execute("ROLLBACK")
                return {"refused": True, "reason": f"Unknown lease {ref_id}."}
            expected = lease["monthly_rent"]
        if round(amount, 2) != round(expected, 2):
            conn.execute("ROLLBACK")
            return {"refused": True, "reason": f"Amount {amount} does not match the bill ({expected})."}
        dup = conn.execute(
            "SELECT id FROM approval_requests WHERE kind=? AND ref_id=? AND status='pending'", (kind, ref_id)
        ).fetchone()
        if dup:
            conn.execute("ROLLBACK")
            return {"refused": True, "reason": f"Already pending as request {dup['id']}.", "request_id": dup["id"]}
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()["balance"]
        available = round(cash - _pending_total(conn), 2)
        if amount > available:
            conn.execute("ROLLBACK")
            return {"refused": True, "reason": f"Not enough uncommitted cash: {available} available after pending requests, {amount} needed."}
        cur = conn.execute(
            "INSERT INTO approval_requests (ticket_id, kind, ref_id, amount, requested_by, reason, created_at) VALUES (?,?,?,?,?,?,?)",
            (ticket_id, kind, ref_id, amount, requested_by, reason, _now()),
        )
        conn.execute("COMMIT")
        return {"request_id": cur.lastrowid, "status": "pending", "kind": kind, "ref_id": ref_id, "amount": amount,
                "cash_available_after_this_request": round(available - amount, 2),
                "next_step": "A human must approve this in the dashboard. Nothing has been paid."}
    finally:
        conn.close()


@mcp.tool(annotations={"destructiveHint": False})
def request_purchase_order(ticket_id: int, sku: str, size: str, qty: int, requested_by: str, reason: str) -> dict:
    """Ask the human operator to approve a restock purchase order (qty x unit_cost,
    paid upfront). Refused if the restock vendor still has an open unpaid invoice
    (they will not ship) or if uncommitted cash cannot cover it."""
    conn = _connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")
        today = _today(conn)
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku.upper(),)).fetchone()
        vendor = _restock_vendor(conn, sku)
        if price is None or vendor is None:
            conn.execute("ROLLBACK")
            return {"refused": True, "reason": f"No pricing or restock vendor for SKU '{sku}'."}
        report = _vendor_report(conn, vendor, today)
        amount = round(qty * price["unit_cost"], 2)
        if not report["can_ship_now"]:
            conn.execute("ROLLBACK")
            return {"refused": True, "reason": f"{vendor['name']} has open unpaid invoice(s) and will not ship.",
                    "blocking_invoices": report["open_unpaid_invoices"], "amount_would_be": amount}
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()["balance"]
        available = round(cash - _pending_total(conn), 2)
        if amount > available:
            conn.execute("ROLLBACK")
            return {"refused": True, "reason": f"Not enough uncommitted cash: {available} available, {amount} needed.",
                    "amount_would_be": amount}
        cur = conn.execute(
            "INSERT INTO approval_requests (ticket_id, kind, ref_id, sku, size, qty, amount, requested_by, reason, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ticket_id, "purchase_order", vendor["id"], sku.upper(), size.upper(), qty, amount, requested_by, reason, _now()),
        )
        conn.execute("COMMIT")
        return {"request_id": cur.lastrowid, "status": "pending", "vendor": vendor["name"], "amount": amount,
                "expected_arrival_if_approved_today": (today + timedelta(days=vendor["lead_days"])).isoformat(),
                "next_step": "A human must approve this in the dashboard. Nothing has been paid or ordered."}
    finally:
        conn.close()


@mcp.tool(annotations={"destructiveHint": False})
def save_customer_draft(ticket_id: int, to_name: str, subject: str, body: str, written_by: str) -> dict:
    """Save a message draft for a customer, landlord, or vendor on the board. It is
    NEVER sent; a human reads it in the dashboard."""
    conn = _connect_rw()
    try:
        cur = conn.execute(
            "INSERT INTO drafts (ticket_id, to_name, subject, body, written_by, created_at) VALUES (?,?,?,?,?,?)",
            (ticket_id, to_name, subject, body, written_by, _now()),
        )
        return {"draft_id": cur.lastrowid, "status": "draft", "sent": False}
    finally:
        conn.close()


@mcp.tool(annotations={"destructiveHint": False})
def update_ticket_status(ticket_id: int, status: str, note: str, updated_by: str) -> dict:
    """Move a ticket to in_progress, awaiting_approval, blocked, or resolved and log
    why. A ticket cannot be resolved while it still has pending approval requests."""
    status = status.lower().strip()
    if status not in TICKET_STATUSES:
        return {"refused": True, "reason": f"status must be one of {sorted(TICKET_STATUSES)}."}
    conn = _connect_rw()
    try:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"refused": True, "reason": f"Unknown ticket {ticket_id}."}
        if status == "resolved":
            pending = conn.execute(
                "SELECT id FROM approval_requests WHERE ticket_id=? AND status='pending'", (ticket_id,)
            ).fetchall()
            if pending:
                return {"refused": True, "reason": f"Requests {[r['id'] for r in pending]} still await human approval; use awaiting_approval."}
        conn.execute("BEGIN")
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.execute(
            "INSERT INTO ticket_updates (ticket_id, status, note, updated_by, at) VALUES (?,?,?,?,?)",
            (ticket_id, status, note, updated_by, _now()),
        )
        conn.execute("COMMIT")
        return {"ticket_id": ticket_id, "status": status}
    finally:
        conn.close()


# ---------------------------------------------------------------- HUMAN ONLY (never given to agents)

@mcp.tool(annotations={"readOnlyHint": True}, tags={"human_only"})
def list_tickets() -> dict:
    """The whole board for the dashboard: every ticket (open or resolved) with its
    status and counts of pending approvals and drafts."""
    with _connect() as conn:
        has_req, has_drafts = _has_table(conn, "approval_requests"), _has_table(conn, "drafts")
        tickets = []
        for t in conn.execute("SELECT * FROM tickets ORDER BY created_at"):
            row = dict(t)
            row["is_open"] = row["status"] != "resolved"
            row["pending_approvals"] = conn.execute(
                "SELECT COUNT(*) FROM approval_requests WHERE ticket_id=? AND status='pending'", (row["id"],)
            ).fetchone()[0] if has_req else 0
            row["drafts"] = conn.execute("SELECT COUNT(*) FROM drafts WHERE ticket_id=?", (row["id"],)).fetchone()[0] if has_drafts else 0
            tickets.append(row)
        return {"date_today": _today(conn).isoformat(), "tickets": tickets}


@mcp.tool(annotations={"readOnlyHint": True}, tags={"human_only"})
def list_approval_requests(status: str = "pending") -> dict:
    """The approval queue for the human operator: requests with the given status
    (pending, paid, rejected, or all)."""
    with _connect() as conn:
        if not _has_table(conn, "approval_requests"):
            return {"requests": []}
        sql, args = "SELECT * FROM approval_requests", ()
        if status != "all":
            sql, args = sql + " WHERE status = ?", (status,)
        return {"requests": [dict(r) for r in conn.execute(sql + " ORDER BY id", args)]}


@mcp.tool(annotations={"destructiveHint": True}, tags={"human_only"})
def approve_request(request_id: int, approved_by: str) -> dict:
    """HUMAN ONLY. Approve a pending request and execute the payment: refuse if cash
    would go negative; otherwise write a payments row (approved_by = the human), lower
    the cash balance, and mark the invoice paid or move the lease due date a month."""
    who = (approved_by or "").strip()
    if not who or who.lower() in AGENT_NAMES or "agent" in who.lower():
        return {"refused": True, "reason": "approved_by must be a named human, not an agent."}
    conn = _connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")
        req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None or req["status"] != "pending":
            conn.execute("ROLLBACK")
            return {"refused": True, "reason": f"Request {request_id} is not pending."}
        acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (req["account"],)).fetchone()
        if acct is None or acct["balance"] < req["amount"]:
            conn.execute("ROLLBACK")
            return {"refused": True, "reason": f"Not enough cash: balance {acct['balance'] if acct else 0}, payment {req['amount']}. No negative balances."}
        today = _today(conn)
        if req["kind"] == "invoice":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                conn.execute("ROLLBACK")
                return {"refused": True, "reason": f"Invoice {req['ref_id']} is no longer open."}
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (req["ref_id"],))
        elif req["kind"] == "purchase_order":
            blocking = conn.execute(
                "SELECT id FROM invoices WHERE vendor_id = ? AND status = 'open'", (req["ref_id"],)
            ).fetchall()
            if blocking:
                conn.execute("ROLLBACK")
                return {"refused": True, "reason": f"Vendor still has open invoice(s) {[b['id'] for b in blocking]}; it will not ship."}
        elif req["kind"] == "rent":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?",
                         (_add_month(date.fromisoformat(lease["next_due"])).isoformat(), req["ref_id"]))
        new_balance = round(acct["balance"] - req["amount"], 2)
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today.isoformat(), req["account"]))
        pay = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?,?,?,?,?,?)",
            (req["kind"], req["ref_id"], req["amount"], req["account"], today.isoformat(), who),
        )
        conn.execute(
            "UPDATE approval_requests SET status='paid', decided_by=?, decided_at=?, payment_id=? WHERE id=?",
            (who, _now(), pay.lastrowid, request_id),
        )
        conn.execute("COMMIT")
        return {"request_id": request_id, "status": "paid", "payment_id": pay.lastrowid, "amount": req["amount"],
                "approved_by": who, "new_balance": new_balance}
    finally:
        conn.close()


@mcp.tool(annotations={"destructiveHint": False}, tags={"human_only"})
def reject_request(request_id: int, rejected_by: str, reason: str) -> dict:
    """HUMAN ONLY. Reject a pending request; no money moves."""
    conn = _connect_rw()
    try:
        cur = conn.execute(
            "UPDATE approval_requests SET status='rejected', decided_by=?, decided_at=?, decision_note=? WHERE id=? AND status='pending'",
            (rejected_by, _now(), reason, request_id),
        )
        if cur.rowcount == 0:
            return {"refused": True, "reason": f"Request {request_id} is not pending."}
        return {"request_id": request_id, "status": "rejected"}
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(show_banner=False)
