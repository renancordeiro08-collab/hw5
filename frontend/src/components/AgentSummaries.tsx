import type { AgentName, BoardEvent, BossDecision } from '../api'
import { AGENTS } from '../agents'

/** After the run: one short line per agent about what it did, plus the Boss's final call. */
export function AgentSummaries({ events }: { events: BoardEvent[] }) {
  const runs = events.filter(e => e.type === 'agent_run')
  const done = [...events].reverse().find(e => e.type === 'ticket_done')
  const decision = (done?.decision ?? null) as BossDecision | null
  if (!runs.length) return null

  const byAgent = new Map<AgentName, BoardEvent[]>()
  runs.forEach(r => byAgent.set(r.agent!, [...(byAgent.get(r.agent!) ?? []), r]))

  return (
    <section className="summaries">
      {decision && (
        <div className="decision">
          <div className="decision-head">
            <h3>Boss's final call</h3>
            <span className={`pill pill-${decision.final_status}`}>{decision.final_status.replace('_', ' ')}</span>
          </div>
          <p>{decision.decision}</p>
          {decision.human_actions_needed.length > 0 && (
            <>
              <h5>Needs a human</h5>
              <ul>{decision.human_actions_needed.map((h, i) => <li key={i}>{h}</li>)}</ul>
            </>
          )}
          {done?.team_usage && (
            <p className="usage">gpt-6-luna · {done.team_usage.requests} model calls · {(done.team_usage.input_tokens + done.team_usage.output_tokens).toLocaleString()} tokens</p>
          )}
        </div>
      )}
      <div className="summary-grid">
        {AGENTS.filter(a => byAgent.has(a.name)).map(a => {
          const rs = byAgent.get(a.name)!
          const tools = [...new Set(rs.flatMap(r => r.tools ?? []))].filter(t => t !== 'delegate')
          return (
            <article key={a.name} className={`summary lane-${a.name}`}>
              <h4><span className="glyph sm" aria-hidden>{a.glyph}</span>{a.label}</h4>
              {rs.map(r => <p key={r.id}>{r.summary}</p>)}
              <div className="tools">{tools.map(t => <code key={t}>{t}</code>)}</div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
