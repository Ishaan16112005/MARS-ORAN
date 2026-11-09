import sys, unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'src'))
from validate_config import validate
from simulator import MARSOranSimulator, cvar, run_one, POLICIES, SLICES, LEGACY_R0
from operating_points import OPS


class TestConfig(unittest.TestCase):
    def test_config(self): self.assertEqual(validate()['status'], 'PASS')


class TestCVaR(unittest.TestCase):
    def test_exact_tail_mean(self):
        self.assertAlmostEqual(cvar([1, 2, 3, 20], .75), 20.0)
        x = list(range(1, 31))                                  # worst 3 of 30 -> (28+29+30)/3
        self.assertAlmostEqual(cvar(x, .9), 29.0)

    def test_ties_do_not_inflate_tail(self):                    # R1-19: 28 ties at 44.975, 2 runs at 47.725
        x = [44.975] * 28 + [47.725] * 2
        self.assertAlmostEqual(cvar(x, .9), (44.975 + 2 * 47.725) / 3)

    def test_fractional_weight(self):
        self.assertAlmostEqual(cvar([1, 2, 3, 4], .5 + .125), (4 + 0.5 * 3) / 1.5)


class TestSimulation(unittest.TestCase):
    def test_all_policies_run(self):
        for p in POLICIES:
            r = MARSOranSimulator(p, seed=17, duration=120).run()
            self.assertEqual(r['tasks_total'], 5); self.assertTrue(0 <= r['mission_success_rate'] <= 1)

    def test_live_step(self):
        s = MARSOranSimulator('MARS', seed=2, duration=10); row = s.step()
        self.assertIn('prb_SC', row); self.assertEqual(s.state.t, 1)

    def test_allocation_invariants(self):
        """sum b = B, bounds, and |b(t)-b(t-1)| <= Delta_max at every step, for every policy and budget."""
        for B in (60, 100, 150):
            for p in POLICIES:
                for op, ov in OPS.items():
                    _, sim = run_one(p, 21, overrides={**ov, 'radio': {'total_prbs': B}}, return_sim=True)
                    tr = pd.DataFrame(sim.state.trace); a = tr[[f'prb_{s}' for s in SLICES]]
                    self.assertTrue((a.sum(axis=1) == B).all(), (B, p, op))
                    for s in SLICES:
                        self.assertTrue(((tr[f'prb_{s}'] >= sim.mins[s]) & (tr[f'prb_{s}'] <= sim.maxs[s])).all())
                    self.assertLessEqual(int(a.diff().abs().max().max()), sim.cfg['controller']['max_reconfig_per_step'])

    def test_common_random_numbers(self):
        sig = set()
        for p in POLICIES:
            _, sim = run_one(p, 33, return_sim=True)
            sig.add(tuple((r['severity'], r['shock']) for r in sim.state.trace))
        self.assertEqual(len(sig), 1)

    def test_legacy_reproduces_r0(self):
        old = pd.read_csv(ROOT / 'archive' / 'R0' / 'results' / 'experiment_runs.csv')
        name = {'STATIC': 'STATIC', 'PROPORTIONAL': 'PROPORTIONAL', 'MISSION_AWARE': 'MISSION_AWARE', 'MARS_RISK_AWARE': 'MARS_V0'}
        for _, r in old[old.seed.isin([20, 21, 22])].iterrows():
            n = run_one(name[r.policy], int(r.seed), overrides=LEGACY_R0)
            self.assertTrue(np.isclose(n['mission_loss'], r.mission_loss)); self.assertTrue(np.isclose(n['total_reconfig_cost'], r.total_reconfig_cost))


if __name__ == '__main__':
    unittest.main()
