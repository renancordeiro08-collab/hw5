// Typed client for the FastAPI backend (backend/main.py).
export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string
  notes: string | null
  created_at: string
  is_open: boolean
  pending_approvals: number
  drafts: number
  running: boolean
}

export interface ApprovalRequest {
  id: number
  ticket_id: number
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number
  sku: string | null
  size: string | null
  qty: number | null
  amount: number
  requested_by: string
  reason: string
  status: 'pending' | 'paid' | 'rejected'
  decided_by: string | null
}

export interface Draft {
  id: number
  ticket_id: number
  to_name: string
  subject: string
  body: string
  written_by: string
  status: string
}

export interface BossDecision {
  ticket_id: number
  final_status: string
  decision: string
  delegated_to: AgentName[]
  approval_request_ids: number[]
  draft_ids: number[]
  human_actions_needed: string[]
  risks: string[]
  rationale: string
  resolved?: boolean
}

export interface TicketDetail {
  date_today: string
  ticket: Ticket
  history: { status: string; note: string; updated_by: string; at: string }[]
  approval_requests: ApprovalRequest[]
  drafts: Draft[]
}

export interface Cash {
  balance: number
  as_of: string
  date_today: string
  pending_approval_total: number
  available_for_new_requests: number
  payments_made: { id: number; kind: string; ref_id: number; amount: number; approved_by: string; paid_at: string }[]
}

export interface BoardEvent {
  id: number
  time: string
  type: string // run_started | agent_step | agent_run | ticket_done | ticket_resolved | human_decision | reset | run_failed
  ticket_id?: number
  agent?: AgentName
  agent_run_id?: string
  chain?: string[]
  step?: 'started' | 'tool_call' | 'tool_result'
  task?: string
  tool?: string
  args?: Record<string, unknown>
  result?: string
  tools?: string[]
  summary?: string
  status?: string
  needs_human?: boolean
  decision?: BossDecision | string
  by?: string
  request_id?: number
  team_usage?: { requests: number; input_tokens: number; output_tokens: number }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error((body as { detail?: string }).detail ?? `${res.status} ${res.statusText}`)
  return body as T
}

export const api = {
  tickets: () => call<{ date_today: string; tickets: Ticket[] }>('/api/tickets'),
  ticket: (id: number) => call<TicketDetail>(`/api/tickets/${id}`),
  run: (id: number) => call<{ status: string }>(`/api/tickets/${id}/run`, { method: 'POST' }),
  events: (since: number) =>
    call<{ events: BoardEvent[]; last_id: number; running_ticket: number | null }>(`/api/events?since=${since}&limit=500`),
  approvals: () => call<{ requests: ApprovalRequest[] }>('/api/approvals?status=all'),
  approve: (id: number, approved_by: string) =>
    call<{ new_balance: number; ticket_resolved: boolean }>(`/api/approvals/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by }),
    }),
  reject: (id: number, rejected_by: string, reason: string) =>
    call(`/api/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ rejected_by, reason }) }),
  resolve: (id: number, approved_by: string) =>
    call(`/api/tickets/${id}/resolve`, { method: 'POST', body: JSON.stringify({ approved_by }) }),
  cash: () => call<Cash>('/api/cash'),
  reset: () => call('/api/reset', { method: 'POST' }),
}
