"""Agent loop: LLM + tool execution cycle.

Provides two entry points:
  agent_loop():            Simple loop with session persistence (s03)
  run_agent_with_tools():  Multi-agent loop with configurable tools/prompts (s05)

Reference: OpenClaw src/agents/agent-loop.ts
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from nanobot.llm.llm_client import deepseek_chat_with_tools
from nanobot.engine.context import SYSTEM_PROMPT
from nanobot.engine.tools.definitions import TOOLS_OPENAI, TOOL_HANDLERS, process_tool_call

log = logging.getLogger("agent")


def agent_loop(
    user_input: str,
    session_key: str,
    session_store: Any,
) -> str:
    """Process one user turn with tool loop and session persistence.

    Flow: load -> append user -> [API -> tools]* -> save -> return

    Reference: s03_sessions.py agent_loop
    """
    session_data = session_store.load_session(session_key)
    messages = session_data["history"]
    messages.append({"role": "user", "content": user_input})

    all_assistant_blocks: list = []

    while True:
        resp = deepseek_chat_with_tools(
            messages, TOOLS_OPENAI,
            model=None, system_prompt=SYSTEM_PROMPT, max_tokens=4096,
        )
        content = resp.get("content") or ""
        tool_calls = resp.get("tool_calls") or []

        if content:
            all_assistant_blocks.append({"type": "text", "text": content})
        for tc in tool_calls:
            try:
                tc_args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
            except json.JSONDecodeError:
                tc_args = {}
            all_assistant_blocks.append({
                "type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc_args,
            })

        if tool_calls:
            assistant_msg: dict = {"role": "assistant", "content": content}
            assistant_msg["tool_calls"] = [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in tool_calls
            ]
            messages.append(assistant_msg)

            for tc in tool_calls:
                try:
                    args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
                except json.JSONDecodeError:
                    args = {}
                result = process_tool_call(tc["name"], args)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                all_assistant_blocks.append({"type": "tool_result", "tool_use_id": tc["id"], "output": result})
            continue

        if content:
            messages.append({"role": "assistant", "content": content})
        break

    session_store.save_turn(session_key, user_input, all_assistant_blocks)
    return content


def run_agent_with_tools(
    agent: Any,
    session_store: Any,
    session_key: str,
    user_text: str,
    *,
    registry: Any = None,
    prompt_builder: Any = None,
) -> str:
    """Multi-agent tool loop with configurable registry and prompt builder.

    Reference: s05_gateway.py run_agent_with_tools
    """
    session_data = session_store.load_session(session_key)
    messages = session_data["history"]
    messages.append({"role": "user", "content": user_text})

    if prompt_builder is not None:
        system_prompt = prompt_builder.build(agent, SYSTEM_PROMPT)
    else:
        system_prompt = f"{SYSTEM_PROMPT}\n\nPersonality: {agent.system_prompt}"

    all_tools = registry.specs if registry is not None else TOOLS_OPENAI
    all_assistant_blocks: list = []

    while True:
        resp = deepseek_chat_with_tools(
            messages, all_tools,
            model=agent.model, system_prompt=system_prompt, max_tokens=4096,
        )
        content = resp.get("content") or ""
        tool_calls = resp.get("tool_calls") or []

        if content:
            all_assistant_blocks.append({"type": "text", "text": content})
        for tc in tool_calls:
            try:
                tc_args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
            except json.JSONDecodeError:
                tc_args = {}
            all_assistant_blocks.append({
                "type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc_args,
            })

        if tool_calls:
            assistant_msg: dict = {"role": "assistant", "content": content}
            assistant_msg["tool_calls"] = [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in tool_calls
            ]
            messages.append(assistant_msg)

            for tc in tool_calls:
                try:
                    args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
                except json.JSONDecodeError:
                    args = {}
                result = None
                if registry is not None:
                    result = registry.handle(tc["name"], args)
                if result is None:
                    result = process_tool_call(tc["name"], args)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                all_assistant_blocks.append({"type": "tool_result", "tool_use_id": tc["id"], "output": result})
            continue

        if content:
            messages.append({"role": "assistant", "content": content})
        break

    session_store.save_turn(session_key, user_text, all_assistant_blocks)
    return content
