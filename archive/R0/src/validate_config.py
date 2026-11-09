from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def validate():
    s=json.loads((ROOT/'config/scenario_v2.json').read_text())
    t=json.loads((ROOT/'config/tasks_v2.json').read_text())['tasks']
    slices=['SC','SV','SX','SM']; total=s['radio']['total_prbs']; mins=s['radio']['min_slice_prbs']; maxs=s['radio']['max_slice_prbs']
    assert all(x in mins and x in maxs for x in slices)
    assert sum(mins.values())<=total
    assert all(mins[x]<=maxs[x] for x in slices)
    ids={x['id'] for x in t}
    assert len(ids)==len(t)
    for x in t:
        assert all(p in ids for p in x['predecessors'])
        assert x['deadline_s']>x['activation_s']
        assert x['workload_bits']>0 and x['compute_units']>0
        assert x['slice'] in slices
    return {'status':'PASS','task_count':len(t),'slice_count':len(slices),'total_prbs':total,'sum_min_prbs':sum(mins.values()),'duration_s':s['simulation']['duration_s']}
if __name__=='__main__': print(validate())
