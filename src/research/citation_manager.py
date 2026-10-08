"""
Assembly — Citation Manager

Tracks, deduplicates, ranks, and cross-verifies sources for the final
answer (PRD Section 11).

Dedupe: sources merge when their canonical URLs match (scheme case,
``www.``, default ports, fragments, and tracking query params are
ignored) or when their titles are near-identical (same normalized text,
or >=90% similar for titles of 20+ chars).

Credibility rule table (first match wins; suffix match covers
subdomains, e.g. ``docs.python.org`` matches ``python.org``):

- official: ``.gov`` / ``.gov.xx`` / ``.mil`` hosts, plus WHO, UN, EU bodies
- academic: ``.edu`` / ``.ac.xx`` hosts, plus known publishers/preprints
- reputable_media: hand-listed outlets with editorial standards
- vendor: hand-listed vendors, plus ``docs.`` / ``developer(s).`` /
  ``support.`` subdomains (official product documentation)
- community: wikis, Q&A, forums, code hosts, personal-blog suffixes
- unknown: everything else, including empty/unparseable URLs

The table is deliberately small and legible: edit the constants below
when the benchmark shows a ranking mistake. Rank order for output is
official > academic > reputable_media > vendor > community > unknown.

Cross-verification: a claim cited to sources on 2+ independent
(registrable) domains counts as verified. ``verified_claims()`` returns
the claim → verified map that ``ConsensusEngine._calculate_evidence_quality``
accepts as its ``verification`` input for a higher evidence_quality.
"""

import difflib
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

# ── Credibility rule table ──────────────────────────────────────────

OFFICIAL_DOMAINS: frozenset[str] = frozenset(
    {
        "who.int",
        "un.org",
        "unesco.org",
        "worldbank.org",
        "europa.eu",
        "oecd.org",
    }
)

ACADEMIC_DOMAINS: frozenset[str] = frozenset(
    {
        "arxiv.org",
        "semanticscholar.org",
        "nature.com",
        "science.org",
        "sciencemag.org",
        "ieee.org",
        "acm.org",
        "springer.com",
        "plos.org",
        "cell.com",
        "thelancet.com",
        "nejm.org",
        "jstor.org",
        "pubmed.ncbi.nlm.nih.gov",
    }
)

REPUTABLE_MEDIA_DOMAINS: frozenset[str] = frozenset(
    {
        "bbc.com",
        "bbc.co.uk",
        "reuters.com",
        "apnews.com",
        "nytimes.com",
        "washingtonpost.com",
        "theguardian.com",
        "economist.com",
        "ft.com",
        "wsj.com",
        "bloomberg.com",
        "npr.org",
        "pbs.org",
        "aljazeera.com",
    }
)

VENDOR_DOMAINS: frozenset[str] = frozenset(
    {
        "microsoft.com",
        "google.com",
        "apple.com",
        "amazon.com",
        "aws.amazon.com",
        "openai.com",
        "anthropic.com",
        "meta.com",
        "nvidia.com",
        "intel.com",
        "ibm.com",
        "oracle.com",
        "salesforce.com",
        "adobe.com",
        "cloudflare.com",
        "python.org",
    }
)

COMMUNITY_DOMAINS: frozenset[str] = frozenset(
    {
        "wikipedia.org",
        "reddit.com",
        "stackoverflow.com",
        "stackexchange.com",
        "medium.com",
        "github.com",
        "gitlab.com",
        "quora.com",
        "youtube.com",
        "discord.com",
        "news.ycombinator.com",
    }
)

#: Subdomains that mark official product documentation (vendor tier).
VENDOR_SUBDOMAINS: frozenset[str] = frozenset(
    {
        "docs",
        "developer",
        "developers",
        "support",
    }
)

#: Suffixes that mark personal/community blogs.
COMMUNITY_SUFFIXES: frozenset[str] = frozenset(
    {
        "wordpress.com",
        "blogspot.com",
        "medium.com",
        "substack.com",
    }
)

#: Higher number = more credible; used to rank final source lists.
CREDIBILITY_RANK: dict[str, int] = {
    "official": 5,
    "academic": 4,
    "reputable_media": 3,
    "vendor": 2,
    "community": 1,
    "unknown": 0,
}

#: Query params dropped during URL canonicalization (trackers, not content).
TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "gclsrc",
        "dclid",
        "msclkid",
        "mc_eid",
        "_hsenc",
        "_openstat",
        "yclid",
        "twclid",
        "igshid",
    }
)

