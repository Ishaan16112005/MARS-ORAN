# Where the network slicing and optimization code is implemented

This guide identifies the actual functions in `src/simulator.py` behind the algorithm described in the research paper.

## Main functions

| Research element | Implementation location | What it does |
|---|---|---|
| Four slice definitions | `SLICES = ['SC','SV','SX','SM']` near the top of `src/simulator.py` | Establishes the slice keys used across the model. SC = robot control; SV = perception/video; SX = responder XR; SM = safety monitoring/sensing. |
| Baseline and proposed policies | `POLICIES` and `MARSOranSimulator.policy_weights()` | Calculates allocation weights under STATIC, PROPORTIONAL, MISSION_AWARE, and MARS_RISK_AWARE. |
| Dynamic task criticality | `MARSOranSimulator.task_criticality()` | Combines task value with deadline urgency, hazard pressure, critical-path weight, AoI pressure, and risk terms. |
| Network slicing / PRB optimizer | `MARSOranSimulator.allocate_prbs()` | Converts policy weights to integer PRB assignments; applies per-slice min/max, total PRB budget correction, a maximum per-step change, and MARS holding time. This is the main function to highlight when your supervisor asks where slicing happens. |
| Radio + edge service | `MARSOranSimulator.step()` | Models channel degradation, demand, PRB-dependent service, edge shares, approximate reliability and AoI; advances the active task. |
| Mission-DAG readiness | `MARSOranSimulator.ready_tasks()` | Makes a task eligible only after its predecessors finish. |
| Task pass/fail | `MARSOranSimulator.step()` in the `active.remaining_bits <= 0 and active.remaining_compute <= 0` block | Records deadline, freshness and reliability tests and marks the task success/failure. |
| Tail-risk analysis | `cvar()` and `run_experiments()` | Computes empirical CVaR90 on the distribution of mission-loss results for each policy. It is an offline evaluation metric, not an exact online CVaR-constrained solver. |
| Main experiment | `run_experiments()` | Runs 30 seeds per policy (default seed range 20–49), writes run-level/task-level CSVs and policy summaries. |
| Parameter sensitivity | `sensitivity_experiment()` | Varies incident severity and total PRBs for selected policies. |
| Ablation study | `ablation_experiment()` | Tests removal of AoI, risk reserve, hysteresis, and urgency components. |
| Live user interface | `src/web_server.py` + `web/index.html`, `web/app.js`, `web/style.css` | Sends parameter choices to a local Python simulator and returns current metrics/plots to the browser. |

## The controller, conceptually

1. Observe the current simulated channel, incident severity, active task and slice demand.
2. For STATIC, use fixed weights; for PROPORTIONAL, use demand shares.
3. For MISSION_AWARE, increase the score for the slice of the currently executable mission task, using dynamic task criticality.
4. For MARS_RISK_AWARE, add a severity-dependent reserve for robot control and safety sensing, penalize unnecessary movement from the prior allocation, and apply a holding period and per-step allocation-change limit.
5. Convert weights into integer PRBs; clip to each slice's allowed bounds.
6. Correct the total allocation so it does not exceed the configured radio budget.
7. Use the allocations in the modelled radio and edge service path, then update task progress, AoI, reliability and metrics.
8. Repeat for each time step.

## Mathematical ideas linked to the code

- **Slice budget:** `sum_s b_s(t) <= B`.
- **Bounds:** `B_min_s <= b_s(t) <= B_max_s`.
- **Transmission service-rate abstraction:** `R_s ≈ b_s W_PRB log2(1 + SINR_s) × efficiency × channel × FBL correction`.
- **Task urgency:** grows as `deadline - current_time` becomes smaller.
- **Dynamic criticality:** task value times a sum of urgency, hazard, critical-path, AoI and risk contributions.
- **Reconfiguration cost:** `sum_s abs(b_s(t) - b_s(t-1))`.
- **Mission loss:** weighted value of tasks that fail the modelled completion conditions.
- **CVaR90:** empirical mean of the worst-tail mission-loss outcomes according to the code's quantile convention.

## Algorithm pseudocode

```text
for each simulation step t:
    observe severity, shock, channel quality and slice demand
    identify currently executable mission task(s)

    if policy is STATIC:
        set fixed slice weights
    else if policy is PROPORTIONAL:
        set weights proportional to observed demand
    else:
        score executable tasks by value, urgency, hazard, critical path, AoI and risk
        map task criticality and demand to per-slice weights
        if policy is MARS_RISK_AWARE:
            add risk reserve to control/safety slices during severe conditions
            penalize avoidable changes from the previous allocation

    convert weights to integer PRBs
    enforce each slice's minimum/maximum PRB bounds
    limit per-step movement and apply MARS holding time
    repair the allocation so total PRBs fit the system budget

    derive radio service and edge-compute shares from the allocation
    update age of information, task bits, compute work and reliability
    evaluate task deadline/freshness/reliability conditions
    log allocations, events and latency proxies

summarize per-policy Monte Carlo results and empirical CVaR90 loss
```

## Accuracy note

The implementation is a heuristic simulator. It does not run a general-purpose optimizer such as a MILP/MIQP solver, and the CVaR metric is evaluated across simulated outcomes rather than imposed as a mathematically guaranteed hard constraint during every allocation decision. The paper must describe it that way.

**Implementation detail to state honestly:** the task service model uses PRB-dependent rate and edge-compute shares to advance task workloads, while the plotted P95 E2E-latency series is a separate simplified latency proxy calculated in `step()`. It should not be presented as a packet-level end-to-end delay measurement or as an exact sum of individually simulated queue/transmission/compute delays.
