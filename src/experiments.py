"""All experiments, statistics and figures of the paper (Revision 1 onward).

Run:  python src/experiments.py            (~10 min on 16 cores)
Outputs: results/paper/*.csv, results/paper/paper_numbers.json,
         figures/paper/*.pdf|png (PDFs are also copied to paper/figures/).

Seeds: evaluation 20-319 (300 paired seeds) for the three operating points and the ablations;
       20-119 (100 seeds) for the sweeps. MARS parameters were selected on disjoint tuning
       seeds 1000-1099 by src/tune_mars.py.
"""
from __future__ import annotations
import json, shutil, sys, time
from multiprocessing import Pool, cpu_count
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from simulator import MARSOranSimulator, POLICIES, SLICES, cvar, deep_update, run_one  # noqa: E402
from operating_points import OPS, OP_LABEL  # noqa: E402

RES = ROOT / 'results' / 'paper'; RES.mkdir(parents=True, exist_ok=True)
FIG = ROOT / 'figures' / 'paper'; FIG.mkdir(parents=True, exist_ok=True)
PFIG = ROOT / 'paper' / 'figures'; PFIG.mkdir(parents=True, exist_ok=True)

EVAL_SEEDS = list(range(20, 320))
SWEEP_SEEDS = list(range(20, 120))
TASK_IDS = ['K1', 'K2', 'K3', 'K4', 'K5']
LABEL = {'STATIC': 'STATIC', 'PROPORTIONAL': 'PROPORTIONAL', 'MISSION_AWARE': 'MISSION-AWARE', 'MYOPIC_OPT': 'MYOPIC-OPT',
         'MARS_V0': 'MARS-v0', 'MARS': 'MARS'}
COLOR = {'MARS': '#2a78d6', 'MISSION_AWARE': '#eb6834', 'PROPORTIONAL': '#1baf7a', 'STATIC': '#eda100',
         'MYOPIC_OPT': '#7a5cc4', 'MARS_V0': '#8c8c88'}
MARKER = {'MARS': 'o', 'MISSION_AWARE': 's', 'PROPORTIONAL': '^', 'STATIC': 'D', 'MYOPIC_OPT': 'P', 'MARS_V0': 'v'}
LSTYLE = {p: ('--' if p in ('MARS_V0', 'MYOPIC_OPT') else '-') for p in POLICIES}
SLICE_COLOR = {'SC': '#2a78d6', 'SV': '#eb6834', 'SX': '#1baf7a', 'SM': '#eda100'}
INK, MUTED, GRID = '#0b0b0b', '#52514e', '#e4e3df'
NUM: dict = {}          # every number quoted in the paper is stored here

plt.rcParams.update({
    'font.size': 8, 'axes.titlesize': 8.5, 'axes.labelsize': 8, 'legend.fontsize': 7, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
    'axes.edgecolor': MUTED, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': MUTED, 'axes.grid': True,
    'grid.color': GRID, 'grid.linewidth': 0.6, 'axes.axisbelow': True, 'axes.spines.top': False, 'axes.spines.right': False,
    'lines.linewidth': 1.5, 'lines.markersize': 4, 'legend.frameon': False, 'savefig.bbox': 'tight', 'pdf.fonttype': 42})
ONE_COL, TWO_COL = 3.5, 7.16


# ---------------------------------------------------------------- parallel runner
def _job(a):
    key, policy, seed, ov, dls, wls, keep_tasks = a
    res, sim = run_one(policy, seed, overrides=ov, deadline_scale=dls, workload_scale=wls, return_sim=True)
    tr = sim.state.trace
    env_sig = hash(tuple((r['severity'], r['shock']) for r in tr))
    return key, res, (sim.state.task_rows if keep_tasks else None), env_sig


def run_many(jobs):
    with Pool(max(1, cpu_count() - 2)) as pool:
        return pool.map(_job, jobs, chunksize=8)


def bootstrap_ci(x, stat=np.mean, n=4000, alpha=0.05, seed=7):
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    boots = np.array([stat(x[i]) for i in idx])
    return float(stat(x)), float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2))


CV = lambda a: cvar(list(a), .9)


# ---------------------------------------------------------------- experiments
def main_experiment():
    jobs = [((op, p, s), p, s, ov, 1.0, 1.0, True) for op, ov in OPS.items() for p in POLICIES for s in EVAL_SEEDS]
    out = run_many(jobs)
    runs, tasks, sig = [], [], {}
    for (op, p, s), res, tr, es in out:
        runs.append({'op': op, **res})
        tasks += [{'op': op, **r} for r in tr]
        sig.setdefault((op, s), set()).add(es)
    assert all(len(v) == 1 for v in sig.values()), 'environment differs across policies for a seed'
    rdf, tdf = pd.DataFrame(runs), pd.DataFrame(tasks)
    rdf.to_csv(RES / 'main_runs.csv', index=False); tdf.to_csv(RES / 'main_tasks.csv', index=False)
    NUM['common_random_numbers_verified'] = True
    return rdf, tdf


