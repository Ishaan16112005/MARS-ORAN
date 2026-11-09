"""Regenerate every result, table and figure of the paper, then check the numbers in the text.

    python src/run_all.py            # uses the tuned MARS parameters in config/scenario_v2.json
    python src/run_all.py --retune   # additionally repeats the MARS parameter search (~12 min)
"""
import subprocess, sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
steps = [['validate_config.py']]
if '--retune' in sys.argv: steps += [['tune_mars.py'], ['apply_tuning.py']]
steps += [['experiments.py'], ['make_tables.py'], ['verify_paper_claims.py']]
for s in steps:
    print(f'==> python src/{s[0]}', flush=True)
    subprocess.run([sys.executable, str(SRC / s[0]), *s[1:]], check=True)
print('All results regenerated; build the paper with: cd paper && tectonic main.tex')
