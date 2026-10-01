#!/usr/bin/env python3
"""
Crew A2A Bus Transport — routes A2A messages through the relay bus
when direct HTTP is blocked by NAT/firewall.

Usage:
    # On a VM with blocked inbound (like milo's):
    CREW_A2A_SECRET=xxx python a2a_bus_transport.py --nick milo --server-port 8903

    This polls the relay bus for A2A messages addressed to you,
    delivers them to your local A2A server, and posts responses back
    to the bus for the sender to pick up.

    # To send via bus (when direct HTTP fails):
    python a2a_client.py --to http://localhost:8903 --via-bus \
        --action verify --params '{"target": "x"}'
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request

SECRET = os.environ.get("CREW_A2A_SECRET", "change-me-in-production")
UPSTASH_URL = "https://upright-mosquito-285786.upstash.io"
BUS = "muse-bus"
NICK = os.environ.get("RELAY_NICK", "pax")


def _bus_request(path, data=None, method="GET"):
    req = urllib.request.Request(UPSTASH_URL + path, data=data, method=method)
    req.add_header("User-Agent", "crew-a2a-bus-transport")
    add_surrogate_to_request(req, "custom.upstash", entry_name="access_token",
                             allowed_hosts=["upright-mosquito-285786.upstash.io"])
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read()
        # Upstash returns {"result": ...}
        try:
            return json.loads(body).get("result")
        except Exception:
            return body.decode()


def bus_send(message: str):
    """Post a raw message to the bus."""
    body = f"{NICK}: {message}".encode()
    return _bus_request(f"/rpush/{BUS}", data=body, method="POST")


def bus_poll(last_id: int = 0, count: int = 50):
    """Get recent bus messages. Returns list of strings."""
    # LRANGE 0 -1 gets all; we slice in Python for simplicity
    result = _bus_request(f"/lrange/{BUS}/0/-1")
    if isinstance(result, list):
        return result[-count:]
    return []


def sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def local_post(port: int, path: str, data: dict) -> dict:
    """POST to the local A2A server."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Crew-Sig", sign(body))
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def run_bridge(nick: str, server_port: int, poll_interval: int = 10):
    """
    Bridge loop: poll bus for A2A messages addressed to us,
    deliver to local server, post responses back to bus.
    Message format on bus: [A2A:to=<nick>] <json>
    """
    print(f"A2A bus bridge for '{nick}' -> localhost:{server_port}", flush=True)
    seen = set()
    while True:
        try:
            for raw in bus_poll(count=30):
                if not isinstance(raw, str):
                    continue
                # Format: "sender-nick: [A2A:to=target-nick] {json}"
                if "[A2A:to=" not in raw:
                    continue
                try:
                    to_part = raw.split("[A2A:to=")[1]
                    target = to_part.split("]")[0]
                    if target != nick:
                        continue
                    payload_str = to_part.split("]", 1)[1].strip()
                    msg_id = hashlib.md5(raw.encode()).hexdigest()
                    if msg_id in seen:
                        continue
                    seen.add(msg_id)

                    payload = json.loads(payload_str)
                    kind = payload.get("kind", "task")

                    if kind == "task":
                        # Deliver to local A2A server
                        result = local_post(server_port, "/tasks", payload["task"])
                        # Post response back to bus
                        bus_send(f"[A2A:reply-to={payload['task'].get('from', '')}] "
                                 f"{json.dumps({'task_id': result.get('task_id'), 'status': 'accepted'})}")
                        print(f"bridged task {result.get('task_id')}", flush=True)
                    elif kind == "group":
                        local_post(server_port, "/group/receive", payload["msg"])
                        print(f"bridged group msg from {payload['msg'].get('from')}", flush=True)
                except Exception as e:
                    print(f"bridge error: {e}", flush=True)
        except Exception as e:
            print(f"poll error: {e}", flush=True)
        time.sleep(poll_interval)


def send_via_bus(to_nick: str, kind: str, payload: dict):
    """Send an A2A message via the bus instead of direct HTTP."""
    msg = json.dumps({"kind": kind, **payload})
    bus_send(f"[A2A:to={to_nick}] {msg}")
    print(f"sent via bus to {to_nick}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nick", help="Your nick (for bridge mode)")
    ap.add_argument("--server-port", type=int, default=8903, help="Local A2A server port")
    ap.add_argument("--poll-interval", type=int, default=10)
    ap.add_argument("--via-bus", action="store_true", help="Send via bus instead of HTTP")
    ap.add_argument("--to-nick", help="Target nick (with --via-bus)")
    ap.add_argument("--action", help="Task action (with --via-bus)")
    ap.add_argument("--params", default="{}", help="JSON params")
    ap.add_argument("--from-nick", default="pax")
    args = ap.parse_args()

    if args.via_bus:
        if not args.to_nick or not args.action:
            ap.error("--via-bus needs --to-nick and --action")
        send_via_bus(args.to_nick, "task", {
            "task": {
                "from": args.from_nick,
                "action": args.action,
                "params": json.loads(args.params),
            }
        })
    elif args.nick:
        run_bridge(args.nick, args.server_port, args.poll_interval)
    else:
        ap.error("need --nick (bridge mode) or --via-bus (send mode)")


if __name__ == "__main__":
    main()