def statistics(rdf):
    rows, prow = [], []
    for op in OPS:
        for p in POLICIES:
            sub = rdf[(rdf.op == op) & (rdf.policy == p)]
            row = {'op': op, 'policy': p, 'n': len(sub)}
            for m in ['mission_success_rate', 'deadline_success_rate', 'reliability_success_rate', 'full_mission',
                      'total_reconfig_cost', 'reconfig_mission', 'reconfig_idle', 'mission_loss']:
                row[m], row[m + '_lo'], row[m + '_hi'] = bootstrap_ci(sub[m])
            row['CVaR90'], row['CVaR90_lo'], row['CVaR90_hi'] = bootstrap_ci(sub.mission_loss, stat=CV)
            rows.append(row)
        mars = rdf[(rdf.op == op) & (rdf.policy == 'MARS')].set_index('seed')
        for p in POLICIES[:-1]:
            other = rdf[(rdf.op == op) & (rdf.policy == p)].set_index('seed')
            for m in ['mission_loss', 'mission_success_rate', 'reconfig_mission', 'total_reconfig_cost']:
                d = (mars[m] - other[m]).loc[EVAL_SEEDS].values
                mean, lo, hi = bootstrap_ci(d)
                nz = d[d != 0]
                pval = float(wilcoxon(nz).pvalue) if len(nz) > 0 else 1.0
                better = (d > 0) if m == 'mission_success_rate' else (d < 0)
                worse = (d < 0) if m == 'mission_success_rate' else (d > 0)
                prow.append({'op': op, 'baseline': p, 'metric': m, 'mean_diff': mean, 'ci_lo': lo, 'ci_hi': hi,
                             'wins': int(better.sum()), 'ties': int((d == 0).sum()), 'losses': int(worse.sum()), 'n_eff': len(nz), 'wilcoxon_p': pval})
    ci, paired = pd.DataFrame(rows), pd.DataFrame(prow)
    ci.to_csv(RES / 'main_ci.csv', index=False); paired.to_csv(RES / 'paired_tests.csv', index=False)
    for _, r in ci.iterrows():
        for m in ['mission_success_rate', 'full_mission', 'total_reconfig_cost', 'reconfig_mission', 'reconfig_idle', 'mission_loss', 'CVaR90']:
            NUM[f'main.{r.op}.{r.policy}.{m}'] = [round(r[m], 4), round(r[m + '_lo'], 4), round(r[m + '_hi'], 4)]
    for _, r in paired.iterrows():
        NUM[f'paired.{r.op}.{r.baseline}.{r.metric}'] = {'mean': round(r.mean_diff, 4), 'ci': [round(r.ci_lo, 4), round(r.ci_hi, 4)],
                                                        'WTL': [r.wins, r.ties, r.losses], 'n_eff': r.n_eff, 'p': float(f'{r.wilcoxon_p:.3g}')}
    return ci, paired


def sweep(name, values, make_kwargs, policies=POLICIES, seeds=SWEEP_SEEDS, base=None):
    base = base or {}
    jobs = []
    for v in values:
        kw = make_kwargs(v)
        ov = deep_update(base, kw.get('overrides', {}))
        for p in policies:
            for s in seeds:
                jobs.append(((v, p, s), p, s, ov, kw.get('deadline_scale', 1.0), kw.get('workload_scale', 1.0), False))
    out = run_many(jobs)
    raw = pd.DataFrame([{name: k[0], 'policy': k[1], 'seed': k[2], **res} for k, res, _, _ in out])
    rows = []
    for (v, p), sub in raw.groupby([name, 'policy'], sort=False):
        m, lo, hi = bootstrap_ci(sub.mission_success_rate, n=1000)
        c, clo, chi = bootstrap_ci(sub.mission_loss, stat=CV, n=1000)
        rows.append({name: v, 'policy': p, 'success_mean': m, 'success_lo': lo, 'success_hi': hi, 'loss_mean': sub.mission_loss.mean(),
                     'CVaR90': c, 'CVaR90_lo': clo, 'CVaR90_hi': chi, 'reconfig_mean': sub.total_reconfig_cost.mean(),
                     'reconfig_mission_mean': sub.reconfig_mission.mean(), 'tasks_observed_mean': sub.tasks_observed.mean(),
                     'full_mission_mean': sub.full_mission.mean()})
    df = pd.DataFrame(rows)
    df.to_csv(RES / f'sweep_{name}.csv', index=False)
    raw[[name, 'policy', 'seed', 'mission_success_rate', 'mission_loss', 'total_reconfig_cost', 'reconfig_mission', 'tasks_observed']].to_csv(
        RES / f'sweep_{name}_runs.csv', index=False)
    print(f'  sweep {name}: {len(values)} values x {len(policies)} policies x {len(seeds)} seeds')
    for _, r in df.iterrows():
        NUM[f'sweep.{name}.{r[name]}.{r.policy}'] = {'success': round(r.success_mean, 3), 'ci': [round(r.success_lo, 3), round(r.success_hi, 3)],
                                                    'cvar': round(r.CVaR90, 2), 'reconfig': round(r.reconfig_mean, 1), 'tasks_obs': round(r.tasks_observed_mean, 2)}
    return df


