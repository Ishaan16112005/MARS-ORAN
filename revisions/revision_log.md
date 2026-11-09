# MARS-O-RAN — Revision Report (Google Deep Review)

Paper: *MARS-O-RAN: Mission-Aware, Risk-Aware Elastic Network Slicing for Emergency Robotics in an O-RAN Digital Twin*
Authors: Ishaan Jayaram Shetty, Prashant Kumar, Himanshu Kumar Sonkar, Naman Kumar — IIIT Dharwad

| Round | PDF uploaded to Deep Review | Date | Result |
|---|---|---|---|
| R0 (initial draft) | `MARS_ORAN_R0_Draft.pdf` | 2026-11-09 | 30 comments (2 Critical, 10 Major, 15 Minor, 3 Suggestion) → Revision 1 |
| R1 | `MARS_ORAN_R1.pdf` | _pending_ | review comments → Revision 2 |
| R2 | `MARS_ORAN_R2.pdf` | _pending_ | review comments → Revision 3 (recommended) |

---

## Pre-review preparation (before the first upload)

Changes made from the earlier v2 manuscript to produce R0:

1. Added a formal problem formulation (Section IV, problem P1) and stated that MARS is a heuristic approximation; CVaR is evaluated, not enforced.
2. Wrote out every model equation exactly as implemented in `src/simulator.py` (demand, channel/SNR, finite-blocklength correction, compute progress, reliability, risk reserve, budget repair).
3. Added a "Baseline Algorithms and Experimental Setup" section with a complete parameter/seed table and a statement that the dataset is synthetic.
4. Added a system-model diagram (Fig. 1) and a complexity analysis.
5. Added `src/verify_paper_claims.py`, which recomputes every number in the text; corrected five statements that disagreed with the data (workload caption, abstract deadline/workload attribution, CVaR attribution, K5 reliability threshold 0.46, seed-20 mission window 20–152 s).
6. Changed the title from "Risk-Constrained" to "Risk-Aware", because no hard risk constraint is enforced.
7. Verified that all result CSVs regenerate byte-identically from fixed seeds.

---

## Round 1 — Review of R0

### Deep Review comments (verbatim)
All 30 comments are reproduced word for word in [`round1_deepreview_comments.md`](round1_deepreview_comments.md) (items R1-01 … R1-30).

### Summary of Revision 1
Revision 1 is a substantial revision; every experiment was re-run.

* **Environment fixes** (affect all results): the 15 % edge-compute bonus now applies to every policy (R1-06); budget repair respects the per-step change limit Δmax (R0 violated it about once per run for MISSION-AWARE and MARS); the initial allocation, tie-breaking, AoI initial value and update order are explicit (R1-13).
* **Exact CVaR estimator** (R1-19): the R0 estimator averaged all losses ≥ the β-quantile. With the exact Rockafellar–Uryasev plug-in, the R0 "MARS has the lowest CVaR" result disappears (MARS-v0 and MISSION-AWARE both 24.54 on the R0 data).
* **Corrected controller (R1-09, R1-12, R1-25):** MARS now uses a normalised criticality score with softmax temperature τ, damping toward b(t−1) instead of the |b−25| penalty, a mission-gated reserve whose split sums to 1, a slack-adaptive hold time, and a transition mode. The R0 controller is kept as **MARS-v0** for comparison.
* **New baseline (R1-26):** MYOPIC-OPT, a one-step exhaustive optimiser with perfect knowledge of the current state and service model.
* **New evaluation design (R1-15, R1-16, R1-17):** 300 paired seeds (was 30) at three operating points: OP-A (σ0 = 0.2, all tasks feasible), OP-B (σ0 = 0.6, the R0 nominal point), and OP-C (concurrent K2‖K3). Reconfiguration is split into mission and idle windows.
* **Tuning protocol:** the MARS parameters are tuned on separate seeds (1000–1099) with the (P1) objective, then evaluated on seeds 20–319.
* **Figures:** reduced from 17 to 15 (system diagram + 14 data figures), as instructed.
* **Automatic check:** `src/verify_paper_claims.py` checks 75 numbers in the text against the results (all pass), and Tables IV–V are generated from the result CSVs by `src/make_tables.py`.
* **Development note (for transparency):** a first version of the corrected controller had no transition mode. On evaluation it lagged MISSION-AWARE badly under stress (−3.9 pp at OP-B, 0.07 vs 0.37 at σ0 = 1.0). The cause was the hold/Δmax interaction described in R1-13: a Δmax-limited change re-armed the hold and froze the allocation part-way to its target. Transition mode fixes exactly this. The parameters were then re-tuned on the tuning seeds only, and the evaluation re-run. The pre-fix results are kept in `archive/R1_development/`.

