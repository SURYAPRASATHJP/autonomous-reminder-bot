from openai import OpenAI 
from dotenv import load_dotenv
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from service1_reminder import create_reminder

load_dotenv()
LLM_API = os.getenv("LLM_API")
LLM_MODEL = os.getenv("LLM_MODEL")
USER_ID = os.getenv("USER_ID")
TIME_ZONE = os.getenv("TIME_ZONE")

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

TOOLS = [
    {
        "type":"function",
        "function":
            {
                "name": "get_current_time",
                "description": "Returns the current local date, time, weekday and timezone"
            }
    },
    {
        "type":"function",
        "function":{
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
                "required": ["reminder_title", "remind_at"]
            }
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
    
def call_llm(history, user_input, USER_ID):

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
            
            result = run_tools(tool_call.function.name, args, USER_ID, user_input)

            messages.append({"role": "tool","tool_call_id": tool_call.id,"content": json.dumps(result)})
        i+=1
    print(messages)    

    return "used tools"