"""Extended statistics, edge-case sweeps and figures for the refined MARS-O-RAN paper.

Does not change simulator.py or the original results. Outputs go to
results/extended/ (CSV) and figures/extended/ (PDF + PNG); the PDFs are also
copied into paper/figures/ for the LaTeX build.

Run:  python src/edge_case_experiments.py
"""
from __future__ import annotations
import json, shutil, sys
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
from simulator import MARSOranSimulator, POLICIES, SLICES, cvar  # noqa: E402

RES = ROOT / 'results' / 'extended'; RES.mkdir(parents=True, exist_ok=True)
FIG = ROOT / 'figures' / 'extended'; FIG.mkdir(parents=True, exist_ok=True)
PFIG = ROOT / 'paper' / 'figures'; PFIG.mkdir(parents=True, exist_ok=True)

SEEDS = list(range(20, 50))          # same seeds as the main experiment
TASK_IDS = ['K1', 'K2', 'K3', 'K4', 'K5']
LABEL = {'STATIC': 'STATIC', 'PROPORTIONAL': 'PROPORTIONAL', 'MISSION_AWARE': 'MISSION-AWARE', 'MARS_RISK_AWARE': 'MARS'}
# Validated categorical palette (fixed entity -> colour), plus a marker per policy as secondary encoding.
COLOR = {'MARS_RISK_AWARE': '#2a78d6', 'MISSION_AWARE': '#eb6834', 'PROPORTIONAL': '#1baf7a', 'STATIC': '#eda100'}
MARKER = {'MARS_RISK_AWARE': 'o', 'MISSION_AWARE': 's', 'PROPORTIONAL': '^', 'STATIC': 'D'}
SLICE_COLOR = {'SC': '#2a78d6', 'SV': '#eb6834', 'SX': '#1baf7a', 'SM': '#eda100'}
INK, MUTED, GRID = '#0b0b0b', '#52514e', '#e4e3df'

plt.rcParams.update({
    'font.size': 8, 'axes.titlesize': 8.5, 'axes.labelsize': 8, 'legend.fontsize': 7,
    'xtick.labelsize': 7, 'ytick.labelsize': 7, 'axes.edgecolor': MUTED, 'axes.labelcolor': INK,
    'xtick.color': MUTED, 'ytick.color': MUTED, 'axes.grid': True, 'grid.color': GRID,
    'grid.linewidth': 0.6, 'axes.axisbelow': True, 'axes.spines.top': False, 'axes.spines.right': False,
    'lines.linewidth': 1.6, 'lines.markersize': 4.5, 'legend.frameon': False, 'savefig.bbox': 'tight',
    'pdf.fonttype': 42,
})
ONE_COL, TWO_COL = 3.5, 7.16


# ---------------------------------------------------------------- simulation helpers
def run(policy, seed, overrides=None, deadline_scale=1.0, workload_scale=1.0):
    """One run; deadline_scale stretches each deadline relative to the incident start,
    workload_scale multiplies both bit and compute workloads of every task."""
    sim = MARSOranSimulator(policy=policy, seed=seed, overrides=overrides)
    start = sim.cfg['incident']['start_time_s']
    for t in sim.tasks:
        if deadline_scale != 1.0:
            t.deadline = int(round(start + (t.deadline - start) * deadline_scale))
        if workload_scale != 1.0:
            t.workload_bits *= workload_scale; t.remaining_bits = t.workload_bits
            t.compute_units *= workload_scale; t.remaining_compute = t.compute_units
    res = sim.run()
    return res, sim


def bootstrap_ci(x, stat=np.mean, n=4000, alpha=0.05, seed=7):
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    boots = np.array([stat(x[i]) for i in idx])
    return float(stat(x)), float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2))


