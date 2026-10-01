# Crew A2A — Agent-to-Agent Task Bus for the Bannerlord Clone Crew

Lightweight A2A (Agent-to-Agent) servers for structured task delegation between
crew agents. Supplements the relay bus (which stays for chat/heartbeats).

## Quick start

```bash
# On each crew VM:
pip install flask requests
python a2a_server.py --nick del --port 8901 --capabilities build,verify

# Send a task (from pax or any agent):
python a2a_client.py --to http://del-vm:8901 --action verify \
  --params '{"target": "clients/campaign", "checks": ["build", "typecheck"]}'
```

## How it works

- Each agent runs `a2a_server.py` with their nick and capabilities.
- Tasks are JSON with a unique ID, action, params, and reply-to.
- The server queues the task, the agent's worker picks it up.
- Status updates and results POST back to the requester's callback URL.
- All messages authenticated via shared secret (`CREW_A2A_SECRET` env var).

## Files

- `a2a_server.py` — the agent server (run one per crew VM)
- `a2a_client.py` — send tasks from any agent
- `protocol.md` — the message format spec
