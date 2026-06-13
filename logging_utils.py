"""Logging redaction helpers (PRIV-01).

Used by the API to strip sensitive substrings before anything reaches the
console, the FastAPI response, or a saved report. Tokens are the main
concern because callers can submit a `github_token` in the request body —
without redaction, a stray exception trace can leak it.

Keep this module dependency-free so it can be imported anywhere.
"""

from __future__ import annotations

import re

# Patterns ordered by specificity. Each replaces the secret-looking match
# with a fixed mask so logs/errors remain useful but never reveal the value.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # GitHub personal-access tokens (classic + fine-grained).
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "ghp_***REDACTED***"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "github_pat_***REDACTED***"),
    # Anthropic API keys.
    (re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b"), "sk-ant-***REDACTED***"),
    # Generic Authorization: Bearer ... headers.
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}=*"), "Bearer ***REDACTED***"),
    # Email addresses — keep the domain so debug info is still useful.
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b"),
     r"***@\1"),
    # Generic "secret-looking" key=value assignments in error strings.
    (re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[^\s'\"&]{8,}"),
     r"\1=***REDACTED***"),
]


def redact_sensitive(value: object) -> str:
    """Return *value* with secret-looking substrings masked.

    Accepts any type — non-strings are stringified first so this is safe to
    call on exceptions, dicts, request bodies, etc.
    """
    text = value if isinstance(value, str) else str(value)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
