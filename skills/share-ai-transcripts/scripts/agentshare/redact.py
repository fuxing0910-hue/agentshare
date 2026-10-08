"""Deterministic, best-effort text replacements; never a secrecy guarantee."""

import re
from collections import Counter


class Redactor:
    def __init__(self, terms=()):
        normalized = set()
        for term in terms:
            if not isinstance(term, str):
                raise ValueError("Custom terms must be strings.")
            term = term.strip()
            if term:
                if len(term) > 4096:
                    raise ValueError("A custom term exceeds 4,096 characters.")
                normalized.add(term)
                if len(normalized) > 1000:
                    raise ValueError("At most 1,000 custom terms are supported.")
        self.counts = Counter()
        self.custom = re.compile("|".join(re.escape(term) for term in sorted(normalized, key=lambda t: (-len(t), t)))) if normalized else None
        self.patterns = [
            ("private_key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
            ("assignment", re.compile(r"(?i)(\b(?:[a-z0-9_-]*(?:api[_-]?key|access[_-]?token|secret|password|passwd|token)[a-z0-9_-]*|authorization)\b[\"']?\s*[:=]\s*)(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;}\])]+)")),
            ("bearer", re.compile(r"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/=-]{4,}")),
            ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,})\b")),
            ("api_token", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}(?![A-Za-z0-9])")),
            ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
            ("email", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
            # In unquoted paths with spaces, err toward omitting the remainder of
            # the line rather than leaving a folder or username suffix behind.
            ("home_path", re.compile(r"(?i)(?:\b[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]|(?<![\w:])/(?:home|Users)/|(?<![\w:])/root(?:/|(?=$|[\s\"']))|(?<![\w])~[\\/])[^\r\n\"'<>|]*")),
        ]

    def _replace(self, category, match):
        self.counts[category] += 1
        marker = f"[REDACTED:{category}]"
        if category == "assignment":
            return match.group(1) + marker
        if category == "bearer":
            return "Bearer " + marker
        return marker

    def redact(self, text):
        for category, pattern in self.patterns:
            text = pattern.sub(lambda match, category=category: self._replace(category, match), text)
        # Do this last: replacing a literal such as "sk-" first could hide a
        # recognizable credential prefix and leave the credential tail behind.
        if self.custom:
            text = self.custom.sub(lambda match: self._replace("custom", match), text)
        return text
