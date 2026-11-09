# MARS-O-RAN Network Slicing Algorithm — Quick Explanation

## Inputs

- Total physical resource blocks `B`.
- Minimum and maximum PRBs for four slices.
- Current traffic-demand estimate per slice.
- Current incident severity and network-shock status.
- Current mission task and its deadline, task value and hazard weight.
- Prior PRB allocation and controller settings.

## Controller steps

1. **Measure/model current conditions:** compute incident severity, channel quality, edge availability, backhaul availability and traffic demand.
2. **Find active task:** the mission dependency graph allows only tasks whose predecessors have completed.
3. **Calculate criticality:** the score uses task value multiplied by a priority factor influenced by deadline urgency, hazard, critical-path position, Age of Information (AoI), and risk.
4. **Select policy behavior:**
   - `STATIC`: fixed distribution.
   - `PROPORTIONAL`: weights follow traffic demand.
   - `MISSION_AWARE`: task-criticality bonus moves resources toward the slice for the current mission task.
   - `MARS_RISK_AWARE`: adds a severity-dependent reserve to robot-control and safety-sensing slices and includes allocation-change penalties/holding time.
5. **Allocate integer PRBs:** convert weights to integer PRBs, apply minimum and maximum slice limits, cap the per-step movement, then repair the total to fit the radio budget.
6. **Serve work:** use the allocation to compute the modeled radio data rate and slice edge share.
7. **Evaluate outcome:** advance remaining bits and compute work; update AoI and reliability; check task deadline, freshness and reliability conditions.
8. **Log results:** save PRB history, task events, end-to-end latency proxies, reconfiguration cost and mission loss.
9. **Compare policies:** repeat across seeds and calculate mean/std metrics and empirical VaR/CVaR tail loss.

## What “optimized network slicing” means here

The software chooses a resource allocation rather than using the same fixed allocation for every situation. The controller is a parameterized heuristic; it is not an exact global optimizer, and it has not been deployed on a physical radio network. The word “optimization” in the paper should be presented as heuristic resource optimization inside a simulated digital twin.
