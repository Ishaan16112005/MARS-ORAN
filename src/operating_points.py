"""The three operating points used in the paper (overrides applied to config/scenario_v2.json)."""
OPS = {
    'A_benign': {},                                                    # chain DAG, sigma_0 = 0.2 (all tasks feasible)
    'B_severe': {'incident': {'initial_severity': 0.6}},               # chain DAG, sigma_0 = 0.6 (K5 infeasible)
    'C_concurrent': {'env': {'concurrent_tasks': True, 'tasks_file': 'tasks_parallel.json'}},  # K2 || K3, sigma_0 = 0.2
}
OP_LABEL = {'A_benign': 'OP-A (benign, chain)', 'B_severe': 'OP-B (severe, chain)', 'C_concurrent': 'OP-C (concurrent)'}