ABLATIONS = {
    'MARS (full)': ('MARS', {}),
    'no criticality terms': ('MARS', {'controller': {'alpha_urgency': 0, 'alpha_hazard': 0, 'alpha_critical_path': 0, 'alpha_aoi': 0}}),
    'saturated softmax (tau=0.05)': ('MARS', {'mars': {'temperature': 0.05}}),
    'with risk reserve (R0=0.2)': ('MARS', {'mars': {'reserve_scale': 0.2}}),
    'no damping': ('MARS', {'mars': {'damping': 0.0}}),
    'no hold time': ('MARS', {'mars': {'hold_time_s': 0}}),
    'fixed hold (no slack/release)': ('MARS', {'mars': {'slack_ref_s': 0, 'release_on_task_change': False}}),
    'no damping + no hold': ('MARS', {'mars': {'damping': 0.0, 'hold_time_s': 0}}),
    'MARS-v0 (full)': ('MARS_V0', {}),
    'v0: no reserve': ('MARS_V0', {'mars_v0': {'risk_reserve_prbs': 0}}),
    'v0: no penalty': ('MARS_V0', {'mars_v0': {'reconfig_penalty': 0.0}}),
    'v0: no reserve + no penalty': ('MARS_V0', {'mars_v0': {'risk_reserve_prbs': 0, 'reconfig_penalty': 0.0}}),
    'v0: no hold time': ('MARS_V0', {'mars_v0': {'hold_time_s': 0}}),
    'env: no edge bonus (MARS)': ('MARS', {'edge': {'active_task_bonus': 0.0}}),
    'env: no edge bonus (MISSION-AWARE)': ('MISSION_AWARE', {'edge': {'active_task_bonus': 0.0}}),
}


def ablation():
    jobs = [((op, name, s), pol, s, deep_update(ov, extra), 1.0, 1.0, False)
            for op, ov in OPS.items() for name, (pol, extra) in ABLATIONS.items() for s in EVAL_SEEDS]
    out = run_many(jobs)
    raw = pd.DataFrame([{'op': k[0], 'variant': k[1], 'seed': k[2], **res} for k, res, _, _ in out])
    rows = []
    for (op, v), sub in raw.groupby(['op', 'variant'], sort=False):
        m, lo, hi = bootstrap_ci(sub.mission_success_rate, n=1000)
        rm, rlo, rhi = bootstrap_ci(sub.reconfig_mission, n=1000)
        rows.append({'op': op, 'variant': v, 'success_mean': m, 'success_lo': lo, 'success_hi': hi, 'reconfig_mission_mean': rm,
                     'reconfig_mission_lo': rlo, 'reconfig_mission_hi': rhi, 'reconfig_total_mean': sub.total_reconfig_cost.mean(),
                     'loss_mean': sub.mission_loss.mean(), 'CVaR90': CV(sub.mission_loss)})
    df = pd.DataFrame(rows); df.to_csv(RES / 'ablation.csv', index=False)
    for _, r in df.iterrows():
        NUM[f'ablation.{r.op}.{r.variant}'] = {'success': round(r.success_mean, 3), 'ci': [round(r.success_lo, 3), round(r.success_hi, 3)],
                                               'reconfig_mission': round(r.reconfig_mission_mean, 1), 'reconfig_total': round(r.reconfig_total_mean, 1),
                                               'loss': round(r.loss_mean, 3), 'cvar': round(r.CVaR90, 3)}
    return df


def weight_logs():
    """Largest slice weight per step (saturation) for MARS-v0 and MARS on seed 20, OP-A and OP-C."""
    logs = {}
    for op in ['A_benign', 'C_concurrent']:
        for p in ['MARS_V0', 'MARS']:
            sim = MARSOranSimulator(p, seed=20, overrides=OPS[op]); log = []
            sim.policy_hook = lambda t, w, log=log: log.append({'t': t, **w})
            sim.run()
            df = pd.DataFrame(log); df['max_weight'] = df[SLICES].max(axis=1)
            tr = pd.DataFrame(sim.state.trace)
            df = df.merge(tr[['time_s', 'active_task'] + [f'prb_{s}' for s in SLICES]], left_on='t', right_on='time_s')
            logs[(op, p)] = df
            mw = df[(df.t >= 20) & (df.t < sim.mission_end())]
            NUM[f'saturation.{op}.{p}.min_max_weight_in_mission'] = round(float(mw.max_weight.min()), 4)
            NUM[f'saturation.{op}.{p}.mean_max_weight_in_mission'] = round(float(mw.max_weight.mean()), 4)
            NUM[f'saturation.{op}.{p}.mission_end'] = int(sim.mission_end())
    pd.concat([d.assign(op=k[0], policy=k[1]) for k, d in logs.items()]).to_csv(RES / 'weight_logs_seed20.csv', index=False)
    return logs


def traces_seed20(op):
    out = {}
    for p in POLICIES:
        _, sim = run_one(p, 20, overrides=OPS[op], return_sim=True)
        out[p] = pd.DataFrame(sim.state.trace)
        NUM[f'seed20.{op}.{p}.mission_end'] = int(sim.mission_end())
    return out


