# MARS-O-RAN Phase 0-10: Step-by-Step Run Manual

## 1. What this package gives you

This repository contains a complete research prototype from Phase 0 through Phase 10:

0. Requirements and scenario definition.
1. Mission DAG and task execution simulator.
2. Radio and edge-compute model.
3. Baseline slicing policies.
4. Dynamic mission criticality.
5. Elastic mission-aware slicing.
6. AoI, reliability and reconfiguration control.
7. Tail-risk/CVaR analysis.
8. Monte Carlo, sensitivity and ablation experiments.
9. Live browser dashboard / digital twin.
10. Reproducible results, plots, report and LaTeX paper.

## 2. Recommended environment

Windows 10/11, Python 3.10 or later, VS Code, 4 GB+ RAM.

## 3. Install

Open a terminal in the project root:

```powershell
python --version
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

For CMD use `.venv\\Scripts\\activate`.

## 4. Verify Phase 0

```powershell
python src/validate_config.py
```

Expected structure of the result:

```text
{'status': 'PASS', 'task_count': 5, 'slice_count': 4, 'total_prbs': 100, ...}
```

## 5. Run the complete experiments

```powershell
python src/run_all.py
python src/make_figures.py
```

`run_all.py` performs the main Monte Carlo experiment, sensitivity study and component ablation study. `make_figures.py` converts the CSV outputs into PNG figures.

## 6. Run tests

```powershell
python -m unittest discover -s tests -v
```

## 7. Read the results

Open:

- `results/policy_summary.csv` - aggregate mean/std metrics and 90% VaR/CVaR.
- `results/experiment_runs.csv` - one row per seed and policy.
- `results/task_results.csv` - task-by-task completion, deadline, freshness and reliability.
- `results/timeseries_mars.csv` - per-second MARS resource allocation and network state.
- `results/sensitivity_severity_prbs.csv` - severity vs. PRB study.
- `results/ablation_results.csv` - removal of controller components.

## 8. Start the live simulation interface

```powershell
python src/web_server.py
```

Open this address in a browser:

`http://127.0.0.1:8765`

The dashboard lets you change:

- Policy: STATIC / PROPORTIONAL / MISSION_AWARE / MARS_RISK_AWARE.
- Initial incident severity.
- Total PRBs.
- Risk-aversion parameter.

Press **Reset with values** after changing parameters. Then use **Step 1 s** to observe the model timestep-by-timestep or **Run to end** for a full 300-s run. The dashboard updates PRB allocations, mission completion, deadline performance, p95 E2E latency and recent mission events.

## 9. How to demonstrate the project

### Demo A: baseline vs. MARS

1. Select `STATIC`, severity `0.60`, PRBs `100`.
2. Reset and run to end.
3. Record mission success, deadline success and reconfiguration cost.
4. Repeat with `MARS_RISK_AWARE`.
5. Compare the results in the dashboard and `results/policy_summary.csv`.

### Demo B: stress the controller

1. Select `MARS_RISK_AWARE`.
2. Set severity to `0.90`.
3. Set PRBs to `60`.
4. Reset.
5. Step through the simulation and watch SC/SV resource protection during degraded conditions.

### Demo C: show the reconfiguration mechanism

Run `PROPORTIONAL` and then `MARS_RISK_AWARE` under the same seed. Proportional allocation reacts to demand every timestep and therefore has a high reconfiguration count; MARS uses a holding time and a per-step reconfiguration limit.

## 10. What the calculations mean

### Radio rate

For slice s:

`R_s = b_s * W_PRB * log2(1 + SINR_s) * eta * FBL_s * h_s`

where `b_s` is PRB allocation, `W_PRB` is PRB bandwidth, `eta` is spectral-efficiency factor, `FBL_s` is a finite-blocklength penalty and `h_s` is a channel-quality factor.

### Transmission time

`T_tx = L / R`

where `L` is the task communication workload in bits.

### Edge compute time

`T_cmp = C / f`

where `C` is normalized compute workload and `f` is the compute rate allocated to the active task.

### End-to-end delay

`T_E2E = T_queue + T_tx + T_xhaul + T_cmp + T_feedback`

The prototype includes explicit backhaul and jitter terms and an E2E-latency proxy.

### Dynamic criticality

For task k:

`chi_k(t) = w_k [1 + a1*Urgency + a2*Hazard + a3*CriticalPath + a4*AoI + a5*Risk]`

The urgency term increases as the task deadline approaches. Hazard, critical-path membership and stale information increase the task's priority.

### AoI

The Age of Information is incremented when no fresh update arrives and reset to a small value when the slice receives a fresh update. A task succeeds only when its AoI requirement is satisfied.

### Reliability

`P_succ = P_radio * P_edge * P_backhaul`

A task must meet its maximum allowed failure probability in addition to deadline and freshness requirements.

### Reconfiguration cost

`C_rec(t) = sum_s |b_s(t) - b_s(t-1)|`

The controller limits how rapidly allocations can move and can hold an allocation for a minimum period.

### Mission loss and CVaR

`L = sum_k chi_k (1-q_k)`

where `q_k=1` only when the task satisfies the required constraints. The 90% CVaR is evaluated from the upper tail of Monte Carlo mission loss values.

## 11. Changing the research assumptions

Edit `config/scenario_v2.json` for radio, incident and controller parameters. Edit `config/tasks_v2.json` for task workload, deadline, criticality and slice mapping. After every change run Phase 0 validation before running experiments.

## 12. Reproducibility

The simulation uses fixed integer seeds. The main experiment uses seeds 20-49. The sensitivity and ablation studies use explicitly listed seeds in the source. The same configuration and seeds regenerate the CSV outputs.

## 13. Interpretation discipline

The package deliberately labels the results as a synthetic digital-twin study. Do not report the simulated millisecond values as measured 5G/O-RAN network performance. For a publishable systems paper, the next validation stage is integration with an ns-3/5G-LENA or O-RAN testbed, calibrated channel models, and a real near-RT RIC/xApp deployment.
