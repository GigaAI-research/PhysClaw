# PhysClaw
PhysClaw*: Physical Continual Learning Agent Workflow


PhysClaw\* is an experimental framework for building distributed physical AI agents.  
The goal of this project is to enable scalable robot intelligence by integrating language models, world models, value models, and robotic systems into a unified workflow.

The system is built on top of **OpenClaw**, and extends it with a distributed node architecture that allows different components (robots, models, tools) to operate as independent services coordinated by a central node server.

[![Static Badge](https://img.shields.io/badge/project-page-blue)](https://physclaw.github.io)


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

