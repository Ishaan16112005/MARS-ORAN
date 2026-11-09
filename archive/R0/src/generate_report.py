from pathlib import Path
import json, pandas as pd
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]
FIG=ROOT/'figures'; RES=ROOT/'results'; OUT=ROOT/'report'; OUT.mkdir(exist_ok=True)

def shade(cell, fill):
    tcPr=cell._tc.get_or_add_tcPr(); shd=OxmlElement('w:shd'); shd.set(qn('w:fill'),fill); tcPr.append(shd)

def set_cell_text(cell,text,bold=False):
    cell.text=''; p=cell.paragraphs[0]; r=p.add_run(str(text)); r.bold=bold; r.font.size=Pt(8.5)

def add_table(doc, df, cols=None, max_rows=20):
    if cols: df=df[cols]
    df=df.head(max_rows)
    tab=doc.add_table(rows=1, cols=len(df.columns)); tab.alignment=WD_TABLE_ALIGNMENT.CENTER; tab.style='Table Grid'
    for i,c in enumerate(df.columns): set_cell_text(tab.rows[0].cells[i],c,True); shade(tab.rows[0].cells[i],'1F4E78')
    for row in df.itertuples(index=False):
        cells=tab.add_row().cells
        for i,v in enumerate(row): set_cell_text(cells[i],v)
    return tab

def add_bullets(doc, items):
    for x in items:
        p=doc.add_paragraph(style='List Bullet'); p.add_run(x)

doc=Document()
sec=doc.sections[0]; sec.top_margin=Inches(.65); sec.bottom_margin=Inches(.65); sec.left_margin=Inches(.7); sec.right_margin=Inches(.7)
styles=doc.styles; styles['Normal'].font.name='Aptos'; styles['Normal'].font.size=Pt(10)
styles['Title'].font.name='Aptos Display'; styles['Title'].font.size=Pt(28)
styles['Heading 1'].font.size=Pt(18); styles['Heading 2'].font.size=Pt(13)

p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=p.add_run('MARS-O-RAN'); r.bold=True; r.font.size=Pt(30)
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=p.add_run('Mission-Aware Risk-Constrained Elastic Network Slicing for Emergency Robotics in O-RAN'); r.bold=True; r.font.size=Pt(18)
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
p.add_run('Complete Phase 0-10 Research Prototype | Final Technical Report').italic=True
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.add_run('Prepared for research simulation, demonstration and paper development')
doc.add_page_break()

# Executive summary
h=doc.add_heading('1. Executive Summary',1)
doc.add_paragraph('This report documents the complete MARS-O-RAN Phase 0-10 prototype. The project reframes emergency network slicing from a conventional network-KPI optimization problem into a mission-task completion problem. A chemical-plant gas-leak mission is represented as five dependent tasks carried over four slices: robot control, safety sensing, responder XR, and perception/AI. The simulator jointly represents radio PRBs, edge compute, deadlines, information freshness (AoI), reliability, reconfiguration cost, stochastic network shocks, and tail mission loss.')
doc.add_paragraph('The implementation is a reproducible synthetic digital twin. It includes deterministic seeds, four resource-allocation policies, Monte Carlo experiments, sensitivity and ablation studies, publication-style graphs, and a local browser interface that allows interactive parameter changes and live time-stepped simulation. The numerical values are model assumptions, not field measurements or safety-certified thresholds.')

summary=pd.read_csv(RES/'policy_summary.csv')
cols=['policy','runs','mission_success_rate_mean','deadline_success_rate_mean','p95_e2e_latency_ms_mean','total_reconfig_cost_mean','CVaR90']
show=summary[cols].copy(); show['policy']=show['policy'].map({'STATIC':'STATIC','PROPORTIONAL':'PROPORT.','MISSION_AWARE':'MISSION-AWARE','MARS_RISK_AWARE':'MARS'})
show.columns=['Policy','Runs','Mission success','Deadline success','P95 E2E (ms)','Reconfig. cost','CVaR90 loss']; show=show.round(3)
doc.add_heading('Main 30-seed result',2); add_table(doc,show)
doc.add_picture(str(FIG/'policy_performance.png'), width=Inches(6.7)); doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
p=doc.add_paragraph('Interpretation: MARS-RISK-AWARE materially improves mission-level outcomes over static/proportional allocation in this model and reduces tail loss and reconfiguration cost relative to the mission-aware baseline. The latter comparison shows an explicit average-performance versus risk/stability trade-off in the selected configuration.')

