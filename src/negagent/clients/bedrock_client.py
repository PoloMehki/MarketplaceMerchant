"""bedrock_client.py — Task 0.2: thin wrapper over Bedrock messages (text + vision).

Dumb by design: it takes Bedrock ``converse``-format message dicts and returns the
assistant's text. No business logic, no prompt building — callers own that so the
wrapper stays trivially mockable.
"""
from __future__ import annotations

from typing import Any, Optional


class BedrockClient:
    """Wraps the boto3 ``bedrock-runtime`` ``converse`` API."""

    def __init__(
        self,
        model_id: str,
        region: str,
        client: Any = None,
    ) -> None:
        self._model_id = model_id
        if client is not None:
            self._client = client
        else:  # pragma: no cover - exercised only against real AWS
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=region)

    def complete(
        self,
        messages: list[dict],
        system: Optional[str] = None,
    ) -> str:
        """Send text messages, return the assistant's reply text."""
        kwargs: dict[str, Any] = {"modelId": self._model_id, "messages": messages}
        if system:
            kwargs["system"] = [{"text": system}]
        response = self._client.converse(**kwargs)
        return self._extract_text(response)

    def complete_vision(
        self,
        messages_with_images: list[dict],
        system: Optional[str] = None,
    ) -> str:
        """Send messages containing image content blocks, return reply text."""
        kwargs: dict[str, Any] = {"modelId": self._model_id, "messages": messages_with_images}
        if system:
            kwargs["system"] = [{"text": system}]
        response = self._client.converse(**kwargs)
        return self._extract_text(response)

    @staticmethod
    def _extract_text(response: dict) -> str:
        return response["output"]["message"]["content"][0]["text"]
