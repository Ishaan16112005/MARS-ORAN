# MARS-O-RAN — Phase 0 Requirements & Scope

## 1. Project definition
**Full name:** Mission-Aware Risk-Constrained Elastic Network Slicing for O-RAN Emergency Robotics (MARS-O-RAN).

**Goal:** Define and later simulate a controller that reallocates radio and edge-computing resources among four service slices according to emergency mission progress, task urgency, information freshness, reliability, and risk—rather than optimizing network KPIs alone.

## 2. In-scope for the first simulation
- One chemical-plant incident environment.
- Four logical slices: robot control, perception/AI video, responder XR, and safety sensing.
- A mission represented as a directed acyclic graph (DAG).
- Finite radio resource budget represented by PRBs.
- Edge compute capacity and end-to-end delay components in later phases.
- Baseline controllers and a mission-aware controller in later phases.
- Simulation-based metrics: task completion, deadline misses, latency, reliability, AoI, resource use, reconfiguration, and risk.

## 3. Out of scope for the initial prototype
- Controlling real robots or UAVs.
- Connecting to a live public 5G network.
- Claiming real-world URLLC performance from an abstract simulation.
- Implementing the full stochastic MINLP at the beginning.
- Training reinforcement learning before the simulator and baselines are validated.
- Detailed RF propagation/PHY realism in Phase 0.

## 4. Emergency scenario
A private 5G-Advanced/6G O-RAN network supports routine monitoring at a chemical plant. An incident (initially a toxic gas leak) triggers a coordinated sequence: detect gas → localize source → navigate UGV → inspect valve → manipulate valve. Optional later scenarios include fire, victim detection, radio degradation, traffic surge, and component outage.

## 5. Slice definitions
| Slice ID | Name | Primary traffic | Key requirements |
|---|---|---|---|
| SC | Robot control | UGV commands and state updates | Low latency, high reliability, fresh state |
| SV | Perception / AI video | UAV/robot video and inference input | High uplink rate and edge compute |
| SX | Responder XR | Maps, alerts, AR overlays | Low latency and high downlink rate |
| SM | Safety sensing | Gas, temperature, pressure, structural sensors | Reliable and fresh updates |

## 6. Mission task definitions
| Task ID | Task | Prerequisite | Completion condition (initial abstraction) |
|---|---|---|---|
| K1 | Gas detection | None | Sensor report received and accepted |
| K2 | Gas-source localization | K1 | Source location estimate produced |
| K3 | UGV navigation to valve | K2 | Robot reaches inspection waypoint |
| K4 | Valve inspection | K3 | Inspection result received |
| K5 | Valve manipulation | K4 | Valve action acknowledged and verified |

These are initial simulation abstractions, not physical safety procedures.

## 7. System actors and modeled entities
- Plant incident generator: creates hazard level and event timing.
- Sensor devices: produce timestamped measurements.
- UAV/robot perception stream: produces video/AI workload.
- UGV: receives control commands and reports state.
- Responder client: receives map/hazard information.
- Radio resource controller: assigns slice-level PRBs.
- Edge server: provides finite processing capacity.
- Mission manager: tracks task prerequisites, deadlines, and completion.

## 8. Assumptions for the first model
1. Start with one logical cell/O-DU and one edge server.
2. Time is discrete and advances in configurable simulation steps.
3. The radio resource budget is a configurable number of PRBs.
4. The four slices share that budget subject to minimum/maximum bounds.
5. Tasks complete only after prerequisites are satisfied.
6. Initial task success is simulated using abstract workload, delay, and success rules.
7. Channel quality, packet loss, failures, and mobility are injected as configurable scenario effects in later phases.
8. All parameter values are provisional and must be calibrated or justified; they are not measured field values.
9. Use fixed random seeds for repeatable experiments.
10. The initial prototype is a simulation, not a production safety system.

## 9. Functional requirements
- FR-01: Load scenario settings from a configuration file.
- FR-02: Represent the mission as tasks with prerequisites, activation times, deadlines, and weights.
- FR-03: Represent four slices and their minimum/maximum resource bounds.
- FR-04: Enforce total radio-resource and edge-compute capacity constraints.
- FR-05: Track task readiness, status, and completion.
- FR-06: Compute task criticality from urgency, hazard, mission value, critical-path status, and freshness need (later phase).
- FR-07: Provide at least fixed, threshold-based, and mission-aware allocation policies.
- FR-08: Track end-to-end delay, task success, AoI, reconfiguration cost, and mission loss.
- FR-09: Run scenario batches with reproducible seeds.
- FR-10: Export results as CSV and produce comparison plots.

## 10. Non-functional requirements
- NFR-01: Python implementation with modular components.
- NFR-02: Configurable parameters; avoid hard-coded scenario assumptions.
- NFR-03: Deterministic repeatability when the same seed/config is used.
- NFR-04: Clear logs explaining task status and allocation decisions.
- NFR-05: No resource allocation may violate capacity or slice bounds.
- NFR-06: Results must distinguish modeled estimates from measured network performance.

## 11. Success criteria for the complete project
The full project will be considered functionally complete when:
- All four slices and the task DAG run end-to-end.
- Capacity constraints are checked at every simulation step.
- At least three policies are compared under common scenarios/seeds.
- Mission-level and network-level metrics are reported.
- Failure and tail-risk scenarios are evaluated.
- The experiment can be reproduced from documented configuration and commands.

## 12. Phase 0 deliverables
- This requirements and scope document.
- Scenario configuration file.
- Mission task graph file.
- Initial parameter sheet.
- Acceptance criteria and a configuration validation script.