def sweep(name, values, make_kwargs, policies=POLICIES, seeds=SEEDS):
    """Generic sweep: for each value and policy, run all seeds and summarise with bootstrap CIs."""
    rows, raw = [], []
    for v in values:
        kw = make_kwargs(v)
        for p in policies:
            res = [run(p, s, **kw)[0] for s in seeds]
            succ = [r['mission_success_rate'] for r in res]
            loss = [r['mission_loss'] for r in res]
            rec = [r['total_reconfig_cost'] for r in res]
            m, lo, hi = bootstrap_ci(succ)
            c, clo, chi = bootstrap_ci(loss, stat=lambda a: cvar(list(a), .9))
            rows.append({name: v, 'policy': p, 'success_mean': m, 'success_lo': lo, 'success_hi': hi,
                         'deadline_mean': float(np.mean([r['deadline_success_rate'] for r in res])),
                         'reliability_mean': float(np.mean([r['reliability_success_rate'] for r in res])),
                         'loss_mean': float(np.mean(loss)), 'CVaR90': c, 'CVaR90_lo': clo, 'CVaR90_hi': chi,
                         'reconfig_mean': float(np.mean(rec)), 'tasks_observed_mean': float(np.mean([r['tasks_observed'] for r in res]))})
            for s, r in zip(seeds, res):
                raw.append({name: v, 'policy': p, 'seed': s, **{k: r[k] for k in ('mission_success_rate', 'mission_loss', 'total_reconfig_cost', 'tasks_observed')}})
    df = pd.DataFrame(rows)
    df.to_csv(RES / f'sweep_{name}.csv', index=False)
    pd.DataFrame(raw).to_csv(RES / f'sweep_{name}_runs.csv', index=False)
    print(f'  sweep {name}: {len(values)} values x {len(policies)} policies x {len(seeds)} seeds')
    return df


def save(fig, name):
    fig.savefig(FIG / f'{name}.pdf'); fig.savefig(FIG / f'{name}.png', dpi=300)
    shutil.copy(FIG / f'{name}.pdf', PFIG / f'{name}.pdf')
    plt.close(fig)


def legend_handles(policies=POLICIES):
    return [plt.Line2D([], [], color=COLOR[p], marker=MARKER[p], label=LABEL[p]) for p in policies]


# ---------------------------------------------------------------- experiments
def main_experiment():
    runs, tasks, traces = [], [], {}
    for s in SEEDS:
        sev_ref = None
        for p in POLICIES:
            res, sim = run(p, s)
            runs.append(res)
            tasks.extend(sim.state.task_rows)
            tr = pd.DataFrame(sim.state.trace)
            # Common random numbers: every policy sees the identical stochastic environment for a seed.
            if sev_ref is None: sev_ref = tr[['severity', 'shock']].values
            else: assert np.array_equal(sev_ref, tr[['severity', 'shock']].values), 'environment differs across policies'
            if s == 20: traces[p] = tr
            lat = tr[['control_latency_ms', 'e2e_latency_ms']].copy(); lat['policy'] = p; lat['seed'] = s
            traces.setdefault('_lat', []).append(lat)
    rdf, tdf = pd.DataFrame(runs), pd.DataFrame(tasks)
    # Reproducibility check against the archived main experiment.
    old = pd.read_csv(ROOT / 'results' / 'experiment_runs.csv')
    merged = rdf.merge(old, on=['policy', 'seed'], suffixes=('', '_old'))
    assert np.allclose(merged['mission_loss'], merged['mission_loss_old']), 'does not reproduce archived results'
    rdf.to_csv(RES / 'main_runs.csv', index=False); tdf.to_csv(RES / 'main_tasks.csv', index=False)
    lat = pd.concat(traces.pop('_lat'), ignore_index=True)
    print('  main experiment reproduced archived results_runs.csv exactly')
    return rdf, tdf, traces, lat


def statistics_table(rdf):
    rows = []
    for p in POLICIES:
        sub = rdf[rdf.policy == p]
        row = {'policy': p}
        for m in ['mission_success_rate', 'deadline_success_rate', 'reliability_success_rate', 'total_reconfig_cost', 'mission_loss']:
            row[m], row[m + '_lo'], row[m + '_hi'] = bootstrap_ci(sub[m])
        row['CVaR90'], row['CVaR90_lo'], row['CVaR90_hi'] = bootstrap_ci(sub.mission_loss, stat=lambda a: cvar(list(a), .9))
        row['full_mission_prob'] = float((sub.tasks_completed_success == 5).mean())
        row['worst_loss'] = float(sub.mission_loss.max()); row['best_loss'] = float(sub.mission_loss.min())
        rows.append(row)
    ci = pd.DataFrame(rows); ci.to_csv(RES / 'main_ci.csv', index=False)

    # Paired (same-seed) comparisons of MARS against every other policy.
    mars = rdf[rdf.policy == 'MARS_RISK_AWARE'].set_index('seed')
    prow = []
    for p in POLICIES[:-1]:
        other = rdf[rdf.policy == p].set_index('seed')
        for m in ['mission_loss', 'total_reconfig_cost', 'mission_success_rate']:
            d = (mars[m] - other[m]).loc[SEEDS].values
            mean, lo, hi = bootstrap_ci(d)
            nz = d[d != 0]
            pval = float(wilcoxon(nz).pvalue) if len(nz) >= 1 and np.any(nz) else 1.0
            prow.append({'baseline': p, 'metric': m, 'mean_diff_MARS_minus_baseline': mean, 'ci_lo': lo, 'ci_hi': hi,
                         'mars_better': int((d < 0).sum() if m != 'mission_success_rate' else (d > 0).sum()),
                         'ties': int((d == 0).sum()), 'mars_worse': int((d > 0).sum() if m != 'mission_success_rate' else (d < 0).sum()),
                         'wilcoxon_p': pval})
    paired = pd.DataFrame(prow); paired.to_csv(RES / 'paired_tests.csv', index=False)
    return ci, paired


