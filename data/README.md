# Data deposit: per-session and per-member measures

Anonymised measures behind every figure and statistic in *The Impact of an AI Teammate's Proactive Behaviours on Team Information Sharing* (Computers in Human Behavior, submitted 2026). Seventeen four-member teams (sessions), each of three human specialists (Aerodynamics, Propulsion, Structures) and one AI teammate (Test Specialist). No message text is included: the chat transcripts and the individual questionnaire responses are personal data held by Iscte under the participants' consent and are not shared.

Built by `15_deposit_measures.py` on 7 October 2026 from the analysis files; the two corrections below are applied in this copy.

| File | Rows | What |
| --- | --- | --- |
| `aggregated_session_stats.csv` | 17 sessions | Session totals: messages, words, interactions with the AI, transactive retrieval, facts shared and unique facts, elaboration-score counts, R1/R2 decision-quality codes, team means of the questionnaire scales |
| `aggregated_member_stats.csv` | 17 x 4 roles | The same communication measures per member, plus the network counts (`replied_to`-based in-degree and out-degree inputs) |
| `member_stats_performance.csv` | 17 x 4 roles | Questionnaire scale scores per human member (blank for the AI rows) with the R1/R2 codes |
| `session_performance_metrics.csv` | 17 sessions | Session timing, the four critical facts' first-disclosure times (or `Not found`), R1/R2 as `Yes`/`No` |
| `function_activation_stats.csv` | 17 sessions | Activations of the agent's five functions per session |

## Conventions

- `Proactivity`: 0 = low-proactivity condition (odd sessions), 1 = high-proactivity condition (even sessions).
- Function numbering in `function_activation_stats.csv` follows the **code** convention: `Function_4` is the proactive insight and `Function_5` the devil's-advocate challenge. The paper numbers them the other way round (paper F4 = devil's-advocate challenge, paper F5 = proactive insight); see the repository README.
- `R1_Motor_overheating_identified_as_main_issue` and `R2_Overheating_caused_by_silicone_foam_isolation` are the two decision-quality criteria (0/1, or `No`/`Yes`). Session 06 is coded R1 = yes in every file (author's ruling of 7 October 2026: the team discussed lowering the motor temperature before its final answer).
- Questionnaire scales: TMS subscales (Lewis, 2003), agent performance and willingness to continue (Dennis et al., 2023, adapted), trust adjective pairs (Shang et al., 2024) on -2 to +2, all others 1 to 5.

## Corrections relative to the original workbook

- `Cognitive Trust` is the mean of the 11 adjective pairs the paper uses (7 reliability + 4 competence: Unreliable-Reliable, Inconsistent-Consistent, Unpredictable-Predictable, Undependable-Dependable, Fickle-Dedicated, Careless-Careful, Unbelievable-Believable, Clueless-Knowledgeable, Incompetent-Competent, Ineffective-Effective, Inexperienced-Experienced), recomputed for every respondent from the item answers. The original workbook column averaged 9 or 10 pairs for five respondents. `Trust Reliability` (7 pairs) and `Trust Competence` (4 pairs) are recomputed the same way; Amateur-Proficient is not used because it belongs to the Understandability sub-dimension in Shang et al. (2024). Team-level `Cognitive Trust` in `aggregated_session_stats.csv` is the mean of the corrected member values and reproduces the paper (1.09 and 0.64).
- Sessions 11 to 16 had no role entered in the questionnaire sheet; roles were recovered by matching each respondent's scale scores to the per-role analysis file, with unique matches in every case.
