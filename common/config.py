# Shared settings for both agents (AGENT_1 and AGENT_2).
# Changing a value here affects both bots.

CONFIG = {
    "MODELS": {
        "STYLE_LLM": {
            "model": "gpt-5.1",
            "effort": "none",
            "verbosity": "medium"
        },
        "R1_DIRECT_QUESTION": {
            "model": "gpt-5.1",
            "effort": "medium",
            "verbosity": "medium"
        },
        "R2_VALIDATION": {
            "model": "gpt-5.1",
            "effort": "low",
            "verbosity": "low"
        },
        "R2_TEAM_QUESTION": {
            "model": "gpt-5.1",
            "effort": "medium",
            "verbosity": "medium"
        },
        "R3_CLASSIFY": {
            "model": "gpt-5.1",
            "effort": "low",
            "verbosity": "medium"
        },
        "R3_GENERATION": {
            "model": "gpt-5.1",
            "effort": "medium",
            "verbosity": "medium"
        },
        "R4_CLASSIFIER": {
            "model": "gpt-5.1",
            "effort": "low",
            "verbosity": "low"
        },
        "R4_REASONING": {
            "model": "gpt-5.1",
            "effort": "medium",
            "verbosity": "medium"
        },
        "R5_TRIGGER_CLASSIFIER": {
            "model": "gpt-5.1",
            "effort": "low",
            "verbosity": "medium"
        },
        "R5_INTERVENTION_GENERATOR": {
            "model": "gpt-5.1",
            "effort": "low",
            "verbosity": "low"
        },
        "SESSION_MEMORY_UPDATE": {
            "model": "gpt-5.1",
            "effort": "high",
            "verbosity": "low"
        },

        # This is not an LLM, so it remains a string
        "EMBEDDING_MODEL": 'BAAI/bge-small-en-v1.5'
    },
    "PROACTIVE_INTERVENTION": {
        "HISTORY_LIMIT": 8,
        "CRITICAL_MASS_THRESHOLD": 4,
        "COOLDOWN_PERIOD": 5,
        "CLASSIFICATION_INTERVAL": 1,
        "RELEVANT_TOPICS": []
    },
    "DYNAMIC_COOLDOWN": {
        "ENABLE": False,             # Master switch
        "FAST_CHAT_THRESHOLD": 15.0, # Seconds between messages to count as "Fast"
        "SLOW_CHAT_THRESHOLD": 60.0,# Seconds to count as "Slow"
        "FAST_MODIFIER": 2,         # Add to cooldown if fast (+2)
        "SLOW_MODIFIER": -1         # Subtract from cooldown if slow (-1)
    },
    "MEMORY": {
        "MESSAGE_BUFFER_SIZE": 20,
        "MEMORY_UPDATE_INTERVAL": 10,
        "MEMORY_LEAD_IN_SIZE": 5,
    },
    "FILTERING": {
        "BOT_NAME": "Chico",
        "MIN_MESSAGE_LENGTH": 7,
        "MESSAGES_TO_IGNORE": {"ok", "okay", "yes", "aye", "no", "thanks", "thank you", "k", "thx", "got it", "i agree", "done",
                               "sounds good", "exactly", "good idea", "yes seems right", "(you have 15min left)", "(you have 5min left)"},
        "QUESTION_STARTERS": ("what", "how", "why", "when", "where", "who", "can", "is", "are", "does", "will", "do",
                              "could", "should", "would")
    },
    "RAG": {
        "NUM_RELEVANT_CHUNKS": 3,
        "RELEVANCE_THRESHOLD": 1.0
    },
    "RESPONSIBILITY_5": {
        "COOLDOWN": 4,
        "PROBABILITY": 1
    }
}