# ---------------------------------------------------------------- figures
def save(fig, name):
    fig.savefig(FIG / f'{name}.pdf'); fig.savefig(FIG / f'{name}.png', dpi=300)
    shutil.copy(FIG / f'{name}.pdf', PFIG / f'{name}.pdf')
    plt.close(fig)


def fmt(v):
    if v == 0: return '0'
    return f'{v:,.0f}' if abs(v) >= 100 else (f'{v:.2f}' if abs(v) >= 1 else f'{v:.3f}')


def fig_main(ci):
    specs = [('mission_success_rate', 'Mission-success score'), ('CVaR90', r'CVaR$_{0.90}$ of mission loss'),
             ('reconfig_mission', 'Reconfig. during mission (PRB-steps)')]
    fig, axes = plt.subplots(3, 3, figsize=(TWO_COL, 4.6), sharey=True)
    y = np.arange(len(POLICIES))[::-1]
    for i, op in enumerate(OPS):
        for j, (m, title) in enumerate(specs):
            ax = axes[i, j]
            for yi, p in zip(y, POLICIES):
                r = ci[(ci.op == op) & (ci.policy == p)].iloc[0]
                ax.errorbar(r[m], yi, xerr=[[r[m] - r[m + '_lo']], [r[m + '_hi'] - r[m]]], fmt=MARKER[p], color=COLOR[p], ms=4.5, capsize=2, lw=1.1)
                ax.annotate(fmt(r[m]), (r[m + '_hi'], yi), xytext=(3, 0), textcoords='offset points', va='center', fontsize=6, color=MUTED)
            ax.set_yticks(y, [LABEL[p] for p in POLICIES]); ax.grid(axis='y', visible=False); ax.margins(x=0.22)
            if i == 0: ax.set_title(title)
            if m == 'mission_success_rate': ax.set_xlim(0, 1.12)
        axes[i, 0].text(-0.62, 0.5, OP_LABEL[op], transform=axes[i, 0].transAxes, rotation=90, va='center', ha='center', fontsize=7.5, color=INK)
    fig.tight_layout(); save(fig, 'fig_main_ci')


def fig_pareto(rdf):
    fig, axes = plt.subplots(1, 2, figsize=(TWO_COL, 2.4), sharey=True)
    jit = np.random.default_rng(3)
    for ax, op in zip(axes, ['A_benign', 'C_concurrent']):
        for p in POLICIES:
            d = rdf[(rdf.op == op) & (rdf.policy == p)]
            ax.scatter(d.reconfig_mission, d.mission_loss + jit.uniform(-0.3, 0.3, len(d)), s=5, marker=MARKER[p], color=COLOR[p], alpha=0.35, lw=0)
            ax.scatter(d.reconfig_mission.mean(), d.mission_loss.mean(), s=55, marker=MARKER[p], facecolor=COLOR[p], edgecolor=INK, lw=0.9, zorder=5, label=LABEL[p])
        ax.set_xlabel('Reconfiguration during mission (PRB-steps)'); ax.set_title(OP_LABEL[op] + ' (outlined = mean)')
    axes[0].set_ylabel('Mission loss $L$ (jittered)'); axes[1].legend(loc='upper right', fontsize=6.5, ncol=2)
    fig.tight_layout(); save(fig, 'fig_pareto')


def fig_loss_tail(rdf):
    fig, axes = plt.subplots(1, 3, figsize=(TWO_COL, 2.3))
    betas = np.round(np.arange(0.0, 0.951, 0.05), 2)
    for ax, op in zip(axes, OPS):
        for p in POLICIES:
            l = rdf[(rdf.op == op) & (rdf.policy == p)].mission_loss.values.tolist()
            ax.plot(betas, [cvar(l, b) for b in betas], marker=MARKER[p], markevery=4, color=COLOR[p], ls=LSTYLE[p], label=LABEL[p])
        ax.set_xlabel(r'Confidence level $\beta$'); ax.set_title(OP_LABEL[op])
    axes[0].set_ylabel(r'CVaR$_\beta$ of mission loss ($\beta=0$: mean)'); axes[0].legend(fontsize=6, loc='center left')
    fig.tight_layout(); save(fig, 'fig_cvar_beta')


def fig_task_breakdown(tdf):
    fig, axes = plt.subplots(1, 3, figsize=(TWO_COL, 2.3), sharey=True)
    for ax, op in zip(axes, OPS):
        sub = tdf[tdf.op == op]
        mat = sub.pivot_table(index='policy', columns='task_id', values='success', aggfunc='sum').reindex(POLICIES)[TASK_IDS].fillna(0) / len(EVAL_SEEDS)
        im = ax.imshow(mat.values, cmap='Blues', vmin=0, vmax=1, aspect='auto')
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat.values[i, j]; ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=6, color='white' if v > 0.6 else INK)
        ax.set_xticks(range(5), TASK_IDS); ax.set_yticks(range(len(POLICIES)), [LABEL[p] for p in POLICIES]); ax.grid(False)
        ax.set_title(OP_LABEL[op])
    fig.colorbar(im, ax=axes, fraction=0.02, pad=0.02, label='Per-task success probability')
    save(fig, 'fig_task_success')


