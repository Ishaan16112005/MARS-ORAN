"""MARS-O-RAN digital twin: mission-aware network slicing for an emergency-robotics mission.

One cell with B PRBs shared by four slices (SC robot control, SV perception video,
SX responder XR, SM safety sensing) and one MEC server. A mission DAG of five tasks
(config/tasks_v2.json, or the concurrent variant config/tasks_parallel.json) is executed
while an incident evolves. Every 1 s step a slicing policy chooses an integer PRB
allocation; the twin then advances task workloads, AoI and reliability.

Policies
  STATIC         fixed shares
  PROPORTIONAL   demand-proportional shares
  MISSION_AWARE  unit-temperature softmax over raw criticality scores (+18 % bonus)
  MYOPIC_OPT     per-step exhaustive search over all feasible integer allocations
                 (perfect knowledge of the current state, no look-ahead)
  MARS_V0        the controller of the initial draft (R0), kept for comparison
  MARS           proposed controller: normalised criticality with softmax temperature,
                 mission-gated risk reserve, damping toward b(t-1), slack-adaptive hold
                 time, and a transition mode (no hold, no damping) after task-set changes

Setting env.edge_bonus_all_policies=False, env.repair_respects_change_limit=False,
env.legacy_init=True and incident.initial_severity=0.6 reproduces the R0 environment
exactly (see tests/test_phase10.py::test_legacy_reproduces_r0).
"""
from __future__ import annotations
import json, math, random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / 'config'

SLICES = ['SC', 'SV', 'SX', 'SM']
POLICIES = ['STATIC', 'PROPORTIONAL', 'MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS']
ALIASES = {'MARS_RISK_AWARE': 'MARS'}          # name used by the old dashboard
MISSION_POLICIES = ('MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS')
CRITICAL_PATH = {'K1': 0.35, 'K2': 0.6, 'K3': 1.0, 'K4': 0.6, 'K5': 1.0}
STATIC_SHARES = {'SC': 0.29, 'SV': 0.26, 'SX': 0.18, 'SM': 0.27}
BASE_DEMAND = {'SC': 33, 'SV': 27, 'SX': 28, 'SM': 42}

LEGACY_R0 = {'env': {'edge_bonus_all_policies': False, 'repair_respects_change_limit': False, 'legacy_init': True},
             'incident': {'initial_severity': 0.6}}


def deep_update(base, overrides):
    out = json.loads(json.dumps(base))
    def rec(a, b):
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict): rec(a[k], v)
            else: a[k] = v
    rec(out, overrides or {})
    return out


def load_config(overrides=None):
    scenario = deep_update(json.loads((CFG / 'scenario_v2.json').read_text(encoding='utf-8')), overrides)
    tasks_file = scenario.get('env', {}).get('tasks_file', 'tasks_v2.json')
    tasks = json.loads((CFG / tasks_file).read_text(encoding='utf-8'))['tasks']
    return scenario, tasks


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def cvar(losses, beta: float = 0.90) -> float:
    """Exact empirical Rockafellar-Uryasev CVaR: mean of the worst (1-beta)N samples,
    with fractional weight on the boundary sample when (1-beta)N is not an integer."""
    a = np.sort(np.asarray(losses, dtype=float))[::-1]
    n = len(a)
    if n == 0: return 0.0
    if beta <= 0: return float(a.mean())
    m = (1.0 - beta) * n
    k = int(math.floor(m + 1e-9))
    frac = max(0.0, m - k)
    tail = a[:k].sum() + (a[k] * frac if k < n and frac > 1e-9 else 0.0)
    return float(tail / m)


def cvar_threshold(losses, beta: float = 0.90) -> float:
    """Estimator used in R0 (mean of losses >= beta-quantile); kept only to document the change."""
    a = np.asarray(losses, dtype=float)
    if len(a) == 0: return 0.0
    var = float(np.quantile(a, beta, method='linear'))
    tail = a[a >= var - 1e-12]
    return float(tail.mean()) if len(tail) else var


def fbl_factor(snr_linear, blocklength, epsilon: float = 0.01):
    """Finite-blocklength correction F in [0.55, 1] (normal-approximation surrogate); works on arrays."""
    snr = np.asarray(snr_linear, dtype=float); n = np.maximum(np.asarray(blocklength, dtype=float), 1.0)
    dispersion = 1.0 - 1.0 / (1.0 + 0.25 * snr)
    qinv = 2.326 if epsilon <= 0.01 else 1.645
    penalty = qinv * np.sqrt(np.maximum(dispersion, 1e-6) / n) / math.log(2)
    nominal = np.log2(1.0 + snr)
    return np.clip(1.0 - penalty / np.maximum(nominal, 0.1), 0.55, 1.0)


