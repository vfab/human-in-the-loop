"""Manual smoke test: run every workflow end-to-end through the running dashboard.

Start the server first (HITL Dashboard launch config), then:
    python tests/smoke_ws.py [workflow_id ...]

Approvals are answered "approve" and text inputs get a canned reply, so the approval and
concurrent/group_chat workflows send real emails when SMTP is configured.
"""

import asyncio
import json
import sys
import urllib.request

import websockets

BASE = "127.0.0.1:8000"
ALL = ["sequential", "concurrent", "group_chat", "approval", "game"]


def post(path: str, body: dict) -> None:
    req = urllib.request.Request(
        f"http://{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req).read()


async def run(workflow_id: str) -> None:
    req = urllib.request.Request(
        f"http://{BASE}/api/workflows/{workflow_id}/start",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    run_id = json.load(urllib.request.urlopen(req))["run_id"]
    print("==", workflow_id)
    steered = False
    try:
        async with websockets.connect(f"ws://{BASE}/ws/workflow/{workflow_id}/{run_id}") as ws:
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                text = msg.get("prompt") or msg.get("content")
                print(" <-", msg.get("type"), str(text)[:140].replace("\n", " "))
                kind = msg.get("type")
                if kind == "approval_required":
                    post(f"/api/workflows/{workflow_id}/approve",
                         {"run_id": run_id, "request_id": msg["request_id"], "approved": True})
                elif kind == "input_required":
                    # Feedback is requested again after each revision, so steer once, then approve
                    answer = "correct" if msg.get("options") else ("" if steered else "Keep it short.")
                    steered = True
                    print(" ->", answer)
                    post(f"/api/workflows/{workflow_id}/input",
                         {"run_id": run_id, "request_id": msg["request_id"], "input": answer})
                elif kind in ("workflow_complete", "error"):
                    break
    except Exception as exc:
        print(" end:", type(exc).__name__, str(exc)[:150])


async def main() -> None:
    for workflow_id in sys.argv[1:] or ALL:
        await run(workflow_id)


if __name__ == "__main__":
    asyncio.run(main())
