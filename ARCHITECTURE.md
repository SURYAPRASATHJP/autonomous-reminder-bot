# Architecture Brief for Autonomous Reminder Bot

## OVERVIEW

The user chats with the bot about reminders in plain english, Reminders can be set with a time and a title. Reminders can repeat, and can be cancelled.

## COMPONENTS

### blocks and arrows
user --> UI -->  parser --> LLM --sql--> DB(postgres) --> poller --> DB(notifications) --> UI

### Streamlit UI (app.py) 
- A chat window with a side bar for reminder notification. 
- every 5 secs it reads for new notifications and displays them in the sidebar

### LLM Parser (parser.py)
- Sends the chat to the LLM and calls the tools.
- Tools: create, list, update (cancel is inside update), delete Reminders and get current time.

### services (service1_reminder.py)
- query runner for all the tools, calculates the next run at for recurring reminders.

### poller (poller.py)
- Three worker threads finds due reminders and sends them to the notification table for delivery.

### Postgres DB (postgres_db.py)
- Store and gives connection to the databse and the two tables.

The DB is the only ground Truth for evrything, UI never talks to the Poller

## FLOW (for a notification)
status(pending) --> claimed(30 secs lease for retry if not status change to sent) --> one-off --yes--> sent --> delivered

one-off --no--> recurring --> next_run_at--> end_date --yes--> sent

end_date --no--> status set to pending --> next_run_at calculated 

## DATABASE

- Reminders table holds the truth about all the reminders
- Notifications table holds the notifications only after the reminders are due

### Reminders table
- it holds everything about scheduling status, next_run_at, is_recurring, times_sent, locked_until

### Notifications table
- Holds what the UI shows, run_at and seen_at


## Avoiding duplicates
- delivery is atleast once. The unique keys (reminder_id, run_at) are used to avoid duplicates.

## Recurring Reminders
- after each delivery to the notifcations table, the next run_at is calculated and stored in the reminders table and set to pending with the times_sent= +1 to see if they are delivered. 

## Updating reminders 
- can only be updated only if the reminder status is pending

## known limits
- Notifications are only shown if the UI is on, or else they wait in the table until the UI is on.
- An index will fix the slowness of the claim query for large tables.
- only daily and weekly day reminders are supported for recurring reminders.
- failed reminders are retired without backoff but has max attempts
- Only UI delivery is supported.