# Phases
h=doc.add_heading('2. Phase 0-10 Completion Matrix',1)
phase_rows=[
('0','Requirements & scope','Scenario, slices, mission DAG, assumptions, validator','Complete'),
('1','Mission simulator','Task precedence, releases, deadlines, event timeline','Complete'),
('2','Radio + edge model','PRB budget, SINR/rate, finite-blocklength penalty, MEC service','Complete'),
('3','Baselines','STATIC and PROPORTIONAL policies','Complete'),
('4','Dynamic criticality','Urgency, hazard, critical path, AoI, risk','Complete'),
('5','Elastic slicing','Task-driven PRB reallocation with slice bounds','Complete'),
('6','AoI + reliability + stability','Freshness checks, end-to-end reliability, holding-time control','Complete'),
('7','Tail-risk','Mission loss, VaR90, CVaR90','Complete'),
('8','Evaluation','30-seed Monte Carlo, sensitivity, ablation','Complete'),
('9','Live digital twin','Browser UI, step/run control, interactive parameters','Complete'),
('10','Research packaging','Figures, final report, LaTeX manuscript, reproducibility bundle','Complete')]
add_table(doc,pd.DataFrame(phase_rows,columns=['Phase','Workstream','Delivered','Status']))

# System architecture
h=doc.add_heading('3. System Architecture and Data Flow',1)
doc.add_paragraph('The conceptual deployment maps naturally onto O-RAN control: telemetry and policy information feed the intelligence layer, the near-real-time control loop updates slice allocations, and the underlying RAN/edge path serves mission traffic. In the prototype, those interfaces are represented as software modules rather than live E2/A1 protocol sessions.')
doc.add_picture(str(FIG/'mars_prb_timeseries.png'), width=Inches(6.7)); doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
add_bullets(doc,[
'Incident generator: severity ramps after the leak and probabilistically creates short network shock periods.',
'Mission manager: exposes the next executable task from the DAG.',
'Criticality engine: converts task state into dynamic priority scores.',
'Slicing controller: converts scores and demand into bounded PRB allocations.',
'Radio/MEC model: converts allocations and stochastic conditions into task progress.',
'Assurance layer: checks deadline, AoI and reliability conditions before marking task success.',
'Risk layer: aggregates mission loss over repeated stochastic runs and computes CVaR.',
'Live dashboard: visualizes the same controller loop step-by-step for demonstration.' ])

# Algorithms
h=doc.add_heading('4. Mathematical Model and Algorithms',1)
doc.add_paragraph('The core mathematical formulation follows the project brief: maximize mission-value-weighted task completion while penalizing reconfiguration and resource cost, under radio, edge, precedence, deadline, freshness, reliability, reconfiguration and tail-risk constraints.')
for title,eq,explain in [
('Radio service rate','R_s = b_s W_PRB log2(1 + gamma_s) eta FBL_s h_s','PRBs, channel quality and a finite-blocklength penalty determine useful service rate.'),
('Transmission delay','T_tx = L / R','A task with workload L bits consumes time according to its allocated service rate.'),
('Edge computation delay','T_cmp = C / f','Normalized compute workload C is processed at allocated edge rate f.'),
('End-to-end delay','T_E2E = T_queue + T_tx + T_xhaul + T_cmp + T_feedback','The simulator includes a backhaul latency/jitter proxy and queue/radio/edge coupling.'),
('Dynamic criticality','chi_k(t) = w_k [1 + a_u U_k + a_h H_k + a_cp I_cp + a_a A_k + a_r R_k]','Priority rises for urgent, hazardous, critical-path, stale-information or risky tasks.'),
('AoI','Delta(t+1) = 1 if fresh update; otherwise Delta(t)+1','Fresh information is an explicit task constraint, not an indirect throughput metric.'),
('Reliability','P_succ = P_radio P_edge P_backhaul','Task reliability must exceed its allowed failure probability.'),
('Reconfiguration cost','C_rec(t) = sum_s |b_s(t)-b_s(t-1)|','MARS restricts rapid allocation movement using a hold time and per-step change limit.'),
('Mission loss','L = sum_k chi_k (1-q_k)','q_k is one only when deadline, freshness and reliability conditions are jointly satisfied.'),
('CVaR90','CVaR_beta(L) = upper-tail risk statistic at beta=0.90','The controller is evaluated on poor realizations instead of expected performance alone.')]:
    doc.add_heading(title,2); p=doc.add_paragraph(); r=p.add_run(eq); r.bold=True; r.font.name='Consolas'; p=doc.add_paragraph(explain)

