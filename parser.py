from openai import OpenAI 
from dotenv import load_dotenv
import os

load_dotenv()
LLM_API = os.getenv("LLM_API")
LLM_MODEL = os.getenv("LLM_MODEL")
USER_ID = os.getenv("USER_ID")

SYSTEM_PROMPT = """you are a friendly reminder assistant, keep replies short and to the point. if the user goes off topic from setting a reminder 
gently remind them that you are reminder bot and whatever they asking is outside your scope."""

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
    response = client.chat.completions.create(
        model = LLM_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=250,
    )
    return response.choices[0].message.content

