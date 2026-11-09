from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'figures'; OUT.mkdir(exist_ok=True)
summary=pd.read_csv(ROOT/'results/policy_summary.csv'); runs=pd.read_csv(ROOT/'results/experiment_runs.csv'); trace=pd.read_csv(ROOT/'results/timeseries_mars.csv'); sens=pd.read_csv(ROOT/'results/sensitivity_severity_prbs.csv'); abl=pd.read_csv(ROOT/'results/ablation_results.csv')
plt.rcParams.update({'figure.figsize':(9,5.2),'axes.grid':True,'font.size':10})

# 1 policy performance
fig,ax=plt.subplots(); x=np.arange(len(summary)); w=.2
for i,m in enumerate(['mission_success_rate_mean','deadline_success_rate_mean','freshness_success_rate_mean','reliability_success_rate_mean']): ax.bar(x+(i-1.5)*w, summary[m], w, label=m.replace('_mean','').replace('_',' '))
ax.set_xticks(x,summary.policy,rotation=20); ax.set_ylim(0,1.05); ax.set_ylabel('Rate'); ax.set_title('Policy performance across Monte Carlo runs'); ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(OUT/'policy_performance.png',dpi=220); plt.close(fig)
# 2 latency
fig,ax=plt.subplots();
for p in runs.policy.unique():
  vals=runs.loc[runs.policy==p,'p95_e2e_latency_ms']; ax.hist(vals,bins=12,alpha=.45,label=p)
ax.set_xlabel('P95 E2E latency (ms)'); ax.set_ylabel('Runs'); ax.set_title('P95 E2E latency distribution'); ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(OUT/'latency_distribution.png',dpi=220); plt.close(fig)
# 3 MARS allocation
fig,ax=plt.subplots();
for s in ['SC','SV','SX','SM']: ax.plot(trace.time_s,trace['prb_'+s],label=s)
ax.set_xlabel('Time (s)'); ax.set_ylabel('PRBs'); ax.set_ylim(0,100); ax.set_title('MARS-RISK-AWARE elastic slice allocation'); ax.legend(); fig.tight_layout(); fig.savefig(OUT/'mars_prb_timeseries.png',dpi=220); plt.close(fig)
# 4 severity and latency
fig,ax=plt.subplots(); ax.plot(trace.time_s,trace.severity,label='severity'); ax2=ax.twinx(); ax2.plot(trace.time_s,trace.p95_e2e_latency_ms if 'p95_e2e_latency_ms' in trace.columns else trace.e2e_latency_ms,alpha=.7,label='E2E latency'); ax.set_xlabel('Time (s)'); ax.set_ylabel('Incident severity'); ax2.set_ylabel('E2E latency (ms)'); ax.set_title('Incident state and latency response'); fig.tight_layout(); fig.savefig(OUT/'severity_latency.png',dpi=220); plt.close(fig)
# 5 cvar
fig,ax=plt.subplots(); ax.bar(summary.policy,summary.CVaR90); ax.set_ylabel('Mission loss'); ax.set_title('90% CVaR mission-loss comparison'); ax.tick_params(axis='x',rotation=20); fig.tight_layout(); fig.savefig(OUT/'cvar_comparison.png',dpi=220); plt.close(fig)
# 6 sensitivity heatmap for MARS
m=sens[sens.policy=='MARS_RISK_AWARE'].pivot(index='severity',columns='total_prbs',values='mission_success_mean')
fig,ax=plt.subplots(); im=ax.imshow(m.values,aspect='auto',vmin=0,vmax=1); ax.set_xticks(range(len(m.columns)),m.columns); ax.set_yticks(range(len(m.index)),[f'{v:.1f}' for v in m.index]); ax.set_xlabel('Total PRBs'); ax.set_ylabel('Initial severity'); ax.set_title('MARS sensitivity: mission success rate'); fig.colorbar(im,ax=ax,label='Rate');
for i in range(m.shape[0]):
 for j in range(m.shape[1]): ax.text(j,i,f'{m.iloc[i,j]:.2f}',ha='center',va='center',fontsize=8)
fig.tight_layout(); fig.savefig(OUT/'sensitivity_heatmap.png',dpi=220); plt.close(fig)
# 7 ablation
fig,ax=plt.subplots(); ax.bar(abl.variant,abl.mission_success_rate); ax.set_ylim(0,1.05); ax.set_ylabel('Mission success rate'); ax.set_title('MARS component ablation'); ax.tick_params(axis='x',rotation=25); fig.tight_layout(); fig.savefig(OUT/'ablation_success.png',dpi=220); plt.close(fig)
print('Figures written to',OUT)
