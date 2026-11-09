from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from validate_config import validate
from simulator import run_experiments,sensitivity_experiment,ablation_experiment
print('[Phase 0] Validation:', validate())
print('[Phases 1-8] Running Monte Carlo experiments...')
summary,runs,tasks=run_experiments()
print(summary.to_string(index=False))
print('[Phase 8] Sensitivity study...'); sensitivity_experiment()
print('[Phase 8] Ablation study...'); ablation_experiment()
print('[Phase 9] Graph generation is handled by src/make_figures.py')
print('DONE. Run: python src/make_figures.py')
