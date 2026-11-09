"""Generate the LaTeX result tables of the paper directly from results/paper/*.csv.

Run after src/experiments.py:   python src/make_tables.py
Writes paper/tables/tab_main.tex and paper/tables/tab_paired.tex (included with \\input).
Precision rule (used in text, tables and figures): probabilities/scores 3 decimals,
losses and CVaR 2 decimals, reconfiguration costs integer PRB-steps, percentages 1 decimal.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / 'results' / 'paper'
OUT = ROOT / 'paper' / 'tables'; OUT.mkdir(parents=True, exist_ok=True)
POL = ['STATIC', 'PROPORTIONAL', 'MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0', 'MARS']
LAB = {'STATIC': 'STATIC', 'PROPORTIONAL': 'PROPORTIONAL', 'MISSION_AWARE': 'MISSION-AWARE', 'MYOPIC_OPT': 'MYOPIC-OPT',
       'MARS_V0': 'MARS-v0', 'MARS': '\\textbf{MARS}'}
OPS = [('A_benign', 'OP-A: benign ($\\sigma_0=0.2$), chain mission'), ('B_severe', 'OP-B: severe ($\\sigma_0=0.6$), chain mission'),
       ('C_concurrent', 'OP-C: benign ($\\sigma_0=0.2$), concurrent mission ($K_2\\parallel K_3$)')]


def ci(r, m, d):
    f = f'{{:.{d}f}}'
    return f'{f.format(r[m])} [{f.format(r[m + "_lo"])}, {f.format(r[m + "_hi"])}]'


def main_table():
    c = pd.read_csv(RES / 'main_ci.csv')
    lines = []
    for op, title in OPS:
        lines.append(f'\\midrule\n\\multicolumn{{7}}{{l}}{{\\emph{{{title}}}}}\\\\')
        for p in POL:
            r = c[(c.op == op) & (c.policy == p)].iloc[0]
            lines.append(f'{LAB[p]} & {ci(r, "mission_success_rate", 3)} & {r.full_mission:.3f} & {ci(r, "mission_loss", 2)} & '
                         f'{ci(r, "CVaR90", 2)} & {r.reconfig_mission:.0f} & {r.reconfig_idle:.0f}\\\\')
    head = ('\\begin{tabular}{lcccccc}\n\\toprule\nPolicy & Success score & Full-mission prob. & Mean loss $L$ & CVaR$_{0.90}(L)$ & '
            '$J_{\\mathrm{rc}}$ mission & $J_{\\mathrm{rc}}$ idle\\\\\n')
    (OUT / 'tab_main.tex').write_text(head + '\n'.join(lines) + '\n\\bottomrule\n\\end{tabular}\n', encoding='utf-8')


def paired_table():
    d = pd.read_csv(RES / 'paired_tests.csv'); c = pd.read_csv(RES / 'main_ci.csv')
    p_fmt = lambda p: '$<10^{-4}$' if p < 1e-4 else f'{p:.3f}'
    lines = []
    short = {'A_benign': 'OP-A', 'B_severe': 'OP-B', 'C_concurrent': 'OP-C'}
    for op, _ in OPS:
        mars_rc = c[(c.op == op) & (c.policy == 'MARS')].reconfig_mission.iloc[0]
        for i, b in enumerate(['MISSION_AWARE', 'MYOPIC_OPT', 'MARS_V0']):
            q = d[(d.op == op) & (d.baseline == b)].set_index('metric')
            s, l, r = q.loc['mission_success_rate'], q.loc['mission_loss'], q.loc['reconfig_mission']
            base_rc = c[(c.op == op) & (c.policy == b)].reconfig_mission.iloc[0]
            lines.append(f'{short[op] if i == 0 else ""} & {LAB[b]} & ${s.mean_diff:+.3f}$ [${s.ci_lo:+.3f}, {s.ci_hi:+.3f}$] & '
                         f'{int(s.wins)}/{int(s.ties)}/{int(s.losses)} & {int(s.n_eff)} & {p_fmt(s.wilcoxon_p)} & '
                         f'${l.mean_diff:+.2f}$ & {p_fmt(l.wilcoxon_p)} & ${100 * (mars_rc / base_rc - 1):+.1f}\\%$\\\\')
        if op != 'C_concurrent': lines.append('\\midrule')
    head = ('\\begin{tabular}{llccccccc}\n\\toprule\nOP & Baseline & $\\Delta$ success [CI] & W/T/L & $N_{\\mathrm{eff}}$ & $p$ & '
            '$\\Delta$ loss & $p$ & $\\Delta J_{\\mathrm{rc}}$ mission\\\\\n\\midrule\n')
    (OUT / 'tab_paired.tex').write_text(head + '\n'.join(lines) + '\n\\bottomrule\n\\end{tabular}\n', encoding='utf-8')


if __name__ == '__main__':
    main_table(); paired_table()
    print('tables written to', OUT)
