import os
import streamlit as st
from dotenv import load_dotenv 
from parser import call_llm
from service1_reminder import get_unseen_notifications, mark_notifications_seen

load_dotenv()
USER_ID = os.getenv("USER_ID")

st.title("Reminder Bot")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "sidebar_notifications" not in st.session_state:
    st.session_state.sidebar_notifications = []

@st.fragment(run_every="5s")
def check_notifications():
    # every 5 seconds it picks up reminders the poller delivered, show them in the chat
    result = get_unseen_notifications(USER_ID)

    # errors quietly on screen if the DB call fails so no flow gets affected
    if not result.get("ok"):
        st.caption(f" Notification error: {result.get('error', 'Unknown error')}")
        return
        
    if not result.get("notifications"):
        return

    if not result["ok"] or not result["notifications"]:
        return

    ids = []
    for n in result["notifications"]:
        st.session_state.sidebar_notifications.append(n["message"])
        ids.append(n["id"])

    # mark seen only after the messages are stored in the session
    mark_notifications_seen(ids)
    st.rerun()

with st.sidebar:
    st.header("Your Reminders")
    if not st.session_state.sidebar_notifications:
        st.write("No new reminders")
    else:
        # Displays the newest reminders at the top
        for notif in reversed(st.session_state.sidebar_notifications):
            st.info(notif)


for msg in st.session_state.messages: 
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

check_notifications()

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
