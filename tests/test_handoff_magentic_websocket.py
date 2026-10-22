#!/usr/bin/env python3
"""
WebSocket-based validation tests for Handoff and Magentic workflows.

Connects directly to the running server and validates workflows via WebSocket.

Run with: python tests/test_handoff_magentic_websocket.py
"""

import asyncio
import json
import sys
import urllib.request
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import websockets
except ImportError:
    print("ERROR: websockets module not found. Install with: python -m pip install websockets")
    sys.exit(1)

BASE = "127.0.0.1:8000"

# Sample inputs for testing
HANDOFF_SCENARIOS = {
    "customer_service_only": "I forgot my password and can't log in to my account",
    "technical_issue": "My API integration keeps crashing with error code 502 when trying to process payments",
    "technical_with_escalation": "We have a critical bug in our payment API that needs urgent management review for billing impact",
}

MAGENTIC_SCENARIOS = {
    "research_task": "Research the top 3 emerging trends in cloud AI infrastructure for 2025",
    "analysis_task": "Analyze the pros and cons of Agent Framework vs LangChain for enterprise applications",
    "complex_task": "Create a comprehensive migration strategy for moving a monolithic ERP system from on-premises to Azure with zero downtime",
}


def post_json(path: str, body: dict) -> dict:
    """POST JSON to server and return response."""
    try:
        req = urllib.request.Request(
            f"http://{BASE}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return json.load(urllib.request.urlopen(req))
    except Exception as e:
        print(f"ERROR: Failed to POST {path}: {e}")
        raise


async def test_workflow(workflow_id: str, test_name: str, topic: str, max_events: int = 100) -> dict:
    """Test a workflow via WebSocket."""
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"Workflow: {workflow_id}")
    print(f"Topic: {topic[:60]}...")
    print(f"{'='*70}")
    
    start_time = datetime.now()
    events = []
    event_types = []
    agent_messages = []
    
    try:
        # Start the workflow
        result = post_json(f"/api/workflows/{workflow_id}/start", {"input": topic})
        run_id = result["run_id"]
        print(f"[OK] Workflow started (run_id: {run_id})")
        
        # Connect via WebSocket
        uri = f"ws://{BASE}/ws/workflow/{workflow_id}/{run_id}"
        print(f"Connecting to {uri}...")
        
        async with websockets.connect(uri) as ws:
            event_num = 0
            while event_num < max_events:
                try:
                    # Wait for event with 120s timeout
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
                    event_num += 1
                    
                    event_type = msg.get("type", "unknown")
                    event_types.append(event_type)
                    events.append(msg)
                    
                    # Print event summary
                    content = msg.get("content") or msg.get("description") or msg.get("prompt")
                    if content:
                        content_preview = str(content)[:70].replace("\n", " ")
                        print(f"  [{event_num}] {event_type:20s} | {content_preview}...")
                    else:
                        print(f"  [{event_num}] {event_type:20s}")
                    
                    # Track agent messages
                    if event_type == "agent_message":
                        agent_messages.append(msg)
                    
                    # Exit on workflow complete or error
                    if event_type in ("workflow_complete", "error"):
                        print(f"\n[OK] Workflow ended with: {event_type}")
                        break
                        
                except asyncio.TimeoutError:
                    print(f"\n[FAIL] TIMEOUT: No event received for 120s")
                    break
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Validation
        success = True
        errors = []
        
        if len(events) == 0:
            success = False
            errors.append("No events received from WebSocket")
        
        if events and events[-1].get("type") != "workflow_complete":
            success = False
            errors.append(f"Workflow did not complete normally (ended with {events[-1].get('type')})")
        
        if len(agent_messages) == 0:
            success = False
            errors.append("No agent messages received")
        
        if duration > 300:  # 5 minutes is too long
            success = False
            errors.append(f"Test took too long ({duration:.1f}s), possible infinite loop")
        
        # Summary
        print(f"\n{'-'*70}")
        print(f"Results:")
        print(f"  Events received:    {len(events)}")
        print(f"  Agent messages:     {len(agent_messages)}")
        print(f"  Duration:           {duration:.1f}s")
        print(f"  Event types:        {', '.join(set(event_types))}")
        print(f"  Status:             {'[OK] PASS' if success else '[FAIL] FAIL'}")
        
        if errors:
            print(f"\nErrors:")
            for error in errors:
                print(f"  - {error}")
        
        return {
            "test": test_name,
            "workflow": workflow_id,
            "success": success,
            "events": len(events),
            "agent_messages": len(agent_messages),
            "duration": duration,
            "event_types": list(set(event_types)),
            "errors": errors
        }
        
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        print(f"\n[FAIL] EXCEPTION: {type(e).__name__}: {e}")
        return {
            "test": test_name,
            "workflow": workflow_id,
            "success": False,
            "events": len(events),
            "agent_messages": len(agent_messages),
            "duration": duration,
            "event_types": list(set(event_types)),
            "errors": [f"{type(e).__name__}: {str(e)[:100]}"]
        }


async def main():
    """Run all validation tests."""
    print("\n" + "="*70)
    print("HITL Dashboard: Handoff & Magentic Workflow Validation")
    print("="*70)
    
    # Check server connectivity
    print("\nChecking server connectivity...")
    try:
        with urllib.request.urlopen(f"http://{BASE}/health") as response:
            health = json.load(response)
        print(f"[OK] Server is healthy")
        print(f"  Config valid: {health.get('config_valid')}")
    except Exception as e:
        print(f"[ERROR] Server is not responding: {e}")
        return
    
    results = []
    
    # Test Handoff workflow
    print("\n" + "="*70)
    print("HANDOFF WORKFLOW TESTS")
    print("="*70)
    
    for test_id, (test_name, topic) in enumerate(HANDOFF_SCENARIOS.items(), 1):
        result = await test_workflow("handoff", f"Handoff-{test_id}: {test_name}", topic)
        results.append(result)
    
    # Test Magentic workflow
    print("\n" + "="*70)
    print("MAGENTIC WORKFLOW TESTS")
    print("="*70)
    
    for test_id, (test_name, topic) in enumerate(MAGENTIC_SCENARIOS.items(), 1):
        result = await test_workflow("magentic", f"Magentic-{test_id}: {test_name}", topic)
        results.append(result)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    
    for result in results:
        status = "[OK] PASS" if result["success"] else "[FAIL] FAIL"
        print(f"{status} | {result['test']:40s} | {result['events']:3d} events | {result['duration']:6.1f}s")
    
    print(f"\n{'-'*70}")
    print(f"OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        print("[OK] All validation tests PASSED!")
        return 0
    else:
        print(f"[FAIL] {total - passed} test(s) FAILED")
        print("\nFailed tests:")
        for result in results:
            if not result["success"]:
                print(f"\n  {result['test']}:")
                for error in result["errors"]:
                    print(f"    - {error}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


