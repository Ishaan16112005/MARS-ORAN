"""Check that every number quoted in paper/main.tex matches the experiment outputs.

Run after src/experiments.py and src/make_tables.py:
    python src/verify_paper_claims.py
For each claim the value is recomputed from results/paper/*.csv / paper_numbers.json, formatted
the way the paper prints it, and searched for in the LaTeX source. Exit code 1 if any check fails.
(Tables IV and V are generated from the same CSVs by src/make_tables.py and need no check.)
"""
from __future__ import annotations
import json, math, re, sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from simulator import fbl_factor, cvar, cvar_threshold  # noqa: E402

RES = ROOT / 'results' / 'paper'
TEX = re.sub(r'\s+', ' ', (ROOT / 'paper' / 'main.tex').read_text(encoding='utf-8'))
N = json.loads((RES / 'paper_numbers.json').read_text())
ci = pd.read_csv(RES / 'main_ci.csv').set_index(['op', 'policy'])
pt = pd.read_csv(RES / 'paired_tests.csv').set_index(['op', 'baseline', 'metric'])
ab = pd.read_csv(RES / 'ablation.csv').set_index(['op', 'variant'])
tasks = pd.read_csv(RES / 'main_tasks.csv'); runs = pd.read_csv(RES / 'main_runs.csv')
sw = lambda n: pd.read_csv(RES / f'sweep_{n}.csv')
fails = []


def check(desc, text):
    ok = text in TEX
    print(f"{'OK  ' if ok else 'FAIL'} {desc:60s} '{text}'")
    if not ok: fails.append(desc)


f3 = lambda v: f'{v:.3f}'; f2 = lambda v: f'{v:.2f}'; f1 = lambda v: f'{v:.1f}'; f0 = lambda v: f'{v:.0f}'
pct = lambda a, b: f'{100 * (1 - a / b):.1f}'
c = lambda op, p, m: ci.loc[(op, p), m]

