import logging
import re
from typing import Optional
from fastapi import Request, HTTPException, status

JWT_PATTERN = re.compile(r"eyJ[a-zA-Z0-9_\-\.]{15,}")

def sanitize_token(token: Optional[str]) -> str:
    """Mask token so only partial prefix and suffix show."""
    if not token:
        return ""
    if len(token) <= 8:
        return "***"
    return f"{token[:3]}...{token[-4:]}"

def get_dhan_credentials(request: Request) -> tuple[str, str]:
    """
    Extract zero-persistence Dhan credentials from request headers.
    Headers:
        X-Dhan-Client-Id: User Client ID
        X-Dhan-Access-Token: 24h JWT Access Token
    """
    client_id = request.headers.get("X-Dhan-Client-Id")
    access_token = request.headers.get("X-Dhan-Access-Token")
    
    if not client_id or not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Dhan authentication headers (X-Dhan-Client-Id, X-Dhan-Access-Token)"
        )
    return client_id.strip(), access_token.strip()

def get_optional_dhan_credentials(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extract credentials if provided; return (None, None) if missing."""
    client_id = request.headers.get("X-Dhan-Client-Id")
    access_token = request.headers.get("X-Dhan-Access-Token")
    return (client_id.strip() if client_id else None, access_token.strip() if access_token else None)

class RedactingFilter(logging.Filter):
    """Logging filter to mask sensitive Dhan tokens."""
    def __init__(self, patterns: list[str] | None = None):
        super().__init__()
        self.patterns = list(patterns) if patterns else []

    def _redact_text(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        for pat in self.patterns:
            if pat and len(pat) > 4 and pat in text:
                text = text.replace(pat, "[REDACTED]")
        return JWT_PATTERN.sub("[REDACTED]", text)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact_text(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                new_args = []
                for a in record.args:
                    if isinstance(a, str):
                        new_args.append(self._redact_text(a))
                    elif isinstance(a, dict):
                        new_args.append({k: (self._redact_text(v) if isinstance(v, str) else v) for k, v in a.items()})
                    else:
                        new_args.append(a)
                record.args = tuple(new_args)
            elif isinstance(record.args, dict):
                record.args = {k: (self._redact_text(v) if isinstance(v, str) else v) for k, v in record.args.items()}
        return True

def setup_security_logging() -> None:
    """Attach RedactingFilter to root logger and standard handlers."""
    root_logger = logging.getLogger()
    redacting_filter = RedactingFilter()
    root_logger.addFilter(redacting_filter)
    for handler in root_logger.handlers:
        handler.addFilter(redacting_filter)
