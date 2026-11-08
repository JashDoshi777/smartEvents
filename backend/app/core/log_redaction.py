"""Secret redaction for log lines / exception messages (API keys in query strings)."""
import re

_PAT = re.compile(r"(?i)((?:api[_-]?key|apikey|key|token|access_token|client_secret|secret)=)[^&\s'\"]+")


def redact(value):
    return _PAT.sub(r"\1REDACTED", value) if isinstance(value, str) else value


def redact_processor(logger, method_name, event_dict):
    """structlog processor: scrub every string value."""
    return {k: redact(v) if isinstance(v, str) else v for k, v in event_dict.items()}
