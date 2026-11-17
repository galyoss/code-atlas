"""Model completions for code review."""

from __future__ import annotations

import asyncio
import os
from typing import Protocol

import httpx

_OPENAI_BASE_URL = "https://api.openai.com/v1"
_TIMEOUT_SECONDS = 60.0


class ModelError(Exception):
    """A model failure with a reason safe to expose on a scan."""


class ModelClient(Protocol):
    def complete(self, *, model: str, system: str, user: str) -> str:
        """Return one completion. Raise TimeoutError when the call does not finish."""


class UnconfiguredModel:
    """Fail closed so a scan cannot invent a vote without a model."""

    def __init__(self, reason: str = "No model provider is configured.") -> None:
        self._reason = reason

    def complete(self, *, model: str, system: str, user: str) -> str:
        raise ModelError(self._reason)


class ChatCompletionsModel:
    """Send independent, non-streaming Chat Completions in JSON mode."""

    def __init__(self, *, base_url: str, api_key: str, timeout: float = _TIMEOUT_SECONDS) -> None:
        url = httpx.URL(base_url)
        if url.scheme not in {"http", "https"} or not url.host or url.userinfo or url.query or url.fragment:
            raise httpx.InvalidURL("Expected an HTTP(S) base URL without credentials, a query or a fragment.")
        self._endpoint = url.copy_with(raw_path=url.raw_path.rstrip(b"/") + b"/chat/completions")
        self._api_key = api_key
        self._timeout = timeout

    def complete(self, *, model: str, system: str, user: str) -> str:
        try:
            response = asyncio.run(self._request(model=model, system=system, user=user))
        except (TimeoutError, httpx.TimeoutException):
            raise TimeoutError("The review call timed out.") from None
        except (httpx.HTTPError, ValueError):
            raise ModelError("The model provider request failed.") from None

        if not response.is_success:
            raise ModelError(f"The model provider returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            raise ModelError("The model provider did not return JSON.") from None
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelError("The model provider did not return a completion.")
        choice = choices[0]
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if choice.get("finish_reason", "stop") != "stop" or not isinstance(content, str) or not content.strip():
            raise ModelError("The model provider did not return a complete text response.")
        return content

    async def _request(self, *, model: str, system: str, user: str) -> httpx.Response:
        async with asyncio.timeout(self._timeout):
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False, trust_env=False) as client:
                return await client.post(
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )


def model_from_env() -> ModelClient:
    base_url = os.environ.get("CODEATLAS_LLM_BASE_URL", "").strip()
    if base_url:
        api_key = os.environ.get("CODEATLAS_LLM_API_KEY", "").strip()
        if not api_key:
            return UnconfiguredModel("No model provider is configured. Set CODEATLAS_LLM_API_KEY for the custom URL.")
    else:
        base_url = _OPENAI_BASE_URL
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return UnconfiguredModel()
    try:
        return ChatCompletionsModel(base_url=base_url, api_key=api_key)
    except httpx.InvalidURL:
        return UnconfiguredModel("No model provider is configured. CODEATLAS_LLM_BASE_URL is invalid.")
