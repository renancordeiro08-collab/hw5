import type { AgentName, BoardEvent } from '../api'
import { AGENTS, agentLabel, describeStep, isRefusal } from '../agents'

type State = 'idle' | 'working' | 'done' | 'waiting'

interface Lane {
  state: State
  line: string
  steps: number
  said?: string // what they were asked / what they asked a teammate
  askedBy?: string
  refused: boolean
}

/** Live view: one card per agent with what it is doing right now. */
export function AgentLanes({ events, running }: { events: BoardEvent[]; running: boolean }) {
  const lanes = new Map<AgentName, Lane>(AGENTS.map(a => [a.name, { state: 'idle', line: 'standing by', steps: 0, refused: false }]))
  const open = new Map<string, AgentName>() // agent_run_id -> agent, still running

  for (const e of events) {
    if (!e.agent) continue
    const lane = lanes.get(e.agent)!
    if (e.type === 'agent_step') {
      if (e.step === 'started') {
        open.set(e.agent_run_id!, e.agent)
        lane.said = e.task
        lane.askedBy = e.chain && e.chain.length > 1 ? agentLabel(e.chain[e.chain.length - 2]) : 'Desk'
      }
      lane.state = 'working'
      lane.line = describeStep(e)
      lane.steps += e.step === 'tool_call' ? 1 : 0
      if (isRefusal(e)) lane.refused = true
      if (e.step === 'tool_call' && e.tool === 'delegate') lane.state = 'waiting'
      if (e.step === 'tool_result' && e.tool === 'delegate') lane.state = 'working'
    } else if (e.type === 'agent_run') {
      open.delete(e.agent_run_id!)
      if (![...open.values()].includes(e.agent)) {
        lane.state = 'done'
        lane.line = e.status === 'ok' ? 'reported back' : `stopped: ${e.status}`
      }
    }
  }

  return (
    <div className="lanes">
      {AGENTS.map(a => {
        const l = lanes.get(a.name)!
        const st: State = !running && l.state !== 'idle' ? 'done' : l.state
        return (
          <article key={a.name} className={`lane lane-${a.name} is-${st}`}>
            <header>
              <span className="glyph" aria-hidden>{a.glyph}</span>
              <div>
                <h4>{a.label}</h4>
                <p className="role">{a.role}</p>
              </div>
              <span className={`state state-${st}`}>{st === 'waiting' ? 'waiting on teammate' : st}</span>
            </header>
            <p className="now">
              {st === 'working' && <span className="pulse" aria-hidden />}
              {l.line}
            </p>
            {l.said && (
              <blockquote title={l.said}>
                <span className="from">{l.askedBy} →</span> {l.said}
              </blockquote>
            )}
            <footer>
              <span>{l.steps} tool call{l.steps === 1 ? '' : 's'}</span>
              {l.refused && <span className="guard">guardrail hit</span>}
            </footer>
          </article>
        )
      })}
    </div>
  )
}
