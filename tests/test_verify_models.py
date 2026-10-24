"""Tests for scripts/verify_models.py — all offline via respx.

Every test uses a fake key and asserts it never appears in captured
output, logs, or report objects (AGENTS.md section 5 key-leak scan).
No test touches the network: respx intercepts all httpx calls, and the
conftest socket guard would fail anything that slipped through.
"""

from datetime import date, timedelta

import httpx
import pytest
import respx

from src.providers.config import ProviderSpec, provider_limits_issue

import scripts.verify_models as verify



def test_quota_metadata_requires_source_and_verification_date() -> None:
    spec = ProviderSpec.model_validate({
        "base": "openai-compatible",
        "url": "https://api.test-verify/v1",
        "enabled": True,
        "models": [{
            "id": "m1",
            "family": "gpt-oss",
            "roles": ["solver"],
            "limits": {"rpm": 30, "rpd": 1000, "tpm": 8000, "context_tokens": 8000},
        }],
    })
    assert "quota_source" in provider_limits_issue("testprov", spec)
    assert "quota_last_verified" in provider_limits_issue("testprov", spec)


def test_verified_quota_metadata_is_routable() -> None:
    spec = ProviderSpec.model_validate({
        "base": "openai-compatible",
        "url": "https://api.test-verify/v1",
        "enabled": True,
        "quota_source": "https://provider.example/limits",
        "quota_last_verified": date(2026, 10, 24),
        "models": [{
            "id": "m1",
            "family": "gpt-oss",
            "roles": ["solver"],
            "limits": {"rpm": 30, "rpd": 1000, "tpm": 8000, "context_tokens": 8000},
        }],
    })
    assert provider_limits_issue("testprov", spec, today=date(2026, 10, 24)) is None


def test_stale_metadata_is_unavailable_not_zero_or_unlimited() -> None:
    spec = ProviderSpec.model_validate({
        "base": "openai-compatible",
        "url": "https://api.test-verify/v1",
        "enabled": True,
        "quota_source": "https://provider.example/limits",
        "quota_last_verified": date(2026, 10, 9),
        "models": [{
            "id": "m1",
            "family": "gpt-oss",
            "roles": ["solver"],
            "limits": {"rpm": 30, "rpd": 1000, "tpm": 8000, "context_tokens": 8000},
        }],
    })
    assert "STALE" in provider_limits_issue("testprov", spec, today=date(2026, 10, 24))


def test_future_verification_date_is_invalid() -> None:
    spec = ProviderSpec.model_validate({
        "base": "openai-compatible",
        "url": "https://api.test-verify/v1",
        "enabled": True,
        "quota_source": "https://provider.example/limits",
        "quota_last_verified": date(2026, 10, 25),
        "models": [{
            "id": "m1",
            "family": "gpt-oss",
            "roles": ["solver"],
            "limits": {"rpm": 30, "rpd": 1000, "tpm": 8000, "context_tokens": 8000},
        }],
    })
    assert "future" in provider_limits_issue("testprov", spec, today=date(2026, 10, 24))


def test_disabled_provider_with_unknown_limits_is_not_routable_requirement() -> None:
    spec = ProviderSpec.model_validate({
        "base": "openai-compatible",
        "enabled": False,
        "models": [{
            "id": "m1",
            "family": "gpt-oss",
            "roles": ["solver"],
            "limits": {"rpm": None, "rpd": None, "tpm": None, "context_tokens": None},
        }],
    })
    assert provider_limits_issue("testprov", spec, today=date(2026, 10, 24)) is None


def _openai_spec() -> object:
    from src.providers.config import ProviderSpec

    return ProviderSpec.model_validate(
        {
            "base": "openai-compatible",
            "url": "https://api.test-verify/v1",
            "enabled": True,
            "models": [
                {"id": "kept-model", "family": "gpt-oss", "roles": ["solver"]},
                {"id": "gone-model", "family": "qwen", "roles": ["solver"]},
            ],
        }
    )


def test_ratelimit_filter_keeps_only_signals() -> None:
    headers = httpx.Headers(
        {
            "x-ratelimit-remaining": "9",
            "x-ratelimit-limit": "30",
            "retry-after": "2",
            "content-type": "application/json",
            "authorization": "Bearer SECRET",
        }
    )
    kept = verify._ratelimit_headers(headers)
    assert kept == {
        "x-ratelimit-remaining": "9",
        "x-ratelimit-limit": "30",
        "retry-after": "2",
    }


