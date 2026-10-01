#!/usr/bin/env python3
"""
Crew A2A Client — send structured tasks to another crew agent's A2A server.

Usage:
    CREW_A2A_SECRET=your-secret python a2a_client.py \\
        --to http://del-vm:8901 \\
        --from pax \\
        --action verify \\
        --params '{"target": "clients/campaign", "checks": ["build", "typecheck", "tests"]}' \\
        --callback http://pax-vm:8900/tasks

    # Check task status:
    python a2a_client.py --to http://del-vm:8901 --status task-abc123

    # Agent worker: poll for pending tasks:
    python a2a_client.py --to http://localhost:8901 --pending
"""

import argparse
import hashlib
import hmac
import json
import os
import urllib.request

SECRET = os.environ.get("CREW_A2A_SECRET", "change-me-in-production")


def sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def call(base: str, path: str, data: dict | None = None, method: str = "GET") -> dict:
    body = json.dumps(data).encode() if data is not None else b""
    req = urllib.request.Request(base.rstrip("/") + path, data=body or None, method=method)
    req.add_header("Content-Type", "application/json")
    if body:
        req.add_header("X-Crew-Sig", sign(body))
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="Base URL of the target agent's A2A server")
    ap.add_argument("--from", dest="from_nick", default="pax")
    ap.add_argument("--action", help="Task action (for new tasks)")
    ap.add_argument("--params", default="{}", help="JSON params for the task")
    ap.add_argument("--callback", default="", help="URL for status updates")
    ap.add_argument("--task-id", default="", help="Explicit task ID (auto-generated if empty)")
    ap.add_argument("--status", help="Check status of this task ID instead of sending")
    ap.add_argument("--pending", action="store_true", help="List pending tasks on the server")
    ap.add_argument("--group", help="Send a group chat message to all peers")
    ap.add_argument("--history", action="store_true", help="Show group chat history")
    ap.add_argument("--register-peer", nargs=2, metavar=("NICK", "URL"),
                    help="Register a peer agent (nick and base URL)")
    args = ap.parse_args()

    if args.pending:
        print(json.dumps(call(args.to, "/tasks/pending"), indent=2))
    elif args.history:
        print(json.dumps(call(args.to, "/group/history"), indent=2))
    elif args.group:
        result = call(args.to, "/group/send",
                      {"from": args.from_nick, "text": args.group}, method="POST")
        print(json.dumps(result, indent=2))
    elif args.register_peer:
        nick, url = args.register_peer
        result = call(args.to, "/peers/register",
                      {"nick": nick, "url": url}, method="POST")
        print(json.dumps(result, indent=2))
    elif args.status:
        print(json.dumps(call(args.to, f"/tasks/{args.status}"), indent=2))
    elif args.action:
        msg = {
            "from": args.from_nick,
            "action": args.action,
            "params": json.loads(args.params),
            "callback": args.callback,
        }
        if args.task_id:
            msg["task_id"] = args.task_id
        result = call(args.to, "/tasks", msg, method="POST")
        print(json.dumps(result, indent=2))
    else:
        ap.error("need --action (send), --status (check), --pending (list), --group (chat), --history, or --register-peer")


if __name__ == "__main__":
    main()
