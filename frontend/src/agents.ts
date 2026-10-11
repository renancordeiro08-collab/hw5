import type { AgentName, BoardEvent } from './api'

export const AGENTS: { name: AgentName; label: string; role: string; glyph: string }[] = [
  { name: 'boss', label: 'Boss', role: 'Routes tickets, makes the final call', glyph: 'B' },
  { name: 'inventory', label: 'Inventory', role: 'Stock by SKU & size, restock vendors', glyph: 'I' },
  { name: 'accounting', label: 'Accounting', role: 'Cash, invoices, margins, approvals', glyph: 'A' },
  { name: 'facilities', label: 'Facilities', role: 'Lease, rent, the shop space', glyph: 'F' },
  { name: 'customer_service', label: 'Customer Service', role: 'Drafts messages (never sends)', glyph: 'C' },
]

export const agentLabel = (n?: string) => AGENTS.find(a => a.name === n)?.label ?? n ?? 'team'

const TOOL_WORDS: Record<string, string> = {
  get_ticket: 'reading the ticket',
  list_open_tickets: 'scanning the board',
  check_stock_and_pricing: 'checking stock & price',
  check_vendor_and_invoices: 'checking the vendor & invoices',
  check_lease_and_cash: 'checking the lease & cash',
  check_cash_position: 'checking cash on hand',
  check_discount_margin: 'testing the discount margin',
  request_payment_approval: 'filing a payment for approval',
  request_purchase_order: 'filing a purchase order',
  save_customer_draft: 'saving a draft',
  update_ticket_status: 'updating the ticket status',
  delegate: 'delegating',
}

/** One plain-English line for a live step, e.g. "checking stock & price (CC-TEE-WHITE S)". */
export function describeStep(e: BoardEvent): string {
  if (e.step === 'started') return 'picked up the task'
  const a = (e.args ?? {}) as Record<string, unknown>
  if (e.tool === 'delegate' && e.step === 'tool_call') return `asks ${agentLabel(String(a.to_agent))} for help`
  const word = TOOL_WORDS[e.tool ?? ''] ?? e.tool ?? 'working'
  if (e.step === 'tool_result') return `${word}: done`
  const detail = [a.sku, a.size, a.qty_needed ?? a.qty, a.invoice_id, a.lease_id && `lease ${a.lease_id}`, a.amount && `$${a.amount}`, a.status]
    .filter(Boolean)
    .join(' · ')
  return detail ? `${word} (${detail})` : word
}

/** Did the tool refuse? Shown as a guardrail hit in the feed. */
export const isRefusal = (e: BoardEvent) => e.step === 'tool_result' && /"refused":\s*true|REFUSED/.test(e.result ?? '')
