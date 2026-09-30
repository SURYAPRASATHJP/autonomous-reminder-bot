import httpx
from dotenv import load_dotenv
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional
import logging
import random
import time
import json
from service1_reminder import create_reminder

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")
USER_ID = os.getenv("USER_ID")
TIME_ZONE = os.getenv("TIME_ZONE")
url = os.getenv("LLM_URL", "https://api.groq.com/openai/v1/responses")

logger = logging.getLogger("parser")

MAX_ATTEMPTS = 5
MAX_RETRY_AFTER_CAP = 30.0  # maximim wait for 429 error
BASE_BACKOFF = 1.0  # base delay in seconds for 500 errors
BACKOFF_FACTOR = 2.0
TIMEOUT_CONFIG = httpx.Timeout(60.0, connect=5.0)

SYSTEM_PROMPT = """you are a friendly reminder assistant, keep replies short and to the point. if the user goes off topic from setting a reminder, YOU MUST ALWAYS write a final text response, never leave your message blank. 
gently remind them that you are reminder bot and whatever they asking is outside your scope. never assume a date or time even if the user gives you the current time.
call get_current_time() function to get the current time,weekday and timezone info and use it when the user talk about reminders, or when data or time comes up, and also when the user requests you to create, list, or cancel a reminder.
call create_reminder() function to create a new reminder, you must always call get_current_time before calling create_reminder to know the current time.

RULES:
1. When you call a tool dont explain your thought process, just call the tool.
2. Only write a reply to the question and nothing about the tool call."""

def get_current_time():
    now= datetime.now(ZoneInfo(TIME_ZONE))
    return {"now_local": now.isoformat(timespec="seconds"),"weekday": now.strftime("%A"),"timezone": TIME_ZONE}

MAX_TOOL_CALLS=5

# Responses API tool format: name, description and parameters sit at the top level (no "function" wrapper)
TOOLS = [
    {
        "type":"function",
        "name": "get_current_time",
        "description": "Returns the current local date, time, weekday and timezone",
        "parameters":{"type": "object","properties": {}}
    },
    {
        "type":"function",
        "name": "create_reminder",
        "description": "Creates a new reminder for the user",
        "parameters":{
            "type": "object",
            "properties": {
                "title":{"type": "string","description": "title of what the reminder is about"},
                "remind_at":{"type": "string","description": "reminder time as local ISO format YYYY-MM-DDTHH:MM:SS with no timezone mentioned"},
                "recurring_type":{"type": "string","enum":["NA", "daily", "days"],"description": "how the reminder should be repeated, NA for non repeating reminders"}, # weekly and monthly later
                "recurring_days":{"type": "string","description": "use this only when recurring type id days, replky with mon,wed,thur"},
                "end_date":{"type": "string","description": "use this only when recurring type reminders, reply with the end date of the reminder as local ISO format"}
            },
            "required": ["title", "remind_at"]
        }
    }
]

def build_history(history, user_input):
    messages=[{"role": "system", "content": SYSTEM_PROMPT},]
    for message in history:
        messages.append({"role": message["role"], "content": message["content"]})
    messages.append({"role": "user", "content": user_input})
    return messages

def run_tools(name, args, user_id, user_message):
    if name == "get_current_time":
        return get_current_time()
    elif name == "create_reminder":
        return create_reminder(user_id, user_message, **args)
    else:
        return {"error": "Unknown tool"}