def ablation_extended():
    modes = {
        'MARS-full': {}, 'no-AoI': {'controller': {'alpha_aoi': 0.0}}, 'no-urgency': {'controller': {'alpha_urgency': 0.0}},
        'no-risk-reserve': {'controller': {'risk_reserve_prbs': 0}}, 'no-hysteresis': {'controller': {'hold_time_s': 0}},
        'no-reconfig-penalty': {'controller': {'reconfig_penalty': 0.0}},
        'no-criticality-terms': {'controller': {'alpha_aoi': 0.0, 'alpha_urgency': 0.0, 'alpha_hazard': 0.0, 'alpha_critical_path': 0.0, 'alpha_risk': 0.0}},
        'no-reserve+no-hysteresis': {'controller': {'risk_reserve_prbs': 0, 'hold_time_s': 0}},
    }
    rows = []
    for name, ov in modes.items():
        res = [run('MARS_RISK_AWARE', s, overrides=ov)[0] for s in SEEDS]
        succ, rec, loss = ([r[k] for r in res] for k in ('mission_success_rate', 'total_reconfig_cost', 'mission_loss'))
        m, lo, hi = bootstrap_ci(succ); rm, rlo, rhi = bootstrap_ci(rec)
        c, clo, chi = bootstrap_ci(loss, stat=lambda a: cvar(list(a), .9))
        rows.append({'variant': name, 'success_mean': m, 'success_lo': lo, 'success_hi': hi, 'reconfig_mean': rm,
                     'reconfig_lo': rlo, 'reconfig_hi': rhi, 'CVaR90': c, 'CVaR90_lo': clo, 'CVaR90_hi': chi})
    df = pd.DataFrame(rows); df.to_csv(RES / 'ablation_30seeds.csv', index=False)
    return df


def softmax_saturation():
    """Explains why some ablations are inert: record MARS slice weights over a run."""
    sim = MARSOranSimulator('MARS_RISK_AWARE', seed=20)
    orig = sim.policy_weights; log = []
    def wrapped(demand, severity, shock):
        w = orig(demand, severity, shock); log.append({'t': sim.state.t, **w}); return w
    sim.policy_weights = wrapped
    sim.run()
    df = pd.DataFrame(log); df['max_weight'] = df[SLICES].max(axis=1)
    df.to_csv(RES / 'mars_weight_saturation.csv', index=False)
    return df


# ---------------------------------------------------------------- figures
def fig_ci(ci):
    fig, axes = plt.subplots(1, 3, figsize=(TWO_COL, 2.0))
    specs = [('mission_success_rate', 'Mission-success score', (0, 1)), ('total_reconfig_cost', 'Reconfiguration cost (PRB-steps)', None),
             ('CVaR90', 'CVaR$_{0.90}$ mission loss', None)]
    y = np.arange(len(POLICIES))[::-1]
    for ax, (m, title, lim) in zip(axes, specs):
        for yi, p in zip(y, POLICIES):
            r = ci[ci.policy == p].iloc[0]
            ax.errorbar(r[m], yi, xerr=[[r[m] - r[m + '_lo']], [r[m + '_hi'] - r[m]]], fmt=MARKER[p], color=COLOR[p],
                        ms=5, capsize=2.5, lw=1.2)
            ax.annotate(f'{r[m]:,.0f}' if r[m] >= 100 else f'{r[m]:.3g}', (r[m + '_hi'], yi), xytext=(4, 0), textcoords='offset points', va='center', fontsize=6.5, color=MUTED)
        ax.set_yticks(y, [LABEL[p] for p in POLICIES] if ax is axes[0] else [''] * 4)
        ax.set_title(title); ax.grid(axis='y', visible=False)
        if lim: ax.set_xlim(*lim)
        ax.margins(x=0.18)
    fig.tight_layout(); save(fig, 'ext_ci_main')


