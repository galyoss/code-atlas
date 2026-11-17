"""Transport one review prompt to an OpenAI-compatible chat completions API.

The check owns the hunter and skeptic prompts. This client sends them and
returns the assistant text, which is the vote JSON. It does not decide a verdict.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_KEY_REASON = "The model key is not configured."
_TIMEOUT = 60


class ModelClient(Protocol):
    def complete(self, *, model: str, system: str, user: str) -> str:
        """Return one completion. Raise TimeoutError when the call does not finish."""


class ModelKeyMissing(Exception):
    """REVIEW_MODEL_API_KEY is absent. No request was sent."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect)


class ChatCompletionsClient:
    """Send the scan's model name to a chat completions endpoint.

    `base_url` and `api_key` default to REVIEW_MODEL_BASE_URL and
    REVIEW_MODEL_API_KEY. A missing key raises ModelKeyMissing before any
    network call. The key is never included in an error message.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = _TIMEOUT,
        urlopen=None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout
        self._urlopen = urlopen

    def complete(self, *, model: str, system: str, user: str) -> str:
        key = _secret(self._api_key, "REVIEW_MODEL_API_KEY")
        if not key:
            raise ModelKeyMissing(_KEY_REASON)
        url = _base(self._base_url) + "/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            if self._urlopen is not None:
                response = self._urlopen(request, timeout=self._timeout)
            else:
                response = _opener().open(request, timeout=self._timeout)
            with response:
                raw = response.read()
        except TimeoutError:
            raise TimeoutError("The review call timed out.") from None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"The review call failed ({exc.code}).") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError("The review call timed out.") from None
            raise RuntimeError("The review call failed.") from None
        return _message_text(raw)


def _secret(explicit: str | None, env_name: str) -> str:
    if explicit is None:
        value = os.environ.get(env_name, "")
    else:
        value = explicit
    if not isinstance(value, str):
        return ""
    return value.strip()


def _base(explicit: str | None) -> str:
    if explicit is None:
        value = os.environ.get("REVIEW_MODEL_BASE_URL", "")
    else:
        value = explicit
    if not isinstance(value, str) or not value.strip():
        value = _DEFAULT_BASE_URL
    return value.strip().rstrip("/")


def _message_text(raw: bytes) -> str:
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("The model did not return JSON.") from None
    if not isinstance(body, dict):
        raise RuntimeError("The model did not return JSON.")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("The model response had no message.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("The model response had no message.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The model response had no message.")
    return content