def fig_attribution(tdf):
    fig, ax = plt.subplots(figsize=(ONE_COL, 2.6))
    order = ['Success', 'Reliability failed', 'Deadline missed', 'Not finished']
    shade = {'Success': '#2a78d6', 'Reliability failed': '#eb6834', 'Deadline missed': '#52514e', 'Not finished': '#c9c8c3'}
    sub = tdf[tdf.op == 'A_benign']
    y = np.arange(len(POLICIES))[::-1]; left = np.zeros(len(POLICIES))
    total = 5 * len(EVAL_SEEDS)
    counts = {o: [] for o in order}
    for p in POLICIES:
        s = sub[sub.policy == p]
        succ = int(s.success.sum()); dl = int((s.deadline_met == 0).sum()); rel = int(((s.success == 0) & (s.deadline_met == 1)).sum())
        counts['Success'].append(succ); counts['Deadline missed'].append(dl); counts['Reliability failed'].append(rel)
        counts['Not finished'].append(total - len(s))
    for o in order:
        w = np.array(counts[o]) / total
        ax.barh(y, w, left=left, color=shade[o], edgecolor='white', lw=0.8, height=0.62, label=o)
        for yi, l, ww in zip(y, left, w):
            if ww > 0.09: ax.text(l + ww / 2, yi, f'{ww:.0%}', ha='center', va='center', fontsize=6, color='white')
        left += w
    ax.set_yticks(y, [LABEL[p] for p in POLICIES]); ax.set_xlim(0, 1); ax.grid(axis='y', visible=False)
    ax.set_xlabel(f'Share of task instances ({total} per policy)'); ax.set_title('OP-A outcome attribution (first failed check)')
    ax.legend(ncol=2, loc='upper center', bbox_to_anchor=(0.4, -0.25), fontsize=6.3)
    fig.tight_layout(); save(fig, 'fig_attribution')


def fig_gantt(tdf, op='A_benign'):
    fig, ax = plt.subplots(figsize=(TWO_COL, 2.6))
    sub = tdf[(tdf.seed == 20) & (tdf.op == op)]
    n = len(POLICIES); rowh = 0.8 / n
    for pi, p in enumerate(POLICIES):
        rows = sub[sub.policy == p].set_index('task_id')
        for ti, k in enumerate(TASK_IDS):
            if k not in rows.index: continue
            r = rows.loc[k]; yb = (4 - ti) + ((n - 1) / 2 - pi) * rowh
            ax.barh(yb, r.finish_s - r.start_s, left=r.start_s, height=rowh * 0.9, color=COLOR[p], hatch=None if r.success else '////',
                    edgecolor='white' if r.success else INK, linewidth=0.3)
    for ti, k in enumerate(TASK_IDS):
        d = sub[sub.task_id == k].deadline_s.iloc[0]; ax.plot([d, d], [4 - ti - 0.42, 4 - ti + 0.42], color=INK, lw=1.4)
    ax.set_yticks([4, 3, 2, 1, 0], ['K1 detect', 'K2 localise', 'K3 navigate', 'K4 inspect', 'K5 manipulate'])
    ax.axvline(20, color=MUTED, lw=0.8); ax.set_xlim(0, 260); ax.grid(axis='y', visible=False)
    ax.set_xlabel('Simulation time (s)'); ax.set_title(f'Task timeline, seed 20, {OP_LABEL[op]} (tick = deadline; hatched = failed check)')
    h = [Patch(color=COLOR[p], label=LABEL[p]) for p in POLICIES] + [Patch(facecolor='white', edgecolor=INK, hatch='////', label='failed')]
    ax.legend(handles=h, loc='lower right', ncol=2, fontsize=6.3)
    fig.tight_layout(); save(fig, 'fig_gantt_seed20')


def fig_trace(traces, op):
    show = ['MISSION_AWARE', 'MARS_V0', 'MARS']
    fig, axes = plt.subplots(len(show) + 1, 1, figsize=(TWO_COL, 5.0), sharex=True, gridspec_kw={'height_ratios': [0.7] + [1] * len(show)})
    base = traces['MARS']; shocks = base.time_s[base.shock == 1].values
    for ax in axes:
        for s in shocks: ax.axvspan(s - 0.5, s + 0.5, color='#e34948', alpha=0.10, lw=0)
    axes[0].plot(base.time_s, base.severity, color=INK, lw=1.1); axes[0].set_ylabel('Severity'); axes[0].set_ylim(0, 1.0)
    axes[0].set_title(f'Seed 20, {OP_LABEL[op]}: severity (shaded = shock) and PRB allocation')
    for ax, p in zip(axes[1:], show):
        tr = traces[p]
        for s in SLICES: ax.plot(tr.time_s, tr['prb_' + s], color=SLICE_COLOR[s], lw=1.0, label=s)
        act = tr.active_task.fillna('')
        for k in sorted(set(act) - {''}):
            ts = tr.time_s[act == k]; ax.text(ts.mean(), 63, k, ha='center', fontsize=6, color=MUTED)
        ax.set_ylabel('PRBs'); ax.set_ylim(0, 70)
        ax.text(1.0, 1.02, f'{LABEL[p]} (reconfig. total {tr.reconfig_cost.sum():.0f})', transform=ax.transAxes, ha='right', fontsize=7)
    axes[1].legend(ncol=4, loc='upper left', bbox_to_anchor=(0, 1.3)); axes[-1].set_xlabel('Simulation time (s)'); axes[-1].set_xlim(0, 300)
    fig.tight_layout(); save(fig, f'fig_trace_{op}')


