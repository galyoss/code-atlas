"""The chat model review agents run on: an OpenAI-compatible chat completions API.

`REVIEW_MODEL_BASE_URL` (default `https://api.openai.com/v1`) and
`REVIEW_MODEL_API_KEY` configure it; the scan's `model` is the provider model
name. A missing key raises ModelKeyMissing before any request is built, and the
key never appears in an error message.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from langchain_openai import ChatOpenAI

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
TIMEOUT = 120
MAX_RETRIES = 6


class ModelKeyMissing(Exception):
    """REVIEW_MODEL_API_KEY is absent. No request was sent."""


class ModelConfigError(ValueError):
    """REVIEW_MODEL_BASE_URL is not an https URL (or http on localhost)."""


def chat_model(model: str, *, base_url: str | None = None, api_key: str | None = None) -> ChatOpenAI:
    key = (api_key if api_key is not None else os.environ.get("REVIEW_MODEL_API_KEY", "")).strip()
    if not key:
        raise ModelKeyMissing("The model key is not configured.")
    url = (base_url if base_url is not None else os.environ.get("REVIEW_MODEL_BASE_URL", "")).strip() or _DEFAULT_BASE_URL
    parsed = urlparse(url)
    if not (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS)):
        raise ModelConfigError("REVIEW_MODEL_BASE_URL must be https, or http on localhost.")
    return ChatOpenAI(
        model=model,
        api_key=key,
        base_url=url.rstrip("/"),
        temperature=0,
        timeout=TIMEOUT,
        # The client backs off on 429 and 5xx responses.
        max_retries=MAX_RETRIES,
        use_responses_api=False,
    )