**Headline results of R1:**

* At OP-A and OP-C, MARS is statistically indistinguishable from MISSION-AWARE, MYOPIC-OPT and MARS-v0 in success, loss and CVaR. It reconfigures 84.0 % / 87.3 % less than MISSION-AWARE and 30.2 % / 37.5 % less than MYOPIC-OPT during the mission (lower in all 300 seeds).
* At OP-B, MARS loses 2.9 pp of success vs MISSION-AWARE (p = 0.015).
* MARS is weaker under scarce PRBs, extreme severity, tight deadlines and heavy workload.
* In the concurrent mission, MARS splits PRBs between K2 and K3 (35/32), close to the optimiser (34/39), whereas MISSION-AWARE gives 57/15.

### Responses and modifications
Section numbers refer to R1. "Re-run" = experiments regenerated.

| # | Severity | Comment (summary) | Response | Change made (section / file) | Re-run |
|---|---|---|---|---|---|
| R1-01 | Major | Introduction presents criticality, AoI, finite-blocklength and CVaR as active drivers, but the ablations show they are inert at the nominal point. | Agreed. The Introduction now has a "What drives the results" paragraph stating that completion is compute-bound, AoI and finite blocklength never bind (6 stale instances of 27 000; F ∈ [0.994, 0.998]), criticality matters only with concurrent tasks, and CVaR is an objective/tuning term, not an enforced constraint. Contributions and Related Work were rewritten to match. | Abstract, §I, §II, §III-E, §VII-D | – |
| R1-02 | Minor | Units missing for C_k and w_k in Table I. | Added units (cu for C_k; w_k, h_k, ε_k dimensionless; L_k in Mb = 10⁶ bits). | Table I | – |
| R1-03 | Minor | Expand related work: CVaR/URLLC slicing, AoI-aware O-RAN slicing, joint radio–MEC slicing. | Added and verified Alsenwi et al. (CVaR eMBB–URLLC slicing), Bennis et al. (tail, risk, scale), Abedin et al. (elastic O-RAN slicing with AoI), Elbamby et al. (wireless edge computing) and Sl-EDGE (joint network/MEC slicing). The radio–edge budget paradox is now related to this literature. | §II, §VIII-A, refs [6]–[10] | – |
| R1-04 | Minor | Missing time arguments in e(t) and Eq. (9); continuous or discrete U(−7,10)? | All time arguments added; the demand noise is stated to be continuous uniform on [−7, 10]. | §III-D, Eq. (9), Table II | – |
| R1-05 | Minor | "180–1800 symbols per PRB" contradicts n_s = max(128, 1800 b_s). | The model uses 1800 channel uses per PRB, n_s = 1800 b_s (the 128 floor never binds). The text now states this and reports the resulting range F_s ∈ [0.994, 0.998]. | §III-E, Eq. (6), `config` key `channel_uses_per_prb` | – |
| R1-06 | **Critical** | The 15 % edge bonus is given only to the mission-oriented policies, which confounds the baseline comparison; edge share is coupled to B. | Fixed: the bonus is now an environment rule (MEC prioritises every executing task) applied identically to all policies. An ablation shows that removing it changes success by ≤ 0.011 at OP-A. The coupling to B is analysed with a second budget sweep in which the slice caps scale with B: the paradox disappears there (0.932 at B = 200), confirming it is an artifact of fixed caps. Decoupled edge scheduling is listed as a design implication. | Eq. (7), §VI-A, §VIII-A, Fig. 9(b), ablation (v); `simulator.py` (`edge_bonus_all_policies`, `scale_max_with_budget`) | Yes |
| R1-07 | Major | Missing bits→Mb conversion; compute dominates radio (radio clears in 1–2 s, compute takes tens of seconds). | The code uses bits consistently (workloads are stored in bits; Table I shows Mb = 10⁶ bits), and this is now stated. The timescale asymmetry is quantified (16–36 Mb per step vs 2.8–4.0 cu/s) and stated explicitly: PRBs act mainly through the coupled edge share. This also appears in the Introduction and Discussion. | §I, §III-E ("Compute dominates"), §IX | – |
| R1-08 | Minor | Inconsistent indicator notation. | Single notation 𝟏{·} via macro `\ind`. | §III | – |
| R1-09 | Major | Unscaled logits saturate the softmax; α_h and α_r are non-identifiable. | MARS now normalises χ_k by χ_ref = 24 and uses a softmax temperature τ (tuned τ = 0.8). The largest weight now averages 0.41 (OP-A) and 0.40 (OP-C), vs 0.9999 / 0.996 for MARS-v0. α_h and α_r are merged into α_h = 0.30. Effect: criticality now shapes allocations (concurrent split 35/32 PRBs), but the ablation shows it improves stability, not success; this is reported. | §V-A, §V-B, Eq. (17), §VII-E, §VIII-E (iii), Fig. 15(c) | Yes |
| R1-10 | Minor | MISSION-AWARE and MARS differ in several factors; cross-reference the ablation. | Stated explicitly in §VI-A, with a pointer to the ablation, which isolates each mechanism. The R1 ablation shows that the R0 savings came entirely from the hold time (R1-29). | §VI-A, §VIII-E | Yes |
| R1-11 | Minor | Reserve weights sum to 1.10 r; Algorithm 1 should use b̂. | MARS-v0 is now documented as using 0.45/0.35/0.30 (sum 1.10, accumulating when the top slice is SC/SV). MARS uses a split that sums to 1 (0.6/0.4). Algorithm 1 uses b̂. | §V-B, §VI-A, Algorithm 1 | – |
| R1-12 | Major | The penalty λ\|b(t−1)−25\| does not penalise the step change, pushes allocations toward 25 and hard-codes B = 100. | Replaced in MARS by post-softmax damping toward b(t−1)/B (Eq. 17), as suggested; no hard-coded 25. MARS-v0 keeps the old penalty for comparison, and the text explains why it was flawed. | §V-B, Eq. (17), §VI-A | Yes |
| R1-13 | Major | Δmax not enforced in the repair loop; hold/Δmax interaction; tie-breaking and initial conditions unspecified; value rule ambiguous. | (a) Repair now operates within the Δmax band, so Δmax is never violated; a unit test checks this for all policies, all operating points and B ∈ {60, 100, 150}. (b) The initial allocation scales with B. (c) The hold/Δmax freeze is fixed by the new transition mode. (d) Tie-breaking (order SC, SV, SX, SM), signed unmet demand, t_last(0⁻) = −∞, Δ_s(0⁻) = 0 and the AoI update order are all specified. (e) x(t) now includes h(t), e(t) and t_last. (f) The value rule is now "τ_k ≤ D_k ∧ q_k = 0"; overrunning tasks keep executing and successors wait. | §III-B, §III-C, §III-F, §IV-A, §IV-B, §V-C, Algorithm 1; `tests/test_phase10.py` | Yes |
| R1-14 | Suggestion | Drive demand and channel with measured O-RAN slicing traces. | Acknowledged as a limitation and listed as the next validation step (Colosseum traces surveyed in [3]). Not done in R1: it requires obtaining and mapping external KPM datasets. | §IX (External validity) | – |
| R1-15 | Suggestion | 30 seeds are too few (many ties, wide CVaR CIs). | Evaluation increased to 300 paired seeds per policy and operating point (sweeps: 100 seeds). N_eff is reported for every Wilcoxon test, and CVaR₀.₉ now averages the worst 30 runs. | §VI-B, §VI-D, Tables IV–V | Yes |
| R1-16 | Major | K5 is infeasible at the nominal point, so the main benchmark cannot evaluate all five tasks. | The primary operating point is now OP-A (σ0 = 0.2; K5 succeeds in 88–94 % of runs), with full paired tables. σ0 = 0.6 is kept as stress point OP-B, and the K5 infeasibility analysis is retained there. | §VI-B, §VII, Tables IV–V | Yes |
| R1-17 | Major | Post-mission idle window inflates the reconfiguration savings. | J_rc is split into mission [t0, τ_end) and idle parts in Tables IV–V and Figs. 2–3; all reconfiguration claims now use the mission part. MARS also switches the reserve off after the mission. The latency proxy is reported separately for the mission and post-mission windows. | §IV-A, §VII-A, §VII-B, §VII-E | Yes |
| R1-18 | Minor | Inconsistent decimal precision; 43.7 % vs 44 %. | One precision rule (scores 3 dp, losses/CVaR 2 dp, reconfiguration integer, percentages 1 dp), applied by the table generator and checked in the text. | `src/make_tables.py`, all sections | – |
| R1-19 | Major | The CVaR threshold estimator is wrong under ties; the MARS β = 0.9 advantage is an artifact. | Confirmed. The exact RU plug-in with fractional weighting is implemented and stated in §IV-A. On the R0 data it gives 24.54 for both MARS-v0 and MISSION-AWARE; §VII-C explains that the earlier advantage was an estimator artifact. Unit tests cover ties and fractional weights. | §IV-A (estimator after Eq. 13), §VII-C, `simulator.cvar`, tests | Yes |
| R1-20 | Minor | Unexplained lower K3 success under MARS. | Explained with data: extra PRBs do not help once b ≥ d; under MARS K3 finishes later (98.4 vs 90.5 s at OP-B) at higher severity (0.717 vs 0.703), near the K3 threshold σ ≈ 0.74. | §VII-D | – |
| R1-21 | Minor | T_h ≤ 1 equivalence relies on integer steps. | Time is now stated to be integer steps; the T_h discussion follows the new parameter sweep. | §III-B, §VIII-E | – |
| R1-22 | Minor | Mission completion times differ between policies on seed 20. | Exact end times for seed 20 are given (133/133/140/144 s), plus the 300-seed means (143.8 vs 133.1 s). | §VII-E, Fig. 7 caption | – |
| R1-23 | Minor | "x" instead of × in a figure label. | That figure was removed under the 15-figure limit; all remaining labels were checked. | `experiments.py` | – |
| R1-24 | Minor | Point plotted at B = 45 below the feasibility floor. | There was no B = 45 run; the axis margin made the B = 50 point look like it. The axis now runs from B = 45 so that the first point (B = 50) sits on the vertical floor line, and the caption names that line. | Fig. 9 | – |
| R1-25 | Major | Evaluate an artifact-corrected MARS instead of deferring fixes. | Done: the corrected controller is now the proposed MARS (temperature, damping toward b(t−1), mission-gated reserve, slack-adaptive hold and transition mode). It was tuned on separate seeds and evaluated against MARS-v0 and four other baselines. | §V, §VI, §VII, §VIII | Yes |
| R1-26 | Suggestion | Justify omitting optimisation/RL baselines, or add a tractable one. | Added MYOPIC-OPT, an exhaustive one-step optimiser over ≤ 33³ integer allocations with perfect current-state knowledge. The Introduction ("Scope of baselines") justifies omitting RL. | §I, §VI-A, all results | Yes |
| R1-27 | Minor | Ref. [4] format (SafeSlice). | Verified on IEEE Xplore: ICMLCN 2025, Barcelona, DOI 10.1109/ICMLCN64995.2025.11140546. Updated. | Ref. [4] | – |
| R1-28 | Minor | Missing public repository URL. | Reproducibility section now names a repository URL and the scripts. **The URL is a placeholder until the authors provide the GitHub link.** | Reproducibility | – |
| R1-29 | Major | Missing no-reserve + no-penalty ablation. | Added for MARS-v0: 0.912 vs 0.924 success and 571 vs 575 PRB-steps at OP-A. The reserve and penalty add nothing beyond the hold time. | §VIII-E (iv), Fig. 15 | Yes |
| R1-30 | **Critical** | Ref. [2] likely hallucinated (O-RAN ALLIANCE, no title/venue). | Replaced with a verifiable WG3 specification: ETSI TS 104 038 V4.1.0 (2024-10), "E2 interface: General Aspects and Principles" (O-RAN.WG3.E2GAP-R003-v04.01). All other references were re-checked; volume/page details that could not be verified were removed rather than guessed. | Ref. [2], reference list | – |

---

## Round 2 — Review of R1

### Deep Review comments (verbatim)
_To be pasted after upload._

### Responses and modifications
| # | Comment (summary) | Response | Change made (section / file) | Re-run needed? |
|---|---|---|---|---|

---

## Round 3 — Review of R2

### Deep Review comments (verbatim)
_To be pasted after upload._

### Responses and modifications
| # | Comment (summary) | Response | Change made (section / file) | Re-run needed? |
|---|---|---|---|---|
