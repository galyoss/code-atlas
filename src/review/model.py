"""The model call a review uses. This package does not call a live model."""

from __future__ import annotations

from typing import Protocol


class ModelClient(Protocol):
    def complete(self, *, model: str, system: str, user: str) -> str:
        """Return one completion. Raise TimeoutError when the call does not finish."""


class UnconfiguredModel:
    """Fail closed so a scan cannot invent a vote without a model."""

    def complete(self, *, model: str, system: str, user: str) -> str:
        raise TimeoutError(f"No model provider is configured for {model}.")