def fig_loss_tail(rdf):
    fig, axes = plt.subplots(1, 2, figsize=(TWO_COL, 2.3))
    ax = axes[0]
    for p in POLICIES:
        x = np.sort(rdf[rdf.policy == p].mission_loss.values); yv = np.arange(1, len(x) + 1) / len(x)
        ax.step(x, yv, where='post', color=COLOR[p], label=LABEL[p])
        ax.plot(x[-1], 1.0, MARKER[p], color=COLOR[p])
    ax.axhline(0.9, color=MUTED, lw=0.8); ax.text(32, 0.92, r'$\beta=0.90$', fontsize=6.5, color=MUTED)
    ax.set_xlabel('Mission loss $L$ per run'); ax.set_ylabel('Empirical CDF'); ax.set_title('(a) Mission-loss distribution (30 seeds)')
    ax.legend(loc='center right')
    ax = axes[1]
    betas = np.round(np.arange(0.0, 0.951, 0.05), 2)
    for p in POLICIES:
        l = rdf[rdf.policy == p].mission_loss.values.tolist()
        ax.plot(betas, [cvar(l, b) if b > 0 else np.mean(l) for b in betas], marker=MARKER[p], markevery=3, color=COLOR[p], label=LABEL[p])
    ax.set_xlabel(r'Confidence level $\beta$'); ax.set_ylabel(r'CVaR$_\beta$ of mission loss'); ax.set_title(r'(b) Tail-risk curve CVaR$_\beta$ ($\beta=0$: mean)')
    fig.tight_layout(); save(fig, 'ext_loss_tail')


def fig_task_breakdown(tdf):
    fig, axes = plt.subplots(1, 2, figsize=(TWO_COL, 2.4), gridspec_kw={'width_ratios': [1, 1.25]})
    ax = axes[0]
    mat = tdf.pivot_table(index='policy', columns='task_id', values='success', aggfunc='mean').reindex(POLICIES)[TASK_IDS]
    im = ax.imshow(mat.values, cmap='Blues', vmin=0, vmax=1, aspect='auto')
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat.values[i, j]; ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=6.5, color='white' if v > 0.6 else INK)
    ax.set_xticks(range(5), [f'{k}\n({s})' for k, s in zip(TASK_IDS, ['SV', 'SM', 'SC', 'SM', 'SC'])])
    ax.set_yticks(range(4), [LABEL[p] for p in POLICIES]); ax.grid(False)
    ax.set_title('(a) Per-task success probability'); fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    ax = axes[1]
    # Failure attribution: each task instance is in exactly one bucket.
    def bucket(r):
        if r.success: return 'Success'
        if not r.deadline_met: return 'Deadline missed'
        if not r.reliability_ok: return 'Reliability failed'
        return 'Stale (AoI)'
    tdf = tdf.assign(outcome=tdf.apply(bucket, axis=1))
    order = ['Success', 'Reliability failed', 'Deadline missed', 'Stale (AoI)']
    shade = {'Success': '#2a78d6', 'Reliability failed': '#eb6834', 'Deadline missed': '#52514e', 'Stale (AoI)': '#eda100'}
    frac = tdf.groupby('policy').outcome.value_counts(normalize=True).unstack(fill_value=0).reindex(POLICIES).reindex(columns=order, fill_value=0)
    left = np.zeros(4); y = np.arange(4)[::-1]
    for o in order:
        ax.barh(y, frac[o].values, left=left, color=shade[o], edgecolor='white', linewidth=1.0, height=0.6, label=o)
        for yi, l, w in zip(y, left, frac[o].values):
            if w > 0.08: ax.text(l + w / 2, yi, f'{w:.0%}', ha='center', va='center', fontsize=6.5, color='white')
        left += frac[o].values
    ax.set_yticks(y, [LABEL[p] for p in POLICIES]); ax.set_xlim(0, 1); ax.grid(axis='y', visible=False)
    ax.set_xlabel('Share of task instances (150 per policy)'); ax.set_title('(b) Outcome attribution (first failed check)')
    ax.legend(ncol=4, loc='upper center', bbox_to_anchor=(0.45, -0.28), fontsize=6.5)
    fig.tight_layout(); save(fig, 'ext_task_breakdown')


