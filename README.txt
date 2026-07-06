Chico Esperto — AI Teammate Agent for Human-Autonomy Team Research
Discord bot implementation of "Chico," the AI teammate used in a Master's thesis study on how AI proactivity affects collaboration in horizontal Human-Autonomy Teams (3 humans + 1 AI). Two experimental conditions were implemented as separate agent instances sharing this codebase.

Conditions
The agent runs in one of two modes, set via `AGENT_TYPE` in `.env`:
AGENT_1 (Low Proactivity): Responds to direct mentions (F1), answers team questions (F2), and performs passive fact-checking (F3).
AGENT_2 (High Proactivity): All of the above, plus unsolicited insight sharing (F4) and devil's-advocate challenge (F5).

Architecture
`agent.py` — Discord event loop, message dispatch logic, cooldown/timing state
`common/config.py` — All tunable parameters (models, timers, filters) in one place
`common/handlers.py` — Responsibility (F1–F5) implementations, datalogger, message chunking
`prompts/` — LLM prompt templates for each responsibility
`knowledge_base.txt` — Task-domain reference material (UAV design specs) used for retrieval-augmented fact-checking
The agent uses local RAG (SentenceTransformers + FAISS) over `knowledge_base.txt` to ground its fact-checking responses, and calls GPT (configured for `gpt-5.1` in `common/config.py`) for generation.

Setup
# fill in DISCORD_AGENT_TOKEN, OPENAI_API_KEY, and AGENT_TYPE in .env

Citation
If you use this code, please cite:
```
[Author]. (2026). Impact of Agent Proactive Behaviours on Collaboration in
Aerospace Human-Autonomy Teams. Master's thesis, Instituto Superior Técnico.
```

Handouts
The handouts pdf contain the information given to each role prior to completing the task.