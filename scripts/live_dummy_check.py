"""Live dummy-key check: preflight + streamed run must end in a terminal event.

Uses disposable dummy keys (never real credentials). Success = either a
real completed answer OR a failed run.finished with stage/error diagnostics
and an actionable message. Failure = stream closes with no run.finished
(the old indefinitely-forming-team symptom).
"""

import json
import sys

import httpx

BASE = "http://127.0.0.1:8001"
DUMMY_KEYS = {
    "groq": "DUMMY-KEY-NOT-REAL-groq-0000",
    "openrouter": "DUMMY-KEY-NOT-REAL-openrouter-0000",
}
QUESTION = "Dummy live check: will this run terminate with a clear outcome?"
TIMEOUT = 420.0


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        health = client.get("/health")
        print("health:", health.status_code, health.text[:120])

        pre = client.post(
            "/api/preflight",
            json={
                "question": QUESTION,
                "time_budget_minutes": 3,
                "provider_keys": DUMMY_KEYS,
                "model_selection": {"selected": [], "pins": {}},
                "usage_snapshot": [],
            },
        )
        print("preflight:", pre.status_code, pre.text[:300])

        finished = None
        counts: dict[str, int] = {}
        answer_len = 0
        with client.stream(
            "POST",
            "/api/run",
            json={
                "question": QUESTION,
                "time_budget_minutes": 3,
                "provider_keys": DUMMY_KEYS,
                "model_selection": {"selected": [], "pins": {}},
                "usage_snapshot": [],
            },
            timeout=httpx.Timeout(TIMEOUT, connect=30.0),
        ) as res:
            print("run status:", res.status_code)
            if res.status_code != 200:
                print("run body:", res.read().decode()[:500])
                return 2
            buf = ""
            for chunk in res.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    part, buf = buf.split("\n\n", 1)
                    for line in part.split("\n"):
                        if not line.startswith("data: "):
                            continue
                        evt = json.loads(line[len("data: ") :])
                        et = evt.get("event_type", "?")
                        counts[et] = counts.get(et, 0) + 1
                        if et == "execution.completed":
                            answer_len = len((evt.get("data") or {}).get("answer", ""))
                        if et == "run.finished":
                            finished = evt
                if finished is not None:
                    break

    print("event counts:", json.dumps(counts))
    if finished is None:
        print("RESULT: FAIL — stream closed with no run.finished")
        return 1
    print("run.finished:", json.dumps(finished)[:600])
    status = finished.get("status")
    if status == "completed" and answer_len > 0:
        print(f"RESULT: PASS — real answer ({answer_len} chars)")
        return 0
    if status in ("failed", "cancelled") and finished.get("message"):
        print(
            "RESULT: PASS — clear actionable failure "
            f"(stage={finished.get('stage')} code={finished.get('error_code')})"
        )
        return 0
    print("RESULT: FAIL — terminal event has no usable outcome")
    return 1


if __name__ == "__main__":
    sys.exit(main())
