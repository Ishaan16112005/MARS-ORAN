"""Grid search for the MARS controller parameters on TUNING seeds (1000-1099), which are disjoint
from the evaluation seeds (20-319) used in the paper.

Selection objective = surrogate of problem (P1), averaged over the three operating points:
    J = E[L] + lambda_cv * CVaR_0.90(L) + lambda_rc * E[J_rc],   lambda_cv = 0.5, lambda_rc = 0.001

Run:  python src/tune_mars.py        (about 12 min on 16 cores)
Writes results/paper/mars_tuning.csv and prints the selected configuration.
"""
from __future__ import annotations
import itertools, sys, time
from multiprocessing import Pool, cpu_count
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from simulator import run_one, cvar, deep_update  # noqa: E402
from operating_points import OPS  # noqa: E402

TUNE_SEEDS = list(range(1000, 1100))
LAMBDA_CV, LAMBDA_RC = 0.5, 0.001
GRID = {'temperature': [0.1, 0.2, 0.4, 0.8, 1.2, 1.6], 'reserve_scale': [0.0, 0.2], 'damping': [0.25, 0.5, 0.75, 0.9],
        'hold_time_s': [4, 8, 12, 20], 'slack_ref_s': [10.0, 20.0, 40.0]}


def evaluate(cfg):
    out = {**cfg}
    js = []
    for op, ov in OPS.items():
        res = [run_one('MARS', s, overrides=deep_update(ov, {'mars': cfg})) for s in TUNE_SEEDS]
        loss = [r['mission_loss'] for r in res]; rc = [r['total_reconfig_cost'] for r in res]
        j = np.mean(loss) + LAMBDA_CV * cvar(loss, .9) + LAMBDA_RC * np.mean(rc)
        out.update({f'{op}_success': np.mean([r['mission_success_rate'] for r in res]), f'{op}_loss': np.mean(loss),
                    f'{op}_reconfig': np.mean(rc), f'{op}_J': j})
        js.append(j)
    out['J'] = float(np.mean(js))
    return out


def main():
    t0 = time.time()
    configs = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    with Pool(max(1, cpu_count() - 2)) as pool:
        rows = pool.map(evaluate, configs, chunksize=4)
    df = pd.DataFrame(rows).sort_values('J')
    out = ROOT / 'results' / 'paper'; out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / 'mars_tuning.csv', index=False)
    print(df.head(10).round(3).to_string(index=False))
    print(f'{len(configs)} configurations in {time.time() - t0:.0f} s; selected:', {k: df.iloc[0][k] for k in GRID})


if __name__ == '__main__':
    main()
