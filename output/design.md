# Design: Campus Customs Ops Board

These are the aesthetic preferences for the agent dashboard (`frontend/`) and the planning page (`output/desk_tickets.html`).

## Direction: "Miami Vice after dark"
It's a neon, retro-futurist control room for a small Yale shop at night: deep evening sky, cyan and hot-pink neon, a glowing grid on the horizon. It should feel **fun and expressive** while staying an **operations tool**. Numbers, statuses, and approval buttons are always the clearest things on screen.

**Mood words:** neon, nocturnal, confident, cinematic, calm-under-pressure.

## Color
| Token | Hex | Used for |
|---|---|---|
| `--bg` / `--bg2` | `#0b0620` / `#170b3b` | Deep indigo night background (vertical gradient) |
| `--cyan` | `#22e6ff` | Primary neon: section labels, cash balance, the Inventory agent |
| `--pink` | `#ff3ea5` | Secondary neon: selection, live state, the Customer Service agent, balance-drop flash |
| `--sun` | `#ffb347` | Sunset orange: the **Boss** and the final-call card |
| `--mint` | `#3cf2a5` | "Money is safe and good": Approve button, paid, resolved, the Accounting agent |
| `--violet` | `#a98bff` | The Facilities agent |
| `--warn` / `--bad` | `#ffcf5a` / `#ff5d7a` | Awaiting approval / blocked and guardrail refusals |
| `--ink` / `--muted` | `#f4eeff` / `#b3a5d9` | Body text / secondary text (both pass contrast on the dark panels) |

**Each agent owns one color**, used everywhere it appears: its card, its lines in the feed, and its summary. You can tell who's talking at a glance.

## Typography
- **Monoton** for the wordmark and the agent glyphs only. It's the retro neon-sign voice, so use it sparingly.
- **Space Grotesk** for everything people read: headings, body text, buttons.
- **JetBrains Mono** for data and labels: ticket ids, SKUs, timestamps, tool names, uppercase section eyebrows (with letter-spacing).
- Money is shown in **tabular numbers**, so the digits don't jump when the balance animates.

## Surfaces and layout
- Frosted dark panels (`rgba` indigo + `backdrop-filter: blur`), with a 1px cyan hairline border and 14–18px radii.
- A perspective neon grid fades in at the bottom of the screen, like a Miami horizon. It's decorative and never sits behind text.
- **Three columns:** ticket board (left) · selected ticket stage (center) · approvals queue + payments (right). It collapses to two columns, then one, on smaller screens. There's no horizontal scrolling, and the side gutter is 16px.
- **Hierarchy:**
  1. the checking balance (top right, large);
  2. the selected ticket and its Run button;
  3. the live agent cards;
  4. the feed;
  5. the summaries.

## Motion (purposeful, never noisy)
- An agent's card **lights up in its color** with a pulsing dot while it's working. It dims to "waiting on teammate" when it delegates.
- New feed items and approval cards **rise in** (300ms).
- After a payment, the **balance counts down** to its new value and flashes pink. You *see* money leave.
- A "LIVE" badge blinks while the team runs. The Run button shows a spinner.
- Everything respects `prefers-reduced-motion`.

## Voice and content
- Plain English over jargon: "checking stock & price (CC-TEE-WHITE S)", not raw function names. Raw tool names appear only as small chips in the summaries.
- What agents say to each other is shown as **quoted speech** in the feed ("Boss → Inventory: …").
- **Guardrail refusals are shown proudly in red** ("Tool refused: vendor will not ship…"). They prove the safety rules work.
- Drafts sit in **dashed pink "never sent" cards**. They look like paper on the desk, not sent mail.
- Money buttons are explicit: **"Approve & pay"**, with the approver's name required.

## Accessibility
- Every interactive element is a real `<button>` or `<input>`, with a visible cyan focus ring.
- Status is never shown by color alone. Every pill also has a text label (open, awaiting approval, blocked, resolved).
- Live regions announce the balance change and toasts.