def reliability(sev, shock, load_ratio):
    """End-to-end success probability (radio x edge x backhaul); load_ratio may be an array."""
    rad = np.clip(0.999 - 0.030 * sev - 0.020 * np.maximum(0.0, np.asarray(load_ratio, dtype=float) - 1.0) - (0.060 if shock else 0.0), 0.82, 0.999)
    edg = clip(0.997 - 0.025 * sev - (0.040 if shock else 0.0), 0.84, 0.997)
    bh = clip(0.998 - 0.020 * sev - (0.040 if shock else 0.0), 0.85, 0.998)
    return rad * edg * bh


@dataclass
class TaskState:
    id: str
    name: str
    slice: str
    preds: List[str]
    activation: int
    deadline: int
    workload_bits: float
    compute_units: float
    value: float
    hazard: float
    max_failure: float
    max_aoi: float
    remaining_bits: float = 0.0
    remaining_compute: float = 0.0
    started: int | None = None
    finished: int | None = None
    aoi_at_finish: float = 999.0
    reliability_at_finish: float = 0.0
    max_criticality: float = 0.0

    def __post_init__(self):
        self.remaining_bits = self.workload_bits
        self.remaining_compute = self.compute_units


@dataclass
class SimState:
    t: int = 0
    severity: float = 0.0
    shock_timer: int = 0
    previous_alloc: Dict[str, int] = field(default_factory=lambda: {s: 25 for s in SLICES})
    last_change_t: int = -999               # t_last(0^-): reallocation is allowed at t = 0
    last_task_set: frozenset = frozenset()
    transition: bool = False               # MARS: task set changed and target not reached yet
    aoi: Dict[str, float] = field(default_factory=lambda: {s: 0.0 for s in SLICES})   # Delta_s(0^-) = 0
    task_rows: List[dict] = field(default_factory=list)
    trace: List[dict] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)


