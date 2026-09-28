from openai import OpenAI 
from dotenv import load_dotenv
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import json

load_dotenv()
LLM_API = os.getenv("LLM_API")
LLM_MODEL = os.getenv("LLM_MODEL")
USER_ID = os.getenv("USER_ID")
TIME_ZONE = os.getenv("TIME_ZONE")

SYSTEM_PROMPT = """you are a friendly reminder assistant, keep replies short and to the point. if the user goes off topic from setting a reminder, YOU MUST ALWAYS write a final text response, never leave your message blank. 
gently remind them that you are reminder bot and whatever they asking is outside your scope. never assume a date or time even if the user gives you the current time.
call get_current_time() function to get the current time,weekday and timezone info and use it when the user talk about reminders, or when data or time comes up, and also when the user requests you to create, list, or cancel a reminder."""

def get_current_time():
    now= datetime.now(ZoneInfo(TIME_ZONE))
    return {"now_local": now.isoformat(timespec="seconds"),"weekday": now.strftime("%A"),"timezone": TIME_ZONE}

MAX_TOOL_CALLS=5

TOOLS = [{
    "type":"function",
    "function":{
        "name": "get_current_time",
        "description": "Returns the current local date, time, weekday and timezone"
    }

}]

def build_history(history, user_input):
    messages=[{"role": "system", "content": SYSTEM_PROMPT},]
    for message in history:
        messages.append({"role": message["role"], "content": message["content"]})
    messages.append({"role": "user", "content": user_input})
    return messages
    
def call_llm(history, user_input,USER_ID):

    client = OpenAI(
        base_url = "https://integrate.api.nvidia.com/v1",
        api_key = LLM_API
    )
    messages = build_history(history, user_input)
    for i in range(MAX_TOOL_CALLS):

        
        response = client.chat.completions.create(
            model = LLM_MODEL,
            messages=messages,
            tools= TOOLS,
            temperature=0.4,
            max_tokens=250,
        )
        message=response.choices[0].message

        # if nno tools where called
        if not getattr(message, 'tool_calls', None):
            return message.content

        # if tools where called we append that to the history
        messages.append(message.model_dump(exclude_unset=True))

        for tool_call in message.tool_calls:
            # check if the reply had the correct json format
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if tool_call.function.name == "get_current_time":
                result = get_current_time()
            else:
                result = {"error": "Unknown tool"}

            messages.append({"role": "tool","tool_call_id": tool_call.id,"content": json.dumps(result)})

        print(messages)    

    return "used tools"