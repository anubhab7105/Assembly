"""
Assembly — Logging Configuration

Structured logging with execution-level context, plus a KeyMaskingFilter
that scrubs anything resembling an API key from every record that passes
through the assembly logger AND the root logger (so third-party HTTP/SDK
debug output is covered too).

What is masked:
- Authorization / x-api-key headers (whole header value, incl. Bearer).
- Values of fields named key/api_key/provider_keys/authorization/token/
  secret/password (JSON `"key": "v"`, `key=v`, `Key: v` shapes).
- Known provider prefixes (AIza, gsk_, csk-, sk-or-, xai-, hf_, tvly-, …).
- Long opaque tokens (40+ base64-ish chars: JWT segments, hex digests).

Deliberately NOT matched: `tokens_used`-style counters (the field pattern
requires `:`/`=` right after the name), UUIDs (36 chars < 40), model and
provider names. Traceback frames are code, not values — frame locals are
never printed by the default formatter, so exc_info is safe to keep.
"""

import json
import logging
import re
import sys

MASK = "***"

# Header values: the whole value goes, Bearer scheme included.
_HEADER_RES = (
    re.compile(r"(?i)(authorization\s*:\s*(?:bearer\s+)?)(\S+)"),
    re.compile(r"(?i)(x-api-key\s*:\s*)(\S+)"),
)

# Field values: "api_key": "v" / api_key=v / Api-Key: v
_FIELD_NAMES = (
    r"api[_-]?key|provider[_-]?keys?|authorization|x-api-key"
    r"|access[_-]?token|refresh[_-]?token|secret|password|bearer"
)
_FIELD_RE = re.compile(
    rf"(?i)(['\"]?(?:{_FIELD_NAMES})['\"]?\s*[:=]\s*)(['\"]?)([^\s'\",}}\]]+)"
)

# Field values that are inline dicts/lists: mask the whole container
# (single nesting level covers request-body echoes like
# provider_keys={'groq': '...'}). Applied before the scalar pattern.
_NESTED_RE = re.compile(
    rf"(?i)(['\"]?(?:{_FIELD_NAMES})['\"]?\s*[:=]\s*)(\{{[^}}]*\}}|\[[^\]]*\])"
)
_PREFIX_RE = re.compile(
    r"AIza[0-9A-Za-z\-_]{20,}"
    r"|gsk_[0-9A-Za-z]{10,}"
    r"|csk-[0-9A-Za-z\-_]{10,}"
    r"|sk-or-[0-9A-Za-z\-_]{10,}"
    r"|xai-[0-9A-Za-z]{10,}"
    r"|hf_[0-9A-Za-z]{10,}"
    r"|tvly-[0-9A-Za-z\-_]{10,}"
    r"|sk-[A-Za-z0-9\-_]{10,}"
)

# Long opaque blobs (JWT segments, hex digests). Floor of 40 keeps UUIDs
# (36 chars) and ordinary words untouched.
_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-+/=]{40,}\b")


def mask_text(text: str) -> str:
    """Scrub key-like material from a log line. Pure function."""
    if not isinstance(text, str):
        return text
    masked = text
    for pattern in _HEADER_RES:
        masked = pattern.sub(rf"\g<1>{MASK}", masked)
    masked = _NESTED_RE.sub(rf"\g<1>{MASK}", masked)
    masked = _FIELD_RE.sub(rf"\g<1>\g<2>{MASK}", masked)
    masked = _PREFIX_RE.sub(MASK, masked)
    masked = _LONG_TOKEN_RE.sub(MASK, masked)
    return masked


class KeyMaskingFilter(logging.Filter):
    """Logging filter that rewrites the rendered message, never drops it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — a broken format must not break logging
            return True
        record.msg = mask_text(message)
        record.args = None
        return True


def _attach_masking(target: logging.Logger) -> None:
    """Add the filter once (idempotent across reloads)."""
    if not getattr(target, "_assembly_masking_attached", False):
        target.addFilter(KeyMaskingFilter())
        target._assembly_masking_attached = True  # type: ignore[attr-defined]


# Third-party loggers whose HTTP/SDK debug output can carry credentials.
# (Logger filters only apply at the record's origin logger, so the root
# logger alone is not enough — each of these gets the filter directly.)
_THIRD_PARTY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "groq",
    "openai",
    "google",
    "googleapiclient",
    "huggingface_hub",
    "keyring",
)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the application logger."""

    logger = logging.getLogger("assembly")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Masking first: it must apply no matter how handlers are configured.
    _attach_masking(logger)
    _attach_masking(logging.getLogger())
    for name in _THIRD_PARTY_LOGGERS:
        _attach_masking(logging.getLogger(name))

    # Avoid duplicate handlers on reload
    if logger.handlers:
        return logger

    import os
    is_production = os.environ.get("APP_ENV", "development") == "production"

    if is_production:
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_record = {
                    "time": self.formatTime(record, self.datefmt),
                    "level": record.levelname,
                    "name": record.name,
                    "message": record.getMessage()
                }
                if record.exc_info:
                    log_record["exc_info"] = self.formatException(record.exc_info)
                return json.dumps(log_record)
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
            datefmt="%H:%M:%S",
        )

    # Force UTF-8 encoding on Windows to avoid cp1252 issues
    import io

    stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    console_handler = logging.StreamHandler(stream)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# ── Module-level logger ──────────────────────────────────────────────
logger = setup_logging()