#: Two-part public suffixes the registrable-domain heuristic must skip.
PUBLIC_SUFFIX_2: frozenset[str] = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "co.jp",
        "co.in",
        "com.br",
    }
)

#: Titles shorter than this need an exact normalized match to dedupe.
SHORT_TITLE_CHARS: int = 20

#: SequenceMatcher ratio at which long titles count as near-identical.
TITLE_SIMILARITY: float = 0.9


# ── URL / title normalization ───────────────────────────────────────


def host_of(url: str) -> str:
    """Lowercased hostname with a leading ``www.`` stripped ("" if none)."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    host = host.removeprefix("www.")
    return host


def canonical_url(url: str) -> str:
    """Canonical form used for dedupe ("" for empty/unparseable URLs).

    Normalizes scheme case, drops default ports and fragments, strips a
    leading ``www.``, removes tracking query params (remaining params are
    sorted), and drops a trailing slash. The path keeps its case.
    """
    text = (url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if not parts.hostname:
        return ""
    host = parts.hostname.lower()
    host = host.removeprefix("www.")
    port = parts.port
    if (parts.scheme == "http" and port == 80) or (
        parts.scheme == "https" and port == 443
    ):
        port = None
    netloc = host if port is None else f"{host}:{port}"
    kept = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in TRACKING_PARAMS
    )
    query = "&".join(f"{k}={v}" if v else k for k, v in kept)
    path = parts.path.rstrip("/") or ""
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def normalize_title(title: str) -> str:
    """Lowercased, de-punctuated, whitespace-collapsed title."""
    lowered = (title or "").lower()
    stripped = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(stripped.split())


def titles_match(first: str, second: str) -> bool:
    """Whether two titles count as near-identical for dedupe purposes."""
    left, right = normalize_title(first), normalize_title(second)
    if not left or not right:
        return False
    if left == right:
        return True
    if min(len(left), len(right)) < SHORT_TITLE_CHARS:
        return False
    ratio = difflib.SequenceMatcher(None, left, right).ratio()
    return ratio >= TITLE_SIMILARITY


def registrable_domain(host: str) -> str:
    """Heuristic eTLD+1 used to judge source independence.

    Takes the last two DNS labels, or three when the suffix is a known
    two-part public suffix (``co.uk`` and friends).
    """
    labels = (host or "").lower().strip(".").split(".")
    labels = [part for part in labels if part]
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in PUBLIC_SUFFIX_2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def classify_credibility(url: str) -> str:
    """Classify a URL into a credibility tier (rule table above)."""
    host = host_of(url)
    if not host:
        return "unknown"

    def _matches(domains: frozenset[str]) -> bool:
        return host in domains or any(host.endswith("." + domain) for domain in domains)

    if (
        host in OFFICIAL_DOMAINS
        or host.endswith((".gov", ".mil"))
        or re.search(r"\.gov\.[a-z]{2,}$", host) is not None
    ):
        return "official"
    if (
        host in ACADEMIC_DOMAINS
        or host.endswith(".edu")
        or re.search(r"\.ac\.[a-z]{2,}$", host) is not None
    ):
        return "academic"
    if _matches(REPUTABLE_MEDIA_DOMAINS):
        return "reputable_media"
    first_label = host.split(".")[0]
    if host in VENDOR_DOMAINS or _matches(VENDOR_DOMAINS):
        return "vendor"
    if first_label in VENDOR_SUBDOMAINS:
        return "vendor"
    if _matches(COMMUNITY_DOMAINS) or _matches(COMMUNITY_SUFFIXES):
        return "community"
    return "unknown"


# ── Manager ─────────────────────────────────────────────────────────


class CitationManager:
    """
    Manages sources and citations across an execution.

    Collects sources from multiple agents and research results,
    deduplicates by canonical URL and near-identical titles, ranks by
    credibility, tracks which claims cite which sources, and reports
    cross-verification for the consensus engine.
    """

    def __init__(self) -> None:
        self._sources: list[dict[str, str]] = []
        self._by_url: dict[str, dict[str, str]] = {}
        self._by_id: dict[str, dict[str, str]] = {}
        self._claims: dict[str, set[str]] = {}
        self._next_id: int = 1

    def add_source(
        self,
        title: str,
        url: str = "",
        snippet: str = "",
        source_id: str | None = None,
    ) -> str:
        """Add a source, merging canonical-URL and near-title duplicates.

        Returns the (new or existing) source id.
        """
        canonical = canonical_url(url)
        if canonical and canonical in self._by_url:
            return self._merge(self._by_url[canonical], title, snippet)
        for existing in self._sources:
            if titles_match(existing["title"], title):
                if canonical:
                    self._by_url[canonical] = existing
                return self._merge(existing, title, snippet)
        record_id = source_id or f"s{self._next_id}"
        if record_id in self._by_id:
            return record_id
        if source_id is None:
            self._next_id += 1
        host = host_of(url)
        record = {
            "id": record_id,
            "title": title,
            "url": url,
            "snippet": snippet,
            "domain": host,
            "credibility": classify_credibility(url),
        }
        self._sources.append(record)
        self._by_id[record_id] = record
        if canonical:
            self._by_url[canonical] = record
        return record_id

    def _merge(self, existing: dict[str, str], title: str, snippet: str) -> str:
        """Fold a duplicate into its record (fill blanks, keep the rest)."""
        if not existing["title"] and title:
            existing["title"] = title
        if not existing["snippet"] and snippet:
            existing["snippet"] = snippet
        return existing["id"]

    def add_sources(self, sources: list[dict[str, str]]) -> list[str]:
        """Add multiple sources, returning their ids in order."""
        return [
            self.add_source(
                title=s.get("title", ""),
                url=s.get("url", ""),
                snippet=s.get("snippet", ""),
                source_id=s.get("id"),
            )
            for s in sources
        ]

    def cite(self, claim: str, source_refs: list[str]) -> None:
        """Record that a claim cites the given sources.

        Refs may be source ids or URLs (resolved via canonicalization);
        unresolvable refs are kept so the claim's citation attempt is
        visible, but they never count as supporting sources.
        """
        refs = self._claims.setdefault(claim, set())
        for ref in source_refs:
            resolved = self._resolve(ref)
            refs.add(resolved if resolved is not None else ref)

    def _resolve(self, ref: str) -> str | None:
        """Resolve a source id or URL to a known source id (None if unknown)."""
        if ref in self._by_id:
            return ref
        canonical = canonical_url(ref)
        if canonical and canonical in self._by_url:
            return self._by_url[canonical]["id"]
        return None

    def sources_for_claim(self, claim: str) -> list[dict[str, str]]:
        """Ranked known sources cited by a claim."""
        ids = self._claims.get(claim, set())
        records = [self._by_id[sid] for sid in ids if sid in self._by_id]
        return self._rank(records)

    def claims_for_source(self, source_ref: str) -> list[str]:
        """All claims citing a source (by id or URL)."""
        resolved = self._resolve(source_ref)
        if resolved is None:
            return []
        return sorted(claim for claim, refs in self._claims.items() if resolved in refs)

    def get_used_sources(self) -> list[dict[str, str]]:
        """Ranked sources cited by at least one claim."""
        used_ids: set[str] = set()
        for refs in self._claims.values():
            used_ids.update(sid for sid in refs if sid in self._by_id)
        return self._rank([self._by_id[sid] for sid in used_ids])

    def get_final_sources(self, used_only: bool = True) -> list[dict[str, str]]:
        """Ranked final source list: cited sources, or all when asked."""
        if not used_only:
            return self._rank(list(self._sources))
        if not self._claims:
            return self._rank(list(self._sources))
        return self.get_used_sources()

    @staticmethod
    def _rank(records: list[dict[str, str]]) -> list[dict[str, str]]:
        """Sort by credibility rank (stable: ties keep insertion order)."""
        return sorted(
            records,
            key=lambda r: CREDIBILITY_RANK.get(r["credibility"], 0),
            reverse=True,
        )

    def verification_for(self, claim: str) -> dict[str, object]:
        """Cross-verification status of one claim.

        Verified when cited known sources span 2+ independent
        registrable domains.
        """
        records = self.sources_for_claim(claim)
        domains = sorted(
            {registrable_domain(r["domain"]) for r in records if r["domain"]}
        )
        return {
            "claim": claim,
            "verified": len(domains) >= 2,
            "domains": domains,
            "source_count": len(records),
        }

    def verified_claims(self) -> dict[str, bool]:
        """Claim → verified map; the consensus engine's verification input."""
        return {
            claim: bool(self.verification_for(claim)["verified"])
            for claim in self._claims
        }

    def cross_verified_ratio(self) -> float:
        """Share of cited claims backed by 2+ independent domains."""
        if not self._claims:
            return 0.0
        verified = sum(
            1 for claim in self._claims if self.verification_for(claim)["verified"]
        )
        return verified / len(self._claims)

    def clear(self) -> None:
        """Reset for a new execution."""
        self._sources.clear()
        self._by_url.clear()
        self._by_id.clear()
        self._claims.clear()
        self._next_id = 1