def send_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    # one Responses API call with the retry, timeout and logging rules from MoonRay llm.py
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY has a problem, not set")
    if not LLM_MODEL:
        raise ValueError("LLM_MODEL has a problem, not set")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error: Optional[Exception] = None
    
    with httpx.Client(timeout=TIMEOUT_CONFIG) as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            start_time = time.perf_counter()

            try:
                response = client.post(url, headers=headers, json=payload)
                latency = time.perf_counter() - start_time
                status = response.status_code

                # 1. Special case: Rate limiting (429)
                if status == 429:
                    retry_after_hdr = response.headers.get("Retry-After")
                    try:
                        wait_seconds = (
                            float(retry_after_hdr)
                            if retry_after_hdr
                            else BASE_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))
                        )
                    except ValueError:
                        wait_seconds = BASE_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))

                    if wait_seconds > MAX_RETRY_AFTER_CAP:
                        logger.error(
                            "Rate limit 429: Retry-After (%.2fs) exceeds cap (%.2fs). Aborting.",
                            wait_seconds,
                            MAX_RETRY_AFTER_CAP,
                        )
                        response.raise_for_status()

                    if attempt == MAX_ATTEMPTS:
                        logger.error("Rate limit 429 persisted through final attempt %d/%d.", attempt, MAX_ATTEMPTS)
                        response.raise_for_status()

                    logger.warning(
                        "Rate limited (429) on attempt %d/%d. Waiting %.2fs...",
                        attempt,
                        MAX_ATTEMPTS,
                        wait_seconds,
                    )
                    time.sleep(wait_seconds)
                    continue

                # 2. General server errors: Any status >= 500 is retried
                if status >= 500:
                    if attempt == MAX_ATTEMPTS:
                        logger.error(
                            "Server error %d on final attempt %d/%d. Latency: %.3fs. Body: %s",
                            status,
                            attempt,
                            MAX_ATTEMPTS,
                            latency,
                            response.text,
                        )
                        response.raise_for_status()

                    jitter_sleep = random.uniform(0.5, BASE_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1)))
                    logger.warning(
                        "Server error %d on attempt %d/%d. Latency: %.3fs. Retrying in %.2fs. Body: %s",
                        status,
                        attempt,
                        MAX_ATTEMPTS,
                        latency,
                        jitter_sleep,
                        response.text,
                    )
                    time.sleep(jitter_sleep)
                    continue

                # 3. Client errors: Any remaining status >= 400 fails immediately
                if status >= 400:
                    logger.error(
                        "Client error %d on attempt %d. Not retryable. Body: %s",
                        status,
                        attempt,
                        response.text,
                    )
                    response.raise_for_status()

                # 4. Safe JSON decoding
                try:
                    data = response.json()
                except (ValueError, json.JSONDecodeError) as parse_err:
                    logger.error("Failed to decode JSON from status %d response. Body: %s", status, response.text)
                    raise RuntimeError(f"Server returned non-JSON payload (Status {status}): {response.text}") from parse_err

                # 5. Check generation completion status before parsing output
                gen_status = data.get("status")
                if gen_status != "completed":
                    incomplete_info = data.get("incomplete_details", "No incomplete_details provided")
                    raise RuntimeError(
                        f"Model generation status is '{gen_status}' (not completed). Reason: {incomplete_info}"
                    )

                response_id = data.get("id")
                usage = data.get("usage", {})
                in_tok = usage.get("input_tokens", 0)
                out_tok = usage.get("output_tokens", 0)
                reason_tok = usage.get("output_tokens_details", {}).get("reasoning_tokens", 0)

                logger.info(
                    "Call succeeded | ID: %s | Status: %d | Latency: %.3fs | Tokens: [in: %s, out: %s, reasoning: %s]",
                    response_id,
                    status,
                    latency,
                    in_tok,
                    out_tok,
                    reason_tok,
                )

                return data

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                latency = time.perf_counter() - start_time
                last_error = exc
                error_type = exc.__class__.__name__

                if attempt == MAX_ATTEMPTS:
                    logger.error(
                        "Network failure (%s) on final attempt %d/%d. Latency: %.3fs.",
                        error_type,
                        attempt,
                        MAX_ATTEMPTS,
                        latency,
                    )
                    raise RuntimeError(f"Request failed after {MAX_ATTEMPTS} attempts due to {error_type}: {exc}") from exc

                sleep_time = random.uniform(0.5, BASE_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1)))
                logger.warning(
                    "Network error (%s) on attempt %d/%d. Latency: %.3fs. Retrying in %.2fs...",
                    error_type,
                    attempt,
                    MAX_ATTEMPTS,
                    latency,
                    sleep_time,
                )
                time.sleep(sleep_time)

    if last_error:
        raise last_error
    raise RuntimeError(f"Request failed unexpectedly after {MAX_ATTEMPTS} attempts.")


def get_text(data: Dict[str, Any]) -> str:
    # pull the final text out of the "message" item in the output list
    reply = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") in ("output_text", "text"):
                    reply = part.get("text", "")
                    break
            if reply:
                break

    if not reply:
        raise RuntimeError("Malformed response: generation marked completed, but no text content found.")
    return reply

def call_llm(history, user_input, USER_ID):

    messages = build_history(history, user_input)
    for i in range(MAX_TOOL_CALLS):

        payload = {
            "model": LLM_MODEL,
            "input": messages,
            "tools": TOOLS,
            "temperature": 0.4,
            "max_output_tokens": 250,
        }
        data = send_request(payload)

        tool_calls = [item for item in data.get("output", []) if item.get("type") == "function_call"]

        # if nno tools where called
        if not tool_calls:
            return get_text(data)

        for tool_call in tool_calls:
            # if tools where called we append that to the history
            messages.append(tool_call)

            # check if the reply had the correct json format
            try:
                args = json.loads(tool_call.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            result = run_tools(tool_call.get("name"), args, USER_ID, user_input)

            messages.append({"type": "function_call_output", "call_id": tool_call.get("call_id"), "output": json.dumps(result)})
        i+=1
    print(messages)

    return "used tools"


if __name__ == "__main__":

    logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",)

    reply = call_llm([], "what time is it right now?", USER_ID)
    print("..........Reply..........")
    print(reply)