# ---- Section VII-A/B: main results and paired tests
check('OP-A STATIC success', f3(c('A_benign', 'STATIC', 'mission_success_rate')))
check('OP-A PROPORTIONAL success', f3(c('A_benign', 'PROPORTIONAL', 'mission_success_rate')))
lo = min(c('A_benign', p, 'mission_success_rate') for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS'])
hi = max(c('A_benign', p, 'mission_success_rate') for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS'])
check('OP-A mission-oriented success range', f'{f3(lo)}--{f3(hi)}')
check('OP-B STATIC success', f3(c('B_severe', 'STATIC', 'mission_success_rate')))
check('OP-B STATIC deadline-fail share', f"{100 * N['tasks.B_severe.STATIC.deadline_fail_share']:.0f}\\%")
for p in ['MARS', 'MISSION_AWARE', 'MARS_V0', 'MYOPIC_OPT']:
    check(f'OP-A {p} reconfig mission', f0(c('A_benign', p, 'reconfig_mission')))
for p in ['MISSION_AWARE', 'MARS_V0', 'MARS']:
    check(f'OP-A {p} reconfig idle', f0(c('A_benign', p, 'reconfig_idle')))
for op in ['A_benign', 'C_concurrent']:
    for b in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0']:
        check(f'{op} reconfig reduction vs {b}', pct(c(op, 'MARS', 'reconfig_mission'), c(op, b, 'reconfig_mission')) + '\\%')
for (op, b) in [('A_benign', 'MISSION_AWARE')]:
    check('OP-A ties vs MISSION-AWARE', f"{int(pt.loc[(op, b, 'mission_success_rate'), 'ties'])} of 300")
minp = min(pt.loc[(op, b, m), 'wilcoxon_p'] for op in ['A_benign', 'C_concurrent'] for b in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0']
           for m in ['mission_success_rate', 'mission_loss'])
check('OP-A/C smallest p (rounded down to 2 dp)', f'$p\\ge{math.floor(minp * 100) / 100:.2f}$')
s = pt.loc[('B_severe', 'MISSION_AWARE', 'mission_success_rate')]; l = pt.loc[('B_severe', 'MISSION_AWARE', 'mission_loss')]
check('OP-B success diff vs MA', f'{-s.mean_diff:.3f} in success against MISSION-AWARE ($p={s.wilcoxon_p:.3f}$)')
check('OP-B loss diff vs MA', f'{l.mean_diff:.2f} in mean loss ($p={l.wilcoxon_p:.3f}$)')
check('abstract OP-B success loss', f'{-100 * s.mean_diff:.1f} percentage points of success ($p={s.wilcoxon_p:.3f}$)')
r = [pct(c(op, 'MARS', 'reconfig_mission'), c(op, 'MISSION_AWARE', 'reconfig_mission')) for op in ['A_benign', 'C_concurrent']]
check('abstract reduction vs MA (rounded)', f'{round(float(r[0]))}--{round(float(r[1]))}\\%')
r = [pct(c(op, 'MARS', 'reconfig_mission'), c(op, 'MYOPIC_OPT', 'reconfig_mission')) for op in ['A_benign', 'C_concurrent']]
check('abstract reduction vs MYOPIC (rounded)', f'{round(float(r[0]))}--{round(float(r[1]))}\\%')

# ---- Section VII-C: CVaR estimator note (R0 archive)
old = pd.read_csv(ROOT / 'archive' / 'R0' / 'results' / 'experiment_runs.csv')
check('R0 threshold CVaR MARS-v0', f2(cvar_threshold(old[old.policy == 'MARS_RISK_AWARE'].mission_loss, .9)))
check('R0 exact CVaR (both)', f"gives {f2(cvar(old[old.policy == 'MARS_RISK_AWARE'].mission_loss, .9))} for both")
assert abs(cvar(old[old.policy == 'MARS_RISK_AWARE'].mission_loss, .9) - cvar(old[old.policy == 'MISSION_AWARE'].mission_loss, .9)) < 1e-9

# ---- Section III / VII-D: model facts
stale = tasks[tasks.freshness_ok == 0]
check('stale task instances', f'{len(tasks):,}'.replace(',', '{,}') + f' task instances, {len(stale)} failed')
assert set(stale.policy) <= {'PROPORTIONAL'}
F = [float(fbl_factor(10 ** ((12 + 7 * math.log10(0.45)) / 10), 10 * 1800)), float(fbl_factor(10 ** 1.8, 60 * 1800))]
check('FBL range', f'$F_s\\in[{F[0]:.3f},{F[1]:.3f}]$')
p_succ = lambda x: (0.999 - 0.030 * x) * (0.997 - 0.025 * x) * (0.998 - 0.020 * x)
g = np.linspace(0, 1, 100001)
check('K5 severity threshold', f'$\\sigma>{g[np.argmax(p_succ(g) < 0.96)]:.2f}$')
check('K3 severity threshold', f'$\\sigma\\approx{g[np.argmax(p_succ(g) < 0.94)]:.2f}$')
k5 = [N[f'tasks.A_benign.{p}.per_task_success']['K5'] for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS']]
check('OP-A K5 success range', f'{100 * min(k5):.0f}--{100 * max(k5):.0f}\\% of runs')
check('OP-B K3 success MARS vs MA', f"{N['tasks.B_severe.MARS.per_task_success']['K3']:.3f} vs.\\ {N['tasks.B_severe.MISSION_AWARE.per_task_success']['K3']:.3f}")
check('OP-B K3 finish', f"{N['tasks.B_severe.MARS.K3_finish_mean']:.1f}\\,s instead of {N['tasks.B_severe.MISSION_AWARE.K3_finish_mean']:.1f}\\,s")
check('OP-B K3 severity', f"({N['tasks.B_severe.MARS.K3_severity_at_finish']:.3f} vs.\\ {N['tasks.B_severe.MISSION_AWARE.K3_severity_at_finish']:.3f})")

# ---- Section VII-E: dynamics
e = {p: N[f'seed20.A_benign.{p}.mission_end'] for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS']}
assert e['MISSION_AWARE'] == e['MYOPIC_OPT']
check('seed 20 mission ends', f"ends at {e['MISSION_AWARE']}\\,s under MISSION-AWARE and MYOPIC-OPT, at {e['MARS_V0']}\\,s under MARS-v0, and at {e['MARS']}\\,s under MARS")
ma, me = N['mission_end.A_benign.MISSION_AWARE'], N['mission_end.A_benign.MARS']
check('mean mission end', f'{me - ma:.1f}\\,s later than MISSION-AWARE ({me:.1f} vs.\\ {ma:.1f}\\,s)')
check('OP-C saturation v0', f"averages {N['saturation.C_concurrent.MARS_V0.mean_max_weight_in_mission']:.3f} during the mission")
check('OP-C saturation MARS', f"averages {N['saturation.C_concurrent.MARS.mean_max_weight_in_mission']:.3f}")
lat = {p: N[f'latency.A_benign.{p}'] for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS']}
check('latency during mission range', f"{min(v['mission'] for v in lat.values()):.1f}--{max(v['mission'] for v in lat.values()):.1f}\\,ms during the mission")
check('latency after (MARS, MA)', f"{lat['MARS']['after']:.1f} and {lat['MISSION_AWARE']['after']:.1f}\\,ms for MARS and MISSION-AWARE")
check('latency after (MYOPIC, v0)', f"{lat['MYOPIC_OPT']['after']:.1f}--{lat['MARS_V0']['after']:.1f}\\,ms for MYOPIC-OPT and MARS-v0")

# concurrency split (recomputed, 100 seeds)
from simulator import run_one  # noqa: E402
from operating_points import OPS  # noqa: E402
split = {}
for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS']:
    sc, sm = [], []
    for sd in range(20, 120):
        _, sim = run_one(p, sd, overrides=OPS['C_concurrent'], return_sim=True)
        tr = pd.DataFrame(sim.state.trace); m = tr.active_task.str.contains('K2') & tr.active_task.str.contains('K3')
        sc += tr.prb_SC[m].tolist(); sm += tr.prb_SM[m].tolist()
    split[p] = (round(np.mean(sc)), round(np.mean(sm)))
check('concurrency MA split', f"gives {split['MISSION_AWARE'][0]} PRBs to SC and {split['MISSION_AWARE'][1]} to SM")
check('concurrency MARS/MYOPIC split', f"MARS gives {split['MARS'][0]} and {split['MARS'][1]}, close to the {split['MYOPIC_OPT'][0]} and {split['MYOPIC_OPT'][1]}")

# ---- Section VIII: sweeps
v = lambda df, key, x, p, col='success_mean': float(df[(df[key] == x) & (df.policy == p)][col].iloc[0])
prb, prbs = sw('total_prbs'), sw('total_prbs_scaledcaps').rename(columns={'total_prbs_scaledcaps': 'total_prbs'})
b200 = [v(prb, 'total_prbs', 200, p) for p in prb.policy.unique()]
check('B=200 fixed caps all ~', f'(0.19 for every policy)'); assert all(abs(x - 0.19) < 0.01 for x in b200)
check('B=200 scaled caps', f"MISSION-AWARE reaches {f3(v(prbs, 'total_prbs', 200, 'MISSION_AWARE'))} and MARS {f3(v(prbs, 'total_prbs', 200, 'MARS'))}")
check('B=55/60 MARS', f"{f3(v(prb, 'total_prbs', 55, 'MARS'))} and {f3(v(prb, 'total_prbs', 60, 'MARS'))}, against {f3(v(prb, 'total_prbs', 55, 'MISSION_AWARE'))} and {f3(v(prb, 'total_prbs', 60, 'MISSION_AWARE'))}")
check('edge share 46/(B+6)', f'from {100 * 46 / 106:.0f}\\% at $B=100$ to {100 * 46 / 156:.0f}\\% at $B=150$')
sev = sw('initial_severity')
r0 = sev[(sev.initial_severity == 0.0)].set_index('policy')
check('sigma0=0 MARS', f"{f3(r0.loc['MARS', 'success_mean'])} [{f3(r0.loc['MARS', 'success_lo'])}, {f3(r0.loc['MARS', 'success_hi'])}]")
check('sigma0=0 MA', f"{f3(r0.loc['MISSION_AWARE', 'success_mean'])} [{f3(r0.loc['MISSION_AWARE', 'success_lo'])}, {f3(r0.loc['MISSION_AWARE', 'success_hi'])}]")
check('sigma0=0 CVaR', f"{f2(r0.loc['MARS', 'CVaR90'])} vs.\\ {f2(r0.loc['MISSION_AWARE', 'CVaR90'])}")
check('sigma0=1 MARS vs MA', f"{f3(v(sev, 'initial_severity', 1.0, 'MARS'))} against {f3(v(sev, 'initial_severity', 1.0, 'MISSION_AWARE'))}")
shk = sw('shock_probability')
check('no shocks all 1.000', '(1.000)'); assert all(v(shk, 'shock_probability', 0.0, p) >= 0.998 for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS'])
check('p_sh=0.08', f"({f3(v(shk, 'shock_probability', 0.08, 'MARS'))} and {f3(v(shk, 'shock_probability', 0.08, 'MARS_V0'))} vs.\\ {f3(v(shk, 'shock_probability', 0.08, 'MISSION_AWARE'))} and {f3(v(shk, 'shock_probability', 0.08, 'MYOPIC_OPT'))}")
storm = [v(shk, 'shock_probability', 0.3, p) for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS']]
check('shock storm range', f'reach {min(storm):.2f}--{max(storm):.2f}')
dl, wl = sw('deadline_scale'), sw('workload_scale')
check('deadline 0.7', f"MARS reaches {f3(v(dl, 'deadline_scale', 0.7, 'MARS'))} against {f3(v(dl, 'deadline_scale', 0.7, 'MISSION_AWARE'))}")
assert v(dl, 'deadline_scale', 0.7, 'MISSION_AWARE') == v(dl, 'deadline_scale', 0.7, 'MYOPIC_OPT') and v(dl, 'deadline_scale', 0.5, 'MARS') == 0
check('deadline 1.5 STATIC/PROP', f"({f3(v(dl, 'deadline_scale', 1.5, 'STATIC'))} and {f3(v(dl, 'deadline_scale', 1.5, 'PROPORTIONAL'))})")
check('workload 1.5', f"MARS reaches {f3(v(wl, 'workload_scale', 1.5, 'MARS'))} against {f3(v(wl, 'workload_scale', 1.5, 'MISSION_AWARE'))}")
oth = [v(wl, 'workload_scale', x, p) for x in (2.0, 3.0) for p in ['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0']]
check('workload 2x/3x others', f'reach {min(oth):.2f}--{max(oth):.2f}')
light = [v(wl, 'workload_scale', 0.25, p) for p in wl.policy.unique()]
check('light load range', f'reach {min(light):.2f}--{max(light):.2f}')
grid = pd.read_csv(RES / 'stress_grid.csv').pivot_table(index=['severity', 'total_prbs'], columns='policy', values='success_mean')
d = grid.MARS - grid.MISSION_AWARE
check('grid close cells', f'in {int((d.abs() <= 0.03).sum())} of 20 cells and behind by more in the other {int((d < -0.03).sum())}')
check('grid worst cell', f'by up to {-d.min():.2f} at $\\sigma_0={d.idxmin()[0]}$, $B={d.idxmin()[1]}$')

# ---- Section VIII-E: parameters and ablation
tp = lambda op: sw(f'mars_temperature_{op}').rename(columns={f'mars_temperature_{op}': 'x'})
t_a = tp('A_benign')
check('tau 0.05 -> 0.8 reconfig', f"falls from {f0(v(t_a, 'x', 0.05, 'MARS', 'reconfig_mission_mean'))} to {f0(v(t_a, 'x', 0.8, 'MARS', 'reconfig_mission_mean'))} PRB-steps")
check('tau 1.6 OP-B', f"({f3(v(tp('B_severe'), 'x', 1.6, 'MARS'))} at OP-B)")
rs = sw('mars_reserve_scale_B_severe').rename(columns={'mars_reserve_scale_B_severe': 'x'})
check('R0=0.8 OP-B', f"lowers it at OP-B ({f3(v(rs, 'x', 0.8, 'MARS'))})")
a = lambda op, var, col: ab.loc[(op, var), col]
check('ablation fixed hold', f"success drops to {f3(a('A_benign', 'fixed hold (no slack/release)', 'success_mean'))} at OP-A and {f3(a('B_severe', 'fixed hold (no slack/release)', 'success_mean'))} at OP-B")
check('ablation saturated softmax reconfig', f"raises reconfiguration to {f0(a('A_benign', 'saturated softmax (tau=0.05)', 'reconfig_mission_mean'))} PRB-steps")
check('ablation no hold reconfig', f"raises it to {f0(a('A_benign', 'no hold time', 'reconfig_mission_mean'))}")
check('ablation no damping reconfig', f"changes little ({f0(a('A_benign', 'no damping', 'reconfig_mission_mean'))})")
check('ablation no criticality success', f"({f3(a('A_benign', 'no criticality terms', 'success_mean'))} vs.\\ {f3(a('A_benign', 'MARS (full)', 'success_mean'))} at OP-A, {f3(a('C_concurrent', 'no criticality terms', 'success_mean'))} vs.\\ {f3(a('C_concurrent', 'MARS (full)', 'success_mean'))} at OP-C)")
inc = [a(op, 'no criticality terms', 'reconfig_mission_mean') / a(op, 'MARS (full)', 'reconfig_mission_mean') - 1 for op in ['A_benign', 'B_severe', 'C_concurrent']]
check('ablation no criticality reconfig increase', f'by {100 * min(inc):.0f}--{100 * max(inc):.0f}\\%')
check('ablation v0 reserve+penalty', f"({f3(a('A_benign', 'v0: no reserve + no penalty', 'success_mean'))} vs.\\ {f3(a('A_benign', 'MARS-v0 (full)', 'success_mean'))} and {f0(a('A_benign', 'v0: no reserve + no penalty', 'reconfig_mission_mean'))} vs.\\ {f0(a('A_benign', 'MARS-v0 (full)', 'reconfig_mission_mean'))} PRB-steps at OP-A)")
db = max(abs(a('A_benign', 'env: no edge bonus (MARS)', 'success_mean') - a('A_benign', 'MARS (full)', 'success_mean')),
         abs(a('A_benign', 'env: no edge bonus (MISSION-AWARE)', 'success_mean') - c('A_benign', 'MISSION_AWARE', 'mission_success_rate')))
check('edge-bonus ablation max change', f'by at most {db:.3f} at OP-A')

# ---- parameters in Table II vs config
cfg = json.loads((ROOT / 'config' / 'scenario_v2.json').read_text())['mars']
check('Table II MARS params', f"{cfg['temperature']:g}, {cfg['damping']:g}, {cfg['hold_time_s']}\\,s, {cfg['slack_ref_s']:g}\\,s, {cfg['reserve_scale']:g} (tuned)")
tune = pd.read_csv(RES / 'mars_tuning.csv')
check('tuning grid size', f'({len(tune)} configurations)')

print(f'\n{len(fails)} failed checks' + (': ' + ', '.join(fails) if fails else ''))
sys.exit(1 if fails else 0)
