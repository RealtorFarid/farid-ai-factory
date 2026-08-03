# Propilot AI — web

The product surface. React 19 + Vite + TypeScript, no UI framework: the design
system is ~40 CSS custom properties in `src/styles/tokens.css`, and every
component reads from them, so the whole app re-themes from one file. Light and
dark are both first-class.

```bash
npm install
npm run dev          # http://localhost:5173, proxies /v1 to the API on :8000
```

Run the API alongside it (`make run` from the repo root) or the panels will
show their offline state — which is itself worth looking at.

## Screens

Every route is backed by a real endpoint. There are no placeholder pages.

| Route | Backed by |
|---|---|
| `/` Today | `GET /v1/workspace/dashboard` — one round trip for all six panels |
| `/chat` Ask Atlas | `POST /v1/agents/atlas/stream`, `POST /v1/runs/{id}/approvals` |
| `/leads` | `GET /v1/workspace/leads`, `/leads/summary` |
| `/inbox` | `GET /v1/workspace/email/summary` |
| `/calendar` | `GET /v1/workspace/calendar/summary` |
| `/activity` | `GET /v1/runs` — every run, tool call and approval |

## The approval gate

The reason this is an operating system and not a chat box.

1. You ask Atlas to do something consequential.
2. The backend pauses the run and emits `approval.required`.
3. The chat renders an approval card showing the exact tool and arguments.
4. Approve or deny. Only then does the action run.

`src/hooks/useChat.ts` owns that state machine. The transcript is a flat list
of entries — user, agent, approval, error — because an approval interleaves
with the agent's prose and is read in order.

## Layout

```
src/
  lib/
    types.ts      Mirrors the backend contracts by hand
    api.ts        Typed client; one `request` for all error handling
    sse.ts        SSE over fetch (EventSource cannot POST)
    format.ts     Dates, money, relative time
  hooks/
    useResource.ts  Async resource: data | error | loading | reload
    useChat.ts      Streaming, approvals, resume
  components/
    ui/           Card, Badge, Button, Skeleton, Async, states
    layout/       AppShell, Sidebar, icons
    panels/       Task, lead, email, calendar, suggestion lists
    chat/         Transcript, approval card, composer
  pages/          Today, Chat, Leads, Inbox, Calendar, Activity
```

`<Async>` renders the right state for a resource — skeleton, error with retry,
empty, or data — so pages stay declarative and no panel invents its own
loading behaviour. Skeletons mirror the real row layout, so nothing jumps when
data lands.

## Notes

- `src/lib/types.ts` is hand-maintained against the FastAPI schemas. Generating
  it from `/openapi.json` is a Phase 4 task; until then a contract change breaks
  the TypeScript build rather than the running UI.
- `useResource` is deliberately not a data-fetching library. Swapping in
  TanStack Query later touches one file.

## Gates

```bash
npm run typecheck    # tsc, strict + noUncheckedIndexedAccess
npm run lint         # eslint, zero warnings
npm run build
```

CI runs all three.
