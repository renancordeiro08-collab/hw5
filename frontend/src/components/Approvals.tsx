import { useState } from 'react'
import type { ApprovalRequest } from '../api'

const money = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const KIND: Record<ApprovalRequest['kind'], string> = { invoice: 'Vendor invoice', rent: 'Rent', purchase_order: 'Purchase order' }

function what(r: ApprovalRequest) {
  if (r.kind === 'invoice') return `Pay invoice #${r.ref_id}`
  if (r.kind === 'rent') return `Pay rent, lease #${r.ref_id}`
  return `Restock ${r.qty} × ${r.sku} ${r.size ?? ''}`
}

interface Props {
  requests: ApprovalRequest[]
  approver: string
  setApprover: (s: string) => void
  onApprove: (id: number) => Promise<void>
  onReject: (id: number) => Promise<void>
}

/** The human-in-the-loop queue. Only this panel can move money. */
export function Approvals({ requests, approver, setApprover, onApprove, onReject }: Props) {
  const [busy, setBusy] = useState<number | null>(null)
  const pending = requests.filter(r => r.status === 'pending')
  const decided = requests.filter(r => r.status !== 'pending')
  const act = async (id: number, fn: (id: number) => Promise<void>) => { setBusy(id); try { await fn(id) } finally { setBusy(null) } }

  return (
    <section className="panel approvals" aria-labelledby="appr-h">
      <h2 id="appr-h">Approvals <span className="count">{pending.length}</span></h2>
      <label className="approver">
        <span>Approving as</span>
        <input value={approver} onChange={e => setApprover(e.target.value)} placeholder="Your name" />
      </label>
      {!pending.length && <p className="empty">Nothing waiting. Agents file payments and purchase orders here; no money moves until a person approves.</p>}
      {pending.map(r => (
        <article key={r.id} className="req">
          <div className="req-top">
            <span className="kind">{KIND[r.kind]}</span>
            <span className="amt">{money(r.amount)}</span>
          </div>
          <h4>{what(r)}</h4>
          <p className="meta">Ticket #{r.ticket_id} · filed by {r.requested_by} · request #{r.id}</p>
          {r.reason && <p className="reason">{r.reason}</p>}
          <div className="req-actions">
            <button className="btn approve" disabled={!approver.trim() || busy === r.id} onClick={() => act(r.id, onApprove)}>
              {busy === r.id ? 'Working…' : 'Approve & pay'}
            </button>
            <button className="btn ghost" disabled={!approver.trim() || busy === r.id} onClick={() => act(r.id, onReject)}>Reject</button>
          </div>
        </article>
      ))}
      {decided.length > 0 && (
        <details className="decided">
          <summary>Decided ({decided.length})</summary>
          {decided.map(r => (
            <p key={r.id}><b className={`st-${r.status}`}>{r.status}</b> · {what(r)} · {money(r.amount)} · {r.decided_by}</p>
          ))}
        </details>
      )}
    </section>
  )
}
