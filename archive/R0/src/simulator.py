from __future__ import annotations
import json, math, random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / 'config'

SLICES = ['SC','SV','SX','SM']
POLICIES = ['STATIC','PROPORTIONAL','MISSION_AWARE','MARS_RISK_AWARE']


def load_config():
    scenario = json.loads((CFG/'scenario_v2.json').read_text(encoding='utf-8'))
    tasks = json.loads((CFG/'tasks_v2.json').read_text(encoding='utf-8'))['tasks']
    return scenario, tasks


def clip(x, lo, hi): return max(lo, min(hi, x))


def cvar(losses: List[float], beta: float=0.90) -> float:
    a = np.asarray(losses, dtype=float)
    if len(a) == 0: return 0.0
    var = float(np.quantile(a, beta, method='linear'))
    tail = a[a >= var - 1e-12]
    return float(tail.mean()) if len(tail) else var


def finite_blocklength_penalty(snr_linear: float, blocklength: float, epsilon: float=0.01) -> float:
    # Conservative normalized dispersion penalty; keeps the model algebraic and reproducible.
    dispersion = 1.0 - 1.0 / (1.0 + 0.25 * snr_linear)
    qinv = 2.326 if epsilon <= 0.01 else 1.645
    penalty = qinv * math.sqrt(max(dispersion, 1e-6) / max(blocklength, 1.0)) / math.log(2)
    nominal = math.log2(1.0 + snr_linear)
    return clip(1.0 - penalty / max(nominal, 0.1), 0.55, 1.0)


@dataclass
class TaskState:
    id: str
    name: str
    slice: str
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
    previous_alloc: Dict[str,int] = field(default_factory=lambda:{s:25 for s in SLICES})
    last_change_t: int = -999
    aoi: Dict[str,float] = field(default_factory=lambda:{s:0.0 for s in SLICES})
    task_rows: List[dict] = field(default_factory=list)
    trace: List[dict] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)


