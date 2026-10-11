import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_URL, api } from './api'
import type { ApprovalRequest, BoardEvent, Cash, Ticket, TicketDetail } from './api'
import { CashMeter } from './components/CashMeter'
import { AgentLanes } from './components/AgentLanes'
import { ActivityFeed } from './components/ActivityFeed'
import { AgentSummaries } from './components/AgentSummaries'
import { Approvals } from './components/Approvals'

const TYPE_LABEL: Record<string, string> = { customer_order: 'Customer order', rent_notice: 'Rent notice', price_override: 'Discount request' }
const STATUS_LABEL: Record<string, string> = {
  open: 'open', in_progress: 'in progress', awaiting_approval: 'awaiting approval', blocked: 'blocked', resolved: 'resolved',
}

function load(key: string, fallback: string) {
  try { return localStorage.getItem(key) ?? fallback } catch { return fallback }
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  // ?ticket=101 opens the board on that ticket (used for the resolved-board screenshots).
  const [selected, setSelected] = useState<number | null>(() => {
    const t = Number(new URLSearchParams(window.location.search).get('ticket'))
    return Number.isFinite(t) && t > 0 ? t : null
  })
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [events, setEvents] = useState<BoardEvent[]>([])
  const [running, setRunning] = useState<number | null>(null)
  const [cash, setCash] = useState<Cash | null>(null)
  const [requests, setRequests] = useState<ApprovalRequest[]>([])
  const [approver, setApproverState] = useState(() => load('approver', ''))
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const lastId = useRef(-1)

  const setApprover = (s: string) => { setApproverState(s); try { localStorage.setItem('approver', s) } catch { /* private mode */ } }
  const say = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 4000) }

  const refresh = useCallback(async () => {
    try {
      const [t, c, a, ev] = await Promise.all([api.tickets(), api.cash(), api.approvals(), api.events(lastId.current)])
      setTickets(t.tickets)
      setCash(c)
      setRequests(a.requests)
      if (ev.last_id < lastId.current) { // trail was reset: start over
        lastId.current = -1
        setEvents([])
      } else if (ev.events.length) {
        lastId.current = ev.last_id
        setEvents(prev => [...prev, ...ev.events.filter(e => !prev.some(p => p.id === e.id))])
      }
      setRunning(ev.running_ticket)
      setError(null)
      setSelected(s => s ?? t.tickets[0]?.id ?? null)
    } catch (e) {
      setError(`Can't reach the backend at ${API_URL}. Start it with: cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000`)
      console.error(e)
    }
  }, [])

  // Poll fast while the team works, slower when idle.
  useEffect(() => {
    refresh()
    const id = setInterval(refresh, running ? 1200 : 4000)
    return () => clearInterval(id)
  }, [refresh, running])

  // Ticket detail (drafts, requests, history) follows the selection and new activity.
  const ticketEvents = useMemo(() => {
    if (selected === null) return []
    const mine = events.filter(e => e.ticket_id === selected)
    const lastStart = [...mine].reverse().find(e => e.type === 'run_started')
    const fromId = lastStart?.id ?? -1
    const reqIds = new Set(requests.filter(r => r.ticket_id === selected).map(r => r.id))
    return events.filter(e => e.id >= fromId && (e.ticket_id === selected || (e.type === 'human_decision' && reqIds.has(e.request_id!))))
  }, [events, selected, requests])

  useEffect(() => {
    if (selected === null) return
    api.ticket(selected).then(setDetail).catch(() => setDetail(null))
  }, [selected, ticketEvents.length, requests])

  const current = tickets.find(t => t.id === selected) ?? null
  const isRunning = running !== null && running === selected
  const hasRun = ticketEvents.some(e => e.type === 'agent_run')

  async function startRun() {
    if (selected === null) return
    try {
      await api.run(selected)
      setRunning(selected)
      say(`Team started on ticket #${selected}`)
      setTimeout(refresh, 400)
    } catch (e) { say((e as Error).message) }
  }

  async function approve(id: number) {
    try {
      const r = await api.approve(id, approver.trim())
      say(`Paid. Checking is now $${r.new_balance.toLocaleString()}${r.ticket_resolved ? ' · ticket resolved' : ''}`)
    } catch (e) { say(`Refused: ${(e as Error).message}`) }
    await refresh()
  }

  async function reject(id: number) {
    const reason = window.prompt('Why reject this request?', 'Not approved by the manager')
    if (!reason) return
    try { await api.reject(id, approver.trim(), reason); say(`Request #${id} rejected. No money moved.`) }
    catch (e) { say((e as Error).message) }
    await refresh()
  }

  async function resolve() {
    if (selected === null) return
    try { await api.resolve(selected, approver.trim() || 'manager'); say(`Ticket #${selected} resolved`) }
    catch (e) { say((e as Error).message) }
    await refresh()
  }

  async function reset() {
    if (!window.confirm('Reset the working database to the original values and clear the event log?')) return
    try { await api.reset(); lastId.current = -1; setEvents([]); say('Fresh start: database reset') }
    catch (e) { say((e as Error).message) }
    await refresh()
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <h1>Campus Customs</h1>
          <p>Multi-Agent Ops Board · <span className="model">gpt-6-luna</span></p>
        </div>
        <CashMeter cash={cash} />
        <button className="btn ghost small" onClick={reset} disabled={running !== null}>Reset database</button>
      </header>

      {error && <div className="banner" role="alert">{error}</div>}

      <div className="grid">
        {/* ---------------------------------------------------- board */}
        <nav className="panel board" aria-labelledby="board-h">
          <h2 id="board-h">Ticket board</h2>
          <ul>
            {tickets.map(t => (
              <li key={t.id}>
                <button className={`ticket ${t.id === selected ? 'sel' : ''} st-${t.status}`} onClick={() => setSelected(t.id)} aria-pressed={t.id === selected}>
                  <span className="t-top">
                    <span className="t-id">#{t.id}</span>
                    <span className={`pill pill-${t.status}`}>{t.running || running === t.id ? 'running' : STATUS_LABEL[t.status] ?? t.status}</span>
                  </span>
                  <span className="t-subject">{t.subject}</span>
                  <span className="t-meta">{TYPE_LABEL[t.type] ?? t.type} · {t.requester}</span>
                  <span className="t-flags">
                    <span className={t.is_open ? 'flag open' : 'flag done'}>{t.is_open ? 'Open' : 'Resolved'}</span>
                    {t.pending_approvals > 0 && <span className="flag warn">{t.pending_approvals} to approve</span>}
                    {t.drafts > 0 && <span className="flag">{t.drafts} draft{t.drafts > 1 ? 's' : ''}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* ---------------------------------------------------- selected ticket */}
        <main className="panel stage">
          {current ? (
            <>
              <div className="stage-head">
                <div>
                  <p className="eyebrow">{TYPE_LABEL[current.type] ?? current.type} · ticket #{current.id}</p>
                  <h2>{current.subject} <span className="muted">· {current.requester}</span></h2>
                  <p className="notes">“{current.notes}”{current.sku && <> · <code>{current.sku}</code> {current.size} × {current.qty}</>}</p>
                </div>
                <div className="stage-actions">
                  <button className="btn run" onClick={startRun} disabled={running !== null || !current.is_open}>
                    {isRunning ? <><span className="spinner" aria-hidden /> Team working…</> : hasRun ? 'Run team again' : 'Start agent team'}
                  </button>
                  {current.is_open && hasRun && !isRunning && current.pending_approvals === 0 && (
                    <button className="btn ghost small" onClick={resolve}>Mark resolved</button>
                  )}
                  {!current.is_open && <span className="resolved-badge">✓ Resolved</span>}
                  {running !== null && running !== selected && <span className="hint">Team busy on #{running}</span>}
                </div>
              </div>

              <h3 className="sec">Agents {isRunning && <span className="live">live</span>}</h3>
              <AgentLanes events={ticketEvents} running={isRunning} />

              <div className="split">
                <section>
                  <h3 className="sec">What they're saying &amp; doing</h3>
                  <ActivityFeed events={ticketEvents} />
                </section>
                <section>
                  <h3 className="sec">Drafts on the board <span className="muted">(never sent)</span></h3>
                  {detail?.drafts.length ? detail.drafts.map(d => (
                    <article key={d.id} className="draft">
                      <p className="draft-to">To {d.to_name} · <b>{d.subject}</b></p>
                      <p className="draft-body">{d.body}</p>
                    </article>
                  )) : <p className="empty">No drafts yet.</p>}
                </section>
              </div>

              {hasRun && !isRunning && <><h3 className="sec">What each agent did</h3><AgentSummaries events={ticketEvents} /></>}
            </>
          ) : <p className="empty">Loading the board…</p>}
        </main>

        {/* ---------------------------------------------------- approvals */}
        <aside>
          <Approvals requests={requests} approver={approver} setApprover={setApprover} onApprove={approve} onReject={reject} />
          {cash && cash.payments_made.length > 0 && (
            <section className="panel ledger">
              <h2>Payments made</h2>
              {cash.payments_made.map(p => (
                <p key={p.id}><b>${p.amount.toLocaleString()}</b> · {p.kind} #{p.ref_id} · approved by {p.approved_by}</p>
              ))}
            </section>
          )}
        </aside>
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  )
}
