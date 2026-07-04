import discord
import os
import asyncio
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from collections import deque
import csv
from datetime import datetime
import time
import re

from common.config import CONFIG
from common.handlers import (
    Datalogger, is_question, send_chunked_message,
    handle_responsibility_1, handle_responsibility_2, handle_responsibility_3,
    update_session_memory, handle_r4_r5_logic
)

from sentence_transformers import SentenceTransformer
import faiss

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
load_dotenv(dotenv_path=os.path.join(SCRIPT_DIR, '.env'))

AGENT_TYPE = os.getenv("AGENT_TYPE", "AGENT_1").upper()
DISCORD_TOKEN = os.getenv("DISCORD_AGENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not DISCORD_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Missing DISCORD_TOKEN or OPENAI_API_KEY from the .env file.")

# Set up the per-session CSV log
LOGS_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
SESSION_ID = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_FILE_PATH = os.path.join(LOGS_DIR, f"datalog_{SESSION_ID}.csv")
CSV_HEADER = ["session_id", "message_id", "message_number", "step_name", "timestamp",
              "step_duration_ms", "total_duration_ms", "details", "metadata"]
with open(LOG_FILE_PATH, "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerow(CSV_HEADER)
print(f"Logging session '{SESSION_ID}' to {LOG_FILE_PATH}")

client = OpenAI(api_key=OPENAI_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

knowledge_path = os.path.join(SCRIPT_DIR, "knowledge_base.txt")
KNOWLEDGE_BASE_TEXT = ""
SESSION_MEMORY_FILE = os.path.join(SCRIPT_DIR, "session_memory.txt")
MESSAGE_BUFFER = deque(maxlen=CONFIG["MEMORY"]["MESSAGE_BUFFER_SIZE"])
MEMORY_UPDATE_TIMER = 0
MESSAGE_COUNTER = 0
IS_READY = False
MESSAGE_TIMESTAMPS = deque(maxlen=5)

if AGENT_TYPE == "AGENT_2":
    TOPIC_HISTORY = deque(maxlen=CONFIG["PROACTIVE_INTERVENTION"]["HISTORY_LIMIT"])
    INTERVENTION_COOLDOWN_COUNTER = 0
    CLASSIFICATION_TIMER = 0
    R5_COOLDOWN_COUNTER = 0
    PROACTIVE_LOGIC_LOCK = asyncio.Lock()

SEARCH_MODEL = None
SEARCH_INDEX = None
KNOWLEDGE_CHUNKS = []

# Load the prompt files. R1/R2/R3-gen/R4/R5 get the mission context prepended.
PROMPTS = {}
prompt_dir = os.path.join(SCRIPT_DIR, "prompts")
with open(os.path.join(prompt_dir, "mission_context.txt"), "r", encoding="utf-8") as f:
    mission_context = f.read() + "\n\n"

prompts_to_load = [
    "responsibility_1", "responsibility_2", "responsibility_2_validation",
    "responsibility_3_classification", "responsibility_3_generation",
    "session_memory_update", "style_final_response"
]
if AGENT_TYPE == "AGENT_2":
    prompts_to_load += [
        "responsibility_4_classifier", "responsibility_4_reasoning",
        "responsibility_5_trigger_check", "responsibility_5_intervention"
    ]
prompts_needing_context = {
    "responsibility_1", "responsibility_2", "responsibility_3_generation",
    "responsibility_4_reasoning", "responsibility_5_intervention"
}
for p_name in prompts_to_load:
    with open(os.path.join(prompt_dir, f"{p_name}.txt"), "r", encoding="utf-8") as f:
        content = f.read()
    PROMPTS[p_name] = (mission_context + content) if p_name in prompts_needing_context else content


def get_session_memory() -> str:
    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


async def run_proactive_check(datalogger, message, cooldown_modifier, r4_cooldown, r5_cooldown, classification_timer):
    """Runs the R4/R5 proactive layer and fires the winning action if it clears cooldown."""
    global INTERVENTION_COOLDOWN_COUNTER, R5_COOLDOWN_COUNTER

    action = await handle_r4_r5_logic(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                      TOPIC_HISTORY, KNOWLEDGE_BASE_TEXT, get_session_memory(),
                                      r4_cooldown, r5_cooldown, classification_timer)
    if not action:
        return

    async with PROACTIVE_LOGIC_LOCK:
        can_run_r4 = action["source"] == "R4" and INTERVENTION_COOLDOWN_COUNTER == 0
        can_run_r5 = action["source"] == "R5" and R5_COOLDOWN_COUNTER == 0
        if not (can_run_r4 or can_run_r5):
            datalogger.log_step("PROACTIVE_ACTION_CANCELLED", details="Cooldown activated.")
            return

        datalogger.log_step("PROACTIVE_WINNER_CONFIRMED", metadata=action)
        await send_chunked_message(datalogger, message, action["text"], is_reply=action["is_reply"],
                                   client=client, prompts=PROMPTS, config=CONFIG,
                                   buffer=MESSAGE_BUFFER, source=action["source"])

        if action["source"] == "R5":
            R5_COOLDOWN_COUNTER = max(1, CONFIG["RESPONSIBILITY_5"]["COOLDOWN"] + cooldown_modifier)
        else:
            INTERVENTION_COOLDOWN_COUNTER = max(1, CONFIG["PROACTIVE_INTERVENTION"]["COOLDOWN_PERIOD"] + cooldown_modifier)


@bot.event
async def on_ready():
    global KNOWLEDGE_BASE_TEXT, SEARCH_MODEL, SEARCH_INDEX, KNOWLEDGE_CHUNKS, IS_READY

    with open(knowledge_path, "r", encoding="utf-8") as f:
        KNOWLEDGE_BASE_TEXT = f.read()

    print("Building the RAG index...")
    SEARCH_MODEL = SentenceTransformer(CONFIG["MODELS"]["EMBEDDING_MODEL"])
    KNOWLEDGE_CHUNKS = [chunk for chunk in KNOWLEDGE_BASE_TEXT.split('\n\n') if chunk.strip()]
    embeddings = SEARCH_MODEL.encode(KNOWLEDGE_CHUNKS, convert_to_tensor=False)
    SEARCH_INDEX = faiss.IndexFlatL2(embeddings.shape[1])
    SEARCH_INDEX.add(np.array(embeddings, dtype=np.float32))
    print(f"RAG index ready with {SEARCH_INDEX.ntotal} vectors.")

    with open(SESSION_MEMORY_FILE, "w") as f:
        f.write(f"Session memory for {bot.user.name} started.\n")
    print(f"{AGENT_TYPE} '{bot.user}' is online. Session memory cleared.")

    IS_READY = True


@bot.event
async def on_message(message: discord.Message):
    start_time = time.time()

    global MEMORY_UPDATE_TIMER, MESSAGE_COUNTER, MESSAGE_TIMESTAMPS
    if AGENT_TYPE == "AGENT_2":
        global INTERVENTION_COOLDOWN_COUNTER, CLASSIFICATION_TIMER, R5_COOLDOWN_COUNTER

    if not IS_READY:
        return
    if message.author == bot.user or isinstance(message.channel, discord.DMChannel):
        return

    MESSAGE_COUNTER += 1
    MESSAGE_TIMESTAMPS.append(start_time)
    message_id = f"{message.id}-{int(start_time)}"
    datalogger = Datalogger(message_id=message_id, start_time=start_time, log_file_path=LOG_FILE_PATH,
                            session_id=SESSION_ID, message_number=MESSAGE_COUNTER)

    try:
        print(f"\n{'=' * 20} New Message #{MESSAGE_COUNTER} ({AGENT_TYPE}) {'=' * 20}")
        datalogger.log_step("MESSAGE_RECEIVED", details=message.content, metadata={"author": message.author.name})

        if message.content == "!clearmemory":
            open(SESSION_MEMORY_FILE, "w").close()
            MESSAGE_BUFFER.clear()
            MEMORY_UPDATE_TIMER = 0
            MESSAGE_COUNTER = 0
            if AGENT_TYPE == "AGENT_2":
                TOPIC_HISTORY.clear()
                INTERVENTION_COOLDOWN_COUNTER = 0
                CLASSIFICATION_TIMER = 0
                R5_COOLDOWN_COUNTER = 0
            await message.channel.send(f"`{AGENT_TYPE}: Session memory and timers cleared.`")
            return

        MESSAGE_BUFFER.append(message)
        MEMORY_UPDATE_TIMER += 1
        if MEMORY_UPDATE_TIMER >= CONFIG["MEMORY"]["MEMORY_UPDATE_INTERVAL"]:
            asyncio.create_task(
                update_session_memory(datalogger, client, PROMPTS, CONFIG, MESSAGE_BUFFER, SESSION_MEMORY_FILE))
            MEMORY_UPDATE_TIMER = 0

        content_lower = message.content.lower().strip()
        min_len = CONFIG["FILTERING"]["MIN_MESSAGE_LENGTH"]
        ignore_list = CONFIG["FILTERING"]["MESSAGES_TO_IGNORE"]

        if content_lower in ignore_list or (len(message.content) < min_len and '?' not in message.content):
            datalogger.log_step("FILTER_IGNORED", details="Message too short or in ignore list")
            return

        # Adjust the proactive cooldown based on how fast the channel is moving
        cooldown_modifier = 0
        dyn_conf = CONFIG.get("DYNAMIC_COOLDOWN", {})
        if dyn_conf.get("ENABLE", False) and len(MESSAGE_TIMESTAMPS) >= 2:
            gaps = [MESSAGE_TIMESTAMPS[i] - MESSAGE_TIMESTAMPS[i - 1] for i in range(1, len(MESSAGE_TIMESTAMPS))]
            avg_gap = sum(gaps) / len(gaps)
            if avg_gap < dyn_conf["FAST_CHAT_THRESHOLD"]:
                cooldown_modifier = dyn_conf["FAST_MODIFIER"]
                datalogger.log_step("DYNAMIC_COOLDOWN", details=f"Fast Chat ({avg_gap:.1f}s). Modifier: +{cooldown_modifier}")
            elif avg_gap > dyn_conf["SLOW_CHAT_THRESHOLD"]:
                cooldown_modifier = dyn_conf["SLOW_MODIFIER"]
                datalogger.log_step("DYNAMIC_COOLDOWN", details=f"Slow Chat ({avg_gap:.1f}s). Modifier: {cooldown_modifier}")

        current_r4_cooldown = INTERVENTION_COOLDOWN_COUNTER if AGENT_TYPE == "AGENT_2" else 0
        current_r5_cooldown = R5_COOLDOWN_COUNTER if AGENT_TYPE == "AGENT_2" else 0

        if AGENT_TYPE == "AGENT_2":
            CLASSIFICATION_TIMER += 1
            if INTERVENTION_COOLDOWN_COUNTER > 0:
                INTERVENTION_COOLDOWN_COUNTER -= 1
            if R5_COOLDOWN_COUNTER > 0:
                R5_COOLDOWN_COUNTER -= 1

        bot_name = CONFIG["FILTERING"].get("BOT_NAME", str(bot.user.name)).lower()
        is_direct_mention = bot.user.mentioned_in(message)
        is_direct_reply = message.reference and message.reference.resolved and message.reference.resolved.author == bot.user
        is_name_call = bool(re.search(r'\b' + re.escape(bot_name) + r'\b', content_lower))
        addressed = is_direct_mention or is_direct_reply or is_name_call

        if AGENT_TYPE == "AGENT_2":
            if addressed:
                await handle_responsibility_1(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                              KNOWLEDGE_BASE_TEXT, get_session_memory())
            elif is_question(message.content, CONFIG):
                r2_result = await handle_responsibility_2(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                                          KNOWLEDGE_BASE_TEXT, get_session_memory())
                if r2_result != "ANSWERED":
                    r3_action = await handle_responsibility_3(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                                              KNOWLEDGE_CHUNKS, SEARCH_INDEX, SEARCH_MODEL, return_action=False)
                    if not r3_action:
                        await run_proactive_check(datalogger, message, cooldown_modifier,
                                                  current_r4_cooldown, current_r5_cooldown, CLASSIFICATION_TIMER)
            else:
                r3_action = await handle_responsibility_3(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                                          KNOWLEDGE_CHUNKS, SEARCH_INDEX, SEARCH_MODEL, return_action=False)
                if not r3_action:
                    await run_proactive_check(datalogger, message, cooldown_modifier,
                                              current_r4_cooldown, current_r5_cooldown, CLASSIFICATION_TIMER)

            if CLASSIFICATION_TIMER >= CONFIG["PROACTIVE_INTERVENTION"]["CLASSIFICATION_INTERVAL"]:
                CLASSIFICATION_TIMER = 0

        else:  # AGENT_1: reactive only (R1-R3)
            if addressed:
                await handle_responsibility_1(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                              KNOWLEDGE_BASE_TEXT, get_session_memory())
            elif is_question(message.content, CONFIG):
                r2_result = await handle_responsibility_2(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                                          KNOWLEDGE_BASE_TEXT, get_session_memory())
                if r2_result != "ANSWERED":
                    await handle_responsibility_3(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                                  KNOWLEDGE_CHUNKS, SEARCH_INDEX, SEARCH_MODEL, return_action=False)
            else:
                await handle_responsibility_3(datalogger, message, client, PROMPTS, CONFIG, MESSAGE_BUFFER,
                                              KNOWLEDGE_CHUNKS, SEARCH_INDEX, SEARCH_MODEL, return_action=False)

    except Exception as e:
        print(f"Unhandled exception in on_message: {e}")
        datalogger.log_step("FATAL_ERROR", details=str(e))
        await message.reply(f"`A critical error occurred in the dispatcher: {e}`")

    finally:
        total_time_ms = (time.time() - start_time) * 1000
        datalogger.log_step("PROCESSING_FINISHED", details=f"Finished Message #{MESSAGE_COUNTER}",
                            metadata={"duration_ms": total_time_ms})
        print(f"[Msg #{MESSAGE_COUNTER}] Finished in {total_time_ms:.2f}ms")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
