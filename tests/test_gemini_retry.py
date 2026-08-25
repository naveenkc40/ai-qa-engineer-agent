from unittest.mock import Mock

import pytest
from google.genai.errors import ClientError, ServerError

from agents.gemini_retry import call_gemini_with_retry


def api_error(code):
    error_class = ClientError if code < 500 else ServerError
    return error_class(code, {"error": {"code": code, "status": "TEST", "message": "failure"}})


@pytest.mark.parametrize("code", [503, 429])
def test_transient_error_then_success(code):
    operation = Mock(side_effect=[api_error(code), "success"])
    sleep = Mock()

    assert call_gemini_with_retry(operation, sleep=sleep, jitter=lambda low, high: (low + high) / 2) == "success"
    assert operation.call_count == 2
    sleep.assert_called_once_with(1.0)


def test_repeated_503_preserves_final_exception():
    failures = [api_error(503) for _ in range(4)]
    operation = Mock(side_effect=failures)

    with pytest.raises(ServerError) as caught:
        call_gemini_with_retry(operation, sleep=lambda _: None)

    assert caught.value is failures[-1]
    assert caught.value.retry_attempts == 4
    assert operation.call_count == 4


def test_401_is_not_retried():
    failure = api_error(401)
    operation = Mock(side_effect=failure)

    with pytest.raises(ClientError) as caught:
        call_gemini_with_retry(operation, sleep=lambda _: None)

    assert caught.value is failure
    assert caught.value.retry_attempts == 1
    operation.assert_called_once_with()
