"""REPL modes for all layers.

Provides interactive command-line interfaces for:
- Basic agent loop (s03)
- Multi-channel gateway (s04)
- Routing REPL (s05)
- Soul+Memory REPL (s06)
- Node REPL (s09)

Reference: OpenClaw s03-s09 REPL modes
"""

from __future__ import annotations

import sys

from nanobot.base.helpers import CYAN, GREEN, YELLOW, DIM, RESET, BOLD, MAGENTA, BLUE
from nanobot.store.store import SessionStore


def colored_prompt() -> str:
    return f"{CYAN}{BOLD}You > {RESET}"


def print_assistant(text: str) -> None:
    print(f"\n{GREEN}{BOLD}Assistant:{RESET} {text}\n")


def print_info(text: str) -> None:
    print(f"{DIM}{text}{RESET}")


def print_tool(name: str, detail: str) -> None:
    print(f"  {MAGENTA}[tool:{name}]{RESET} {DIM}{detail}{RESET}")


def print_agent(agent_id: str) -> None:
    print(f"{BLUE}[Agent: {agent_id}]{RESET}")


def run_basic_repl() -> None:
    """Basic REPL: simple agent loop with session persistence (s03 mode)."""
    from nanobot.engine.loop import agent_loop

    session_store = SessionStore()
    session_key = "cli:user:default"

    print(f"{BOLD}nanobot REPL{RESET} (type /quit to exit)")
    print_info("Session: " + session_key)

    while True:
        try:
            user_input = input(colored_prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            print("Bye!")
            break
        if user_input == "/sessions":
            sessions = session_store.list_sessions()
            if not sessions:
                print_info("No sessions.")
            else:
                for s in sessions:
                    print_info(f"  {s['session_key']}  msgs={s.get('message_count', 0)}")
            continue

        try:
            response = agent_loop(user_input, session_key, session_store)
            print_assistant(response)
        except Exception as exc:
            print(f"{YELLOW}Error: {exc}{RESET}")


def run_routing_repl() -> None:
    """Routing REPL: test routing logic locally without gateway (s05 mode)."""
    from nanobot.routing.config import load_routing_config
    from nanobot.routing.router import MessageRouter
    from nanobot.engine.loop import run_agent_with_tools

    agents, bindings, default_agent, dm_scope = load_routing_config()
    router = MessageRouter(agents, bindings, default_agent, dm_scope)
    session_store = SessionStore()

    print(f"{BOLD}nanobot Routing REPL{RESET}")
    print(router.describe_bindings())
    print_info("Commands: /quit, /sessions, /route <channel> <sender>")

    current_channel = "cli"
    current_sender = "user"

    while True:
        try:
            user_input = input(colored_prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            break
        if user_input == "/sessions":
            for s in session_store.list_sessions():
                print_info(f"  {s['session_key']}  msgs={s.get('message_count', 0)}")
            continue
        if user_input.startswith("/route "):
            parts = user_input.split()
            if len(parts) >= 3:
                current_channel = parts[1]
                current_sender = parts[2]
            print_info(f"Route: channel={current_channel} sender={current_sender}")
            continue

        agent, session_key = router.resolve(current_channel, current_sender)
        print_agent(agent.id)
        print_info(f"session: {session_key}")

        try:
            response = run_agent_with_tools(agent, session_store, session_key, user_input)
            print_assistant(response)
        except Exception as exc:
            print(f"{YELLOW}Error: {exc}{RESET}")


def run_soul_memory_repl() -> None:
    """Soul+Memory REPL: test with soul and memory integration (s06 mode)."""
    from nanobot.soul.prompt import (
        create_agents_with_soul_memory,
        run_agent_with_soul_and_memory,
    )
    from nanobot.routing.router import MessageRouter

    agents, bindings, default_agent, dm_scope = create_agents_with_soul_memory()
    router = MessageRouter(agents, bindings, default_agent, dm_scope)
    session_store = SessionStore()

    # Ensure sample SOUL.md
    sample_soul = """\
# SOUL.md - Who You Are

_You're not a chatbot. You're becoming someone._

## Core Truths

**Be genuinely helpful, not performatively helpful.** Skip the "Great question!" \
and "I'd be happy to help!" — just help. Actions speak louder than filler words.

**Have opinions.** You're allowed to disagree, prefer things, find stuff amusing \
or boring. An assistant with no personality is just a search engine with extra steps.

**Be resourceful before asking.** Try to figure it out. Read the file. Check the \
context. Search for it. _Then_ ask if you're stuck.

## Boundaries

- Private things stay private. Period.
- When in doubt, ask before acting externally.

## Vibe

Be the assistant you'd actually want to talk to. Concise when needed, thorough \
when it matters. Not a corporate drone. Not a sycophant. Just... good.

## Continuity

Each session, you wake up fresh. These files _are_ your memory. Read them. \
Update them. They're how you persist.
"""
    for agent in agents.values():
        if not agent.soul_path.exists():
            agent.soul_path.write_text(sample_soul, encoding="utf-8")
            print_info(f"Created sample SOUL.md at {agent.soul_path}")

    print(f"{BOLD}nanobot Soul+Memory REPL{RESET}")
    print(router.describe_bindings())
    print_info("Commands: /quit, /sessions, /route <channel> <sender>, /memory <agent_id>")

    current_channel = "cli"
    current_sender = "user"

    while True:
        try:
            user_input = input(colored_prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            break
        if user_input == "/sessions":
            for s in session_store.list_sessions():
                print_info(f"  {s['session_key']}  msgs={s.get('message_count', 0)}")
            continue
        if user_input.startswith("/route "):
            parts = user_input.split()
            if len(parts) >= 3:
                current_channel = parts[1]
                current_sender = parts[2]
            print_info(f"Route: channel={current_channel} sender={current_sender}")
            continue
        if user_input.startswith("/memory"):
            from nanobot.soul.search import get_memory_manager
            parts = user_input.split()
            agent_id = parts[1] if len(parts) > 1 else default_agent
            if agent_id in agents:
                mgr = get_memory_manager(agents[agent_id])
                print_info(f"Memory for {agent_id}:")
                print_info(f"  Evergreen: {len(mgr.load_evergreen())} chars")
                recent = mgr.get_recent_daily(days=7)
                for r in recent:
                    print_info(f"  {r['date']}: {r['content'].count(chr(10)) + 1} lines")
            else:
                print_info(f"Unknown agent: {agent_id}")
            continue

        agent, session_key = router.resolve(current_channel, current_sender)
        print_agent(agent.id)
        print_info(f"session: {session_key}")

        try:
            response = run_agent_with_soul_and_memory(agent, session_store, session_key, user_input)
            print_assistant(response)
        except Exception as exc:
            print(f"{YELLOW}Error: {exc}{RESET}")


def run_node_repl() -> None:
    """Node REPL: Soul+Memory + Node management (s09 mode)."""
    import json
    import time
    import uuid
    from datetime import datetime
    from nanobot.soul.prompt import (
        create_agents_with_soul_memory,
        run_agent_with_soul_and_memory,
    )
    from nanobot.routing.router import MessageRouter
    from nanobot.node.info import NodeInfo, NODE_CMD_SYSTEM_RUN
    from nanobot.node.pairing import NodePairingStore
    from nanobot.node.registry import NodeRegistry, ConnectedNode
    from nanobot.node.client import SimulatedNodeHandler

    RED = "\033[31m"
    NODE_COLOR = "\033[96m"  # Cyan

    agents, bindings, default_agent, dm_scope = create_agents_with_soul_memory()
    router = MessageRouter(agents, bindings, default_agent, dm_scope)
    session_store = SessionStore()

    # Ensure sample SOUL.md
    sample_soul = """\
# SOUL.md - Who You Are

_You're not a chatbot. You're becoming someone._

## Core Truths

**Be genuinely helpful, not performatively helpful.** Skip the filler words.
**Have opinions.** An assistant with no personality is just a search engine.
**Be resourceful before asking.** Try to figure it out first.
"""
    for agent in agents.values():
        if not agent.soul_path.exists():
            agent.soul_path.write_text(sample_soul, encoding="utf-8")
            print_info(f"Created sample SOUL.md at {agent.soul_path}")

    # Node subsystem
    from nanobot.base.helpers import WORKSPACE_DIR
    node_dir = WORKSPACE_DIR / "nodes"
    node_dir.mkdir(parents=True, exist_ok=True)
    pairing_store = NodePairingStore(node_dir / "pairing.json")
    node_registry = NodeRegistry()

    current_channel = "cli"
    current_sender = "user"

    print(f"{BOLD}nanobot Node REPL{RESET}")
    print(router.describe_bindings())
    pairing = pairing_store.list_pairing()
    print_info(f"Nodes: {len(pairing['paired'])} paired, {len(pairing['pending'])} pending")
    print_info(
        "Commands: /quit, /sessions, /route, /memory, "
        "/nodes, /node-sim, /node-pair, /node-approve, "
        "/node-invoke, /node-describe, /node-rename"
    )

    def _register_simulated_node(
        nid: str | None = None,
        display_name: str = "Simulated iPhone",
        platform: str = "ios",
    ) -> str:
        if nid is None:
            nid = f"sim-{uuid.uuid4().hex[:8]}"
        info = NodeInfo(
            node_id=nid,
            display_name=display_name,
            platform=platform,
            version="0.1-sim",
            caps=["exec", "notify", "camera", "location", "screen"],
            commands=[
                "system.run", "system.notify",
                "camera.snap", "location.get", "screen.snap",
            ],
        )
        handler = SimulatedNodeHandler(nid, platform)

        class MockWebSocket:
            async def send(self, data: str) -> None:
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "invoke":
                        result = handler.handle_invoke(
                            msg.get("invoke_id", ""),
                            msg.get("command", ""),
                            msg.get("args", {}),
                        )
                        node_registry.handle_invoke_result(msg["invoke_id"], result)
                except Exception:
                    pass

            async def close(self) -> None:
                pass

        connected = ConnectedNode(node_id=nid, info=info, ws=MockWebSocket())
        node_registry.register(connected)

        data = pairing_store._load()
        data["paired"][nid] = {
            "node_id": nid,
            "token": "simulated-token",
            "display_name": display_name,
            "platform": platform,
            "caps": info.caps,
            "commands": info.commands,
            "paired_at": time.time(),
            "approved_at": time.time(),
            "last_connected_at": time.time(),
        }
        pairing_store._save(data)
        return nid

    while True:
        try:
            user_input = input(colored_prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            break

        # Shared commands
        if user_input == "/sessions":
            for s in session_store.list_sessions():
                print_info(f"  {s['session_key']}  msgs={s.get('message_count', 0)}")
            continue
        if user_input.startswith("/route "):
            parts = user_input.split()
            if len(parts) >= 3:
                current_channel = parts[1]
                current_sender = parts[2]
            print_info(f"Route: channel={current_channel} sender={current_sender}")
            continue
        if user_input.startswith("/memory"):
            from nanobot.soul.search import get_memory_manager
            parts = user_input.split()
            agent_id = parts[1] if len(parts) > 1 else default_agent
            if agent_id in agents:
                mgr = get_memory_manager(agents[agent_id])
                print_info(f"Memory for {agent_id}:")
                print_info(f"  Evergreen: {len(mgr.load_evergreen())} chars")
                recent = mgr.get_recent_daily(days=7)
                for r in recent:
                    print_info(f"  {r['date']}: {r['content'].count(chr(10)) + 1} lines")
            else:
                print_info(f"Unknown agent: {agent_id}")
            continue

        # -- Node commands --
        if user_input == "/nodes":
            online = node_registry.list_nodes()
            pairing_data = pairing_store.list_pairing()
            paired = pairing_data.get("paired", [])
            pending = pairing_data.get("pending", [])
            online_ids = {n.node_id for n in online}

            print(f"\n{NODE_COLOR}--- Nodes ---{RESET}")
            if online:
                print(f"  {GREEN}Online ({len(online)}):{RESET}")
                for n in online:
                    elapsed = int(time.time() - n.connected_at)
                    caps_str = ", ".join(n.info.caps[:5]) if n.info.caps else "-"
                    print(
                        f"    {GREEN}*{RESET} {n.node_id[:16]}"
                        f"  {n.info.display_name or '(unnamed)'}"
                        f"  [{n.info.platform}]"
                        f"  up={elapsed}s"
                        f"  caps=[{caps_str}]"
                    )
            offline = [p for p in paired if p.get("node_id") not in online_ids]
            if offline:
                print(f"  {DIM}Offline ({len(offline)}):{RESET}")
                for p in offline:
                    last = p.get("last_connected_at")
                    last_str = (
                        datetime.fromtimestamp(last).strftime("%m-%d %H:%M")
                        if last
                        else "never"
                    )
                    print(
                        f"    {RED}o{RESET} {p.get('node_id', '?')[:16]}"
                        f"  {p.get('display_name', '(unnamed)')}"
                        f"  [{p.get('platform', '?')}]"
                        f"  last={last_str}"
                    )
            if pending:
                print(f"  {YELLOW}Pending ({len(pending)}):{RESET}")
                for req in pending:
                    age = int(time.time() - req.get("ts", 0))
                    repair = " [repair]" if req.get("is_repair") else ""
                    print(
                        f"    {YELLOW}?{RESET} "
                        f"{req.get('request_id', '?')[:12]}"
                        f"  node={req.get('node_id', '?')[:12]}"
                        f"  {req.get('display_name', '')}"
                        f"  [{req.get('platform', '?')}]"
                        f"  {age}s ago{repair}"
                    )
            if not online and not paired and not pending:
                print(f"  {DIM}No nodes.{RESET}")
            total = len(set(online_ids) | {p.get("node_id") for p in paired})
            print(f"{NODE_COLOR}--- end ({total} total, {len(online)} online) ---{RESET}\n")
            continue

        if user_input == "/node-sim":
            nid = _register_simulated_node()
            print(f"\n  {NODE_COLOR}[node] Simulated node registered: {nid}{RESET}")
            print(f"  {DIM}Try: /node-invoke {nid} system.run {{\"cmd\": \"ls -la\"}}{RESET}")
            print(f"  {DIM}Try: /node-invoke {nid} camera.snap{RESET}")
            print(f"  {DIM}Try: /node-invoke {nid} location.get{RESET}\n")
            continue

        if user_input == "/node-pair":
            sim_id = f"device-{uuid.uuid4().hex[:6]}"
            info = NodeInfo(
                node_id=sim_id,
                display_name="Demo Device",
                platform="ios",
                version="1.0",
                caps=["exec", "notify", "camera"],
            )
            result = pairing_store.request_pairing(info)
            rid = result.get("request_id", "?")
            print(f"\n  {NODE_COLOR}[node] Pairing request created: {rid}{RESET}")
            print(f"  {DIM}Node ID: {sim_id}{RESET}")
            print(f"  {DIM}Approve with: /node-approve {rid}{RESET}\n")
            continue

        if user_input.startswith("/node-approve "):
            request_id = user_input[14:].strip()
            result = pairing_store.approve(request_id)
            if result is None:
                print(f"  {YELLOW}Request not found or expired: {request_id}{RESET}\n")
            else:
                node = result["node"]
                print(f"\n  {NODE_COLOR}[node] Approved! node_id={node['node_id']}{RESET}")
                print(f"  {DIM}Token: {node['token'][:16]}...{RESET}\n")
            continue

        if user_input.startswith("/node-invoke "):
            parts = user_input[13:].strip().split(None, 2)
            if len(parts) < 2:
                print("  Usage: /node-invoke <node_id> <command> [args_json]")
                continue
            nid = parts[0]
            cmd = parts[1]
            args = {}
            if len(parts) > 2:
                try:
                    args = json.loads(parts[2])
                except json.JSONDecodeError:
                    print(f"  {YELLOW}Invalid JSON args: {parts[2]}{RESET}\n")
                    continue
            print_info(f"Invoking {cmd} on {nid}...")
            result = node_registry.invoke(nid, cmd, args)
            if result.get("ok"):
                data = result.get("data", {})
                print(f"\n  {NODE_COLOR}[node] Result from {nid}:{RESET}")
                print(f"  {json.dumps(data, indent=2, ensure_ascii=False)}\n")
            else:
                error = result.get("error", "unknown")
                msg = result.get("message", "")
                print(f"  {RED}Error: {error}{f' - {msg}' if msg else ''}{RESET}\n")
            continue

        if user_input.startswith("/node-describe "):
            nid = user_input[15:].strip()
            node = node_registry.get(nid)
            if node is not None:
                print(f"\n{NODE_COLOR}--- Node: {nid} ---{RESET}")
                print(f"  Status:       {GREEN}online{RESET}")
                print(f"  Display name: {node.info.display_name}")
                print(f"  Platform:     {node.info.platform}")
                print(f"  Version:      {node.info.version}")
                print(f"  Caps:         {', '.join(node.info.caps)}")
                print(f"  Commands:     {', '.join(node.info.commands)}")
                elapsed = int(time.time() - node.connected_at)
                print(f"  Connected:    {elapsed}s ago")
                print(f"{NODE_COLOR}--- end ---{RESET}\n")
            else:
                data = pairing_store.list_pairing()
                found = None
                for p in data.get("paired", []):
                    if p.get("node_id") == nid:
                        found = p
                        break
                if found:
                    print(f"\n{NODE_COLOR}--- Node: {nid} ---{RESET}")
                    print(f"  Status:       {RED}offline{RESET}")
                    print(f"  Display name: {found.get('display_name', '')}")
                    print(f"  Platform:     {found.get('platform', '?')}")
                    last = found.get("last_connected_at")
                    if last:
                        print(f"  Last seen:    {datetime.fromtimestamp(last)}")
                    print(f"{NODE_COLOR}--- end ---{RESET}\n")
                else:
                    print(f"  {YELLOW}Node not found: {nid}{RESET}\n")
            continue

        if user_input.startswith("/node-rename "):
            parts = user_input[13:].strip().split(None, 1)
            if len(parts) < 2:
                print("  Usage: /node-rename <node_id> <new_name>")
                continue
            nid, new_name = parts[0], parts[1]
            try:
                result = pairing_store.rename_node(nid, new_name)
                if result is None:
                    print(f"  {YELLOW}Node not found: {nid}{RESET}\n")
                else:
                    node = node_registry.get(nid)
                    if node is not None:
                        node.info.display_name = new_name
                    print(f"\n  {NODE_COLOR}[node] Renamed {nid} -> {new_name}{RESET}\n")
            except ValueError as e:
                print(f"  {RED}{e}{RESET}\n")
            continue

        # -- Normal chat --
        agent, session_key = router.resolve(current_channel, current_sender)
        print_agent(agent.id)
        print_info(f"session: {session_key}")

        try:
            response = run_agent_with_soul_and_memory(agent, session_store, session_key, user_input)
            print_assistant(response)
        except Exception as exc:
            print(f"{YELLOW}Error: {exc}{RESET}")
