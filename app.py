import os
import streamlit as st
from dotenv import load_dotenv 
from parser import call_llm

load_dotenv()
USER_ID = os.getenv("USER_ID")

st.title("Reminder Bot")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages: 
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Type your message here")

if user_input:
    history = list(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)
        
    reply = call_llm(history, user_input, USER_ID)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.write(reply)
        
    st.rerun()