def fig_gantt(tdf):
    fig, ax = plt.subplots(figsize=(TWO_COL, 2.4))
    sub = tdf[tdf.seed == 20]
    rowh = 0.16
    for pi, p in enumerate(POLICIES):
        rows = sub[sub.policy == p].set_index('task_id')
        for ti, k in enumerate(TASK_IDS):
            ybase = (4 - ti) + (1.5 - pi) * rowh
            if k not in rows.index: continue
            r = rows.loc[k]
            ax.barh(ybase, r.finish_s - r.start_s, left=r.start_s, height=rowh * 0.85, color=COLOR[p],
                    hatch=None if r.success else '////', edgecolor='white' if r.success else INK, linewidth=0.3)
    for ti, k in enumerate(TASK_IDS):
        d = sub[sub.task_id == k].deadline_s.iloc[0]
        ax.plot([d, d], [4 - ti - 0.35, 4 - ti + 0.35], color=INK, lw=1.4)
    ax.set_yticks([4, 3, 2, 1, 0], ['K1 gas detect', 'K2 localise', 'K3 UGV nav.', 'K4 inspect', 'K5 manipulate'])
    ax.axvline(20, color=MUTED, lw=0.8); ax.text(21, -0.55, 'incident', fontsize=6.5, color=MUTED)
    ax.set_xlabel('Simulation time (s)'); ax.grid(axis='y', visible=False); ax.set_xlim(0, 300)
    ax.set_title('Task execution timeline, seed 20 (black tick = deadline; hatched = task failed a success check)')
    h = legend_handles() + [Patch(facecolor='white', edgecolor=INK, hatch='////', label='failed')]
    h = [Patch(color=COLOR[p], label=LABEL[p]) for p in POLICIES] + [h[-1]]
    ax.legend(handles=h, loc='lower right', ncol=1)
    fig.tight_layout(); save(fig, 'ext_gantt_seed20')


def fig_trace(traces):
    fig, axes = plt.subplots(3, 1, figsize=(TWO_COL, 4.2), sharex=True, gridspec_kw={'height_ratios': [0.8, 1.2, 1.2]})
    base = traces['MARS_RISK_AWARE']
    shocks = base.time_s[base.shock == 1].values
    for ax in axes:
        for s in shocks: ax.axvspan(s - 0.5, s + 0.5, color='#e34948', alpha=0.10, lw=0)
    axes[0].plot(base.time_s, base.severity, color=INK, lw=1.2)
    axes[0].set_ylabel('Severity'); axes[0].set_ylim(0, 1.05)
    axes[0].set_title('Seed 20: incident severity (shaded = network shock) and PRB allocation')
    for ax, p in zip(axes[1:], ['MISSION_AWARE', 'MARS_RISK_AWARE']):
        tr = traces[p]
        for s in SLICES: ax.plot(tr.time_s, tr['prb_' + s], color=SLICE_COLOR[s], lw=1.1, label=s)
        # active-task band
        act = tr.active_task.fillna('')
        for k in TASK_IDS:
            ts = tr.time_s[act == k]
            if len(ts): ax.text(ts.mean(), 63, k, ha='center', fontsize=6.5, color=MUTED)
        ax.set_ylabel('PRBs'); ax.set_ylim(0, 68)
        ax.text(1.0, 1.02, f'{LABEL[p]}  (total reconfig. = {tr.reconfig_cost.sum():.0f})', transform=ax.transAxes, ha='right', fontsize=7, color=INK)
    axes[1].legend(ncol=4, loc='upper left', bbox_to_anchor=(0, 1.22))
    axes[2].set_xlabel('Simulation time (s)')
    fig.tight_layout(); save(fig, 'ext_trace_seed20')


