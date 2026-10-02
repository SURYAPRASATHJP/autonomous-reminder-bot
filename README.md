Autonomous Reminder Bot

A reminder assistant you talk to in plain language. Tell it what to remember and when, and it saves the reminder in Postgres. When the time comes, a background poller delivers the reminder to the app, where it shows up in the sidebar.

how it works:

1. User in the streamlit chat sends "Remind me to call the dentist tomorrow at 9 am."
2. LLM call, parses the message, and creates,lists,deletes,updates,cancels the reminders in Postgres.
3. Claim due rows from Postgres.
4. 3 workers in threads, deliver to the notification table.
5. The reminder is marked as sent.
6. The streamlit checks for new notifications in the notification table and displays them in the sidebar.

Delivery system is atleast once not exactly once.

Reminder status:

1. pending
2. claimed
3. sent
4. cancelled
5. failed

Tool list:

1. get_current_time
2. create_reminder
3. list_reminders
4. update_reminder
5. delete_reminder

Tech stack:

Python, Streamlit, Postgres 16, psycopg2, httpx (plain HTTP calls to the Groq Responses API, no SDK), python-dotenv.

Project structure:

app.py               Streamlit UI: chat, sidebar, notification check
parser.py            LLM request with retry and timeout,tool definitions
service1_reminder.py Reminder and notification database functions
postgres_db.py       Connection and table creation (safe to run again)
poller.py            Background workers: claim, deliver, mark sent
.env.example         Names of the settings you need

Setup:

1. requirments:
python 3.10 or newer
Pstgres 16 or newer
groq API key

2. intall dependencies:
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

4. copy .env.example to .env and fill in the values

5. create the tables 
python postgres_db.py

6. run the app
first terminal: "python poller.py"
second terminal: "streamlit run app.py"