doc.add_heading('Controller logic',2)
add_bullets(doc,[
'1. Sample current demand, incident severity, channel state and shock status.',
'2. Determine the currently active/ready mission task from the DAG.',
'3. Compute dynamic task criticality and convert slice scores into a resource target.',
'4. Enforce minimum/maximum slice bounds and total PRB capacity.',
'5. For MARS-RISK-AWARE, apply risk reserve to control/safety slices and penalize unnecessary movement from the current allocation.',
'6. Calculate radio and edge service; advance task workloads.',
'7. Update AoI and evaluate radio/edge/backhaul reliability.',
'8. Mark a task successful only if deadline + freshness + reliability all pass.',
'9. Repeat until the 300-s horizon ends.' ])

# results
h=doc.add_heading('5. Simulation Results',1)
doc.add_paragraph('Main experiment: 30 independent seeds (20-49), 300 seconds per run, 100 PRBs, one edge server, four slices, five mission tasks. Each policy is run against the same class of stochastic environment with its own deterministic seed.')
doc.add_picture(str(FIG/'cvar_comparison.png'), width=Inches(6.7)); doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
doc.add_picture(str(FIG/'mars_prb_timeseries.png'), width=Inches(6.7)); doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
doc.add_picture(str(FIG/'severity_latency.png'), width=Inches(6.7)); doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER

# detailed task sample
doc.add_page_break()
doc.add_heading('Example task-level run (seed 20)',2)
from pathlib import Path
sys_path=ROOT/'src'; import sys; sys.path.insert(0,str(sys_path))
from simulator import run_one
r,t,trace,e=run_one('MARS_RISK_AWARE',20)
tt=t[['task_id','slice','start_s','finish_s','deadline_s','aoi_at_finish_s','reliability','success']].copy(); tt.columns=['Task','Slice','Start','Finish','Deadline','AoI (s)','Reliability','Success']; add_table(doc,tt.round(3))

# sensitivity and ablation
h=doc.add_heading('6. Sensitivity and Ablation',1)
doc.add_picture(str(FIG/'sensitivity_heatmap.png'), width=Inches(6.7)); doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
doc.add_paragraph('Sensitivity varies initial incident severity and the total PRB budget. This study prevents the project from being validated only at one nominal operating point.')
doc.add_picture(str(FIG/'ablation_success.png'), width=Inches(6.7)); doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
abl=pd.read_csv(RES/'ablation_results.csv'); add_table(doc,abl.round(3))
doc.add_paragraph('The current ablation shows that hysteresis is a major contributor to stability: removing it increases PRB reconfiguration cost substantially and lowers mission success in the tested seeds. AoI and risk-reserve effects are weaker in this single-cell parameterization; this motivates larger multi-cell and mobility experiments rather than over-claiming their importance from one scenario.')

# novelty
h=doc.add_heading('7. What Is Novel in MARS-O-RAN',1)
doc.add_paragraph('The defensible novelty is the combination and control abstraction, not the use of O-RAN slicing alone. The project connects mission semantics to resource allocation and risk management in one closed loop.')
add_bullets(doc,[
'Mission-task graph driven slicing: the resource target follows the next executable safety task and its dependency position.',
'Dynamic mission criticality: task weight changes with deadline urgency, hazard, critical-path status, freshness pressure and risk.',
'Cross-layer radio-edge coupling: a slice allocation changes both communication service and edge-compute progress.',
'Joint task success criterion: throughput is not sufficient; the task must satisfy deadline, AoI and reliability simultaneously.',
'Tail-risk protection: mission loss is evaluated using CVaR90 over stochastic realizations.',
'Elasticity with stability constraints: resource movement is bounded by a hold time and per-step change budget.',
'Live research digital twin: the controller can be demonstrated interactively by changing scenario stressors.' ])

