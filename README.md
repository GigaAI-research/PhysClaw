# PhysClaw
PhysClaw*: Physical Continual Learning Agent Workflow


PhysClaw\* is an experimental framework for building distributed physical AI agents.  
The goal of this project is to enable scalable robot intelligence by integrating language models, world models, value models, and robotic systems into a unified workflow.

The system is built on top of **OpenClaw**, and extends it with a distributed node architecture that allows different components (robots, models, tools) to operate as independent services coordinated by a central node server.

[![Static Badge](https://img.shields.io/badge/project-page-blue)](https://gigaai-research.github.io/PhysClaw/)


> ⚠️ This project is under active development.  
> The repository currently provides the initial architecture and development roadmap.

<!-- <p align="center">
<img src="assets/wechat_group_qr.png" width="200">
</p> -->

---

## Overview

PhysClaw* aims to support **distributed physical intelligence systems** where multiple heterogeneous components collaborate through a unified communication layer.

The system architecture includes:

- **PhysClaw Gateway**
- **Node Server** for orchestration
- **Robot Nodes**
- **Model Nodes**
- **Training and Data Tools**

These components communicate through a standardized messaging protocol and can be deployed as independent nodes in a distributed system.

---

<!-- ## Architecture (Concept)

```

Human Interaction
│
Channel
│
PhysClaw Gateway
│
Node Server
│
┌─────────────── Distributed Nodes ────────────────┐
│                                                   │
Robot Nodes     VLA Model Nodes    Value Models     World Models
│                                                   │
Training Tools / Data Management / Other Devices

```

PhysClaw* extends the OpenClaw agent framework with a **node-based distributed execution system** that enables scalable experimentation for embodied AI.

--- -->

## Project Status

🚧 **Early Development Stage**

This repository currently contains the **initial code structure** and the development of core components is in progress.

The system is not yet ready for external use.

---

## Implemented Minimal Architecture (Current)

Based on the architecture description and OpenClaw integration direction, the repository now includes a runnable minimal stack:

- **Node Server** (`node_server/`)
	- Node register / unregister / heartbeat
	- Node listing and typed listing
	- Message routing (direct / broadcast / by node type)
- **Shared Protocol Layer** (`shared/`)
	- Unified node types
	- Message schema and serialization
	- Shared config and HTTP JSON utils
- **Nodes** (`nodes/`)
	- `BaseNode` (lifecycle + heartbeat + message sending)
	- `RobotNode` (targeted commands: move / pick / place)
	- `VLANode` (action planning stub)
	- `ValueModelNode` (action scoring stub)
	- `WorldModelNode` (next-state prediction stub)

---

## One-Command Minimal Demo

Run:

```bash
./scripts/run_minimal_demo.sh
```

What it does:

1. Starts the PhysClaw Node Server
2. Starts and registers one `RobotNode`
3. Accepts text input from terminal
4. Tries to forward the text to `openclaw agent --message ...` (if OpenClaw CLI exists)
5. Routes the command into `robot-demo-1` and executes robot action

Example input:

```text
move to 1 2 3
```

Expected effect:

- message routed by Node Server
- robot node returns: `robot moved to pose [1.0, 2.0, 3.0]`

---

## TODO Roadmap

The following core components are currently under development:

- [ ] **Integration with OpenClaw codebase**
- [ ] **Node Server**
- [ ] **Robot Node**
- [ ] **VLA Model Node**
- [ ] **Value Model Node**
- [ ] **World Model Node**
---

## Vision

PhysClaw* explores a scalable architecture for **physical AGI systems**, where robots, models, and tools operate as modular components that continuously learn and improve through interaction.

We believe distributed architectures will play an important role in enabling **large-scale continual learning for embodied agents**.

<!-- ---

## License

To be announced. -->