def fig_line_sweep(df, key, xlabel, name, title, vline=None, vtext=None, logx=False):
    fig, axes = plt.subplots(1, 2, figsize=(TWO_COL, 2.3))
    for p in POLICIES:
        d = df[df.policy == p].sort_values(key)
        for ax, m in zip(axes, ['success', 'CVaR90']):
            mean = d[m + '_mean'] if m == 'success' else d[m]
            ax.fill_between(d[key], d[m + '_lo'], d[m + '_hi'], color=COLOR[p], alpha=0.15, lw=0)
            ax.plot(d[key], mean, marker=MARKER[p], color=COLOR[p], label=LABEL[p])
    axes[0].set_ylabel('Mission-success score'); axes[0].set_ylim(-0.02, 1.02)
    axes[1].set_ylabel('CVaR$_{0.90}$ mission loss')
    for ax, t in zip(axes, ['(a) ', '(b) ']):
        ax.set_xlabel(xlabel)
        if logx: ax.set_xscale('symlog', linthresh=0.01)
        if vline is not None:
            ax.axvline(vline, color=MUTED, lw=0.8)
            if vtext: ax.text(vline, ax.get_ylim()[1], vtext, fontsize=6.3, color=MUTED, ha='left', va='top')
    axes[0].set_title('(a) ' + title + ': success (95% CI)'); axes[1].set_title('(b) ' + title + ': tail loss (95% CI)')
    axes[0].legend(loc='best')
    fig.tight_layout(); save(fig, name)


def fig_stress_grid(df):
    fig, axes = plt.subplots(1, 4, figsize=(TWO_COL, 2.1), sharey=True)
    for ax, p in zip(axes, POLICIES):
        m = df[df.policy == p].pivot(index='severity', columns='total_prbs', values='success_mean').sort_index(ascending=False)
        im = ax.imshow(m.values, cmap='Blues', vmin=0, vmax=1, aspect='auto')
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                v = m.values[i, j]; ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=6, color='white' if v > 0.6 else INK)
        ax.set_xticks(range(m.shape[1]), m.columns); ax.set_yticks(range(m.shape[0]), [f'{v:.1f}' for v in m.index])
        ax.set_title(LABEL[p]); ax.set_xlabel('Total PRBs $B$'); ax.grid(False)
    axes[0].set_ylabel('Initial severity')
    fig.colorbar(im, ax=axes, fraction=0.02, pad=0.02, label='Mission-success score')
    save(fig, 'ext_stress_grid')


def fig_mars_params(ra, ht, mc):
    fig, axes = plt.subplots(2, 3, figsize=(TWO_COL, 3.4), sharex='col')
    for col, (df, key, xl) in enumerate([(ra, 'risk_aversion', r'Risk aversion $\rho$'), (ht, 'hold_time_s', 'Hold time $T_h$ (s)'),
                                         (mc, 'max_reconfig_per_step', r'Max change per step $\Delta_{max}$ (PRBs)')]):
        d = df.sort_values(key)
        ax = axes[0, col]
        ax.fill_between(d[key], d.success_lo, d.success_hi, color=COLOR['MARS_RISK_AWARE'], alpha=0.15, lw=0)
        ax.plot(d[key], d.success_mean, marker='o', color=COLOR['MARS_RISK_AWARE'])
        ax.set_ylim(0.3, 1.0)
        ax = axes[1, col]
        ax.plot(d[key], d.reconfig_mean, marker='o', color=COLOR['MARS_RISK_AWARE'])
        ax.set_xlabel(xl)
        if key == 'max_reconfig_per_step': ax.set_xscale('log', base=2)
    axes[0, 0].set_ylabel('Mission-success score'); axes[1, 0].set_ylabel('Reconfig. cost')
    for ax, (key, default) in zip(axes[0], [('ra', .55), ('ht', 4), ('mc', 16)]): ax.axvline(default, color=MUTED, lw=0.8)
    for ax, default in zip(axes[1], [.55, 4, 16]): ax.axvline(default, color=MUTED, lw=0.8)
    axes[0, 0].set_title('(a) Risk aversion'); axes[0, 1].set_title('(b) Hysteresis hold time'); axes[0, 2].set_title('(c) Per-step change limit')
    fig.tight_layout(); save(fig, 'ext_mars_params')


