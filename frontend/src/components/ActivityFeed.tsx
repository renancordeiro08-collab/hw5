import { useEffect, useRef } from 'react'
import type { BoardEvent } from '../api'
import { agentLabel, describeStep, isRefusal } from '../agents'

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

/** The running conversation: who asked whom, which tools fired, what got refused. */
export function ActivityFeed({ events }: { events: BoardEvent[] }) {
  const end = useRef<HTMLLIElement>(null)
  const items = events.filter(e => e.type !== 'agent_step' || e.step !== 'tool_result' || isRefusal(e))

  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [items.length])

  if (!items.length) return <p className="empty">No activity yet. Start the team and the conversation shows up here live.</p>

  return (
    <ol className="feed">
      {items.map(e => {
        const who = agentLabel(e.agent)
        let text: string, kind = e.type
        if (e.type === 'agent_step' && e.tool === 'delegate' && e.step === 'tool_call') {
          kind = 'say'
          text = String((e.args as { task?: string })?.task ?? '')
        } else if (e.type === 'agent_step') {
          kind = isRefusal(e) ? 'refused' : e.step ?? 'step'
          text = isRefusal(e) ? `Tool refused: ${(e.result ?? '').replace(/[{}"]/g, '').slice(0, 180)}` : describeStep(e)
        } else if (e.type === 'agent_run') {
          kind = 'report'
          text = e.summary ?? 'reported back'
        } else if (e.type === 'run_started') { text = 'Team run started'; }
        else if (e.type === 'ticket_done') { text = 'Boss made the final call. Run finished.' }
        else if (e.type === 'ticket_resolved') { text = `Ticket marked resolved (${e.by})` }
        else if (e.type === 'human_decision') { text = `${e.by} ${e.decision === 'approve' ? 'approved' : 'rejected'} request #${e.request_id}` }
        else if (e.type === 'run_failed') { text = 'Run failed. See the audit trail.' }
        else text = e.type
        const to = kind === 'say' ? ` → ${agentLabel(String((e.args as { to_agent?: string })?.to_agent))}` : ''
        return (
          <li key={e.id} className={`ev ev-${kind} ag-${e.agent ?? 'desk'}`}>
            <time>{time(e.time)}</time>
            <span className="who">{e.agent ? who : 'Desk'}{to}</span>
            <span className="what">{text}</span>
          </li>
        )
      })}
      <li ref={end} aria-hidden className="feed-end" />
    </ol>
  )
}
