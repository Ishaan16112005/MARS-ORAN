"""Recompute every number quoted in the paper text from the simulator / result CSVs.

Run after `python src/run_all.py` and `python src/edge_case_experiments.py`:
    python src/verify_paper_claims.py
Prints one line per claim and writes results/extended/paper_claims.json so the
LaTeX text can be checked against the implementation.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from simulator import MARSOranSimulator, POLICIES, SLICES, cvar  # noqa: E402

RES = ROOT / 'results' / 'extended'
SEEDS = list(range(20, 50))
claims: dict[str, object] = {}


def put(key, val):
    if isinstance(val, (np.floating, float)):
        val = round(float(val), 4)
    claims[key] = val
    print(f'{key:55s} {val}')


# ---------------------------------------------------------------- main table / paired tests
ci = pd.read_csv(RES / 'main_ci.csv').set_index('policy')
for p in POLICIES:
    for m in ['mission_success_rate', 'deadline_success_rate', 'reliability_success_rate', 'total_reconfig_cost', 'mission_loss', 'CVaR90']:
        put(f'main.{p}.{m}', f"{ci.loc[p, m]:.4f} [{ci.loc[p, m + '_lo']:.4f}, {ci.loc[p, m + '_hi']:.4f}]")
    put(f'main.{p}.full_mission_prob', ci.loc[p, 'full_mission_prob'])
rec_ma, rec_mars = ci.loc['MISSION_AWARE', 'total_reconfig_cost'], ci.loc['MARS_RISK_AWARE', 'total_reconfig_cost']
put('main.reconfig_reduction_vs_MA_pct', 100 * (1 - rec_mars / rec_ma))

paired = pd.read_csv(RES / 'paired_tests.csv')
for _, r in paired.iterrows():
    put(f"paired.{r.baseline}.{r.metric}", f"{r.mean_diff_MARS_minus_baseline:.4f} [{r.ci_lo:.4f}, {r.ci_hi:.4f}] W/T/L={r.mars_better}/{r.ties}/{r.mars_worse} p={r.wilcoxon_p:.3g}")

runs = pd.read_csv(RES / 'main_runs.csv')
for p in POLICIES:
    l = runs[runs.policy == p].mission_loss.values
    put(f'loss.{p}.mode', float(pd.Series(l).mode().iloc[0]))
    put(f'cvar_beta.{p}', {b: round(cvar(list(l), b) if b > 0 else float(np.mean(l)), 3) for b in [0.0, 0.5, 0.55, 0.7, 0.8, 0.85, 0.9, 0.95]})

tasks = pd.read_csv(RES / 'main_tasks.csv')
put('tasks.K5.success_any_policy', int(tasks[tasks.task_id == 'K5'].success.sum()))
for p in POLICIES:
    t = tasks[tasks.policy == p]
    put(f'tasks.{p}.deadline_fail_share_of_150', float((t.deadline_met == 0).sum() / 150))
    put(f'tasks.{p}.per_task_success', t.groupby('task_id').success.mean().round(3).to_dict())
put('tasks.K5.mean_start_s(MA,MARS)', float(tasks[(tasks.task_id == 'K5') & tasks.policy.isin(['MISSION_AWARE', 'MARS_RISK_AWARE'])].start_s.mean()))
put('tasks.mission_end_s(MA,MARS)', float(tasks[(tasks.task_id == 'K5') & tasks.policy.isin(['MISSION_AWARE', 'MARS_RISK_AWARE'])].finish_s.mean()))


# ---------------------------------------------------------------- reliability threshold for K5 (no load/shock penalty)
def p_succ(s):
    return (0.999 - 0.030 * s) * (0.997 - 0.025 * s) * (0.998 - 0.020 * s)
grid = np.linspace(0, 1, 100001)
put('rel.sigma_threshold_for_0.96', float(grid[np.argmax(p_succ(grid) < 0.96)]))
put('rel.sigma_threshold_for_0.94(K3)', float(grid[np.argmax(p_succ(grid) < 0.94)]))
put('rel.p_succ_at_sigma0.8', p_succ(0.8))


# ---------------------------------------------------------------- per-step traces: latency in/after mission, severity during K5, edge share
lat_in, lat_after, sev_k5 = {p: [] for p in POLICIES}, {p: [] for p in POLICIES}, []
for s in SEEDS:
    for p in ['MISSION_AWARE', 'MARS_RISK_AWARE']:
        sim = MARSOranSimulator(p, seed=s); sim.run()
        tr = pd.DataFrame(sim.state.trace)
        end = max(t.finished for t in sim.tasks if t.finished is not None)
        lat_in[p] += tr[(tr.time_s >= 20) & (tr.time_s < end)].control_latency_ms.tolist()
        lat_after[p] += tr[tr.time_s >= end].control_latency_ms.tolist()
        k5 = tr[tr.active_task == 'K5']
        sev_k5 += k5.severity.tolist()
for p in ['MISSION_AWARE', 'MARS_RISK_AWARE']:
    put(f'latency.{p}.during_mission_mean_ms', np.mean(lat_in[p]))
    put(f'latency.{p}.after_mission_mean_ms', np.mean(lat_after[p]))
put('severity.during_K5_mean', np.mean(sev_k5))


def edge_share_K2(B, policy='MISSION_AWARE', seed=20):
    sim = MARSOranSimulator(policy, seed=seed, overrides={'radio': {'total_prbs': B}})
    alloc_log = []
    orig = sim.allocate_prbs
    def wrapped(d, sev, sh):
        a = orig(d, sev, sh); alloc_log.append((sim.state.t, dict(a))); return a
    sim.allocate_prbs = wrapped
    sim.run()
    k2 = next(t for t in sim.tasks if t.id == 'K2')
    shares = []
    for t, a in alloc_log:
        if k2.started is not None and k2.started <= t < (k2.finished or 999):
            raw = {s: a[s] / B for s in SLICES}; raw['SM'] *= 1.15
            shares.append(raw['SM'] / sum(raw.values()))
    return float(np.mean(shares)), k2.finished, k2.deadline
for B in [100, 120, 150]:
    sh, fin, dl = edge_share_K2(B)
    put(f'edge.K2_share_B{B}(MA,seed20)', f'{sh:.3f} finish={fin} deadline={dl}')

# ---------------------------------------------------------------- sweeps
def sw(name):
    return pd.read_csv(RES / f'sweep_{name}.csv')
def val(df, key, v, p, col='success_mean'):
    return float(df[(df[key] == v) & (df.policy == p)][col].iloc[0])

prb = sw('total_prbs')
for B in [50, 55, 60, 70, 80, 100, 120, 150, 200]:
    put(f'sweep.prbs.B{B}', {p: round(val(prb, 'total_prbs', B, p), 3) for p in POLICIES})
sev = sw('initial_severity')
for v in [0.0, 0.2, 0.4, 0.8, 0.9, 1.0]:
    put(f'sweep.sev.{v}', {p: f"{val(sev, 'initial_severity', v, p):.3f} [{val(sev, 'initial_severity', v, p, 'success_lo'):.3f},{val(sev, 'initial_severity', v, p, 'success_hi'):.3f}] cvar={val(sev, 'initial_severity', v, p, 'CVaR90'):.2f}" for p in POLICIES})
shk = sw('shock_probability')
for v in [0.0, 0.3]:
    put(f'sweep.shock.{v}', {p: round(val(shk, 'shock_probability', v, p), 3) for p in POLICIES})
dl = sw('deadline_scale')
for v in [0.5, 0.6, 0.7, 0.8, 0.9, 1.5]:
    put(f'sweep.deadline.{v}', {p: f"{val(dl, 'deadline_scale', v, p):.3f} [{val(dl, 'deadline_scale', v, p, 'success_lo'):.3f},{val(dl, 'deadline_scale', v, p, 'success_hi'):.3f}]" for p in POLICIES})
wl = sw('workload_scale')
for v in [0.25, 0.5, 1.25, 1.5, 2.0, 3.0]:
    put(f'sweep.workload.{v}', {p: round(val(wl, 'workload_scale', v, p), 3) for p in POLICIES})
    put(f'sweep.workload.{v}.tasks_observed', {p: round(val(wl, 'workload_scale', v, p, 'tasks_observed_mean'), 2) for p in POLICIES})
grid_df = pd.read_csv(RES / 'stress_grid.csv')
g = grid_df.pivot_table(index=['severity', 'total_prbs'], columns='policy', values='success_mean')
put('grid.max_abs_diff_MARS_vs_MA', float((g['MARS_RISK_AWARE'] - g['MISSION_AWARE']).abs().max()))
put('grid.cells_adaptive_below_nonadaptive', [f'sev={i[0]},B={i[1]}' for i, r in g.iterrows()
                                              if max(r.MARS_RISK_AWARE, r.MISSION_AWARE) < max(r.STATIC, r.PROPORTIONAL) - 1e-9])
for name, key in [('risk_aversion', 'risk_aversion'), ('hold_time_s', 'hold_time_s'), ('max_reconfig_per_step', 'max_reconfig_per_step')]:
    d = sw(name)
    put(f'sweep.{name}', {str(r[key]): (round(r.success_mean, 3), round(r.reconfig_mean, 1)) for _, r in d.iterrows()})
ab = pd.read_csv(RES / 'ablation_30seeds.csv')
put('ablation', {r.variant: (round(r.success_mean, 3), round(r.reconfig_mean, 1), round(r.CVaR90, 2)) for _, r in ab.iterrows()})
sat = pd.read_csv(RES / 'mars_weight_saturation.csv')
mars20 = tasks[(tasks.policy == 'MARS_RISK_AWARE') & (tasks.seed == 20)]
s0, s1 = int(mars20.start_s.min()), int(mars20.finish_s.max())
put('saturation.mission_window_seed20', f'{s0}-{s1}')
put('saturation.min_max_weight_in_mission', float(sat[(sat.t >= s0) & (sat.t < s1)].max_weight.min()))

(RES / 'paper_claims.json').write_text(json.dumps(claims, indent=1, default=str), encoding='utf-8')
print('\nwritten', RES / 'paper_claims.json')


# ---------------------------------------------------------------- B=120 task-level failure anatomy, stress-grid cells, runtime
import time
for p in ['MISSION_AWARE', 'MARS_RISK_AWARE']:
    rows = []
    for s in SEEDS:
        sim = MARSOranSimulator(p, seed=s, overrides={'radio': {'total_prbs': 120}}); sim.run(); rows += sim.state.task_rows
    t = pd.DataFrame(rows)
    put(f'B120.{p}.K2_deadline_miss', float((t[t.task_id == 'K2'].deadline_met == 0).mean()))
    put(f'B120.{p}.K3_reliability_fail', float((t[t.task_id == 'K3'].reliability_ok == 0).mean()))
for (sv, B) in [(0.8, 120), (1.0, 60), (0.2, 100), (0.6, 120)]:
    put(f'grid.sev{sv}_B{B}', g.loc[(sv, B)].round(3).to_dict())
t0 = time.perf_counter()
for p in POLICIES: MARSOranSimulator(p, seed=20).run()
put('runtime.four_policies_one_seed_s', time.perf_counter() - t0)
(RES / 'paper_claims.json').write_text(json.dumps(claims, indent=1, default=str), encoding='utf-8')
