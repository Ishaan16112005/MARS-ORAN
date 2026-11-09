"""Write the configuration selected by src/tune_mars.py (first row of results/paper/mars_tuning.csv)
into config/scenario_v2.json (section "mars")."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
best = pd.read_csv(ROOT / 'results' / 'paper' / 'mars_tuning.csv').iloc[0]
p = ROOT / 'config' / 'scenario_v2.json'
cfg = json.loads(p.read_text())
for k in ['temperature', 'reserve_scale', 'damping', 'slack_ref_s']: cfg['mars'][k] = float(best[k])
cfg['mars']['hold_time_s'] = int(best['hold_time_s'])
p.write_text(json.dumps(cfg, indent=2) + '\n')
print('MARS parameters set to', cfg['mars'])