class MARSOranSimulator:
    def __init__(self, policy='MARS_RISK_AWARE', seed=17, duration=None, overrides=None):
        self.cfg, task_specs = load_config()
        if overrides:
            self.cfg = deep_update(self.cfg, overrides)
        self.policy = policy.upper()
        if self.policy not in POLICIES: raise ValueError(f'Unknown policy: {policy}')
        self.seed = int(seed)
        self.duration = int(duration or self.cfg['simulation']['duration_s'])
        self.rng = random.Random(self.seed)
        self.np_rng = np.random.default_rng(self.seed)
        self.tasks = [TaskState(
            id=t['id'], name=t['name'], slice=t['slice'], activation=int(t['activation_s']), deadline=int(t['deadline_s']),
            workload_bits=float(t['workload_bits']), compute_units=float(t['compute_units']), value=float(t['value']),
            hazard=float(t['hazard_weight']), max_failure=float(t['max_failure_prob']), max_aoi=float(t['max_aoi_s']))
            for t in task_specs
        ]
        self.state = SimState()
        self.last_quality = {s:1.0 for s in SLICES}
        self.aoi_updates = {s:0 for s in SLICES}
        self.total_reconfig = 0.0
        self.reliability_samples = []
        self.service_events = []

    def current_severity(self, t):
        inc = self.cfg['incident']; start=inc['start_time_s']
        if t < start: return 0.05
        base = inc['initial_severity'] + (t-start)*inc['severity_growth_per_s']
        noise = self.np_rng.normal(0, 0.025)
        return clip(base + noise, 0.0, 1.0)

    def network_conditions(self, t):
        sev = self.current_severity(t)
        shock_p = self.cfg['incident']['shock_probability'] * (1 + sev)
        shock = self.state.shock_timer > 0
        if (not shock) and self.rng.random() < shock_p:
            self.state.shock_timer = int(self.cfg['incident']['shock_duration_s'])
            shock = True
            self.state.events.append({'time_s':t,'event':'NETWORK_SHOCK','severity':round(sev,4)})
        if self.state.shock_timer > 0: self.state.shock_timer -= 1
        degradation = clip(0.15*sev + (0.27 if shock else 0.0), 0, 0.65)
        channel = {s: clip(1.0-degradation + self.np_rng.normal(0,0.018), 0.45, 1.0) for s in SLICES}
        edge = clip(1.0-0.25*sev-(0.18 if shock else 0),0.55,1.0)
        backhaul = clip(1.0-0.18*sev-(0.25 if shock else 0),0.55,1.0)
        return sev, shock, channel, edge, backhaul

    def ready_tasks(self):
        done = {t.id for t in self.tasks if t.finished is not None}
        active = [t for t in self.tasks if t.started is not None and t.finished is None]
        if active: return active[:1]
        ready=[]
        for t in self.tasks:
            if t.finished is None and t.started is None and self.state.t >= t.activation:
                preds = next((spec.get('predecessors',[]) for spec in json.loads((CFG/'tasks_v2.json').read_text())['tasks'] if spec['id']==t.id),[])
                if all(p in done for p in preds): ready.append(t)
        return ready

    def task_criticality(self, task, severity):
        p = self.cfg['controller']
        slack = max(task.deadline-self.state.t, 0.5)
        urgency = 1.0 / (slack + p['urgency_epsilon_s'])
        # Normalize urgency against a 40-s reference to keep weights in a practical range.
        urgency_n = clip(40.0*urgency, 0.0, 1.0)
        aoi_pressure = clip(self.state.aoi[task.slice] / max(task.max_aoi,1.0), 0, 3.0) / 3.0
        cp = 1.0 if task.id in ('K3','K5') else 0.6 if task.id in ('K2','K4') else 0.35
        risk = severity * task.hazard
        score = task.value * (1.0 + p['alpha_urgency']*urgency_n + p['alpha_hazard']*risk + p['alpha_critical_path']*cp + p['alpha_aoi']*aoi_pressure + p['alpha_risk']*risk)
        task.max_criticality=max(task.max_criticality,score)
        return score

    def policy_weights(self, demand, severity, shock):
        p=self.cfg['controller']; total=max(sum(demand.values()),1)
        if self.policy=='STATIC':
            return {'SC':0.29,'SV':0.26,'SX':0.18,'SM':0.27}
        if self.policy=='PROPORTIONAL':
            return {s:demand[s]/total for s in SLICES}
        ready=self.ready_tasks()
        urgency_scores={s:0.0 for s in SLICES}
        for task in ready: urgency_scores[task.slice]=max(urgency_scores[task.slice], self.task_criticality(task,severity))
        for s in SLICES: urgency_scores[s] += 0.35*demand[s]/total
        if self.policy=='MISSION_AWARE':
            bonus=max(urgency_scores.values())*0.18
            target=max(urgency_scores,key=urgency_scores.get)
            urgency_scores[target]+=bonus
        else:
            # Tail-risk reserve: protect SC/SV when severity/shock is high while avoiding constant oscillation.
            target=max(urgency_scores,key=urgency_scores.get)
            reserve=p['risk_reserve_prbs']*(0.5 + severity) * (0.55 + 0.9*p['risk_aversion']) if shock or severity>0.72 else p['risk_reserve_prbs']*severity*(0.55 + 0.9*p['risk_aversion'])
            urgency_scores['SC'] += 0.45*reserve
            urgency_scores['SV'] += 0.35*reserve
            urgency_scores[target] += 0.30*reserve
            # Penalize unnecessary reconfiguration using distance to prior allocation.
            for s in SLICES:
                urgency_scores[s] -= p['reconfig_penalty']*abs(self.state.previous_alloc[s]-25)
        exp=np.exp(np.array([urgency_scores[s] for s in SLICES])-max(urgency_scores.values()))
        weights={s:float(exp[i]/exp.sum()) for i,s in enumerate(SLICES)}
        return weights

    def allocate_prbs(self,demand,severity,shock):
        radio=self.cfg['radio']; mins=radio['min_slice_prbs']; maxs=radio['max_slice_prbs']; total=radio['total_prbs']
        weights=self.policy_weights(demand,severity,shock)
        target={s:int(round(total*weights[s])) for s in SLICES}
        alloc={s:int(clip(target[s],mins[s],maxs[s])) for s in SLICES}
        # Enforce maximum per-step reconfiguration and budgets.
        prev=self.state.previous_alloc
        maxchg=self.cfg['controller']['max_reconfig_per_step']
        can_change=self.state.t-self.state.last_change_t >= self.cfg['controller']['hold_time_s']
        if self.policy=='MARS_RISK_AWARE' and not can_change:
            alloc=prev.copy()
        else:
            for s in SLICES:
                lo=max(mins[s],prev[s]-maxchg); hi=min(maxs[s],prev[s]+maxchg)
                alloc[s]=int(clip(alloc[s],lo,hi))
        def fix_budget():
            while sum(alloc.values())>total:
                candidates=[s for s in SLICES if alloc[s]>mins[s]]
                if not candidates: break
                s=max(candidates,key=lambda q:alloc[q]-mins[q]); alloc[s]-=1
            while sum(alloc.values())<total:
                candidates=[s for s in SLICES if alloc[s]<maxs[s]]
                if not candidates: break
                s=max(candidates,key=lambda q:(demand[q]-alloc[q])) ; alloc[s]+=1
        fix_budget()
        chg=sum(abs(alloc[s]-prev[s]) for s in SLICES)
        if chg>0: self.state.last_change_t=self.state.t
        self.total_reconfig += chg
        return alloc

    def step(self):
        t=self.state.t
        sev,shock,channel,edge,backhaul=self.network_conditions(t)
        self.state.severity=sev
        demand={s:max(8.0, {'SC':33,'SV':27,'SX':28,'SM':42}[s] + self.rng.uniform(-7,10) + 18*sev*(1 if s in ('SV','SM') else 0.4)) for s in SLICES}
        alloc=self.allocate_prbs(demand,sev,shock)
        radio=self.cfg['radio'];
        # compute share is based on current active task; remainder is shared between slices.
        active=next((x for x in self.tasks if x.started is not None and x.finished is None), None)
        task_criticality={s:0.0 for s in SLICES}
        if active: task_criticality[active.slice]=self.task_criticality(active,sev)
        compute_share={s:self.cfg['edge']['total_compute_units']*(alloc[s]/max(radio['total_prbs'],1)) for s in SLICES}
        # During an active mission task, its slice receives a small edge-side priority bonus.
        if active:
            bonus=0.15 if self.policy in ('MISSION_AWARE','MARS_RISK_AWARE') else 0.0
            compute_share[active.slice] *= (1.0 + bonus)
            z=sum(compute_share.values())
            scale=self.cfg['edge']['total_compute_units']/max(z,1e-9)
            compute_share={s:compute_share[s]*scale for s in SLICES}

        # AoI: safety/control receive fresh updates based on delivered service budget.
        for s in SLICES:
            served = alloc[s] >= radio['min_slice_prbs'][s] + (5 if s in ('SC','SV') else 0)
            if served:
                self.state.aoi[s]=self.cfg['aoi']['fresh_update_aoi_s']; self.aoi_updates[s]+=1
            else: self.state.aoi[s]+=1

        ready=self.ready_tasks()
        if active is None and ready:
            task=ready[0]
            task.started=t
            self.state.events.append({'time_s':t,'event':'START','task_id':task.id})
            active=task
        # Calculate per-second rates for the active task.
        if active:
            s=active.slice
            snr_db=radio['base_snr_db'][s] + 7.0*math.log10(max(channel[s],0.1))
            snr_lin=10**(snr_db/10)
            fbl=finite_blocklength_penalty(snr_lin, blocklength=max(128,alloc[s]*1800))
            rate_bps=alloc[s]*radio['prb_bandwidth_hz']*math.log2(1+snr_lin)*radio['spectral_efficiency_factor']*fbl*channel[s]
            compute_rate=compute_share[s]*self.cfg['edge']['compute_efficiency']*edge
            # State updates: the same timestep carries radio bits and normalized compute work.
            active.remaining_bits=max(0.0,active.remaining_bits-rate_bps)
            active.remaining_compute=max(0.0,active.remaining_compute-compute_rate/10.0)
            load_ratio=demand[s]/max(alloc[s],1)
            radio_rel=clip(0.999 - 0.030*sev - 0.020*max(0.0,load_ratio-1.0) - (0.060 if shock else 0.0),0.82,0.999)
            edge_rel=clip(0.997-0.025*sev-(0.040 if shock else 0),0.84,0.997)
            bh_rel=clip(0.998-0.020*sev-(0.040 if shock else 0),0.85,0.998)
            rel=radio_rel*edge_rel*bh_rel
            self.last_quality[s]=rel
            self.reliability_samples.append(rel)
            if active.remaining_bits<=0 and active.remaining_compute<=0:
                finish=t+1
                active.finished=finish
                active.aoi_at_finish=self.state.aoi[s]
                active.reliability_at_finish=rel
                deadline_ok=(finish<=active.deadline)
                freshness_ok=(active.aoi_at_finish<=active.max_aoi)
                reliability_ok=(rel >= 1.0-active.max_failure)
                late=max(0,finish-active.deadline)
                success=int(deadline_ok and freshness_ok and reliability_ok)
                value=active.value*(1.0 if success else (0.45 if deadline_ok else 0.10))
                self.state.task_rows.append({
                    'policy':self.policy,'seed':self.seed,'task_id':active.id,'task_name':active.name,'slice':active.slice,
                    'start_s':active.started,'finish_s':finish,'deadline_s':active.deadline,'late_by_s':late,
                    'deadline_met':int(deadline_ok),'freshness_ok':int(freshness_ok),'reliability_ok':int(reliability_ok),'success':success,
                    'aoi_at_finish_s':round(active.aoi_at_finish,3),'reliability':round(rel,5),'criticality_max':round(active.max_criticality,4),'mission_value':round(value,4)
                })
                self.state.events.append({'time_s':finish,'event':'COMPLETE' if success else 'FAIL','task_id':active.id,'success':success})

        control_latency=8.0 + 0.55*max(0,35-alloc['SC']) + 7.0*sev + (8.0 if shock else 0) + self.rng.random()*2.5
        delivered=sum(min(demand[s],alloc[s]) for s in SLICES)
        demand_sum=sum(demand.values())
        e2e_latency=4.0 + self.cfg['backhaul']['base_latency_ms'] + self.cfg['backhaul']['jitter_ms']*self.rng.random() + max(0,20-alloc['SC'])*0.7 + 20*sev
        self.state.trace.append({
            'time_s':t,'policy':self.policy,'severity':round(sev,5),'shock':int(shock),'active_task':active.id if active else '',
            'aoi_SC_s':round(self.state.aoi['SC'],3),'aoi_SV_s':round(self.state.aoi['SV'],3),
            'control_latency_ms':round(control_latency,4),'e2e_latency_ms':round(e2e_latency,4),'edge_factor':round(edge,5),'backhaul_factor':round(backhaul,5),
            'radio_reliability':round(float(active.reliability_at_finish) if active and active.finished is not None else float(np.mean(list(self.last_quality.values()))),5),
            'delivery_ratio':round(delivered/max(demand_sum,1),5),'reconfig_cost':sum(abs(alloc[s]-self.state.previous_alloc[s]) for s in SLICES),
            **{f'prb_{s}':alloc[s] for s in SLICES}, **{f'demand_{s}':round(demand[s],3) for s in SLICES}
        })
        self.state.previous_alloc=alloc.copy()
        self.state.t+=1
        return self.state.trace[-1]

    def run(self):
        for _ in range(self.duration): self.step()
        return self.result()

    def result(self):
        tasks=pd.DataFrame(self.state.task_rows)
        trace=pd.DataFrame(self.state.trace)
        total=len(self.tasks)
        completed=int(tasks['success'].sum()) if not tasks.empty else 0
        deadline=int(tasks['deadline_met'].sum()) if not tasks.empty else 0
        freshness=int(tasks['freshness_ok'].sum()) if not tasks.empty else 0
        reliability=int(tasks['reliability_ok'].sum()) if not tasks.empty else 0
        mission_value=float(tasks['mission_value'].sum()) if not tasks.empty else 0.0
        weights=[]
        for t in self.tasks: weights.append(t.value*(1+0.25*t.hazard))
        denom=sum(weights) or 1
        loss=denom-mission_value
        if trace.empty:
            mean_control = p95_control = mean_e2e = p95_e2e = 0.0
            mean_aoi_sc = mean_aoi_sv = mean_delivery = 0.0
        else:
            mean_control = float(trace['control_latency_ms'].mean())
            p95_control = float(trace['control_latency_ms'].quantile(.95))
            mean_e2e = float(trace['e2e_latency_ms'].mean())
            p95_e2e = float(trace['e2e_latency_ms'].quantile(.95))
            mean_aoi_sc = float(trace['aoi_SC_s'].mean())
            mean_aoi_sv = float(trace['aoi_SV_s'].mean())
            mean_delivery = float(trace['delivery_ratio'].mean())
        return {
            'policy':self.policy,'seed':self.seed,'tasks_completed_success':completed,'tasks_observed':len(tasks),'tasks_total':total,
            'mission_success_rate':completed/total if total else 0.0,
            'deadline_success_rate':deadline/total if total else 0.0,
            'freshness_success_rate':freshness/total if total else 0.0,
            'reliability_success_rate':reliability/total if total else 0.0,
            'mean_control_latency_ms':mean_control,'p95_control_latency_ms':p95_control,
            'mean_e2e_latency_ms':mean_e2e,'p95_e2e_latency_ms':p95_e2e,
            'mean_aoi_SC_s':mean_aoi_sc,'mean_aoi_SV_s':mean_aoi_sv,'mean_delivery_ratio':mean_delivery,
            'total_reconfig_cost':float(self.total_reconfig),'mission_value':mission_value,'mission_loss':loss,
            'mean_reliability':float(np.mean(self.reliability_samples)) if self.reliability_samples else 0.0,
        }