def fig_latency(rdf):
    fig, axes = plt.subplots(1, 2, figsize=(TWO_COL, 2.3), sharex=True)
    sub = rdf[rdf.op == 'A_benign']
    for ax, col, t in zip(axes, ['control_latency_mission_ms', 'control_latency_after_ms'], ['(a) During the mission', '(b) After the mission ends']):
        data = [sub[sub.policy == p][col].dropna().values for p in POLICIES]
        bp = ax.boxplot(data, orientation='horizontal', widths=0.5, patch_artist=True, medianprops={'color': INK}, flierprops={'markersize': 2})
        for patch, p in zip(bp['boxes'], POLICIES): patch.set_facecolor(COLOR[p]); patch.set_alpha(0.55); patch.set_edgecolor(MUTED)
        ax.set_yticks(range(1, len(POLICIES) + 1), [LABEL[p] for p in POLICIES]); ax.grid(axis='y', visible=False)
        ax.set_xlabel('Mean control-latency proxy per run (ms)'); ax.set_title(t + ', OP-A, 300 seeds')
    fig.tight_layout(); save(fig, 'fig_latency')


def fig_line_sweep(df, key, xlabel, name, title, vline=None, vtext=None, xlim=None, policies=POLICIES, df2=None, label2=None):
    fig, axes = plt.subplots(1, 2, figsize=(TWO_COL, 2.4))
    for p in policies:
        d = df[df.policy == p].sort_values(key)
        axes[0].fill_between(d[key], d.success_lo, d.success_hi, color=COLOR[p], alpha=0.12, lw=0)
        axes[0].plot(d[key], d.success_mean, marker=MARKER[p], color=COLOR[p], ls=LSTYLE[p], label=LABEL[p])
        if df2 is not None:
            d2 = df2[df2.policy == p].sort_values(key)
            axes[1].plot(d2[key], d2.success_mean, marker=MARKER[p], color=COLOR[p], ls=LSTYLE[p])
        else:
            axes[1].fill_between(d[key], d.CVaR90_lo, d.CVaR90_hi, color=COLOR[p], alpha=0.12, lw=0)
            axes[1].plot(d[key], d.CVaR90, marker=MARKER[p], color=COLOR[p], ls=LSTYLE[p])
    axes[0].set_ylabel('Mission-success score'); axes[0].set_ylim(-0.02, 1.02)
    if df2 is not None:
        axes[1].set_ylabel('Mission-success score'); axes[1].set_ylim(-0.02, 1.02)
        axes[0].set_title(f'(a) {title}: fixed slice caps'); axes[1].set_title(f'(b) {title}: {label2}')
    else:
        axes[1].set_ylabel('CVaR$_{0.90}$ of mission loss')
        axes[0].set_title(f'(a) {title}: success (95% CI)'); axes[1].set_title(f'(b) {title}: tail loss (95% CI)')
    for ax in axes:
        ax.set_xlabel(xlabel)
        if xlim: ax.set_xlim(*xlim)
        if vline is not None:
            ax.axvline(vline, color=MUTED, lw=0.8)
            if vtext: ax.text(vline, ax.get_ylim()[1], vtext, fontsize=6.2, color=MUTED, ha='left', va='top')
    axes[0].legend(loc='best', fontsize=6, ncol=2)
    fig.tight_layout(); save(fig, name)


def fig_stress_grid(df):
    show = ['PROPORTIONAL', 'MISSION_AWARE', 'MYOPIC_OPT', 'MARS']
    fig, axes = plt.subplots(1, 4, figsize=(TWO_COL, 2.1), sharey=True)
    for ax, p in zip(axes, show):
        m = df[df.policy == p].pivot(index='severity', columns='total_prbs', values='success_mean').sort_index(ascending=False)
        im = ax.imshow(m.values, cmap='Blues', vmin=0, vmax=1, aspect='auto')
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                v = m.values[i, j]; ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=5.8, color='white' if v > 0.6 else INK)
        ax.set_xticks(range(m.shape[1]), m.columns); ax.set_yticks(range(m.shape[0]), [f'{v:.1f}' for v in m.index])
        ax.set_title(LABEL[p]); ax.set_xlabel('Total PRBs $B$'); ax.grid(False)
    axes[0].set_ylabel(r'Initial severity $\sigma_0$')
    fig.colorbar(im, ax=axes, fraction=0.02, pad=0.02, label='Mission-success score')
    save(fig, 'fig_stress_grid')


