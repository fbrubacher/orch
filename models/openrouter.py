"""Thin, model-agnostic client for the OpenRouter chat-completions API.

OpenRouter is OpenAI-compatible, so every agent — regardless of the underlying
model — talks to the same endpoint with the same request/response shape. This
client knows nothing about planners, executors or reviewers; it only knows how
to send messages (optionally with tools) and hand back the assistant turn.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

logger = logging.getLogger("orch.openrouter")


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter cannot fulfil a request."""


@dataclass
class ChatResult:
    """A single assistant turn returned by the API."""

    message: dict[str, Any]
    finish_reason: str
    raw: dict[str, Any]

    @property
    def content(self) -> str:
        return self.message.get("content") or ""

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return self.message.get("tool_calls") or []


class OpenRouterClient:
    """Minimal HTTP client around ``POST /chat/completions``."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 180.0,
        max_retries: int = 4,
        app_url: Optional[str] = None,
        app_title: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise OpenRouterError(
                "OPENROUTER_API_KEY is not set. Export it or pass api_key explicitly."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.app_url = app_url or os.getenv("OPENROUTER_APP_URL")
        self.app_title = app_title or os.getenv("OPENROUTER_APP_TITLE")
        self._session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter uses these for attribution; both are optional.
        if self.app_url:
            headers["HTTP-Referer"] = self.app_url
        if self.app_title:
            headers["X-Title"] = self.app_title
        return headers

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
        response_format: Optional[dict[str, Any]] = None,
        extra_body: Optional[dict[str, Any]] = None,
    ) -> ChatResult:
        """Send a chat request and return the assistant turn.

        Retries transient failures (429 / 5xx / network errors) with capped
        exponential backoff. Raises :class:`OpenRouterError` on hard failures.
        """

        payload: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        if temperature is not None:
            payload["temperature"] = temperature
        if response_format is not None:
            payload["response_format"] = response_format
        if extra_body:
            payload.update(extra_body)

        url = f"{self.base_url}/chat/completions"
        last_error: Optional[str] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._session.post(
                    url,
                    headers=self._headers(),
                    data=json.dumps(payload),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:  # network-level failure
                last_error = f"network error: {exc}"
                self._sleep(attempt)
                continue

            if response.status_code == 200:
                return self._parse(response.json())

            # Retry on rate limiting and server errors.
            if response.status_code in (408, 409, 429) or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}: {response.text[:500]}"
                self._sleep(attempt, response)
                continue

            # Non-retryable client error.
            raise OpenRouterError(
                f"OpenRouter request failed (HTTP {response.status_code}): "
                f"{response.text[:1000]}"
            )

        raise OpenRouterError(
            f"OpenRouter request failed after {self.max_retries} attempts. "
            f"Last error: {last_error}"
        )

    @staticmethod
    def _parse(body: dict[str, Any]) -> ChatResult:
        try:
            choice = body["choices"][0]
        except (KeyError, IndexError) as exc:
            raise OpenRouterError(f"Unexpected response shape: {body}") from exc
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason") or ""
        return ChatResult(message=message, finish_reason=finish_reason, raw=body)

    def _sleep(self, attempt: int, response: Optional[requests.Response] = None) -> None:
        delay = min(2 ** (attempt - 1), 30)
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass
        logger.warning("Retrying OpenRouter request in %.1fs (attempt %d)", delay, attempt)
        time.sleep(delay)