# what remains
h=doc.add_heading('8. Validation Status and Research Limitations',1)
doc.add_paragraph('Completed validation in this package means code-level reproducibility and internal simulation consistency. It does not mean physical validation of a commercial 5G/6G or O-RAN network.')
add_bullets(doc,[
'The radio model is analytical rather than a full PHY/MAC packet simulator.',
'Edge compute uses normalized compute units rather than measured CPU/GPU cycles.',
'Reliability is a stochastic analytical proxy rather than measured BLER or equipment failure data.',
'The current MARS controller is a fast heuristic; the original optimization problem is not solved exactly as an MINLP.',
'The current live interface does not establish A1/E2 sessions with a real RIC.',
'No field safety claim should be inferred from the simulated numbers.' ])

doc.add_heading('Recommended next research validation',2)
add_bullets(doc,[
'Integrate the controller with ns-3/5G-LENA or a comparable packet-level simulator.',
'Add multi-cell mobility, interference, handovers and packet-level reliability.',
'Expose the controller through an actual O-RAN xApp/rApp prototype and E2 telemetry mapping.',
'Compare the heuristic to CVaR-constrained optimization and reinforcement-learning baselines.',
'Calibrate workloads and reliability using measured or trace-derived data.',
'Add confidence intervals and statistical significance tests over larger seed counts.' ])

# live interface manual
h=doc.add_heading('9. Live Simulation Interface Manual',1)
doc.add_paragraph('The live interface is intentionally dependency-light. A standard-library Python HTTP server serves a browser page. The JavaScript client sends reset/step/run requests to the local server.')
add_bullets(doc,[
'Run `python src/web_server.py` from the project root.',
'Open `http://127.0.0.1:8765`.',
'Select a policy and adjust incident severity, total PRBs and risk aversion.',
'Click Reset with values to apply the new scenario.',
'Click Step 1 s to observe one simulation timestep or Run to end for a full 300-s trajectory.',
'Watch the PRB allocation chart, mission metrics, task table and event stream.',
'Repeat under the same seed and different parameter values for a reproducible demonstration.' ])

# file map
h=doc.add_heading('10. Repository and Deliverable Map',1)
files=[
('config/scenario_v2.json','Main scenario assumptions'),('config/tasks_v2.json','Mission DAG and task parameters'),('src/simulator.py','Core simulation + controllers'),('src/validate_config.py','Phase 0 validator'),('src/run_all.py','Main experiment orchestrator'),('src/make_figures.py','Graph generator'),('src/web_server.py','Live browser interface'),('tests/test_phase10.py','Automated checks'),('results/policy_summary.csv','Main aggregate results'),('results/task_results.csv','Task-level results'),('results/sensitivity_severity_prbs.csv','Sensitivity results'),('results/ablation_results.csv','Ablation results'),('latex/MARS_ORAN_Research_Paper.tex','Research paper source'),('latex/MARS_ORAN_Research_Paper.pdf','Compiled paper'),('docs/STEP_BY_STEP_GUIDE.md','Run manual'),('docs/NOVELTY_AND_ALGORITHMS.md','Novelty + algorithm note')]
add_table(doc,pd.DataFrame(files,columns=['Path','Purpose']))

# references
h=doc.add_heading('11. Selected Technical References',1)
refs=[
'O-RAN ALLIANCE, Non-Real-time RAN Intelligent Controller and A1 Interface Workgroup, 2026.',
'O-RAN ALLIANCE, Near-Real-time RAN Intelligent Controller and E2 Interface Workgroup, 2026.',
'O-RAN ALLIANCE, O-RAN ALLIANCE Completed its Specification Release 5 (O-RAN-R005), Jun. 2026.',
'3GPP, TS 23.501, System architecture for the 5G System (5GS), current specification under change control, 2026.',
'Y. Polyanskiy, H. V. Poor, and S. Verdú, Channel Coding Rate in the Finite Blocklength Regime, IEEE Transactions on Information Theory, 2010.',
'S. Kaul, R. D. Yates, and M. Gruteser, Real-time status: How often should one update?, IEEE INFOCOM, 2012.',
'R. T. Rockafellar and S. Uryasev, Optimization of Conditional Value-at-Risk, Journal of Risk, 2000.' ]
for x in refs: doc.add_paragraph(x,style='List Number')

# footer
for section in doc.sections:
    footer=section.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER; footer.text='MARS-O-RAN Research Prototype - Synthetic simulation results - Phase 0-10'

path=OUT/'MARS_ORAN_Final_Report.docx'; doc.save(path); print(path)
