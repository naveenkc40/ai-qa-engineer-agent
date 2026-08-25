"""Retry policy for synchronous Gemini API calls."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

from google.genai import errors

T = TypeVar("T")

TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4


def call_gemini_with_retry(
    operation: Callable[[], T],
    *,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> T:
    """Run a Gemini operation, retrying only explicitly transient API errors.

    The original exception from the final call is re-raised, with the total
    number of attempted calls attached for workflow reporting.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return operation()
        except errors.APIError as error:
            try:
                error.retry_attempts = attempt
            except (AttributeError, TypeError):
                pass
            if error.code not in TRANSIENT_STATUS_CODES or attempt == MAX_ATTEMPTS:
                raise
            base_delay = 2 ** (attempt - 1)
            sleep(jitter(base_delay * 0.8, base_delay * 1.2))


def retry_attempts(error: Exception) -> int:
    """Return attempted Gemini calls, or one call for a non-retried failure."""
    return int(getattr(error, "retry_attempts", 1))


def error_type(error: Exception) -> str:
    """Return a stable report label without changing the underlying error."""
    code = getattr(error, "code", None)
    labels = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        429: "rate_limited",
        500: "internal_server_error",
        502: "bad_gateway",
        503: "service_unavailable",
        504: "gateway_timeout",
    }
    if code in labels:
        return labels[code]
    name = type(error).__name__
    return "".join(
        ("_" + character.lower()) if character.isupper() else character
        for character in name
    ).lstrip("_")
