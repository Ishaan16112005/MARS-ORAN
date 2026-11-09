# Generated Results

## Main experiment

- 4 policies
- 30 deterministic seeds: 20-49
- 300 s per run
- 120 total policy-runs per experiment suite

## Main aggregate results

See `policy_summary.csv`.

The 30-run means are:

| Policy | Mission success | Deadline success | P95 E2E (ms) | Reconfig cost | CVaR90 loss |
|---|---:|---:|---:|---:|---:|
| STATIC | 0.187 | 1.000 | 28.63 | 14.0 | 45.16 |
| PROPORTIONAL | 0.193 | 0.193 | 28.78 | 3413.8 | 45.13 |
| MISSION_AWARE | 0.727 | 1.000 | 28.63 | 1828.5 | 24.54 |
| MARS_RISK_AWARE | 0.707 | 1.000 | 28.63 | 1029.7 | 23.26 |

These figures come from the included synthetic digital-twin model and should be reported as simulation evidence, not measured field performance.
