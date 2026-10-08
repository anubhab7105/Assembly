"""Citation manager tests: dedupe, credibility ranking, cross-verification.

Pure offline unit tests (no providers, no network): URL/title
normalization, the documented credibility rule table, claim→source
tracking, and the verification input consumed by the consensus engine.
"""

from src.agents.base_agent import AgentOutput
from src.orchestration.consensus import ConsensusEngine
from src.research.citation_manager import (
    CitationManager,
    canonical_url,
    classify_credibility,
    normalize_title,
    registrable_domain,
    titles_match,
)


def _manager() -> CitationManager:
    return CitationManager()


# ── Canonical URLs ──────────────────────────────────────────────────


def test_canonical_url_drops_noise() -> None:
    assert (
        canonical_url("https://www.Example.com:443/Path/?utm_source=x&b=2#frag")
        == "https://example.com/Path?b=2"
    )
    assert canonical_url("http://example.com:80/a/") == "http://example.com/a"
    assert canonical_url("") == ""
    assert canonical_url("http:///no-host") == ""


def test_url_variants_dedupe_to_one_source() -> None:
    manager = _manager()
    first = manager.add_source("T", "https://example.com/page?utm_source=news")
    second = manager.add_source("T", "http://www.example.com/page#section")
    assert first == second
    assert len(manager.get_final_sources(used_only=False)) == 1


def test_distinct_query_params_stay_distinct() -> None:
    manager = _manager()
    manager.add_source("A", "https://example.com/p?id=1")
    manager.add_source("B", "https://example.com/p?id=2")
    assert len(manager.get_final_sources(used_only=False)) == 2


# ── Near-identical titles ───────────────────────────────────────────


def test_normalize_title() -> None:
    assert normalize_title("  Hello,  WORLD! ") == "hello world"


def test_titles_match_rules() -> None:
    assert titles_match("Hello World", "hello, world!") is True
    assert titles_match("short", "shorter") is False
    assert titles_match("", "anything") is False
    long_a = "the quick brown fox jumps over the lazy dog near the river"
    long_b = "the quick brown fox jumps over the lazy dog near the lake"
    assert titles_match(long_a, long_b) is True
    assert titles_match(long_a, "completely unrelated headline here") is False


def test_empty_url_sources_dedupe_by_title() -> None:
    manager = _manager()
    first = manager.add_source("Hello World!")
    second = manager.add_source("hello world")
    assert first == second
    assert len(manager.get_final_sources(used_only=False)) == 1


# ── Credibility ranking ─────────────────────────────────────────────


def test_classify_all_tiers() -> None:
    assert classify_credibility("https://www.whitehouse.gov/briefing") == "official"
    assert classify_credibility("https://army.mil/news") == "official"
    assert classify_credibility("https://www.who.int/emergencies") == "official"
    assert classify_credibility("https://mit.edu/research") == "academic"
    assert classify_credibility("https://arxiv.org/abs/2301.1") == "academic"
    assert classify_credibility("https://cs.ox.ac.uk/paper") == "academic"
    assert classify_credibility("https://www.bbc.co.uk/news") == "reputable_media"
    assert classify_credibility("https://reuters.com/world") == "reputable_media"
    assert classify_credibility("https://openai.com/research") == "vendor"
    assert classify_credibility("https://docs.python.org/3/") == "vendor"
    assert classify_credibility("https://developer.mozilla.org/en") == "vendor"
    assert classify_credibility("https://en.wikipedia.org/wiki/X") == "community"
    assert classify_credibility("https://stackoverflow.com/q/1") == "community"
    assert classify_credibility("https://myblog.wordpress.com/post") == "community"
    assert classify_credibility("https://random-blog.example/x") == "unknown"
    assert classify_credibility("") == "unknown"


def test_final_sources_ranked_by_credibility() -> None:
    manager = _manager()
    manager.add_source("community", "https://reddit.com/r/x")
    manager.add_source("unknown", "https://random.example/x")
    manager.add_source("vendor", "https://openai.com/research")
    manager.add_source("media", "https://reuters.com/world")
    manager.add_source("academic", "https://arxiv.org/abs/1")
    manager.add_source("official", "https://whitehouse.gov/briefing")
    tiers = [s["credibility"] for s in manager.get_final_sources(used_only=False)]
    assert tiers == [
        "official",
        "academic",
        "reputable_media",
        "vendor",
        "community",
        "unknown",
    ]


def test_source_record_carries_domain_and_tier() -> None:
    manager = _manager()
    manager.add_source("T", "https://WWW.NYTIMES.COM/article")
    (record,) = manager.get_final_sources(used_only=False)
    assert record["domain"] == "nytimes.com"
    assert record["credibility"] == "reputable_media"


# ── Claim tracking ──────────────────────────────────────────────────


def test_cite_tracks_claims_and_used_sources() -> None:
    manager = _manager()
    cited = manager.add_source("Cited", "https://reuters.com/a")
    manager.add_source("Uncited", "https://random.example/b")
    manager.cite("water boils at 100C", [cited])
    used = manager.get_used_sources()
    assert [s["id"] for s in used] == [cited]
    assert manager.sources_for_claim("water boils at 100C")[0]["id"] == cited
    assert manager.claims_for_source(cited) == ["water boils at 100C"]
    assert manager.claims_for_source("https://reuters.com/a") == ["water boils at 100C"]