def fig_mars_params(sw):
    keys = [('temperature', r'Softmax temperature $\tau$', True), ('reserve_scale', r'Reserve scale $R_0$', False),
            ('damping', r'Damping $\mu$', False), ('hold_time_s', r'Hold time $T_h$ (s)', False),
            ('max_reconfig_per_step', r'Change limit $\Delta_{\max}$', True)]
    fig, axes = plt.subplots(2, 5, figsize=(TWO_COL, 3.0), sharex='col')
    opc = {'A_benign': '#2a78d6', 'B_severe': '#e34948', 'C_concurrent': '#1baf7a'}
    for col, (k, xl, logx) in enumerate(keys):
        for op in OPS:
            d = sw[(k, op)].sort_values(k)
            axes[0, col].plot(d[k], d.success_mean, marker='o', color=opc[op], label=OP_LABEL[op].split(' (')[0])
            axes[1, col].plot(d[k], d.reconfig_mission_mean, marker='o', color=opc[op])
        axes[1, col].set_xlabel(xl)
        if logx: axes[1, col].set_xscale('log', base=2)
        cur = sw[(k, 'nominal')]
        for r in range(2): axes[r, col].axvline(cur, color=MUTED, lw=0.8)
    axes[0, 0].set_ylabel('Success score'); axes[1, 0].set_ylabel('Reconfig. in mission')
    axes[0, 0].legend(fontsize=6)
    fig.tight_layout(); save(fig, 'fig_mars_params')


def fig_ablation(ab, logs):
    fig = plt.figure(figsize=(TWO_COL, 3.2))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 0.8, 1.0], wspace=0.35)
    ax0 = fig.add_subplot(gs[0]); ax1 = fig.add_subplot(gs[1], sharey=ax0); ax2 = fig.add_subplot(gs[2])
    names = list(ABLATIONS)
    y = np.arange(len(names))[::-1]
    off = {'A_benign': 0.22, 'B_severe': 0.0, 'C_concurrent': -0.22}
    opc = {'A_benign': '#2a78d6', 'B_severe': '#e34948', 'C_concurrent': '#1baf7a'}
    for op in OPS:
        d = ab[ab.op == op].set_index('variant').loc[names]
        ax0.errorbar(d.success_mean, y + off[op], xerr=[d.success_mean - d.success_lo, d.success_hi - d.success_mean], fmt='o', ms=3, color=opc[op], capsize=1.5, lw=0.9, label=OP_LABEL[op].split(' (')[0])
        ax1.plot(d.reconfig_mission_mean, y + off[op], 'o', ms=3, color=opc[op])
    ax0.set_yticks(y, names, fontsize=6.2); plt.setp(ax1.get_yticklabels(), visible=False)
    for ax in (ax0, ax1): ax.grid(axis='y', visible=False)
    ax0.set_title('(a) Success (95% CI)'); ax1.set_title('(b) Reconfig. (mission)'); ax0.legend(fontsize=6, loc='lower left')
    for p, ls in [('MARS_V0', '--'), ('MARS', '-')]:
        d = logs[('A_benign', p)]; ax2.plot(d.t, d.max_weight, color=COLOR[p], ls=ls, lw=1.0, label=LABEL[p])
    ax2.set_ylim(0, 1.05); ax2.set_xlabel('Simulation time (s)'); ax2.set_ylabel('Largest slice weight')
    ax2.set_title('(c) Max. slice weight, seed 20, OP-A'); ax2.legend(fontsize=6, loc='lower right')
    fig.tight_layout(); save(fig, 'fig_ablation')


