# Crew A2A Protocol

Minimal agent-to-agent task protocol for the bannerlord-clone crew.
Supplements the relay bus (chat/heartbeats stay on the bus).

## Message format

All POST bodies are JSON with an `X-Crew-Sig` header:
HMAC-SHA256 of the raw body using `CREW_A2A_SECRET`.

## Endpoints

### `GET /health`
Returns `{nick, capabilities[], pending_count}`. No auth needed.

### `POST /tasks` — submit a task
```json
{
  "from": "pax",
  "action": "verify",
  "params": {"target": "clients/campaign", "checks": ["build"]},
  "callback": "http://pax-vm:8900/tasks",
  "task_id": "optional-custom-id"
}
```
Returns `202 {"task_id": "...", "status": "accepted"}`.

### `GET /tasks/pending` — agent worker polls this
Returns all tasks with `status == "pending"`.

### `GET /tasks/<id>` — check one task
Returns the full task including `updates[]` and `result`.

### `POST /tasks/<id>/update` — report progress
```json
{"status": "working|done|failed", "text": "build passed", "result": {...}}
```

## Task lifecycle

`pending` → `working` → `done` | `failed`

The agent's worker loop polls `/tasks/pending`, marks tasks `working`
when starting, and posts updates as it goes.

## Standard actions

| Action | Params | Used by |
|--------|--------|---------|
| `verify` | `{target, checks[]}` | pax → any lane |
| `build` | `{target}` | pax → Rowan |
| `review` | `{files[]}` | any → pax |
| `fetch` | `{dataset, region}` | pax → Hana |

Lanes can add their own; document them here.