def deep_update(base, overrides):
    out=json.loads(json.dumps(base))
    def rec(a,b):
        for k,v in b.items():
            if isinstance(v,dict) and isinstance(a.get(k),dict): rec(a[k],v)
            else: a[k]=v
    rec(out,overrides); return out


def run_one(policy,seed,overrides=None,duration=None):
    sim=MARSOranSimulator(policy=policy,seed=seed,duration=duration,overrides=overrides)
    result=sim.run(); return result,pd.DataFrame(sim.state.task_rows),pd.DataFrame(sim.state.trace),pd.DataFrame(sim.state.events)


def run_experiments(seeds=range(20,50), duration=None):
    out=ROOT/'results'; out.mkdir(exist_ok=True)
    results=[]; tasks=[]; all_losses=[]
    first_trace=None; first_events=None; first_tasks=None
    for seed in seeds:
        for policy in POLICIES:
            res,tr,trace,events=run_one(policy,seed,duration=duration)
            results.append(res); all_losses.append({'policy':policy,'seed':seed,'mission_loss':res['mission_loss']})
            if not tr.empty: tasks.append(tr)
            if seed==min(seeds) and policy=='MARS_RISK_AWARE': first_trace,first_events,first_tasks=trace,events,tr
    rdf=pd.DataFrame(results); tdf=pd.concat(tasks,ignore_index=True) if tasks else pd.DataFrame()
    rdf.to_csv(out/'experiment_runs.csv',index=False); tdf.to_csv(out/'task_results.csv',index=False)
    summary=rdf.groupby('policy').agg(['mean','std'])
    rows=[]
    for p in POLICIES:
        sub=rdf[rdf.policy==p]
        row={'policy':p,'runs':len(sub)}
        for m in ['mission_success_rate','deadline_success_rate','freshness_success_rate','reliability_success_rate','mean_control_latency_ms','p95_control_latency_ms','mean_e2e_latency_ms','p95_e2e_latency_ms','mean_aoi_SC_s','mean_aoi_SV_s','mean_delivery_ratio','total_reconfig_cost','mission_value','mission_loss','mean_reliability']:
            row[m+'_mean']=float(sub[m].mean()); row[m+'_std']=float(sub[m].std(ddof=1) if len(sub)>1 else 0)
        losses=sub['mission_loss'].values.tolist(); row['VaR90']=float(np.quantile(losses,.90)); row['CVaR90']=cvar(losses,.90); rows.append(row)
    pd.DataFrame(rows).to_csv(out/'policy_summary.csv',index=False)
    cdf=pd.DataFrame(all_losses)
    cdf.to_csv(out/'cvar_losses.csv',index=False)
    if first_trace is not None:
        first_trace.to_csv(out/'timeseries_mars.csv',index=False); first_tasks.to_csv(out/'mars_task_trace.csv',index=False); first_events.to_csv(out/'mars_events.csv',index=False)
    meta={'seeds':len(list(seeds)),'policies':POLICIES,'duration_s':duration or 300,'note':'Synthetic digital-twin model; not a measurement of commercial O-RAN performance.'}
    (out/'experiment_meta.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return pd.DataFrame(rows),rdf,tdf


def sensitivity_experiment():
    out=ROOT/'results'; out.mkdir(exist_ok=True)
    rows=[]
    for sev in [0.2,0.4,0.6,0.8,1.0]:
        for prbs in [60,80,100,120]:
            scenario={'incident':{'initial_severity':sev},'radio':{'total_prbs':prbs}}
            for policy in ['PROPORTIONAL','MARS_RISK_AWARE']:
                vals=[]
                for seed in [41,42,43,44,45]:
                    res,_,_,_=run_one(policy,seed,overrides=scenario)
                    vals.append(res['mission_success_rate'])
                rows.append({'severity':sev,'total_prbs':prbs,'policy':policy,'mission_success_mean':np.mean(vals),'mission_success_std':np.std(vals,ddof=1)})
    df=pd.DataFrame(rows); df.to_csv(out/'sensitivity_severity_prbs.csv',index=False)
    return df


def ablation_experiment():
    out=ROOT/'results'; out.mkdir(exist_ok=True)
    modes={
        'MARS-full':{},
        'no-AoI':{'controller':{'alpha_aoi':0.0}},
        'no-risk-reserve':{'controller':{'risk_reserve_prbs':0}},
        'no-hysteresis':{'controller':{'hold_time_s':0}},
        'no-urgency':{'controller':{'alpha_urgency':0.0}},
    }
    rows=[]
    for name,ov in modes.items():
        vals=[]
        for seed in [51,52,53,54,55,56]:
            r,_,_,_=run_one('MARS_RISK_AWARE',seed,overrides=ov); vals.append(r)
        row={'variant':name}
        for m in ['mission_success_rate','deadline_success_rate','mean_aoi_SC_s','mean_aoi_SV_s','total_reconfig_cost','CVaR90']:
            if m=='CVaR90': row[m]=cvar([x['mission_loss'] for x in vals],.9)
            else: row[m]=float(np.mean([x[m] for x in vals]))
        rows.append(row)
    df=pd.DataFrame(rows); df.to_csv(out/'ablation_results.csv',index=False); return df

if __name__=='__main__':
    print(run_experiments()[0].to_string(index=False))