class MARSOranSimulator:
    def __init__(self, policy='MARS', seed=17, duration=None, overrides=None):
        self.cfg, task_specs = load_config(overrides)
        self.policy = ALIASES.get(policy.upper(), policy.upper())
        if self.policy not in POLICIES: raise ValueError(f'Unknown policy: {policy}')
        self.seed = int(seed)
        self.duration = int(duration or self.cfg['simulation']['duration_s'])
        self.rng = random.Random(self.seed)
        self.np_rng = np.random.default_rng(self.seed)
        self.env = {'edge_bonus_all_policies': True, 'repair_respects_change_limit': True,
                    'concurrent_tasks': False, 'legacy_init': False, **self.cfg.get('env', {})}
        self.tasks = [TaskState(
            id=t['id'], name=t['name'], slice=t['slice'], preds=list(t.get('predecessors', [])),
            activation=int(t['activation_s']), deadline=int(t['deadline_s']),
            workload_bits=float(t['workload_bits']), compute_units=float(t['compute_units']), value=float(t['value']),
            hazard=float(t['hazard_weight']), max_failure=float(t['max_failure_prob']), max_aoi=float(t['max_aoi_s']))
            for t in task_specs]
        r = self.cfg['radio']; self.B = int(r['total_prbs'])
        self.mins = dict(r['min_slice_prbs'])
        self.maxs = {s: (min(self.B, int(round(r['max_slice_prbs'][s] * self.B / 100))) if r.get('scale_max_with_budget') else int(r['max_slice_prbs'][s]))
                     for s in SLICES}
        p = self.cfg['controller']
        self.chi_ref = max(t.value for t in self.tasks) * (1 + p['alpha_urgency'] + p['alpha_hazard'] + p['alpha_critical_path'] + p['alpha_aoi'])
        self.state = SimState()
        if not self.env['legacy_init']: self.state.previous_alloc = self.initial_allocation()
        self.last_quality = {s: 1.0 for s in SLICES}
        self.total_reconfig = 0.0
        self.reliability_samples = []
        self.policy_hook = None             # optional callback(t, weights) for logging

    # ------------------------------------------------------------------ environment
    def initial_allocation(self):
        """b(0^-): equal share B/|S| projected onto the bounds, with deterministic remainder handling."""
        a = {s: int(clip(self.B // len(SLICES), self.mins[s], self.maxs[s])) for s in SLICES}
        while sum(a.values()) < self.B:
            for s in SLICES:
                if sum(a.values()) < self.B and a[s] < self.maxs[s]: a[s] += 1
        while sum(a.values()) > self.B:
            s = max([q for q in SLICES if a[q] > self.mins[q]], key=lambda q: a[q] - self.mins[q]); a[s] -= 1
        return a

    def current_severity(self, t):
        inc = self.cfg['incident']; start = inc['start_time_s']
        if t < start: return 0.05
        base = inc['initial_severity'] + (t - start) * inc['severity_growth_per_s']
        return clip(base + self.np_rng.normal(0, 0.025), 0.0, 1.0)

    def network_conditions(self, t):
        sev = self.current_severity(t)
        shock_p = self.cfg['incident']['shock_probability'] * (1 + sev)
        shock = self.state.shock_timer > 0
        if (not shock) and self.rng.random() < shock_p:
            self.state.shock_timer = int(self.cfg['incident']['shock_duration_s'])
            shock = True
            self.state.events.append({'time_s': t, 'event': 'NETWORK_SHOCK', 'severity': round(sev, 4)})
        if self.state.shock_timer > 0: self.state.shock_timer -= 1
        degradation = clip(0.15 * sev + (0.27 if shock else 0.0), 0, 0.65)
        channel = {s: clip(1.0 - degradation + self.np_rng.normal(0, 0.018), 0.45, 1.0) for s in SLICES}
        edge = clip(1.0 - 0.25 * sev - (0.18 if shock else 0), 0.55, 1.0)
        backhaul = clip(1.0 - 0.18 * sev - (0.25 if shock else 0), 0.55, 1.0)
        return sev, shock, channel, edge, backhaul

    def active_tasks(self):
        return [t for t in self.tasks if t.started is not None and t.finished is None]

    def startable_tasks(self):
        done = {t.id for t in self.tasks if t.finished is not None}
        busy = {t.slice for t in self.active_tasks()}
        out = []
        for t in self.tasks:
            if t.started is None and self.state.t >= t.activation and all(p in done for p in t.preds):
                if self.env['concurrent_tasks']:
                    if t.slice not in busy: out.append(t); busy.add(t.slice)
                else:
                    out.append(t)
        return out

    def decision_tasks(self):
        """R(t): the executing task(s); if none executes (chain mode), the tasks that may start now."""
        active = self.active_tasks()
        if self.env['concurrent_tasks']: return active + self.startable_tasks()
        return active[:1] if active else self.startable_tasks()

    def mission_active(self):
        return self.state.t >= self.cfg['incident']['start_time_s'] and any(t.finished is None for t in self.tasks)

    # ------------------------------------------------------------------ criticality and policies
    def task_criticality(self, task, severity):
        p = self.cfg['controller']
        slack = max(task.deadline - self.state.t, 0.5)
        urgency_n = clip(p['urgency_ref_s'] / (slack + p['urgency_epsilon_s']), 0.0, 1.0)
        aoi_pressure = clip(self.state.aoi[task.slice] / max(task.max_aoi, 1.0), 0, 3.0) / 3.0
        cp = CRITICAL_PATH.get(task.id, 0.35)
        score = task.value * (1.0 + p['alpha_urgency'] * urgency_n + p['alpha_hazard'] * severity * task.hazard
                              + p['alpha_critical_path'] * cp + p['alpha_aoi'] * aoi_pressure)
        task.max_criticality = max(task.max_criticality, score)
        return score

    def slice_scores(self, demand, severity, ready, normalized):
        total = max(sum(demand.values()), 1)
        u = {s: 0.0 for s in SLICES}
        for task in ready:
            chi = self.task_criticality(task, severity)
            if normalized: chi /= self.chi_ref
            u[task.slice] = max(u[task.slice], chi)
        dw = self.cfg['controller']['demand_weight']
        for s in SLICES: u[s] += dw * demand[s] / total
        return u

    @staticmethod
    def softmax(u, temperature=1.0):
        x = np.array([u[s] for s in SLICES]) / temperature
        e = np.exp(x - x.max())
        return {s: float(e[i] / e.sum()) for i, s in enumerate(SLICES)}

    def reserve(self, severity, shock, scale):
        rho = self.cfg['controller']['risk_aversion']
        g = (0.5 + severity) if (shock or severity > 0.72) else severity
        return scale * (0.55 + 0.9 * rho) * g

    def policy_weights(self, demand, severity, shock, ready):
        total = max(sum(demand.values()), 1)
        if self.policy == 'STATIC': return dict(STATIC_SHARES)
        if self.policy == 'PROPORTIONAL': return {s: demand[s] / total for s in SLICES}
        if self.policy == 'MISSION_AWARE':
            u = self.slice_scores(demand, severity, ready, normalized=False)
            target = max(u, key=u.get)
            u[target] += self.cfg['controller']['mission_aware_bonus'] * max(u.values())
            return self.softmax(u)
        if self.policy == 'MARS_V0':
            v0 = self.cfg['mars_v0']
            u = self.slice_scores(demand, severity, ready, normalized=False)
            target = max(u, key=u.get)
            r = self.reserve(severity, shock, v0['risk_reserve_prbs'])
            u['SC'] += 0.45 * r; u['SV'] += 0.35 * r; u[target] += 0.30 * r
            for s in SLICES: u[s] -= v0['reconfig_penalty'] * abs(self.state.previous_alloc[s] - 25)
            return self.softmax(u)
        # MARS (proposed)
        m = self.cfg['mars']
        u = self.slice_scores(demand, severity, ready, normalized=True)
        if self.mission_active():
            r = self.reserve(severity, shock, m['reserve_scale'])
            for s, share in m['reserve_split'].items(): u[s] += share * r
        w = self.softmax(u, m['temperature'])
        mu = 0.0 if self.state.transition else m['damping']      # no damping while a task transition is in progress
        prev = self.state.previous_alloc
        return {s: (1 - mu) * w[s] + mu * prev[s] / self.B for s in SLICES}

    def mars_update_transition(self, ready):
        """A change of the decision task set R(t) starts a transition: hold and damping are suspended
        until the (Delta_max-limited) allocation has reached the softmax target."""
        task_set = frozenset(t.id for t in ready)
        if self.cfg['mars'].get('release_on_task_change', True) and task_set != self.state.last_task_set:
            self.state.transition = True
        self.state.last_task_set = task_set

    def mars_hold(self, ready):
        m = self.cfg['mars']
        if self.state.transition:
            return False
        th = m['hold_time_s']
        if ready and m.get('slack_ref_s'):
            slack = min(t.deadline - self.state.t for t in ready)
            th = th * min(1.0, max(slack, 0.0) / m['slack_ref_s'])
        return self.state.t - self.state.last_change_t < th

    def bands(self):
        prev = self.state.previous_alloc
        if not self.env['repair_respects_change_limit']: return dict(self.mins), dict(self.maxs)
        d = self.cfg['controller']['max_reconfig_per_step']
        return ({s: max(self.mins[s], prev[s] - d) for s in SLICES}, {s: min(self.maxs[s], prev[s] + d) for s in SLICES})

    def repair(self, alloc, demand, lo, hi):
        """Make sum(alloc) == B: remove from the largest surplus over B_min, add to the largest (signed)
        unmet demand d_s - b_s; ties resolved by slice order SC, SV, SX, SM."""
        while sum(alloc.values()) > self.B:
            cands = [s for s in SLICES if alloc[s] > lo[s]]
            if not cands: break
            s = max(cands, key=lambda q: alloc[q] - self.mins[q]); alloc[s] -= 1
        while sum(alloc.values()) < self.B:
            cands = [s for s in SLICES if alloc[s] < hi[s]]
            if not cands: break
            s = max(cands, key=lambda q: demand[q] - alloc[q]); alloc[s] += 1
        return alloc

    def myopic_allocation(self, demand, sev, shock, channel, edge, ready, lo, hi):
        prev = self.state.previous_alloc
        if not ready: return dict(prev)
        r = self.cfg['radio']; e = self.cfg['edge']; bonus = e['active_task_bonus']
        g = np.meshgrid(*[np.arange(lo[s], hi[s] + 1) for s in SLICES[:3]], indexing='ij')
        b = {s: g[i].ravel() for i, s in enumerate(SLICES[:3])}
        b['SM'] = self.B - b['SC'] - b['SV'] - b['SX']
        ok = (b['SM'] >= lo['SM']) & (b['SM'] <= hi['SM'])
        b = {s: v[ok] for s, v in b.items()}
        if len(b['SC']) == 0: return dict(prev)
        cost = self.cfg['myopic']['reconfig_weight'] * sum(np.abs(b[s] - prev[s]) for s in SLICES)
        fsum = self.B + bonus * sum(b[t.slice] for t in ready)
        feasible = np.ones(len(cost), dtype=bool)
        for t in ready:
            s = t.slice; bs = b[s].astype(float)
            snr = 10 ** ((r['base_snr_db'][s] + 7.0 * math.log10(max(channel[s], 0.1))) / 10)
            rate = bs * r['prb_bandwidth_hz'] * math.log2(1 + snr) * r['spectral_efficiency_factor'] * channel[s] \
                * fbl_factor(snr, np.maximum(128, bs * r['channel_uses_per_prb']))
            comp = e['total_compute_units'] * bs * (1 + bonus) / fsum * e['compute_efficiency'] * edge / 10.0
            t_hat = np.maximum(t.remaining_bits / np.maximum(rate, 1e-9), t.remaining_compute / np.maximum(comp, 1e-9))
            rel_fail = reliability(sev, shock, demand[s] / np.maximum(bs, 1)) < 1.0 - t.max_failure
            wk = t.value * (1 + 0.25 * t.hazard)
            cost = cost + wk * t_hat + 50.0 * wk * rel_fail
            if s in ('SC', 'SV'): feasible &= bs >= self.mins[s] + 5
        if not feasible.any(): feasible[:] = True
        cost = np.where(feasible, cost, np.inf)
        i = int(np.argmin(cost))
        return {s: int(b[s][i]) for s in SLICES}

    def allocate_prbs(self, demand, severity, shock, channel, edge, ready):
        prev = self.state.previous_alloc
        lo, hi = self.bands()
        if self.policy == 'MYOPIC_OPT':
            alloc = self.myopic_allocation(demand, severity, shock, channel, edge, ready, lo, hi)
        else:
            if self.policy == 'MARS': self.mars_update_transition(ready)
            w = self.policy_weights(demand, severity, shock, ready)
            if self.policy_hook: self.policy_hook(self.state.t, w)
            if self.policy == 'MARS_V0':
                hold = self.state.t - self.state.last_change_t < self.cfg['mars_v0']['hold_time_s']
            elif self.policy == 'MARS':
                hold = self.mars_hold(ready)
            else:
                hold = False
            if hold:
                alloc = dict(prev)
            else:
                d = self.cfg['controller']['max_reconfig_per_step']
                target = {s: int(clip(int(round(self.B * w[s])), self.mins[s], self.maxs[s])) for s in SLICES}
                alloc = {s: int(clip(target[s], max(self.mins[s], prev[s] - d), min(self.maxs[s], prev[s] + d))) for s in SLICES}
                if self.policy == 'MARS' and self.state.transition and all(abs(target[s] - prev[s]) <= d for s in SLICES):
                    self.state.transition = False          # target reached in this step; hold re-arms afterwards
        alloc = self.repair(alloc, demand, lo, hi)
        chg = sum(abs(alloc[s] - prev[s]) for s in SLICES)
        if chg > 0: self.state.last_change_t = self.state.t
        self.total_reconfig += chg
        return alloc

    # ------------------------------------------------------------------ dynamics
    def step(self):
        t = self.state.t
        sev, shock, channel, edge, backhaul = self.network_conditions(t)
        self.state.severity = sev
        demand = {s: max(8.0, BASE_DEMAND[s] + self.rng.uniform(-7, 10) + 18 * sev * (1 if s in ('SV', 'SM') else 0.4)) for s in SLICES}
        ready = self.decision_tasks()
        alloc = self.allocate_prbs(demand, sev, shock, channel, edge, ready)
        radio = self.cfg['radio']; E = self.cfg['edge']
        # Edge shares (Eq. 7). The active-task bonus is part of the environment and applies to every
        # policy unless the legacy R0 behaviour is requested.
        active_now = self.active_tasks()
        compute_share = {s: E['total_compute_units'] * alloc[s] / max(self.B, 1) for s in SLICES}
        if active_now:
            gets_bonus = self.env['edge_bonus_all_policies'] or self.policy in MISSION_POLICIES
            for a in active_now:
                compute_share[a.slice] *= (1.0 + (E['active_task_bonus'] if gets_bonus else 0.0))
            scale = E['total_compute_units'] / max(sum(compute_share.values()), 1e-9)
            compute_share = {s: compute_share[s] * scale for s in SLICES}
        # AoI (updated before the task-completion checks of this step).
        for s in SLICES:
            if alloc[s] >= self.mins[s] + (5 if s in ('SC', 'SV') else 0):
                self.state.aoi[s] = self.cfg['aoi']['fresh_update_aoi_s']
            else:
                self.state.aoi[s] += 1
        # Start tasks (chain mode: one at a time; concurrent mode: one per free slice).
        if self.env['concurrent_tasks']:
            starting = self.startable_tasks()
        else:
            starting = self.startable_tasks()[:1] if not active_now else []
        for task in starting:
            task.started = t
            self.state.events.append({'time_s': t, 'event': 'START', 'task_id': task.id})
        # Serve every executing task on its slice.
        for active in self.active_tasks():
            s = active.slice
            snr_lin = 10 ** ((radio['base_snr_db'][s] + 7.0 * math.log10(max(channel[s], 0.1))) / 10)
            fbl = float(fbl_factor(snr_lin, max(128, alloc[s] * radio['channel_uses_per_prb'])))
            rate_bps = alloc[s] * radio['prb_bandwidth_hz'] * math.log2(1 + snr_lin) * radio['spectral_efficiency_factor'] * fbl * channel[s]
            compute_rate = compute_share[s] * E['compute_efficiency'] * edge
            active.remaining_bits = max(0.0, active.remaining_bits - rate_bps)          # bits (L_k in bits)
            active.remaining_compute = max(0.0, active.remaining_compute - compute_rate / 10.0)
            rel = float(reliability(sev, shock, demand[s] / max(alloc[s], 1)))
            self.last_quality[s] = rel
            self.reliability_samples.append(rel)
            if active.remaining_bits <= 0 and active.remaining_compute <= 0:
                finish = t + 1
                active.finished = finish
                active.aoi_at_finish = self.state.aoi[s]
                active.reliability_at_finish = rel
                deadline_ok = finish <= active.deadline
                freshness_ok = active.aoi_at_finish <= active.max_aoi
                reliability_ok = rel >= 1.0 - active.max_failure
                success = int(deadline_ok and freshness_ok and reliability_ok)
                value = active.value * (1.0 if success else (0.45 if deadline_ok else 0.10))
                self.state.task_rows.append({
                    'policy': self.policy, 'seed': self.seed, 'task_id': active.id, 'task_name': active.name, 'slice': s,
                    'start_s': active.started, 'finish_s': finish, 'deadline_s': active.deadline, 'late_by_s': max(0, finish - active.deadline),
                    'deadline_met': int(deadline_ok), 'freshness_ok': int(freshness_ok), 'reliability_ok': int(reliability_ok), 'success': success,
                    'aoi_at_finish_s': round(active.aoi_at_finish, 3), 'reliability': round(rel, 5), 'severity_at_finish': round(sev, 5),
                    'criticality_max': round(active.max_criticality, 4), 'mission_value': round(value, 4)})
                self.state.events.append({'time_s': finish, 'event': 'COMPLETE' if success else 'FAIL', 'task_id': active.id, 'success': success})

        control_latency = 8.0 + 0.55 * max(0, 35 - alloc['SC']) + 7.0 * sev + (8.0 if shock else 0) + self.rng.random() * 2.5
        delivered = sum(min(demand[s], alloc[s]) for s in SLICES)
        e2e_latency = 4.0 + self.cfg['backhaul']['base_latency_ms'] + self.cfg['backhaul']['jitter_ms'] * self.rng.random() + max(0, 20 - alloc['SC']) * 0.7 + 20 * sev
        executing = [a.id for a in self.tasks if a.started is not None and (a.finished is None or a.finished == t + 1)]
        self.state.trace.append({
            'time_s': t, 'policy': self.policy, 'severity': round(sev, 5), 'shock': int(shock), 'active_task': '+'.join(executing),
            'aoi_SC_s': round(self.state.aoi['SC'], 3), 'aoi_SV_s': round(self.state.aoi['SV'], 3),
            'control_latency_ms': round(control_latency, 4), 'e2e_latency_ms': round(e2e_latency, 4),
            'edge_factor': round(edge, 5), 'backhaul_factor': round(backhaul, 5),
            'delivery_ratio': round(delivered / max(sum(demand.values()), 1), 5),
            'reconfig_cost': sum(abs(alloc[s] - self.state.previous_alloc[s]) for s in SLICES),
            **{f'prb_{s}': alloc[s] for s in SLICES}, **{f'demand_{s}': round(demand[s], 3) for s in SLICES},
            **{f'edge_share_{s}': round(compute_share[s], 3) for s in SLICES}})
        self.state.previous_alloc = alloc.copy()
        self.state.t += 1
        return self.state.trace[-1]

    def run(self):
        for _ in range(self.duration): self.step()
        return self.result()

    def mission_end(self):
        """tau_end: completion of the last task, or the horizon if some task never finishes."""
        if all(t.finished is not None for t in self.tasks): return max(t.finished for t in self.tasks)
        return self.duration

    def result(self):
        tasks = pd.DataFrame(self.state.task_rows)
        trace = pd.DataFrame(self.state.trace)
        total = len(self.tasks)
        col = lambda c: int(tasks[c].sum()) if not tasks.empty else 0
        mission_value = float(tasks['mission_value'].sum()) if not tasks.empty else 0.0
        loss = sum(t.value * (1 + 0.25 * t.hazard) for t in self.tasks) - mission_value
        t0, tend = self.cfg['incident']['start_time_s'], self.mission_end()
        out = {'policy': self.policy, 'seed': self.seed, 'tasks_completed_success': col('success'), 'tasks_observed': len(tasks), 'tasks_total': total,
               'mission_success_rate': col('success') / total, 'deadline_success_rate': col('deadline_met') / total,
               'freshness_success_rate': col('freshness_ok') / total, 'reliability_success_rate': col('reliability_ok') / total,
               'full_mission': int(col('success') == total), 'mission_end_s': tend,
               'total_reconfig_cost': float(self.total_reconfig), 'mission_value': mission_value, 'mission_loss': loss,
               'mean_reliability': float(np.mean(self.reliability_samples)) if self.reliability_samples else 0.0}
        if not trace.empty:
            mw = (trace.time_s >= t0) & (trace.time_s < tend)
            out.update({'reconfig_mission': float(trace.reconfig_cost[mw].sum()), 'reconfig_idle': float(trace.reconfig_cost[~mw].sum()),
                        'mean_control_latency_ms': float(trace.control_latency_ms.mean()), 'p95_control_latency_ms': float(trace.control_latency_ms.quantile(.95)),
                        'control_latency_mission_ms': float(trace.control_latency_ms[mw].mean()) if mw.any() else float('nan'),
                        'control_latency_after_ms': float(trace.control_latency_ms[trace.time_s >= tend].mean()) if (trace.time_s >= tend).any() else float('nan'),
                        'mean_e2e_latency_ms': float(trace.e2e_latency_ms.mean()), 'p95_e2e_latency_ms': float(trace.e2e_latency_ms.quantile(.95)),
                        'mean_aoi_SC_s': float(trace.aoi_SC_s.mean()), 'mean_aoi_SV_s': float(trace.aoi_SV_s.mean()),
                        'mean_delivery_ratio': float(trace.delivery_ratio.mean())})
        return out


def run_one(policy, seed, overrides=None, duration=None, deadline_scale=1.0, workload_scale=1.0, return_sim=False):
    """One run. deadline_scale stretches each deadline relative to the incident start (rounded to 1 s);
    workload_scale multiplies both the bit and the compute workload of every task."""
    sim = MARSOranSimulator(policy=policy, seed=seed, duration=duration, overrides=overrides)
    start = sim.cfg['incident']['start_time_s']
    for t in sim.tasks:
        if deadline_scale != 1.0:
            t.deadline = int(round(start + (t.deadline - start) * deadline_scale))
        if workload_scale != 1.0:
            t.workload_bits *= workload_scale; t.remaining_bits = t.workload_bits
            t.compute_units *= workload_scale; t.remaining_compute = t.compute_units
    res = sim.run()
    return (res, sim) if return_sim else res


if __name__ == '__main__':
    for p in POLICIES:
        r = run_one(p, 20)
        print(f"{p:14s} success={r['mission_success_rate']:.2f} loss={r['mission_loss']:.3f} reconfig={r['total_reconfig_cost']:.0f}")