# ---------------------------------------------------------------- driver
def main():
    t0 = time.time()
    print('[1] Main experiment: 3 operating points x 6 policies x 300 seeds')
    rdf, tdf = main_experiment()
    ci, paired = statistics(rdf)
    for op in OPS:
        for p in POLICIES:
            t = tdf[(tdf.op == op) & (tdf.policy == p)]
            NUM[f'tasks.{op}.{p}.per_task_success'] = (t.groupby('task_id').success.sum() / len(EVAL_SEEDS)).round(3).to_dict()
            NUM[f'tasks.{op}.{p}.deadline_fail_share'] = round(float((t.deadline_met == 0).sum() / (5 * len(EVAL_SEEDS))), 4)
            NUM[f'tasks.{op}.{p}.K3_finish_mean'] = round(float(t[t.task_id == 'K3'].finish_s.mean()), 2)
            NUM[f'tasks.{op}.{p}.K3_severity_at_finish'] = round(float(t[t.task_id == 'K3'].severity_at_finish.mean()), 4)
            sub = rdf[(rdf.op == op) & (rdf.policy == p)]
            NUM[f'latency.{op}.{p}'] = {'mission': round(float(sub.control_latency_mission_ms.mean()), 2), 'after': round(float(sub.control_latency_after_ms.mean()), 2)}
            NUM[f'mission_end.{op}.{p}'] = round(float(sub.mission_end_s.mean()), 2)
    print('[2] Sweeps (100 seeds)')
    prb = sweep('total_prbs', [50, 55, 60, 70, 80, 90, 100, 120, 150, 200], lambda v: {'overrides': {'radio': {'total_prbs': v}}})
    prb_s = sweep('total_prbs_scaledcaps', [50, 55, 60, 70, 80, 90, 100, 120, 150, 200],
                  lambda v: {'overrides': {'radio': {'total_prbs': v, 'scale_max_with_budget': True}}}
                  ).rename(columns={'total_prbs_scaledcaps': 'total_prbs'})
    sev = sweep('initial_severity', [0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0], lambda v: {'overrides': {'incident': {'initial_severity': v}}})
    shk = sweep('shock_probability', [0.0, 0.005, 0.018, 0.04, 0.08, 0.15, 0.3], lambda v: {'overrides': {'incident': {'shock_probability': v}}})
    dl = sweep('deadline_scale', [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5], lambda v: {'deadline_scale': v})
    wl = sweep('workload_scale', [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0], lambda v: {'workload_scale': v})
    grid = []
    for B in [60, 80, 100, 120]:
        g = sweep(f'grid_B{B}', [0.2, 0.4, 0.6, 0.8, 1.0], lambda v, B=B: {'overrides': {'incident': {'initial_severity': v}, 'radio': {'total_prbs': B}}})
        grid.append(g.rename(columns={f'grid_B{B}': 'severity'}).assign(total_prbs=B))
    grid = pd.concat(grid, ignore_index=True); grid.to_csv(RES / 'stress_grid.csv', index=False)
    for f in list(RES.glob('sweep_grid_B*')): f.unlink()
    for k in list(NUM):
        if k.startswith('sweep.grid_B'): del NUM[k]
    for _, r in grid.iterrows(): NUM[f'grid.sev{r.severity}.B{r.total_prbs}.{r.policy}'] = round(r.success_mean, 3)
    print('[3] MARS parameter sweeps (100 seeds, all operating points)')
    mcfg = MARSOranSimulator('MARS').cfg
    psw = {}
    for k, vals, sect in [('temperature', [0.05, 0.1, 0.2, 0.4, 0.8, 1.6], 'mars'), ('reserve_scale', [0.0, 0.1, 0.2, 0.4, 0.8], 'mars'),
                          ('damping', [0.0, 0.25, 0.5, 0.75, 0.9], 'mars'), ('hold_time_s', [0, 1, 2, 4, 6, 8, 12, 20], 'mars'),
                          ('max_reconfig_per_step', [2, 4, 8, 16, 32, 64], 'controller')]:
        psw[(k, 'nominal')] = mcfg[sect][k]
        for op, ov in OPS.items():
            psw[(k, op)] = sweep(f'mars_{k}_{op}', vals, lambda v, k=k, sect=sect: {'overrides': {sect: {k: v}}}, policies=['MARS'],
                                 base=ov).rename(columns={f'mars_{k}_{op}': k})
    print('[4] Ablation (300 seeds, all operating points)')
    ab = ablation(); logs = weight_logs()
    print('[5] Figures')
    # 14 data figures (+ the TikZ system diagram in the paper = 15 figures in total).
    traces_seed20('A_benign'); tr_c = traces_seed20('C_concurrent')
    fig_main(ci); fig_pareto(rdf); fig_loss_tail(rdf); fig_task_breakdown(tdf); fig_attribution(tdf); fig_gantt(tdf)
    fig_trace(tr_c, 'C_concurrent')
    fig_line_sweep(prb, 'total_prbs', 'Total PRB budget $B$', 'fig_sweep_prbs', 'PRB budget', vline=50, vtext=r' $B=\sum_s B^{\min}_s$',
                   xlim=(45, 205), df2=prb_s, label2=r'caps $B^{\max}_s$ scaled with $B$')
    fig_line_sweep(sev, 'initial_severity', r'Initial incident severity $\sigma_0$', 'fig_sweep_severity', 'Severity', vline=0.2, vtext=' OP-A')
    fig_line_sweep(shk, 'shock_probability', r'Network-shock probability $p_{\mathrm{sh}}$', 'fig_sweep_shock', 'Shock rate', vline=0.018, vtext=' nominal')
    fig_line_sweep(dl, 'deadline_scale', 'Deadline scale factor (1 = nominal)', 'fig_sweep_deadline', 'Deadline tightness', vline=1.0)
    fig_line_sweep(wl, 'workload_scale', 'Workload scale factor (1 = nominal)', 'fig_sweep_workload', 'Workload', vline=1.0)
    fig_mars_params(psw); fig_ablation(ab, logs)      # stress grid and latency are reported as numbers only
    NUM['runtime_s'] = round(time.time() - t0, 1)
    (RES / 'paper_numbers.json').write_text(json.dumps(NUM, indent=1, default=float), encoding='utf-8')
    print(f'Done in {time.time() - t0:.0f} s. CSVs -> {RES}, figures -> {FIG}')


if __name__ == '__main__':
    main()