def test_used_only_flag() -> None:
    manager = _manager()
    manager.add_source("A", "https://a.example/1")
    manager.add_source("B", "https://b.example/2")
    assert len(manager.get_final_sources(used_only=False)) == 2
    # No claims yet: legacy behavior returns everything.
    assert len(manager.get_final_sources(used_only=True)) == 2
    manager.cite("claim", ["https://a.example/1"])
    assert [s["title"] for s in manager.get_final_sources(used_only=True)] == ["A"]


def test_add_sources_returns_ids_and_honors_explicit_id() -> None:
    manager = _manager()
    ids = manager.add_sources(
        [
            {"id": "custom", "title": "A", "url": "https://a.example/1"},
            {"title": "B", "url": "https://b.example/2"},
        ]
    )
    assert ids == ["custom", "s1"]
    assert manager.add_source("A again", "https://a.example/1") == "custom"


def test_clear_resets_everything() -> None:
    manager = _manager()
    sid = manager.add_source("A", "https://a.example/1")
    manager.cite("claim", [sid])
    manager.clear()
    assert manager.get_final_sources(used_only=False) == []
    assert manager.get_used_sources() == []
    assert manager.verified_claims() == {}
    assert manager.cross_verified_ratio() == 0.0


# ── Cross-verification ──────────────────────────────────────────────


def test_registrable_domain() -> None:
    assert registrable_domain("docs.python.org") == "python.org"
    assert registrable_domain("www.bbc.co.uk") == "bbc.co.uk"
    assert registrable_domain("example.com") == "example.com"


def test_single_domain_claim_is_not_verified() -> None:
    manager = _manager()
    manager.add_source("A1", "https://reuters.com/a")
    manager.add_source("A2", "https://www.reuters.com/b")
    manager.cite("claim", ["https://reuters.com/a", "https://www.reuters.com/b"])
    status = manager.verification_for("claim")
    assert status["verified"] is False
    assert status["domains"] == ["reuters.com"]


def test_two_independent_domains_verify_a_claim() -> None:
    manager = _manager()
    manager.add_source("A", "https://reuters.com/a")
    manager.add_source("B", "https://apnews.com/b")
    manager.add_source("C", "https://random.example/c")
    manager.cite("verified claim", ["https://reuters.com/a", "https://apnews.com/b"])
    manager.cite("lone claim", ["https://random.example/c"])
    assert manager.verification_for("verified claim")["verified"] is True
    assert manager.verification_for("lone claim")["verified"] is False
    assert manager.verified_claims() == {
        "verified claim": True,
        "lone claim": False,
    }
    assert manager.cross_verified_ratio() == 0.5


def test_same_org_subdomains_are_not_independent() -> None:
    manager = _manager()
    manager.add_source("A", "https://docs.python.org/3/")
    manager.add_source("B", "https://python.org/about/")
    manager.cite("claim", ["https://docs.python.org/3/", "https://python.org/about/"])
    assert manager.verification_for("claim")["verified"] is False


# ── Consensus input ─────────────────────────────────────────────────


def _agent_output(agent_id: str, claim: str) -> AgentOutput:
    return AgentOutput(
        agent_id=agent_id,
        agent_type="solver",
        position="The answer is 42.",
        reasoning_summary="summary",
        confidence=0.8,
        evidence=[{"claim": claim, "source_id": ""}],
        supports=[],
        disagrees_with=[],
        remaining_uncertainty=[],
        sources=[],
        provider="mock",
        model="mock-model",
        family=f"fam-{agent_id}",
        tokens_used=10,
        latency_ms=5.0,
    )


def test_verified_claim_raises_evidence_quality() -> None:
    engine = ConsensusEngine()
    outputs = [_agent_output("agent_01", "water boils at 100C")]
    plain = engine.evaluate(list(outputs), 1).factors["evidence_quality"]
    verified = engine.evaluate(
        list(outputs), 1, verification={"water boils at 100C": True}
    ).factors["evidence_quality"]
    assert verified > plain


def test_unverified_map_leaves_score_unchanged() -> None:
    engine = ConsensusEngine()
    outputs = [_agent_output("agent_01", "water boils at 100C")]
    plain = engine.evaluate(list(outputs), 1).factors["evidence_quality"]
    same = engine.evaluate(
        list(outputs), 1, verification={"water boils at 100C": False}
    ).factors["evidence_quality"]
    assert same == plain


def test_end_to_end_manager_to_consensus() -> None:
    manager = _manager()
    manager.add_source("A", "https://reuters.com/a")
    manager.add_source("B", "https://apnews.com/b")
    manager.cite(
        "water boils at 100C", ["https://reuters.com/a", "https://apnews.com/b"]
    )
    engine = ConsensusEngine()
    outputs = [_agent_output("agent_01", "water boils at 100C")]
    plain = engine.evaluate(list(outputs), 1).factors["evidence_quality"]
    boosted = engine.evaluate(
        list(outputs), 1, verification=manager.verified_claims()
    ).factors["evidence_quality"]
    assert boosted > plain
