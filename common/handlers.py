import discord
import json
import asyncio
import numpy as np
from openai import OpenAI
from collections import deque, Counter
import time
import csv
from datetime import datetime
import random



def clean_and_parse_json(raw_text):
    """Strips Markdown code blocks and parses JSON."""
    text = raw_text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}



class Datalogger:
    def __init__(self, message_id: str, start_time: float, log_file_path: str, session_id: str, message_number: int):
        self.message_id = message_id
        self.start_time = start_time
        self.last_step_time = start_time
        self.log_file_path = log_file_path
        self.session_id = session_id
        self.message_number = message_number

    def log_step(self, step_name: str, details: str = "", metadata: dict = None):
        current_time = time.time()
        timestamp = datetime.now().isoformat()
        step_duration_ms = (current_time - self.last_step_time) * 1000
        total_duration_ms = (current_time - self.start_time) * 1000
        metadata_str = json.dumps(metadata) if metadata else ""
        try:
            with open(self.log_file_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([self.session_id, self.message_id, self.message_number, step_name, timestamp,
                                 f"{step_duration_ms:.2f}", f"{total_duration_ms:.2f}",
                                 details, metadata_str])
                f.flush()
        except Exception as e:
            print(f"Logging error: could not write to {self.log_file_path}: {e}")
        self.last_step_time = current_time


def is_question(text: str, config: dict) -> bool:
    text_lower = text.lower().strip()
    if '?' in text_lower: return True
    last_punct_index = max(text_lower.rfind('.'), text_lower.rfind('!'))
    sentence_to_check = text_lower[last_punct_index + 1:].strip() if last_punct_index != -1 else text_lower
    if not sentence_to_check: return False
    words_to_check = sentence_to_check.split()
    for starter in config["FILTERING"]["QUESTION_STARTERS"]:
        if starter in words_to_check[:3]: return True
    return False


async def update_session_memory(datalogger: Datalogger, client: OpenAI, prompts: dict, config: dict, buffer: deque,
                                memory_file_path: str):
    if len(buffer) < config["MEMORY"]["MEMORY_UPDATE_INTERVAL"]: return
    datalogger.log_step("MEMORY_UPDATE_START")
    try:
        with open(memory_file_path, "r", encoding="utf-8") as f:
            previous_memory = f.read().strip()
    except FileNotFoundError:
        previous_memory = "No previous memory."

    context_size = config["MEMORY"]["MEMORY_UPDATE_INTERVAL"] + config["MEMORY"]["MEMORY_LEAD_IN_SIZE"]
    conversation_transcript = "\n".join(
        [f"[{msg.author.display_name}]: {msg.content}" for msg in list(buffer)[-context_size:]])
    prompt_input = prompts["session_memory_update"].format(session_memory=previous_memory,
                                                           conversation_transcript=conversation_transcript)

    try:
        model_config = config["MODELS"]["SESSION_MEMORY_UPDATE"]
        completion = await asyncio.to_thread(
            client.responses.create,
            model=model_config["model"],
            input=prompt_input,
            reasoning={"effort": model_config["effort"]},
            text={"verbosity": model_config["verbosity"]}
        )
        new_memory = completion.output_text.strip()
        with open(memory_file_path, "w", encoding="utf-8") as f:
            f.write(new_memory)
        datalogger.log_step("MEMORY_UPDATE_SUCCESS", details=new_memory)
    except Exception as e:
        datalogger.log_step("MEMORY_UPDATE_FAIL", details=str(e))
        print(f"Session memory update failed: {e}")


async def send_chunked_message(datalogger: Datalogger, message: discord.Message, text: str, is_reply: bool = False, *,
                               client: OpenAI, prompts: dict, config: dict, buffer: deque, source: str = "Unknown"):
    """Sends a message, applying the styling layer first."""
    if text in ["NO_ANSWER_FOUND", "NO_INSIGHT_FOUND"]:
        final_text = text
    else:
        final_text = await rephrase_for_naturality(datalogger, client, prompts, config, text, buffer)

    datalogger.log_step("MESSAGE_SEND_ATTEMPT", details=final_text)
    max_len = 2000
    try:
        if len(final_text) <= max_len:
            if is_reply:
                await message.reply(final_text)
            else:
                await message.channel.send(final_text)
        else:
            chunks = [final_text[i:i + max_len] for i in range(0, len(final_text), max_len)]
            for i, chunk in enumerate(chunks):
                if i == 0 and is_reply:
                    await message.reply(chunk)
                else:
                    await message.channel.send(chunk)

        datalogger.log_step("MESSAGE_SENT_SUCCESS")

        preview = (final_text[:75] + '...') if len(final_text) > 75 else final_text
        print(f"[Msg #{datalogger.message_number}] [{source}] sent: \"{preview}\"")

    except Exception as e:
        datalogger.log_step("MESSAGE_SENT_FAIL", details=str(e))
        print(f"Error sending message: {e}")



async def handle_responsibility_1(datalogger: Datalogger, message: discord.Message, client: OpenAI, prompts: dict,
                                  config: dict, buffer: deque, knowledge: str, memory: str):
    datalogger.log_step("R1_START")
    user_query = message.content
    user_query = user_query.replace(f"<@{message.guild.me.id}>", "").strip()
    bot_name = config["FILTERING"].get("BOT_NAME", "").lower()
    if bot_name and user_query.lower().startswith(bot_name):
        user_query = user_query[len(bot_name):].strip(" ,.:?!")

    conversation_transcript = "\n".join([f"[{msg.author.display_name}]: {msg.content}" for msg in list(buffer)[-10:]])
    prompt_input = prompts["responsibility_1"].format(query=user_query, conversation_transcript=conversation_transcript,
                                                      knowledge_base=knowledge, session_memory=memory)
    try:
        datalogger.log_step("R1_LLM_CALL_START")
        model_config = config["MODELS"]["R1_DIRECT_QUESTION"]
        completion = await asyncio.to_thread(
            client.responses.create,
            model=model_config["model"],
            input=prompt_input,
            reasoning={"effort": model_config["effort"]},
            text={"verbosity": model_config["verbosity"]}
        )
        response_text = completion.output_text.strip()
        datalogger.log_step("R1_LLM_CALL_SUCCESS", details=response_text)
        await send_chunked_message(datalogger, message, response_text, is_reply=True,
                                   client=client, prompts=prompts, config=config, buffer=buffer, source="R1")
    except Exception as e:
        datalogger.log_step("R1_ERROR", details=str(e))
        print(f"Error in R1: {e}")


async def handle_responsibility_2(datalogger: Datalogger, message: discord.Message, client: OpenAI, prompts: dict,
                                  config: dict, buffer: deque, knowledge: str, memory: str):
    datalogger.log_step("R2_START")
    validation_prompt_input = prompts["responsibility_2_validation"].format(query=message.content)
    try:
        datalogger.log_step("R2_VALIDATION_START")
        model_config_val = config["MODELS"]["R2_VALIDATION"]
        completion_val = await asyncio.to_thread(
            client.responses.create,
            model=model_config_val["model"],
            input=validation_prompt_input,
            reasoning={"effort": model_config_val["effort"]},
            text={"verbosity": model_config_val["verbosity"]}
        )
        decision = completion_val.output_text.strip()
        datalogger.log_step("R2_VALIDATION_SUCCESS", details=f"Decision: {decision}")
        if "No" in decision:
            datalogger.log_step("R2_DECISION_NOT_A_QUESTION")
            return "NOT_A_QUESTION"
    except Exception as e:
        datalogger.log_step("R2_VALIDATION_ERROR", details=str(e))
        return "ERROR"

    datalogger.log_step("R2_ANSWERING_START")
    conversation_transcript = "\n".join([f"[{msg.author.display_name}]: {msg.content}" for msg in list(buffer)[-10:]])
    answer_prompt_input = prompts["responsibility_2"].format(query=message.content,
                                                             conversation_transcript=conversation_transcript,
                                                             knowledge_base=knowledge, session_memory=memory)
    try:
        model_config_ans = config["MODELS"]["R2_TEAM_QUESTION"]
        completion_ans = await asyncio.to_thread(
            client.responses.create,
            model=model_config_ans["model"],
            input=answer_prompt_input,
            reasoning={"effort": model_config_ans["effort"]},
            text={"verbosity": model_config_ans["verbosity"]}
        )
        reply = completion_ans.output_text.strip()
        datalogger.log_step("R2_ANSWERING_SUCCESS", details=f"Reply length: {len(reply)}")

        if reply != "NO_ANSWER_FOUND":
            await send_chunked_message(datalogger, message, reply, is_reply=True,
                                       client=client, prompts=prompts, config=config, buffer=buffer, source="R2")
            return "ANSWERED"
        else:
            datalogger.log_step("R2_DECISION_NO_ANSWER")
            return "NO_ANSWER_FOUND"
    except Exception as e:
        datalogger.log_step("R2_ANSWERING_ERROR", details=str(e))
        return "ERROR"



async def track_topic(datalogger: Datalogger, client: OpenAI, prompts: dict, config: dict, buffer: deque,
                      topic_history: deque):
    datalogger.log_step("R4_TOPIC_TRACKING_START")
    interval = config["PROACTIVE_INTERVENTION"]["CLASSIFICATION_INTERVAL"]
    message_batch = list(buffer)[-interval:]
    if not message_batch: return

    unique_active_topics = list(set(topic_history))
    active_topics_str = ", ".join(unique_active_topics) if unique_active_topics else "None"

    indexed_transcript = "\n".join(
        [f"{i + 1}: [{msg.author.display_name}]: {msg.content}" for i, msg in enumerate(message_batch)])

    classification_prompt_input = prompts["responsibility_4_classifier"].format(
        active_topics_list=active_topics_str,
        indexed_transcript=indexed_transcript
    )
    try:
        model_config = config["MODELS"]["R4_CLASSIFIER"]
        completion = await asyncio.to_thread(
            client.responses.create,
            model=model_config["model"],
            input=classification_prompt_input,
            reasoning={"effort": model_config["effort"]},
            text={"verbosity": model_config["verbosity"]}
        )
        results = clean_and_parse_json(completion.output_text)
        datalogger.log_step("R4_TOPIC_TRACKING_SUCCESS", metadata=results)
        newly_added_topics = [topic for topic in results.values() if topic != "Irrelevant"]
        if newly_added_topics:
            topic_history.extend(newly_added_topics)
    except Exception as e:
        datalogger.log_step("R4_TOPIC_TRACKING_ERROR", details=str(e))
        print(f"Topic classification failed: {e}")


async def handle_responsibility_3(datalogger: Datalogger, message: discord.Message, client: OpenAI, prompts: dict,
                                  config: dict, buffer: deque, knowledge_chunks: list, search_index, search_model,
                                  return_action: bool = False) -> dict | None:
    datalogger.log_step("R3_START")
    user_statement = message.content
    query_embedding = search_model.encode([user_statement])
    k = config["RAG"]["NUM_RELEVANT_CHUNKS"]
    distances, indices = search_index.search(np.array(query_embedding, dtype=np.float32), k)

    best_score = distances[0][0]

    if best_score > config["RAG"]["RELEVANCE_THRESHOLD"]:
        datalogger.log_step("R3_DECISION_IRRELEVANT", metadata={"score": float(best_score)})
        return None

    datalogger.log_step("R3_RAG_SUCCESS", metadata={"best_score": float(best_score)})

    retrieved_context = "\n---\n".join([knowledge_chunks[i] for i in indices[0]])
    try:
        transcript = "\n".join([f"[{msg.author.display_name}]: {msg.content}" for msg in list(buffer)[-10:]])
        prompt_input_cls = prompts["responsibility_3_classification"].format(user_statement=user_statement,
                                                                             conversation_transcript=transcript,
                                                                             retrieved_chunks=retrieved_context)
        datalogger.log_step("R3_CLASSIFICATION_START")
        model_config_cls = config["MODELS"]["R3_CLASSIFY"]
        completion_cls = await asyncio.to_thread(
            client.responses.create,
            model=model_config_cls["model"],
            input=prompt_input_cls,
            reasoning={"effort": model_config_cls["effort"]},
            text={"verbosity": model_config_cls["verbosity"]}
        )
        result = clean_and_parse_json(completion_cls.output_text)
        decision = result.get("decision")
        datalogger.log_step("R3_CLASSIFICATION_SUCCESS", metadata=result)

        if decision in ["Wrong", "Incomplete"]:
            datalogger.log_step("R3_GENERATION_START")
            prompt_input_gen = prompts["responsibility_3_generation"].format(user_statement=user_statement,
                                                                             conversation_transcript=transcript,
                                                                             retrieved_chunks=retrieved_context)
            model_config_gen = config["MODELS"]["R3_GENERATION"]
            completion_gen = await asyncio.to_thread(
                client.responses.create,
                model=model_config_gen["model"],
                input=prompt_input_gen,
                reasoning={"effort": model_config_gen["effort"]},
                text={"verbosity": model_config_gen["verbosity"]}
            )
            response_text = completion_gen.output_text.strip()
            datalogger.log_step("R3_GENERATION_SUCCESS", details=response_text)

            if return_action:
                return {"priority": 1, "text": response_text, "is_reply": True, "source": "R3"}
            else:
                await send_chunked_message(datalogger, message, response_text, is_reply=True,
                                           client=client, prompts=prompts, config=config, buffer=buffer, source="R3")
                return {"sent": True}
        else:
            datalogger.log_step("R3_DECISION_NO_ACTION", details=f"Decision was '{decision}'")
    except Exception as e:
        datalogger.log_step("R3_ERROR", details=str(e))
    return None


async def handle_responsibility_4(datalogger: Datalogger, message: discord.Message, client: OpenAI, prompts: dict,
                                  config: dict, buffer: deque, topic_history: deque, knowledge: str,
                                  memory: str) -> dict | None:
    datalogger.log_step("R4_ANALYSIS_START")

    if not topic_history:
        datalogger.log_step("R4_DECISION_NO_HISTORY")
        return None

    topic_counts = Counter(topic_history)
    critical_mass = config["PROACTIVE_INTERVENTION"]["CRITICAL_MASS_THRESHOLD"]
    last_topic = topic_history[-1]

    if last_topic == "Irrelevant":
        datalogger.log_step("R4_DECISION_TOPIC_IRRELEVANT")
        return None

    if topic_counts[last_topic] >= critical_mass:
        datalogger.log_step("R4_CRITICAL_MASS_REACHED",
                            metadata={"topic": last_topic, "count": topic_counts[last_topic]})

        transcript = "\n".join([f"[{msg.author.display_name}]: {msg.content}" for msg in list(buffer)[-15:]])
        prompt_input = prompts["responsibility_4_reasoning"].format(detected_topic=last_topic,
                                                                    discussion_transcript=transcript,
                                                                    knowledge_base=knowledge, session_memory=memory)
        try:
            datalogger.log_step("R4_REASONING_START")
            model_config = config["MODELS"]["R4_REASONING"]
            completion = await asyncio.to_thread(
                client.responses.create,
                model=model_config["model"],
                input=prompt_input,
                reasoning={"effort": model_config["effort"]},
                text={"verbosity": model_config["verbosity"]}
            )
            insight = completion.output_text.strip()
            datalogger.log_step("R4_REASONING_SUCCESS", details=insight)

            if insight != "NO_INSIGHT_FOUND":
                return {"priority": 3, "text": insight, "is_reply": False, "source": "R4"}
            else:
                datalogger.log_step("R4_DECISION_NO_INSIGHT")
        except Exception as e:
            datalogger.log_step("R4_ERROR", details=str(e))

        # Clear the topic history only when no insight was produced, to avoid a stuck loop
        topic_history.clear()
        return None

    datalogger.log_step("R4_DECISION_CONDITIONS_NOT_MET",
                        metadata={"last_topic": last_topic, "count": topic_counts.get(last_topic, 0)})
    return None


async def handle_responsibility_5(datalogger: Datalogger, message: discord.Message, client: OpenAI, prompts: dict,
                                  config: dict, buffer: deque, session_memory: str, knowledge_base: str,
                                  current_topic: str = "General Discussion") -> dict | None:
    datalogger.log_step("R5_ANALYSIS_START")

    recent_messages = list(buffer)[-15:]

    if not recent_messages:
        return None

    target_msg_obj = recent_messages[-1]
    target_message = f"[{target_msg_obj.author.display_name}]: {target_msg_obj.content}"

    context_msgs = recent_messages[:-1]
    conversation_context = "\n".join([f"[{msg.author.display_name}]: {msg.content}" for msg in context_msgs])

    prompt_input_trig = prompts["responsibility_5_trigger_check"].format(
        session_memory=session_memory,
        knowledge_base=knowledge_base,
        current_topic=current_topic,
        target_message=target_message,
        conversation_context=conversation_context
    )

    try:
        datalogger.log_step("R5_TRIGGER_CHECK_START")

        model_config_trig = config["MODELS"]["R5_TRIGGER_CLASSIFIER"]

        completion_trig = await asyncio.to_thread(
            client.responses.create,
            model=model_config_trig["model"],
            input=prompt_input_trig,
            reasoning={"effort": model_config_trig["effort"]},
            text={"verbosity": model_config_trig["verbosity"]}
        )

        result = clean_and_parse_json(completion_trig.output_text)
        decision = result.get("decision", "NO_INTERVENTION")

        reasoning = result.get("reasoning", "No reasoning provided")
        datalogger.log_step("R5_TRIGGER_CHECK_SUCCESS", metadata={"decision": decision, "reasoning": reasoning})

        if decision == "INTERVENE":
            target_statement = result.get("statement", target_msg_obj.content)

            datalogger.log_step("R5_PROBABILITY_CHECK_START",
                                metadata={"probability": config["RESPONSIBILITY_5"]["PROBABILITY"]})

            if random.random() <= config["RESPONSIBILITY_5"]["PROBABILITY"]:
                datalogger.log_step("R5_GENERATION_START")

                full_transcript = conversation_context + "\n" + target_message

                prompt_input_gen = prompts["responsibility_5_intervention"].format(
                    target_statement=target_statement,
                    conversation_transcript=full_transcript
                )

                model_config_gen = config["MODELS"]["R5_INTERVENTION_GENERATOR"]

                completion_gen = await asyncio.to_thread(
                    client.responses.create,
                    model=model_config_gen["model"],
                    input=prompt_input_gen,
                    reasoning={"effort": model_config_gen["effort"]},
                    text={"verbosity": model_config_gen["verbosity"]}
                )

                question = completion_gen.output_text.strip()

                datalogger.log_step("R5_GENERATION_SUCCESS", details=question)
                return {"priority": 2, "text": question, "is_reply": True, "source": "R5"}
            else:
                datalogger.log_step("R5_DECISION_PROBABILITY_FAIL")
        else:
            datalogger.log_step("R5_DECISION_NO_TRIGGER")

    except Exception as e:
        datalogger.log_step("R5_ERROR", details=str(e))

    return None

async def handle_r4_r5_logic(datalogger, message, client, prompts, config, buffer, topic_history, knowledge_base,
                             session_memory, r4_cooldown, r5_cooldown, classification_timer):
    """Runs R4 and R5 analysis in parallel and proposes the highest-priority action."""
    if classification_timer >= config["PROACTIVE_INTERVENTION"]["CLASSIFICATION_INTERVAL"]:
        await track_topic(datalogger, client, prompts, config, buffer, topic_history)

    current_topic = topic_history[-1] if topic_history else "General Discussion"

    tasks_to_run = []
    if r5_cooldown == 0:
        tasks_to_run.append(
            handle_responsibility_5(datalogger, message, client, prompts, config, buffer, session_memory,
                                    knowledge_base, current_topic))
    if r4_cooldown == 0:
        tasks_to_run.append(
            handle_responsibility_4(datalogger, message, client, prompts, config, buffer, topic_history, knowledge_base,
                                    session_memory))

    if not tasks_to_run:
        return None

    results = await asyncio.gather(*tasks_to_run)
    actions = [res for res in results if res is not None]
    if not actions:
        return None

    return min(actions, key=lambda x: x["priority"])


async def rephrase_for_naturality(datalogger: Datalogger, client: OpenAI, prompts: dict, config: dict, raw_text: str,
                                  buffer: deque) -> str:
    """Takes raw text from a reasoning LLM and uses a fast styling LLM to make it conversational."""
    datalogger.log_step("STYLE_REPHRASE_START")
    try:
        transcript = "\n".join([f"[{msg.author.display_name}]: {msg.content}" for msg in list(buffer)[-6:]])
        prompt_input = prompts["style_final_response"].format(conversation_transcript=transcript, raw_text=raw_text)

        model_config = config["MODELS"]["STYLE_LLM"]
        completion = await asyncio.to_thread(
            client.responses.create,
            model=model_config["model"],
            input=prompt_input,
            reasoning={"effort": model_config["effort"]},
            text={"verbosity": model_config["verbosity"]}
        )
        rephrased_text = completion.output_text.strip()
        datalogger.log_step("STYLE_REPHRASE_SUCCESS", details=rephrased_text)
        return rephrased_text
    except Exception as e:
        datalogger.log_step("STYLE_REPHRASE_ERROR", details=str(e))
        print(f"Styling layer failed, falling back to raw text: {e}")
        return raw_text