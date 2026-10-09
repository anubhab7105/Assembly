"""Key-leak scan: a sentinel secret must appear in no logs, DB rows, or responses."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import AgentRun, Execution
from src.orchestration.orchestrator import Orchestrator


def _string_values(obj: Any) -> list[str]:
    return [str(v) for v in vars(obj).values() if isinstance(v, str)]


async def test_fake_key_absent_from_logs_result_and_db(
    orchestrator: Orchestrator,
    db_session: Session,
    fake_key: str,
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", fake_key)
    events: list[dict[str, Any]] = []

    async def on_progress(event: dict[str, Any]) -> None:
        events.append(event)

    with caplog.at_level(logging.INFO, logger="assembly"):
        result = await orchestrator.execute(
            execution_id="test-exec-leak",
            question="What is the mock answer?",
            time_budget_minutes=3,
            on_progress=on_progress,
        )

    assert result.status == "completed"
    assert fake_key not in caplog.text

    # Response payload: answer, sources, and progress events carry no secret.
    assert fake_key not in result.answer
    assert fake_key not in str(result.sources)
    assert fake_key not in str(events)
    # Only provider/model names are recorded, never keys.
    assert set(result.providers_used) <= {"mock-a", "mock-b", "mock-c"}

    # Database rows written from the result carry no secret either.
    execution = Execution(
        question="What is the mock answer?",
        time_budget_minutes=3,
        status=result.status,
        final_answer=result.answer,
        final_sources=result.sources,
        consensus_score=result.consensus_score,
        total_tokens_used=result.total_tokens,
        agent_count=result.agent_count,
        debate_rounds=result.debate_rounds,
    )
    db_session.add(execution)
    db_session.flush()
    db_session.add(
        AgentRun(
            execution_id=execution.id,
            agent_type="solver",
            model="mock-model",
            provider="mock-a",
            input_tokens=10,
            output_tokens=20,
            confidence=0.9,
        )
    )
    db_session.commit()

    rows: list[Any] = []
    rows += db_session.query(Execution).all()
    rows += db_session.query(AgentRun).all()
    assert rows != []
    for row in rows:
        for value in _string_values(row):
            assert fake_key not in value
