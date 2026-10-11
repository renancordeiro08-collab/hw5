import { useEffect, useRef, useState } from 'react'
import type { Cash } from '../api'

const money = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

/** The checking balance. It counts down and flashes pink when a payment lands. */
export function CashMeter({ cash }: { cash: Cash | null }) {
  const [shown, setShown] = useState<number | null>(null)
  const [flash, setFlash] = useState(false)
  const prev = useRef<number | null>(null)

  useEffect(() => {
    if (!cash) return
    const from = prev.current ?? cash.balance
    const to = cash.balance
    prev.current = to
    if (from === to) { setShown(to); return }
    setFlash(true)
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const start = performance.now(), dur = reduce ? 0 : 900
    let raf = 0
    const tick = (t: number) => {
      const k = dur ? Math.min(1, (t - start) / dur) : 1
      setShown(from + (to - from) * (1 - Math.pow(1 - k, 3)))
      if (k < 1) raf = requestAnimationFrame(tick)
      else setTimeout(() => setFlash(false), 900)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [cash])

  return (
    <div className={`cash ${flash ? 'flash' : ''}`} aria-live="polite">
      <div className="cash-label">Checking balance</div>
      <div className="cash-value">{shown === null ? '—' : money(shown)}</div>
      {cash && (
        <div className="cash-sub">
          <span>Pending approval <b>{money(cash.pending_approval_total)}</b></span>
          <span>Uncommitted <b>{money(cash.available_for_new_requests)}</b></span>
          <span>Desk date <b>{cash.date_today}</b></span>
        </div>
      )}
    </div>
  )
}
