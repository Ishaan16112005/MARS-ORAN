from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from simulator import MARSOranSimulator
sim=MARSOranSimulator('MARS_RISK_AWARE',seed=17,duration=300)
print('MARS-O-RAN live CLI demo - Ctrl+C to stop')
for _ in range(80):
    row=sim.step()
    if sim.state.t<=5 or sim.state.t%5==0 or row.get('shock'):
        print(f"t={sim.state.t:3d}s sev={row['severity']:.2f} task={row['active_task'] or '-':>2} PRBs[SC={row['prb_SC']:2d} SV={row['prb_SV']:2d} SX={row['prb_SX']:2d} SM={row['prb_SM']:2d}] E2E={row['e2e_latency_ms']:.1f}ms")
    time.sleep(0.05)
print('CLI demo ended; full dashboard: python src/web_server.py')