def fig_pareto(rdf):
    fig, ax = plt.subplots(figsize=(ONE_COL, 2.6))
    jit = np.random.default_rng(3)
    for p in POLICIES:
        d = rdf[rdf.policy == p]
        ax.scatter(d.total_reconfig_cost, d.mission_loss + jit.uniform(-0.25, 0.25, len(d)), s=12, marker=MARKER[p],
                   facecolor=COLOR[p], edgecolor='white', linewidth=0.4, alpha=0.9, label=LABEL[p])
        ax.scatter(d.total_reconfig_cost.mean(), d.mission_loss.mean(), s=60, marker=MARKER[p], facecolor=COLOR[p], edgecolor=INK, linewidth=0.9, zorder=5)
    ax.set_xlabel('Total reconfiguration cost (PRB-steps)'); ax.set_ylabel('Mission loss $L$')
    ax.set_title('Per-run loss vs. reconfiguration (outlined = mean)')
    ax.legend(loc='center right', fontsize=6.5)
    fig.tight_layout(); save(fig, 'ext_pareto')


def fig_ablation(ab, sat):
    fig = plt.figure(figsize=(TWO_COL, 2.5))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 0.9, 1.0])
    ax0 = fig.add_subplot(gs[0]); ax1 = fig.add_subplot(gs[1], sharey=ax0); ax2 = fig.add_subplot(gs[2])
    y = np.arange(len(ab))[::-1]
    for ax, m in zip([ax0, ax1], ['success', 'reconfig']):
        mean = ab[m + '_mean']
        full = ab[ab.variant == 'MARS-full'][m + '_mean'].iloc[0]
        ax.axvline(full, color=MUTED, lw=0.8)
        ax.errorbar(mean, y, xerr=[mean - ab[m + '_lo'], ab[m + '_hi'] - mean], fmt='o', color=COLOR['MARS_RISK_AWARE'], capsize=2.5, ms=4.5, lw=1.1)
        ax.grid(axis='y', visible=False)
    ax0.set_yticks(y, ab.variant); plt.setp(ax1.get_yticklabels(), visible=False)
    ax0.set_title('(a) Success (95% CI)'); ax1.set_title('(b) Reconfig. cost')
    ax1.set_xlabel('PRB-steps')
    ax2.plot(sat.t, sat.max_weight, color=COLOR['MARS_RISK_AWARE'], lw=1.1)
    ax2.set_ylim(0, 1.05); ax2.set_xlabel('Simulation time (s)'); ax2.set_ylabel('Largest slice weight')
    ax2.set_title('(c) Softmax saturation, seed 20')
    fig.tight_layout(); save(fig, 'ext_ablation')