def test_classify_probe_errors() -> None:
    assert verify._classify_probe_error(200, "") is None
    assert (
        verify._classify_probe_error(403, "your plan does not allow this model")
        == "plan-not-allowed"
    )
    assert (
        verify._classify_probe_error(402, "insufficient credits, add billing")
        == "quota/payment-required"
    )
    assert (
        verify._classify_probe_error(404, "model does not exist") == "model-not-found"
    )
    assert verify._classify_probe_error(429, "slow down") == "rate-limited"
    assert verify._classify_probe_error(401, "invalid api key") == "auth-error"
    assert verify._classify_probe_error(500, "boom") == "http-500"


def test_snippet_masks_key_material(fake_key: str) -> None:
    out = verify._snippet(f"oops {fake_key} happened " * 50)
    assert fake_key not in out
    assert len(out) <= 300


@respx.mock
async def test_openai_list_reports_missing(monkeypatch, fake_key: str) -> None:
    monkeypatch.setattr(verify, "_resolve_key", lambda _pid: fake_key)
    respx.get("https://api.test-verify/v1/models").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "kept-model"}, {"id": "other-model"}]}
        )
    )
    # Probes must also be mocked: kept ok, gone is plan-blocked.
    respx.post("https://api.test-verify/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(
                200,
                headers={"x-ratelimit-remaining": "29"},
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {},
                },
            ),
            httpx.Response(
                403, text='{"error": {"message": "your plan does not allow qwen"}}'
            ),
        ]
    )
    verdict = await verify.verify_provider(
        "testprov",
        _openai_spec(),
        timeout=5.0,
        max_tokens=5,  # type: ignore[arg-type]
    )
    assert verdict.list_status == 200
    assert verdict.missing_ids == ["gone-model"]
    assert len(verdict.probes) == 2
    assert verdict.probes[0].ok is True
    assert verdict.probes[0].ratelimit_headers.get("x-ratelimit-remaining") == "29"
    assert verdict.probes[1].ok is False
    assert verdict.probes[1].error_kind == "plan-not-allowed"
    blob = verdict.model_dump_json()
    assert fake_key not in blob


@respx.mock
async def test_openai_probe_ok_carries_no_key(
    monkeypatch, fake_key: str, capsys, caplog
) -> None:
    import logging

    monkeypatch.setattr(verify, "_resolve_key", lambda _pid: fake_key)
    respx.get("https://api.test-verify/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "kept-model"}]})
    )
    respx.post("https://api.test-verify/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"x-ratelimit-limit": "100", "x-ratelimit-remaining": "99"},
            json={"choices": [{"message": {"content": "ok"}}], "usage": {}},
        )
    )
    from src.providers.config import ProviderSpec

    spec = ProviderSpec.model_validate(
        {
            "base": "openai-compatible",
            "url": "https://api.test-verify/v1",
            "enabled": True,
            "models": [{"id": "kept-model", "family": "gpt-oss", "roles": ["solver"]}],
        }
    )
    with caplog.at_level(logging.INFO, logger="assembly"):
        verdict = await verify.verify_provider(
            "testprov", spec, timeout=5.0, max_tokens=5
        )
        verify.print_verdict(verdict)
        code = verify.print_summary([verdict])
    assert code == 0
    out = capsys.readouterr().out
    assert "kept-model" in out and "HTTP 200" in out
    assert "x-ratelimit-remaining=99" in out
    assert fake_key not in out
    assert fake_key not in caplog.text


