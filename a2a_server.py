#!/usr/bin/env python3
"""
Crew A2A Server — receives structured tasks from other crew agents.

Usage:
    CREW_A2A_SECRET=your-secret python a2a_server.py --nick del --port 8901 \\
        --capabilities build,verify --callback http://pax-vm:8900/tasks

Each agent runs one. Tasks queue in memory; the agent's worker loop
(or a human) picks them up via GET /tasks/pending.
"""

import argparse
import hashlib
import hmac
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

SECRET = os.environ.get("CREW_A2A_SECRET", "change-me-in-production")
TASKS: dict = {}  # task_id -> task dict


def verify_sig(body: bytes, sig: str) -> bool:
    expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


class Handler(BaseHTTPRequestHandler):
    nick = "unknown"
    capabilities: list = []

    def _send(self, code: int, obj: dict):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth(self, body: bytes) -> bool:
        sig = self.headers.get("X-Crew-Sig", "")
        return verify_sig(body, sig)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"nick": self.nick, "capabilities": self.capabilities,
                             "pending": sum(1 for t in TASKS.values() if t["status"] == "pending")})
        elif parsed.path == "/tasks/pending":
            pending = [t for t in TASKS.values() if t["status"] == "pending"]
            self._send(200, {"tasks": pending})
        elif parsed.path.startswith("/tasks/"):
            tid = parsed.path.split("/")[2]
            task = TASKS.get(tid)
            if task:
                self._send(200, task)
            else:
                self._send(404, {"error": "not found"})
        else:
            self._send(404, {"error": "unknown path"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if not self._auth(body):
            self._send(401, {"error": "bad signature"})
            return

        try:
            msg = json.loads(body)
        except json.JSONDecodeError:
            self._send(400, {"error": "bad json"})
            return

        parsed = urlparse(self.path)
        if parsed.path == "/tasks":
            # New task submission.
            action = msg.get("action", "")
            tid = msg.get("task_id") or f"task-{uuid.uuid4().hex[:8]}"
            task = {
                "task_id": tid,
                "from": msg.get("from", "unknown"),
                "action": action,
                "params": msg.get("params", {}),
                "callback": msg.get("callback", ""),
                "status": "pending",
                "created_at": time.time(),
                "updates": [],
            }
            TASKS[tid] = task
            print(f"[{self.nick}] new task {tid}: {action} from {task['from']}", flush=True)
            self._send(202, {"task_id": tid, "status": "accepted"})
        elif parsed.path.startswith("/tasks/") and parsed.path.endswith("/update"):
            tid = parsed.path.split("/")[2]
            task = TASKS.get(tid)
            if not task:
                self._send(404, {"error": "not found"})
                return
            task["updates"].append({"at": time.time(), "text": msg.get("text", "")})
            if msg.get("status"):
                task["status"] = msg["status"]
            if msg.get("result") is not None:
                task["result"] = msg["result"]
            print(f"[{self.nick}] task {tid} -> {task['status']}", flush=True)
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "unknown path"})

    def log_message(self, *args):
        pass  # quiet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nick", required=True, help="Agent nick (del, milo, mute, pax)")
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--capabilities", default="", help="Comma-separated capability list")
    args = ap.parse_args()

    Handler.nick = args.nick
    Handler.capabilities = [c.strip() for c in args.capabilities.split(",") if c.strip()]

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Crew A2A server for '{args.nick}' on port {args.port}", flush=True)
    print(f"Capabilities: {Handler.capabilities}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
