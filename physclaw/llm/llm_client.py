"""LLM client for DeepSeek / OpenAI-compatible APIs.

Provides a unified interface for calling LLMs with tool support.
Reference: OpenClaw llm_client.py
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


class LLMClientError(Exception):
    """Base error for LLM client operations."""
    pass


class LLMValidationError(LLMClientError):
    """Validation error (e.g., missing API key)."""
    pass


class LLMClientConfig:
    """LLM client configuration."""

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.default_model = os.getenv("DEEPSEEK_DEFAULT_MODEL", "deepseek-chat")

    def require_api_key(self) -> str:
        if not self.api_key:
            raise LLMValidationError(
                "DEEPSEEK_API_KEY not set. "
                "Set it in .env file or as environment variable."
            )
        return self.api_key


def load_env_if_exists() -> None:
    """Load .env file if it exists in the current or parent directories."""
    for candidate in [Path(".env"), Path.home() / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return
    load_dotenv()


def deepseek_chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str | None = None,
    system_prompt: str | None = None,
    max_tokens: int = 4096,
    **kwargs,
) -> dict[str, Any]:
    """Call DeepSeek/OpenAI-compatible API with tool support.

    Returns dict with keys: content, tool_calls, finish_reason.
    """
    try:
        import openai
    except ImportError:
        raise LLMClientError("openai package required: pip install openai")

    config = LLMClientConfig()
    api_key = config.require_api_key()
    model = model or config.default_model

    client = openai.OpenAI(
        api_key=api_key,
        base_url=config.base_url,
    )

    api_messages = []
    if system_prompt:
        api_messages.append({"role": "system", "content": system_prompt})
    api_messages.extend(messages)

    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": api_messages,
        "max_tokens": max_tokens,
    }
    if tools:
        call_kwargs["tools"] = tools

    try:
        response = client.chat.completions.create(**call_kwargs)
    except Exception as e:
        raise LLMClientError(f"API call failed: {e}") from e

    choice = response.choices[0]
    message = choice.message

    tool_calls = []
    if message.tool_calls:
        for tc in message.tool_calls:
            tool_calls.append({
                "id": tc.id or f"call_{uuid.uuid4().hex[:8]}",
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            })

    return {
        "content": message.content or "",
        "tool_calls": tool_calls,
        "finish_reason": choice.finish_reason or "stop",
    }
