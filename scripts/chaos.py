import asyncio
import random
import sys
import time
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestration.orchestrator import Orchestrator
from src.orchestration.time_controller import Deadline
from src.providers.mock_provider import MockProvider
from tests.conftest import MockRouter

async def run_execution(run_idx: int) -> dict:
    execution_id = f"chaos-{run_idx}-{uuid.uuid4().hex[:8]}"
    budget_minutes = 3
    budget_seconds = budget_minutes * 60
    
    # Fault injection configuration
    faults = ["rate_limit", "timeout", "malformed"]
    
    # Create providers with random faults
    providers = []
    for i in range(3):
        provider_name = f"mock-{chr(97+i)}" # mock-a, mock-b, mock-c
        fail_next = {}
        always_fail = {}
        
        # Randomly inject a fault
        if random.random() < 0.3:
            role = random.choice(["solver", "critic", "synthesize", "plan"])
            fault = random.choice(faults)
            
            # 50% chance of fail_next (transient) vs always_fail (permanent/provider down)
            if random.random() < 0.5:
                fail_next[role] = fault
            else:
                always_fail[role] = fault
                
        provider = MockProvider(
            provider_name=provider_name,
            fail_next=fail_next,
            always_fail=always_fail,
            latency_seconds=random.uniform(0.1, 0.5)
        )
        providers.append(provider)

    router = MockRouter(providers)
    
    orch = Orchestrator()
    orch.router = router
    
    deadline = Deadline(budget_seconds=budget_seconds)
    start_time = time.time()
    
    tasks_before = len([t for t in asyncio.all_tasks() if not t.done()])
    
    try:
        result = await orch.execute(
            execution_id=execution_id,
            question="What is the meaning of life?",
            time_budget_minutes=budget_minutes,
            deadline=deadline
        )
    except Exception as e:
        print(f"[{run_idx}] Unhandled exception: {e}")
        result = None

    end_time = time.time()
    elapsed = end_time - start_time
    
    # Let tasks settle
    await asyncio.sleep(0.1)
    
    return {
        "run_idx": run_idx,
        "elapsed": elapsed,
        "budget": budget_seconds,
        "margin": deadline.synth_reserve,
        "result": result,
    }

async def main():
    print("Starting Chaos Engineering Run: 30 Executions...")
    
    tasks = [run_execution(i) for i in range(30)]
    results = await asyncio.gather(*tasks)
    
    failures = 0
    bugs = 0
    
    for r in results:
        idx = r["run_idx"]
        res = r["result"]
        
        if res is None:
            print(f"[{idx}] CRASH: Execution completely crashed without returning ExecutionResult.")
            bugs += 1
            failures += 1
            continue
            
        status = res.status
        if status not in ("completed", "failed", "cancelled"):
            print(f"[{idx}] BUG: Invalid terminal state: {status}")
            bugs += 1
            
        max_allowed_time = r["budget"] + r["margin"] + 5.0 # buffer for sync execution overhead
        if r["elapsed"] > max_allowed_time:
            print(f"[{idx}] BUG: Deadline exceeded! Took {r['elapsed']:.2f}s, allowed: {max_allowed_time:.2f}s")
            bugs += 1
            
        if getattr(res, "total_tokens", -1) < 0:
            print(f"[{idx}] BUG: Quota counters invalid: {getattr(res, 'total_tokens', 'missing')}")
            bugs += 1
            
        if status == "failed":
            failures += 1
            
    await asyncio.sleep(0.5)
    remaining_tasks = [t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()]
    if remaining_tasks:
        print(f"BUG: GLOBAL TASK LEAK DETECTED! {len(remaining_tasks)} tasks leaked.")
        for t in remaining_tasks:
            print(f"  - {t.get_name()}: {t.get_coro()}")
        bugs += 1

    print("-" * 40)
    print(f"Total runs: 30")
    print(f"Failures (Graceful): {failures}")
    print(f"Bugs (Assertion Failures): {bugs}")
    
    if bugs > 0:
        sys.exit(1)
    else:
        print("All chaos assertions passed!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
