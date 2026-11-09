# MARS-O-RAN: Network Slicing and Optimization Code + Research Paper

**Authors:** Ishaan Jayaram Shetty, Prashant Kumar, Himanshu Kumar Sonkar (Department of Electronics and Communication Engineering), and Naman Kumar (Department of Computer Science and Engineering) — IIIT Dharwad

This package brings together the Python code that models and allocates radio resources among four slices, the experiment outputs used in the paper draft, and the LaTeX/PDF research paper.

## Important scope statement

This is a **Python software simulation/digital twin**. It models network slicing and a heuristic that allocates Physical Resource Blocks (PRBs); it does **not** configure a real 5G base station, deploy an O-RAN xApp, or send commands through the E2/A1 interfaces. Present the result as simulated policy evaluation, not as a live network deployment.

## Main code to show your supervisor

- `src/simulator.py` — **main algorithm and simulation**. The policy logic, task criticality, integer PRB allocation, radio/edge service model, task success checks, and Monte Carlo experiment code are here.
- `config/scenario_v2.json` — radio budget, PRB bounds, edge budget, incident model, controller parameters, freshness settings.
- `config/tasks_v2.json` — five-task emergency mission DAG: gas detection → gas-source localization → UGV navigation → valve inspection → valve manipulation.
- `src/run_all.py` — runs the main 30-seed-per-policy experiment, sensitivity study, and ablation study.
- `src/make_figures.py` — creates graphs from results.
- `src/web_server.py` and `web/` — interactive local browser dashboard.
- `paper/MARS_ORAN_Research_Paper_v2.tex` and `.pdf` — research paper accompanying this source.
- `src/edge_case_experiments.py` — confidence intervals, paired tests, edge-case sweeps, and the paper's figures (writes `results/extended/` and `figures/extended/`).
- `results/` and `figures/` — saved experiment outputs and plots.
- `CODE_TO_PAPER_MAP.md` — maps paper sections to source functions.

## Run on Windows 10/11

Install Python 3.10 or newer. Extract this folder, open it in VS Code, and use **Terminal → New Terminal**.

### 1. Create an environment and install dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

### 2. Validate the settings

```powershell
python src/validate_config.py
```

Expected: `status: PASS`, 5 tasks, 4 slices, 100 total PRBs.

### 3. Run the research experiments and tests

```powershell
python src/run_all.py
python src/make_figures.py
python -m unittest discover -s tests -v
```

The primary experiment uses **30 seeds for each of four policies**, i.e. 120 policy-runs, each with a nominal 300-second simulation horizon. Sensitivity and ablation runs follow the main experiment and take additional time. CSV results are written under `results/`; plots are written under `figures/`.

Alternatively, double-click `RUN_EXPERIMENTS.bat` in Windows. This creates a virtual environment if needed, installs dependencies, runs validation, experiments, graph generation, and tests.

### 4. Start the interactive dashboard

```powershell
python src/web_server.py
```

Open `http://127.0.0.1:8765`. Choose STATIC, PROPORTIONAL, MISSION_AWARE, or MARS_RISK_AWARE; change incident severity, total PRBs, or risk aversion; click **Reset with values**; then step through time or run to the end.

Alternatively, run `START_LIVE.bat` on Windows.

### 5. Run a short terminal demonstration

```powershell
python src/demo_cli.py
```

This prints simulation time, severity, active task, PRB allocations and E2E-latency proxy.

## Results to quote carefully

The included experiment table reports:

| Policy | Mission-success task fraction | Deadline-success fraction | P95 E2E (ms) | Reconfiguration cost | CVaR90 loss |
|---|---:|---:|---:|---:|---:|
| STATIC | 0.187 | 0.200 | 28.627 | 14.000 | 45.158 |
| PROPORTIONAL | 0.193 | 0.193 | 28.778 | 3413.800 | 45.125 |
| MISSION-AWARE | 0.727 | 1.000 | 28.630 | 1828.533 | 24.542 |
| MARS | 0.707 | 1.000 | 28.627 | 1029.667 | 23.258 |

These are synthetic simulator outputs. “Mission-success task fraction” means successful task instances divided by observed task instances; it is not the probability that all five tasks in a mission succeed. MISSION-AWARE has a slightly higher success fraction than MARS, while MARS has lower CVaR90 loss and lower reconfiguration cost than MISSION-AWARE for this configuration.

## What this code does not do

- It does not control real radio equipment.
- It does not implement a standards-compliant Near-RT RIC, xApp, E2 service model, or A1 policy path.
- It does not use ns-3/5G-LENA packet-level simulations or measured network traces.
- It does not solve the full stochastic mixed-integer optimization problem exactly at every step. It uses a heuristic allocation rule, and CVaR is computed from experiment outcomes for comparison.

These limitations should be included when presenting the results.