def fig_latency(lat, rdf):
    fig, axes = plt.subplots(1, 2, figsize=(TWO_COL, 2.3))
    for p in POLICIES:
        x = np.sort(lat[lat.policy == p].control_latency_ms.values); yv = np.arange(1, len(x) + 1) / len(x)
        axes[0].plot(x, yv, color=COLOR[p], label=LABEL[p], marker=MARKER[p], markevery=len(x) // 6)
    axes[0].axhline(0.95, color=MUTED, lw=0.8); axes[0].text(9, 0.965, 'P95', fontsize=6.5, color=MUTED)
    axes[0].set_xlabel('Control-latency proxy (ms), all 300 s x 30 seeds'); axes[0].set_ylabel('Empirical CDF')
    axes[0].set_title('(a) Per-step control latency'); axes[0].legend(loc='lower right')
    data = [rdf[rdf.policy == p].p95_control_latency_ms.values for p in POLICIES]
    bp = axes[1].boxplot(data, orientation='horizontal', widths=0.5, patch_artist=True, medianprops={'color': INK}, flierprops={'markersize': 3})
    for patch, p in zip(bp['boxes'], POLICIES): patch.set_facecolor(COLOR[p]); patch.set_alpha(0.55); patch.set_edgecolor(MUTED)
    axes[1].set_yticks(range(1, 5), [LABEL[p] for p in POLICIES]); axes[1].grid(axis='y', visible=False)
    axes[1].set_xlabel('Per-run P95 control latency (ms)'); axes[1].set_title('(b) Run-level P95 spread (30 runs)')
    fig.tight_layout(); save(fig, 'ext_latency')


def fig_success_components(rdf):
    comps = [('mission_success_rate', 'Mission\nsuccess'), ('deadline_success_rate', 'Deadline\nmet'),
             ('reliability_success_rate', 'Reliability\nmet'), ('freshness_success_rate', 'Freshness\nmet')]
    fig, ax = plt.subplots(figsize=(ONE_COL, 2.3))
    x = np.arange(len(comps)); w = 0.2
    for i, p in enumerate(POLICIES):
        means = [rdf[rdf.policy == p][m].mean() for m, _ in comps]
        ax.bar(x + (i - 1.5) * w, means, w * 0.9, color=COLOR[p], label=LABEL[p])
    ax.set_xticks(x, [c for _, c in comps]); ax.set_ylim(0, 1.05); ax.set_ylabel('Fraction of tasks')
    ax.grid(axis='x', visible=False); ax.set_title('Task success components per policy')
    ax.legend(ncol=2, loc='upper center', bbox_to_anchor=(0.5, -0.3), fontsize=6.5)
    fig.tight_layout(); save(fig, 'ext_success_components')


# ---------------------------------------------------------------- driver
def main():
    print('[1] Main experiment re-run with per-task / per-step logging')
    rdf, tdf, traces, lat = main_experiment()
    print('[2] Bootstrap CIs and paired tests'); ci, paired = statistics_table(rdf)
    print('[3] Edge-case sweeps')
    prb = sweep('total_prbs', [50, 55, 60, 70, 80, 90, 100, 120, 150, 200], lambda v: {'overrides': {'radio': {'total_prbs': v}}})
    sev = sweep('initial_severity', [0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0], lambda v: {'overrides': {'incident': {'initial_severity': v}}})
    shk = sweep('shock_probability', [0.0, 0.005, 0.018, 0.04, 0.08, 0.15, 0.3], lambda v: {'overrides': {'incident': {'shock_probability': v}}})
    dl = sweep('deadline_scale', [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5], lambda v: {'deadline_scale': v})
    wl = sweep('workload_scale', [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0], lambda v: {'workload_scale': v})
    grid = []
    for prbs in [60, 80, 100, 120]:
        g = sweep('grid_tmp', [0.2, 0.4, 0.6, 0.8, 1.0], lambda v, b=prbs: {'overrides': {'incident': {'initial_severity': v}, 'radio': {'total_prbs': b}}})
        grid.append(g.rename(columns={'grid_tmp': 'severity'}).assign(total_prbs=prbs))
    grid = pd.concat(grid, ignore_index=True); grid.to_csv(RES / 'stress_grid.csv', index=False)
    for f in RES.glob('sweep_grid_tmp*'): f.unlink()
    mars = ['MARS_RISK_AWARE']
    ra = sweep('risk_aversion', [0.0, 0.2, 0.4, 0.55, 0.7, 0.85, 1.0], lambda v: {'overrides': {'controller': {'risk_aversion': v}}}, policies=mars)
    ht = sweep('hold_time_s', [0, 1, 2, 4, 6, 8, 12, 20], lambda v: {'overrides': {'controller': {'hold_time_s': v}}}, policies=mars)
    mc = sweep('max_reconfig_per_step', [1, 2, 4, 8, 16, 32, 64], lambda v: {'overrides': {'controller': {'max_reconfig_per_step': v}}}, policies=mars)
    print('[4] Extended ablation and weight saturation'); ab = ablation_extended(); sat = softmax_saturation()

    print('[5] Figures')
    fig_ci(ci); fig_success_components(rdf); fig_loss_tail(rdf); fig_task_breakdown(tdf); fig_gantt(tdf); fig_trace(traces)
    fig_line_sweep(prb, 'total_prbs', 'Total PRB budget $B$', 'ext_sweep_prbs', 'PRB budget', vline=50, vtext=r' $B=\sum B^{min}_s$')
    fig_line_sweep(sev, 'initial_severity', 'Initial incident severity', 'ext_sweep_severity', 'Severity')
    fig_line_sweep(shk, 'shock_probability', 'Network-shock probability per step', 'ext_sweep_shock', 'Shock rate', vline=0.018, vtext=' nominal')
    fig_line_sweep(dl, 'deadline_scale', 'Deadline scale factor (1 = nominal)', 'ext_sweep_deadline', 'Deadline tightness', vline=1.0)
    fig_line_sweep(wl, 'workload_scale', 'Task workload scale factor (1 = nominal)', 'ext_sweep_workload', 'Workload', vline=1.0)
    fig_stress_grid(grid); fig_mars_params(ra, ht, mc); fig_pareto(rdf); fig_ablation(ab, sat); fig_latency(lat, rdf)
    print('Done. CSVs ->', RES, ' figures ->', FIG)


if __name__ == '__main__':
    main()
