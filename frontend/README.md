# Campus Customs Ops Board (React + Vite + TypeScript)

The human dashboard for the agent team. It calls the FastAPI backend at `VITE_API_URL` (`.env.development` → `http://localhost:8000`).

```bash
npm install
npm run dev        # http://localhost:5173
```

- `src/App.tsx`: layout, polling, actions (run, approve, reject, resolve, reset)
- `src/api.ts`: typed client for the backend routes
- `src/components/`: `AgentLanes` (live agent cards), `ActivityFeed`, `AgentSummaries`, `Approvals`, `CashMeter`
- `src/index.css`: Miami Vice theme (see `../output/design.md`)

Open `/?ticket=101` to go straight to a ticket.