@respx.mock
async def test_gemini_list_and_probe(monkeypatch, fake_key: str) -> None:
    monkeypatch.setattr(verify, "_resolve_key", lambda _pid: fake_key)
    respx.get(verify.GEMINI_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "models/gemini-3.8-flash"}]},
        )
    )
    respx.post(verify.GEMINI_LIST_URL + "/gemini-3.8-flash:generateContent").mock(
        return_value=httpx.Response(200, json={"candidates": [{}]})
    )
    respx.post(verify.GEMINI_LIST_URL + "/gemini-retired:generateContent").mock(
        return_value=httpx.Response(
            404, text='{"error": {"message": "model not found"}}'
        )
    )
    from src.providers.config import ProviderSpec

    spec = ProviderSpec.model_validate(
        {
            "base": "google-genai",
            "enabled": True,
            "models": [
                {"id": "gemini-3.8-flash", "family": "gemini", "roles": ["solver"]},
                {"id": "gemini-retired", "family": "gemini", "roles": ["solver"]},
            ],
        }
    )
    verdict = await verify.verify_provider("gemini", spec, timeout=5.0, max_tokens=5)
    assert verdict.list_status == 200
    assert verdict.missing_ids == ["gemini-retired"]
    assert verdict.probes[0].ok is True
    assert verdict.probes[1].error_kind == "model-not-found"
    assert fake_key not in verdict.model_dump_json()


async def test_verify_skips_without_key(monkeypatch) -> None:
    monkeypatch.setattr(verify, "_resolve_key", lambda _pid: "")
    verdict = await verify.verify_provider(
        "testprov",
        _openai_spec(),
        timeout=5.0,
        max_tokens=5,  # type: ignore[arg-type]
    )
    assert verdict.key_present is False
    assert "no key" in verdict.skipped_reason
    assert verdict.probes == []


def test_unknown_provider_arg_exits_2(capsys) -> None:
    code = verify.main(["--provider", "definitely-not-a-provider"])
    assert code == 2
    assert "unknown provider" in capsys.readouterr().out


def test_limit_headers_keep_only_limits() -> None:
    headers = {
        "x-ratelimit-limit-requests": "30",
        "x-ratelimit-remaining-requests": "29",
        "x-ratelimit-reset-requests": "60",
        "retry-after": "2",
        "content-type": "application/json",
    }
    kept = verify._limit_headers(headers)
    assert kept == {"x-ratelimit-limit-requests": "30"}


def test_save_report_writes_only_limits(tmp_path, fake_key: str) -> None:
    verdict = verify.ProviderVerdict(
        provider="testprov",
        base="openai-compatible",
        enabled=True,
        key_present=True,
        catalog_ids=["m1", "m2"],
        listed_ids=["m1"],
        missing_ids=["m2"],
        list_status=200,
        probes=[
            verify.TinyProbe(
                provider="testprov",
                model="m1",
                http_status=200,
                ok=True,
                ratelimit_headers={
                    "x-ratelimit-limit-requests": "30",
                    "x-ratelimit-remaining-requests": "29",
                    "x-ratelimit-reset-requests": "60",
                },
            ),
            verify.TinyProbe(
                provider="testprov",
                model="m2",
                http_status=403,
                ok=False,
                ratelimit_headers={"x-ratelimit-limit-tokens": "1000"},
                error_kind="plan-not-allowed",
                error_snippet=f"blocked {fake_key}",
            ),
        ],
    )
    out = tmp_path / "sub" / "verify_report.md"
    saved = verify.save_report([verdict], out)
    assert saved == out
    text = out.read_text(encoding="utf-8")
    assert "`m1`" in text and "200" in text and "plan-not-allowed" in text
    assert "x-ratelimit-limit-requests=30" in text
    assert fake_key not in text
    assert "remaining-requests" not in text  # usage counters excluded
    assert "reset-requests" not in text
    assert "retry-after" not in text.lower()


def test_main_save_flag_writes_report(monkeypatch, tmp_path, capsys) -> None:
    verdict = verify.ProviderVerdict(
        provider="testprov",
        base="openai-compatible",
        enabled=True,
        key_present=True,
        catalog_ids=["m1"],
        listed_ids=["m1"],
        list_status=200,
        probes=[
            verify.TinyProbe(
                provider="testprov",
                model="m1",
                http_status=200,
                ok=True,
                ratelimit_headers={"x-ratelimit-limit-requests": "30"},
            )
        ],
    )

    async def _stub(
        config: object,
        only: object,
        include_disabled: object,
        timeout: object,
        max_tokens: object,
    ) -> list:
        return [verdict]

    monkeypatch.setattr(verify, "verify_all", _stub)
    target = tmp_path / "verify_report.md"
    code = verify.main(["--save", str(target)])
    assert code == 0
    assert target.is_file()
    assert "x-ratelimit-limit-requests=30" in target.read_text(encoding="utf-8")
    assert "Saved limit-headers report" in capsys.readouterr().out
