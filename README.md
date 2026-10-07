# Chico — the AI teammate used in *The Impact of Agent Proactive Behaviours on Team Information Sharing*

Companion repository for the paper (submitted to *Computers in Human Behavior*; derived from an MSc thesis at Instituto Superior Técnico). It holds the complete implementation of "Chico", the autonomous AI teammate, together with its prompts, its knowledge base and the three human role handouts. In the study, seventeen four-member teams (three human specialists plus Chico as the Test Specialist) worked a hidden-profile engineering diagnosis over a synchronous Discord text channel, with the agent's communication proactivity manipulated between teams.

> **Read this first if you are coming from the paper.** The paper and this code number the two proactive functions **the other way round**. In the paper, **F4 is the devil's-advocate challenge and F5 is the proactive insight**. In this code, in its data logs and in the thesis, `responsibility_4` / `R4` is the insight and `responsibility_5` / `R5` is the devil's advocate. The full mapping, and the reason for it, is in the section [Function numbering: paper versus code](#function-numbering-paper-versus-code) below.

## The two conditions

The agent runs in one of two modes, set with `AGENT_TYPE` in `.env`:

- **`AGENT_1`, low proactivity.** Direct response (paper F1), question answering (F2) and factual correction (F3). Every one of these is triggered by something a user said. The agent never acts on its own initiative.
- **`AGENT_2`, high proactivity.** All of the above, plus the two functions triggered by the agent's own monitoring of the discussion: the devil's-advocate challenge (paper F4) and the proactive insight (paper F5).

Both conditions share this codebase, the model configuration, the prompts and the memory architecture. The manipulation is only which functions are active.

## Function numbering: paper versus code

The paper numbers the five functions in the order in which the agent evaluates them, first match wins: F1 direct response, F2 question answering, F3 factual correction, **F4 devil's-advocate challenge, F5 proactive insight**. That order reflects the implementation: when both proactive handlers produce a candidate, the devil's-advocate action (`priority: 2`) beats the insight (`priority: 3`) in `handle_r4_r5_logic`, so the challenge does take precedence over the insight.

The code was written, run and logged before that renumbering, with the insight as responsibility 4 and the devil's advocate as responsibility 5, and the thesis uses the same convention as the code. The code is published exactly as it ran during the sessions, so its internal numbering has been left as it was to stay consistent with the collected data logs. Use this table when moving between the paper and anything in this repository:

| Paper | Function | Prompt files | Handler | Log steps | Thesis |
|---|---|---|---|---|---|
| F1 | Direct response | `responsibility_1.txt` | `handle_responsibility_1` | `R1_*` | F1 |
| F2 | Question answering | `responsibility_2*.txt` | `handle_responsibility_2` | `R2_*` | F2 |
| F3 | Factual correction | `responsibility_3_*.txt` | `handle_responsibility_3` | `R3_*` | F3 |
| **F4** | **Devil's-advocate challenge** | `responsibility_5_trigger_check.txt`, `responsibility_5_intervention.txt` | `handle_responsibility_5` | `R5_*` | **F5** |
| **F5** | **Proactive insight** | `responsibility_4_classifier.txt`, `responsibility_4_reasoning.txt` | `handle_responsibility_4` | `R4_*` | **F4** |

Three practical consequences:

- In the per-session data logs written by `Datalogger` (`AI_datalog.csv`), the step names `R5_TRIGGER_CHECK_*` and `R5_GENERATION_*` belong to the devil's-advocate challenge (paper F4), and `R4_TOPIC_TRACKING_*`, `R4_CRITICAL_MASS_REACHED` and `R4_REASONING_*` belong to the proactive insight (paper F5).
- Any table or file that counts activations by column name, such as `Function_4_Activations` and `Function_5_Activations` in the analysis outputs, uses the code numbering. The paper's table of activation rates reports the devil's-advocate challenge at 18.5% of activations and the insight at 4.6%; in code terms those are `Function_5` and `Function_4` respectively.
- The cooldown variables in `agent.py` follow the code numbering as well: `R5_COOLDOWN_COUNTER` is the challenge's cooldown, and `INTERVENTION_COOLDOWN_COUNTER` (passed as the "r4 cooldown") is the insight's.

When in doubt, resolve a function by its **name**, never by its number.

## What each function does

- **Direct response (F1).** Fires when the agent is named, mentioned or replied to.
- **Question answering (F2).** Fires when a message is a technical question the knowledge base can answer, even if it was not addressed to the agent. A validation call first checks that an answer exists (`responsibility_2_validation.txt`); otherwise the agent stays silent (`NO_ANSWER_FOUND`).
- **Factual correction (F3).** Fires when a message contains a claim that is incorrect or incomplete against the knowledge base; the agent supplies the correct value.
- **Devil's-advocate challenge (paper F4, code R5).** Fires when a message rests on an assumption the knowledge base neither supports nor contradicts. The agent has no fact to offer, so it asks one open question about what the reasoning rests on (`responsibility_5_trigger_check.txt` decides, `responsibility_5_intervention.txt` writes the question). F3 asserts, F4 asks, and the two never fire on the same message.
- **Proactive insight (paper F5, code R4).** A topic tracker classifies recent messages by technical topic (`responsibility_4_classifier.txt`). Once one topic has recurred `CRITICAL_MASS_THRESHOLD` times (4 in `common/config.py`) without the agent having contributed to it, the agent volunteers a synthesised insight (`responsibility_4_reasoning.txt`), or stays silent (`NO_INSIGHT_FOUND`).

Every trigger is evaluated against the content of the discussion, never against a message count. The message counts in `common/config.py` govern only the cooldown that follows a firing, which is why teams that chatted faster became eligible for more interventions.

## Architecture

- `agent.py`: Discord event loop, message dispatch, cooldown and timing state, the condition switch.
- `common/config.py`: every tunable parameter in one place (models per function, thresholds, cooldowns, buffer sizes, filters).
- `common/handlers.py`: the function implementations, the small-talk pre-filter, the topic tracker, the datalogger and message chunking.
- `prompts/`: the prompt template for each function, plus `mission_context.txt` (the agent's role), `session_memory_update.txt` (the periodic summary that keeps track of what other members have surfaced) and `style_final_response.txt` (the fixed-prompt rewrite that keeps tone constant across functions and conditions).
- `knowledge_base.txt`: the Test Specialist's handout, the only task knowledge the agent holds. It contains the agent's one critical unique fact (the motor's cruise temperature) and none of the three critical facts held by the humans, so the agent sits under the same hidden-profile split as they do. The agent is never told which of its facts are critical, unique or common.

Generation uses `gpt-5.1` through the OpenAI API (the model settings per function are in `common/config.py`). Fact-checking is grounded by local retrieval over `knowledge_base.txt` (SentenceTransformers `BAAI/bge-small-en-v1.5` embeddings with FAISS). A pre-processing filter keeps the agent from reasoning over small talk, and every outgoing message passes through the style rewrite so that the manipulation changes what the agent does, not how it sounds.

## Handouts

`Handout Aero.pdf`, `Handout Estruturas.pdf` and `Handout Propulsão.pdf` are the role handouts given to the Aerodynamics, Structures and Propulsion participants before the team task, as distributed. Each contains common background, several role-specific facts, and that role's one critical unique fact. The agent's handout is `knowledge_base.txt`.

## Setup

1. `pip install discord.py openai numpy sentence-transformers faiss-cpu python-dotenv`
2. Copy `.env.example` to `.env` and fill in `DISCORD_AGENT_TOKEN`, `OPENAI_API_KEY` and `AGENT_TYPE` (`AGENT_1` or `AGENT_2`).
3. `python agent.py`

The agent expects to be a member of a Discord text channel shared with the human participants.

## Citation

If you use this code or the handouts, please cite the paper:

```
[Reference to be added upon publication: The Impact of Agent Proactive
Behaviours on Team Information Sharing. Computers in Human Behavior.]
```

The agent was first described, under the code's numbering of the functions, in:

```
Jacob, G. (2026). Impact of Agent Proactive Behaviours on Collaboration in
Aerospace Human-Autonomy Teams. MSc thesis, Instituto Superior Técnico,
Universidade de Lisboa.
```

## Data

`data/` holds the anonymised per-session and per-member measures behind every figure and statistic in the paper (session totals, per-member communication and network measures, questionnaire scale scores, decision-quality codes, function activations), with a README that documents each file and the conventions. No message text is included: the transcripts and the individual questionnaire responses are personal data held under the participants' consent and are not shared. Note that `function_activation_stats.csv` uses the code's function numbering, not the paper's (see above).
