# Research and citation provenance test contract

The offline regression matrix in `tests/test_research_provenance_e2e.py` verifies Assembly's source/citation plumbing at deterministic component boundaries:

- search success, empty-result fallback, and provider-error fallback;
- provider provenance (only the provider that returned accepted results is reported as used);
- untrusted page text remains inside sanitizer delimiters and cannot escape through an embedded delimiter;
- final citations are renumbered against the exact source pool supplied to the composer;
- dangling/out-of-range markers are neutralized, while retrieved-but-uncited sources are omitted;
- rendered source titles remain paired with their URLs.

These tests use in-memory provider fixtures and synthetic source records. They make no production network requests and need no API keys. They verify source identity, citation mapping, fallback behavior at the router boundary, and rendering structure only. They do **not** establish that a source is factually accurate, that a generated claim is true, or that a model correctly interpreted a source.

At runtime the orchestrator emits an explicit researcher status when the search result set is empty: `Web search returned nothing; no external sources were used.` The final composer independently emits `No external sources were used.` when it has no valid cited source.
