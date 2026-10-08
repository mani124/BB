import logging
from typing import Optional
from fastapi import Request, HTTPException, status

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
        self.patterns = patterns or []

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pat in self.patterns:
                if pat and len(pat) > 4 and pat in record.msg:
                    record.msg = record.msg.replace(pat, "[REDACTED]")
        return True
