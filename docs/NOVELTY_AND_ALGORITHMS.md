# MARS-O-RAN: What We Have Done and What Is Novel

## Completed system

### Phase 0 - Problem definition
Defined one chemical-plant emergency scenario, four slices, five mission tasks, task dependencies and a reproducible parameter sheet.

### Phase 1 - Mission simulator
Implemented a discrete-time mission engine. Tasks can execute only when predecessors finish. Task deadlines are checked explicitly.

### Phase 2 - Network + compute model
Implemented a single-cell abstraction with finite PRB budget, per-slice minimum/maximum allocation, SINR-dependent rate, a finite-blocklength penalty, edge compute sharing, backhaul delay, channel degradation and shock states.

### Phase 3 - Baselines
Implemented STATIC and PROPORTIONAL policies so that the contribution is tested against simple alternatives rather than only against an unimplemented ideal.

### Phase 4 - Dynamic criticality
Implemented task priority based on mission value, deadline urgency, hazard severity, critical-path position, information age and risk.

### Phase 5 - Elastic mission-aware slicing
The controller reallocates PRBs toward the slice serving the currently executable mission task while respecting slice bounds and the cell budget.

### Phase 6 - AoI + reliability + stability
Task success is now multi-condition: deadline, freshness and end-to-end reliability. The controller includes a minimum hold time and a per-step change limit.

### Phase 7 - Tail risk
Mission loss is evaluated over stochastic realizations and CVaR at beta=0.90 is reported rather than using only expected loss.

### Phase 8 - Experiments
The package runs multi-seed Monte Carlo, severity/PRB sensitivity and ablation studies.

### Phase 9 - Live interface
A dependency-light browser dashboard exposes the simulator as a local digital twin. Slider changes alter the simulation inputs and the next reset/run uses those inputs.

### Phase 10 - Research packaging
Reproducible CSV data, publication-style plots, a technical report and LaTeX manuscript are included.

## Novelty claim to defend

The novelty is not "O-RAN slicing" by itself. The defensible contribution is the **joint control abstraction** that makes slice resources mission-aware and risk-constrained rather than KPI-only.

1. **Mission-task graph driven slicing:** resource priority follows the currently executable task and its position in the mission DAG.
2. **Dynamic mission criticality:** priority changes with deadline slack, physical hazard, critical-path membership, AoI pressure and risk.
3. **Cross-layer radio-edge coupling:** PRB decisions influence both communication and edge-compute progress.
4. **Freshness-aware task success:** a task is not counted as successful when throughput is sufficient if required information is stale.
5. **Tail-risk protection:** the controller accounts for poor stochastic realizations using CVaR-oriented mission-loss evaluation.
6. **Control-stability constraint:** elasticity is not unconstrained. Holding time and reconfiguration limits reduce allocation oscillation.
7. **Interactive digital twin:** the research hypothesis can be demonstrated live by changing stress parameters and observing the policy response.

## Mathematical core

The conceptual objective is:

`maximize E[sum_k chi_k q_k] - lambda_rec sum_t C_rec(t) - lambda_p P_resource - lambda_c E_compute`

subject to:

`sum_s b_s(t) <= B`

`B_s_min <= b_s(t) <= B_s_max`

`T_E2E,k <= D_k-A_k`

`AoI_k <= Delta_k_max`

`P_succ,k >= 1-epsilon_k_max`

`C_rec(t) <= C_max`

`CVaR_beta(L) <= Gamma`

with the mission-loss definition:

`L = sum_k chi_k (1-q_k)`.

The full research implementation uses a fast heuristic controller rather than claiming an exact mixed-integer stochastic optimizer. This is deliberate: the simulation is intended to demonstrate the control loop and generate reproducible evidence before moving to a solver-based optimization stage.

## What remains outside this prototype

The current package is not a commercial O-RAN stack, not an ns-3 PHY/MAC implementation, and not a hardware safety controller. It does not model every 3GPP/O-RAN protocol message. The next research-grade validation should integrate a packet-level simulator, a more detailed traffic model, and a real xApp/rApp execution path.
