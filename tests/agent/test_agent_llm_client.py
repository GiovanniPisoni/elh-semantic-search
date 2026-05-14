"""Tests for :class:`elh_rag.agent.agent_llm_client.AgentLLMClient`."""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import pytest

from elh_rag.agent.agent_llm_client import AgentLLMClient, StreamChunk

# Fixtures


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch time.sleep so tenacity's exponential backoff is instant in tests.
    """
    monkeypatch.setattr("time.sleep", lambda *a, **kw: None)


@pytest.fixture
def mock_message() -> MagicMock:
    """A mocked Anthropic Message response with end_turn stop_reason."""
    response = MagicMock()
    response.content = [MagicMock(text="Hello!")]
    response.stop_reason = "end_turn"
    response.usage.input_tokens = 100
    response.usage.output_tokens = 20
    return response


# Helpers for constructing real SDK exception instances


def _rate_limit_error() -> anthropic.RateLimitError:
    return anthropic.RateLimitError(
        "rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(message="connection failed", request=MagicMock())


def _timeout_error() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=MagicMock())


def _bad_request_error() -> anthropic.BadRequestError:
    return anthropic.BadRequestError(
        "bad request",
        response=MagicMock(status_code=400),
        body=None,
    )


def _auth_error() -> anthropic.AuthenticationError:
    return anthropic.AuthenticationError(
        "auth failed",
        response=MagicMock(status_code=401),
        body=None,
    )


# 1. Initialization


class TestInitialization:
    def test_client_is_lazily_initialised(self) -> None:
        """The Anthropic SDK client is NOT created at __init__ time."""
        c = AgentLLMClient()
        assert c._client is None

    def test_settings_fallback_uses_config_defaults(self) -> None:
        """Constructor without args reads everything from settings."""
        from elh_rag.config import settings

        c = AgentLLMClient()
        assert c._model == settings.agent_llm_model
        assert c._max_tokens == settings.agent_llm_max_tokens
        assert c._temperature == settings.agent_llm_temperature
        assert c._max_retries == settings.agent_llm_max_retries

    def test_explicit_args_override_settings(self) -> None:
        """Constructor arguments win over settings defaults."""
        c = AgentLLMClient(
            model="custom-model",
            max_tokens=512,
            temperature=0.7,
            max_retries=5,
        )
        assert c._model == "custom-model"
        assert c._max_tokens == 512
        assert c._temperature == 0.7
        assert c._max_retries == 5

    def test_temperature_zero_is_respected(self) -> None:
        """temperature=0 must NOT fall back to settings (it's a valid value)."""
        c = AgentLLMClient(temperature=0.0)
        assert c._temperature == 0.0


# 2. call() — retry policy


class TestCallRetry:
    def test_call_succeeds_on_first_attempt(self, mock_message: MagicMock) -> None:
        """No retry needed when the SDK returns cleanly."""
        c = AgentLLMClient(max_retries=3)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = mock_message
        c._client = mock_anthropic

        result = c.call(messages=[], tools=[], system="sys")

        assert result is mock_message
        assert mock_anthropic.messages.create.call_count == 1

    def test_call_retries_on_rate_limit_then_succeeds(self, mock_message: MagicMock) -> None:
        """RateLimitError on attempt 1, success on attempt 2."""
        c = AgentLLMClient(max_retries=3)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.side_effect = [
            _rate_limit_error(),
            mock_message,
        ]
        c._client = mock_anthropic

        result = c.call(messages=[], tools=[], system="sys")

        assert result is mock_message
        assert mock_anthropic.messages.create.call_count == 2

    def test_call_retries_on_api_timeout_then_succeeds(self, mock_message: MagicMock) -> None:
        """APITimeoutError is retryable."""
        c = AgentLLMClient(max_retries=3)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.side_effect = [
            _timeout_error(),
            mock_message,
        ]
        c._client = mock_anthropic

        result = c.call(messages=[], tools=[], system="sys")

        assert result is mock_message
        assert mock_anthropic.messages.create.call_count == 2

    def test_call_retries_on_connection_error_then_succeeds(self, mock_message: MagicMock) -> None:
        """APIConnectionError is retryable."""
        c = AgentLLMClient(max_retries=3)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.side_effect = [
            _connection_error(),
            mock_message,
        ]
        c._client = mock_anthropic

        result = c.call(messages=[], tools=[], system="sys")

        assert result is mock_message
        assert mock_anthropic.messages.create.call_count == 2

    def test_call_does_not_retry_on_bad_request(self) -> None:
        """BadRequestError = our bug, propagate immediately."""
        c = AgentLLMClient(max_retries=3)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.side_effect = _bad_request_error()
        c._client = mock_anthropic

        with pytest.raises(anthropic.BadRequestError):
            c.call(messages=[], tools=[], system="sys")

        assert mock_anthropic.messages.create.call_count == 1

    def test_call_does_not_retry_on_auth_error(self) -> None:
        """AuthenticationError = config issue, propagate immediately."""
        c = AgentLLMClient(max_retries=3)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.side_effect = _auth_error()
        c._client = mock_anthropic

        with pytest.raises(anthropic.AuthenticationError):
            c.call(messages=[], tools=[], system="sys")

        assert mock_anthropic.messages.create.call_count == 1

    def test_call_gives_up_after_max_retries(self) -> None:
        """After N consecutive retryable failures, the last error propagates."""
        c = AgentLLMClient(max_retries=3)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.side_effect = _rate_limit_error()
        c._client = mock_anthropic

        with pytest.raises(anthropic.RateLimitError):
            c.call(messages=[], tools=[], system="sys")

        assert mock_anthropic.messages.create.call_count == 3


# 3. call() — argument propagation


class TestCallArgs:
    def test_call_passes_all_kwargs_to_sdk(self, mock_message: MagicMock) -> None:
        """model, max_tokens, temperature, system, messages, tools all forwarded."""
        c = AgentLLMClient(
            model="test-model",
            max_tokens=100,
            temperature=0.5,
            max_retries=1,
        )
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = mock_message
        c._client = mock_anthropic

        messages = [{"role": "user", "content": "hello"}]
        tools = [{"name": "tool1", "description": "...", "input_schema": {}}]

        c.call(messages=messages, tools=tools, system="custom-system")

        mock_anthropic.messages.create.assert_called_once_with(
            model="test-model",
            max_tokens=100,
            temperature=0.5,
            system="custom-system",
            messages=messages,
            tools=tools,
        )


# 4. stream() — end-to-end + retry


class TestStream:
    def test_stream_yields_text_deltas_then_final_message(self) -> None:
        """Happy path: 3 text deltas + 1 final_message chunk."""
        text_deltas = ["Hello", ", ", "world!"]
        final_message = MagicMock(stop_reason="end_turn")

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_stream
        mock_stream.__exit__.return_value = False
        mock_stream.text_stream = iter(text_deltas)
        mock_stream.get_final_message.return_value = final_message

        c = AgentLLMClient(max_retries=1)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.stream.return_value = mock_stream
        c._client = mock_anthropic

        chunks = list(c.stream(messages=[], tools=[], system="sys"))

        assert len(chunks) == 4
        assert all(isinstance(c, StreamChunk) for c in chunks)

        # First 3 chunks are text deltas
        assert chunks[0].text_delta == "Hello"
        assert chunks[1].text_delta == ", "
        assert chunks[2].text_delta == "world!"
        assert all(c.final_message is None for c in chunks[:3])

        # Last chunk is the final message
        assert chunks[3].text_delta is None
        assert chunks[3].final_message is final_message

    def test_stream_retries_on_rate_limit_during_open(self) -> None:
        """Retry policy Z: rate-limit on stream.open() triggers retry."""
        final_message = MagicMock()

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_stream
        mock_stream.__exit__.return_value = False
        mock_stream.text_stream = iter([])
        mock_stream.get_final_message.return_value = final_message

        c = AgentLLMClient(max_retries=3)
        mock_anthropic = MagicMock()
        mock_anthropic.messages.stream.side_effect = [
            _rate_limit_error(),  # first open fails
            mock_stream,  # second open succeeds
        ]
        c._client = mock_anthropic

        chunks = list(c.stream(messages=[], tools=[], system="sys"))

        # Open was attempted twice
        assert mock_anthropic.messages.stream.call_count == 2
        # Stream had no text deltas, only the final
        assert len(chunks) == 1
        assert chunks[0].final_message is final_message


# 5. StreamChunk dataclass


class TestStreamChunkDataclass:
    def test_default_all_fields_none(self) -> None:
        chunk = StreamChunk()
        assert chunk.text_delta is None
        assert chunk.tool_use is None
        assert chunk.final_message is None

    def test_text_delta_only(self) -> None:
        chunk = StreamChunk(text_delta="hello")
        assert chunk.text_delta == "hello"
        assert chunk.tool_use is None
        assert chunk.final_message is None

    def test_frozen(self) -> None:
        """StreamChunk is immutable (frozen dataclass with slots)."""
        chunk = StreamChunk(text_delta="hello")
        with pytest.raises((AttributeError, TypeError)):
            chunk.text_delta = "world"  # type: ignore[misc]
