"""
Request context, request-ID generation, logging helpers, and error sanitization.
Provides zero-leak logging and correlation IDs for application services and routers.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from uuid import uuid4
from fastapi import Request

logger = logging.getLogger("smart_recycling")

PATH_REGEX = re.compile(r"(?:/[a-zA-Z0-9_\.\-]+){2,}")
SECRET_REGEX = re.compile(
    r"(api[-_]?key|secret|token|password|authorization)[\s:=]+['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?",
    re.IGNORECASE,
)


def get_request_id(request: Optional[Request] = None) -> str:
    """
    Extracts an incoming X-Request-ID header, or generates a cryptographically random UUID4.
    """
    if request:
        header_val = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
        if header_val and len(header_val.strip()) > 0:
            return header_val.strip()[:64]
    return str(uuid4())


def sanitize_message(message: str) -> str:
    """
    Sanitizes strings to ensure file paths, secrets, or internal stack traces are redacted.
    """
    if not message:
        return ""
    text = str(message)
    # Redact sensitive credentials/tokens
    text = SECRET_REGEX.sub(r"\1: [REDACTED]", text)
    # Redact local filesystem paths
    text = PATH_REGEX.sub("[FILE_PATH]", text)
    return text


def log_request_event(
    logger_instance: logging.Logger,
    level: int,
    message: str,
    request_id: Optional[str] = None,
    **extra_fields,
) -> None:
    """
    Emits a structured log line with correlated request ID and sanitized payload.
    """
    req_id = request_id or "[no-req-id]"
    sanitized = sanitize_message(message)
    sanitized_extras = {k: sanitize_message(str(v)) for k, v in extra_fields.items()}
    logger_instance.log(
        level,
        f"[{req_id}] {sanitized}",
        extra={"request_id": req_id, **sanitized_extras},
    )
